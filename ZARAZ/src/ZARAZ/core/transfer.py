"""Kopiervorgänge: Spielstände sicher ans Ziel bringen.

Jede Datei wird nach dem Kopieren per SHA-256 mit der Quelle verglichen –
so merkst du sofort, wenn ein Backup fehlerhaft ist.
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
    """Verhalten, wenn am Ziel bereits eine Datei gleichen Namens liegt."""

    RENAME = "rename"        # umbenennen: name_20240501-120000.sav
    OVERWRITE = "overwrite"  # überschreiben
    SKIP = "skip"            # unverändert lassen


STATUS_LABELS = {
    "copied": "kopiert",
    "renamed": "kopiert (neuer Name)",
    "overwritten": "überschrieben",
    "identical": "identisch vorhanden",
    "skipped": "übersprungen",
    "error": "fehlgeschlagen",
}


@dataclass(frozen=True)
class TransferResult:
    """Ergebnis eines einzelnen Datei-Transfers."""

    source: Path
    destination: Path
    status: str    # siehe STATUS_LABELS
    verified: bool  # SHA-256-Abgleich nach dem Kopieren


def default_strategy() -> CollisionStrategy:
    """Die Strategie aus config.py, mit Fallback bei Tippfehlern."""
    try:
        return CollisionStrategy(COLLISION_STRATEGY)
    except ValueError:
        logger.warning("Ungültige COLLISION_STRATEGY '%s' in config.py – nutze 'rename'.",
                       COLLISION_STRATEGY)
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
    """Löst einen Namenskonflikt am Ziel auf. None = Datei überspringen."""
    if not dest.exists():
        return dest
    if strategy is CollisionStrategy.OVERWRITE:
        return dest
    if strategy is CollisionStrategy.SKIP:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return dest.with_name(f"{dest.stem}_{stamp}{dest.suffix}")


def _safe_folder_name(path: Path) -> str:
    """Erzeugt einen sauberen Ordnernamen aus dem Quell-Laufwerk (z.B. 'E:\\' -> 'E')."""
    name = (path.name or str(path)).strip()
    for bad in (":", "\\", "/"):
        name = name.replace(bad, "_")
    name = name.strip("_ ")
    return name or "quelle"


def transfer_save(
    save: SaveFile,
    backup_dir: Path,
    strategy: Optional[CollisionStrategy] = None,
) -> TransferResult:
    """Kopiert einen einzelnen Spielstand ins Backup-Verzeichnis.

    Ziel-Layout:  <backup_dir>/<Laufwerksname>/<relativer Pfad auf der Karte>
    Beispiel:     ~/Zaraz/Backups/E/EDGB/SAVES/pokemon-blau.sav
    """
    strategy = strategy or default_strategy()
    source = save.path
    dest = backup_dir / _safe_folder_name(save.source_root) / save.relative_path

    # Bereits identisch vorhanden? -> nichts zu tun
    if dest.exists() and _files_identical(source, dest):
        return TransferResult(source, dest, "identical", verified=True)

    existed = dest.exists()
    resolved = _resolve_destination(dest, strategy)
    if resolved is None:
        return TransferResult(source, dest, "skipped", verified=False)

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, resolved)  # copy2 erhält Zeitstempel & Metadaten
    except OSError as exc:
        logger.error("Kopieren fehlgeschlagen (%s): %s", source, exc)
        return TransferResult(source, resolved, "error", verified=False)

    if resolved != dest:
        status = "renamed"
    elif existed:
        status = "overwritten"
    else:
        status = "copied"

    verified = _files_identical(source, resolved)
    if not verified:
        logger.error("Verifizierung fehlgeschlagen: %s != %s", source, resolved)
    return TransferResult(source, resolved, status, verified)


def transfer_all(
    saves: list[SaveFile],
    backup_dir: Path,
    strategy: Optional[CollisionStrategy] = None,
    on_progress: Optional[Callable[[TransferResult, int, int], None]] = None,
) -> list[TransferResult]:
    """Überträgt mehrere Spielstände; ruft `on_progress(result, i, n)` pro Datei auf."""
    results: list[TransferResult] = []
    for i, save in enumerate(saves, start=1):
        result = transfer_save(save, backup_dir, strategy)
        results.append(result)
        if on_progress is not None:
            on_progress(result, i, len(saves))
    return results


def summarize(results: list[TransferResult]) -> str:
    """Einzeilige Zusammenfassung der Ergebnisse."""
    counts: dict[str, int] = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    if not counts:
        return "nichts zu tun"
    return ", ".join(
        f"{n}x {STATUS_LABELS.get(status, status)}" for status, n in counts.items()
    )