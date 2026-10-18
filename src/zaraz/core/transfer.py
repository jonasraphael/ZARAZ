"""Copy operations: moving save files safely to their destination.

Every file is compared with the source through SHA-256 after copying, so a
broken backup is reported immediately.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from zaraz.config import COLLISION_STRATEGY, TRANSFER_CHUNK_SIZE
from zaraz.core.save_extractor import SaveFile

logger = logging.getLogger(__name__)


class CollisionStrategy(str, Enum):
    """Behaviour when a file with the same name already exists."""

    RENAME = "rename"        # rename: name_20240501-120000.sav
    OVERWRITE = "overwrite"  # replace the existing file
    SKIP = "skip"            # leave the existing file untouched


STATUS_LABELS = {
    "copied": "copied",
    "renamed": "copied (new name)",
    "overwritten": "overwritten",
    "identical": "already identical",
    "skipped": "skipped",
    "error": "failed",
}


@dataclass(frozen=True)
class TransferResult:
    """Result of a single file transfer."""

    source: Path
    destination: Path
    status: str    # see STATUS_LABELS
    verified: bool  # SHA-256 comparison after copying


def default_strategy() -> CollisionStrategy:
    """The strategy from config.py, with a fallback for typos."""
    try:
        return CollisionStrategy(COLLISION_STRATEGY)
    except ValueError:
        logger.warning(
            "Invalid COLLISION_STRATEGY '%s' in config.py – using 'rename'.",
            COLLISION_STRATEGY,
        )
        return CollisionStrategy.RENAME


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(TRANSFER_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _files_identical(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return _sha256(a) == _sha256(b)
    except OSError:
        return False


def _resolve_destination(dest: Path, strategy: CollisionStrategy) -> Optional[Path]:
    """Resolves a name collision at the destination. None = skip the file.

    Renamed files get a timestamp; if that name is taken as well (two saves
    with the same name copied within one second), a counter is appended so no
    existing backup is ever overwritten by accident.
    """
    if not dest.exists():
        return dest
    if strategy is CollisionStrategy.OVERWRITE:
        return dest
    if strategy is CollisionStrategy.SKIP:
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = dest.with_name(f"{dest.stem}_{stamp}{dest.suffix}")
    counter = 2
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem}_{stamp}-{counter}{dest.suffix}")
        counter += 1
    return candidate


def _safe_folder_name(path: Path) -> str:
    """Builds a clean folder name from the source drive (e.g. 'E:\\' -> 'E')."""
    name = (path.name or str(path)).strip()
    for bad in (":", "\\", "/"):
        name = name.replace(bad, "_")
    name = name.strip("_ ")
    return name or "source"


def transfer_save(
    save: SaveFile,
    backup_dir: Path,
    strategy: Optional[CollisionStrategy] = None,
) -> TransferResult:
    """Copies a single save file into the backup directory.

    Destination layout:  <backup_dir>/<drive name>/<relative path on the card>
    Example:             ~/Zaraz/Backups/E/EDGB/SAVES/pokemon-blue.sav
    """
    strategy = strategy or default_strategy()
    source = save.path
    dest = backup_dir / _safe_folder_name(save.source_root) / save.relative_path

    # Already there and identical? -> nothing to do
    if dest.exists() and _files_identical(source, dest):
        return TransferResult(source, dest, "identical", verified=True)

    existed = dest.exists()
    resolved = _resolve_destination(dest, strategy)
    if resolved is None:
        return TransferResult(source, dest, "skipped", verified=False)

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, resolved)  # copy2 keeps timestamps and metadata
    except OSError as exc:
        logger.error("Copy failed (%s): %s", source, exc)
        return TransferResult(source, resolved, "error", verified=False)

    if resolved != dest:
        status = "renamed"
    elif existed:
        status = "overwritten"
    else:
        status = "copied"

    verified = _files_identical(source, resolved)
    if not verified:
        logger.error("Verification failed: %s != %s", source, resolved)
    return TransferResult(source, resolved, status, verified)


def transfer_all(
    saves: list[SaveFile],
    backup_dir: Path,
    strategy: Optional[CollisionStrategy] = None,
    on_progress: Optional[Callable[[TransferResult, int, int], None]] = None,
) -> list[TransferResult]:
    """Transfers several save files; calls `on_progress(result, i, n)` per file."""
    results: list[TransferResult] = []
    for i, save in enumerate(saves, start=1):
        result = transfer_save(save, backup_dir, strategy)
        results.append(result)
        if on_progress is not None:
            on_progress(result, i, len(saves))
    return results


def summarize(results: list[TransferResult]) -> str:
    """Single-line summary of the results."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    if not counts:
        return "nothing to do"
    return ", ".join(
        f"{n}x {STATUS_LABELS.get(status, status)}" for status, n in counts.items()
    )
