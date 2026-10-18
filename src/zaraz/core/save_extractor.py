"""Finds save files (.sav, .srm, ...) on a drive."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from zaraz.config import EXCLUDED_DIRS, SAVE_EXTENSIONS

logger = logging.getLogger(__name__)

# Folder names that hint at a console or flash card (display heuristic only).
_FOLDER_HINTS = {
    "edgb": "Game Boy (EverDrive)",
    "edgba": "Game Boy Advance (EverDrive)",
    "ed64": "Nintendo 64 (EverDrive 64)",
    "edsnes": "SNES (EverDrive)",
    "edn8": "NES / Famicom (EverDrive)",
    "twilightmenu": "Nintendo DS (TWiLight Menu++)",
    "checkpoint": "Nintendo 3DS (Checkpoint)",
    "jksv": "Nintendo Switch (JKSV)",
    "saves": "Flashcard / Emulator",
}

# Extra extensions that are only recognised inside certain context folders,
# because anywhere else they produce far too many false positives.
_CONTEXT_EXTENSIONS = {
    "checkpoint": {".bin"},            # 3DS: /3ds/Checkpoint/saves/…
    "jksv": {".bin"},                  # Switch: /JKSV/…
    "ed64": {".eep", ".sra", ".fla"},  # N64: EEPROM, SRAM and flash saves
}

# File NAMES (without extension) that only count as save files inside the
# matching context. Checkpoint (3DS), for example, exports the save file
# simply as "main".
_CONTEXT_FILENAMES = {
    "checkpoint": {"main"},
}

# Size heuristic for .sav files (fallback when no folder name matches).
_SIZE_HINTS = (
    (32 * 1024, "Game Boy / GBC / NES (typically 32 KiB)"),
    (64 * 1024, "SNES (typically 64 KiB)"),
    (128 * 1024, "Game Boy Advance (typically 128 KiB)"),
    (512 * 1024, "Nintendo DS flash card (typically 512 KiB)"),
)

UNKNOWN_CONSOLE = "unknown"


@dataclass(frozen=True)
class SaveFile:
    """A detected save file."""

    path: Path
    size_bytes: int
    source_root: Path

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024

    @property
    def relative_path(self) -> Path:
        try:
            return self.path.relative_to(self.source_root)
        except ValueError:
            return self.path

    def guess_console(self) -> str:
        """Guessed console of origin (display heuristic only, not authoritative)."""
        parts_lower = {p.lower().strip() for p in self.path.parts}

        for key, hint in _FOLDER_HINTS.items():
            if key == "saves":
                continue  # generic – only used as a fallback
            if key in parts_lower:
                return hint
        if "saves" in parts_lower:
            return _FOLDER_HINTS["saves"]

        for limit, hint in _SIZE_HINTS:
            if self.size_bytes <= limit:
                return hint
        return UNKNOWN_CONSOLE


def scan_for_saves(
    root: Path,
    extensions: frozenset[str] = SAVE_EXTENSIONS,
    excluded_dirs: frozenset[str] = EXCLUDED_DIRS,
) -> list[SaveFile]:
    """Recursively searches `root` for save files.

    Excluded system folders are never entered at all.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a valid directory: {root}")

    exts = {e.lower() for e in extensions}
    excluded_lower = {d.lower() for d in excluded_dirs}
    saves: list[SaveFile] = []

    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, onerror=_log_walk_error
    ):
        # Filter exclusions right in the walk -> the folder is never entered.
        dirnames[:] = [
            d
            for d in dirnames
            if d.lower() not in excluded_lower and not d.startswith(".")
        ]

        # Context extensions and file names (.bin/.eep only in matching folders).
        parts_lower = {p.lower() for p in Path(dirpath).parts}
        allowed = set(exts)
        allowed_names: set[str] = set()
        for context, extra in _CONTEXT_EXTENSIONS.items():
            if context in parts_lower:
                allowed |= extra
        for context, names in _CONTEXT_FILENAMES.items():
            if context in parts_lower:
                allowed_names |= names

        for filename in filenames:
            if (
                Path(filename).suffix.lower() not in allowed
                and filename.lower() not in allowed_names
            ):
                continue
            full_path = Path(dirpath) / filename
            try:
                size = full_path.stat().st_size
            except OSError as exc:
                logger.debug("Skipping %s: %s", full_path, exc)
                continue
            saves.append(
                SaveFile(path=full_path, size_bytes=size, source_root=root)
            )

    logger.info("%d save files found under %s", len(saves), root)
    return saves


def _log_walk_error(error: OSError) -> None:
    logger.debug("Access error while scanning: %s", error)
