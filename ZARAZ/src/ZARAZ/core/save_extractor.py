"""Sucht Spielstände (.sav, .srm, ...) auf einem Datenträger."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from zaraz.config import EXCLUDED_DIRS, SAVE_EXTENSIONS

logger = logging.getLogger(__name__)

# Ordner-Namen, die auf eine Konsole/Flashcard hindeuten (Anzeige-Heuristik).
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

# Zusätzliche Endungen, die NUR in bestimmten Kontext-Ordnern erkannt werden
# (weil sie überall sonst zu viele Fehltreffer liefern würden).
# Zusätzliche Endungen, die NUR in bestimmten Kontext-Ordnern erkannt werden
# (weil sie überall sonst zu viele Fehltreffer liefern würden).
_CONTEXT_EXTENSIONS = {
    "checkpoint": {".bin"},            # 3DS: /3ds/Checkpoint/saves/…
    "jksv": {".bin"},                  # Switch: /JKSV/…
    "ed64": {".eep", ".sra", ".fla"},  # N64: EEPROM-, SRAM- und Flash-Saves
}

# Datei-NAMEN (ohne Endung), die nur im passenden Kontext als Spielstand
# gelten. Checkpoint (3DS) exportiert die Save-Datei z.B. schlicht als "main".
_CONTEXT_FILENAMES = {
    "checkpoint": {"main"},
}

# Größen-Heuristik für .sav-Dateien (Rückfall, wenn kein Ordnername passt)
_SIZE_HINTS = (
    (32 * 1024, "Game Boy / GBC / NES (typisch 32 KiB)"),
    (64 * 1024, "SNES (typisch 64 KiB)"),
    (128 * 1024, "Game Boy Advance (typisch 128 KiB)"),
    (512 * 1024, "Nintendo DS Flashcard (typisch 512 KiB)"),
)


@dataclass(frozen=True)
class SaveFile:
    """Ein gefundener Spielstand."""

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
        """Vermutete Herkunfts-Konsole (reine Anzeige-Heuristik, nicht belastbar)."""
        parts_lower = {p.lower().strip() for p in self.path.parts}

        for key, hint in _FOLDER_HINTS.items():
            if key == "saves":
                continue  # generisch – nur als Rückfall
            if key in parts_lower:
                return hint
        if "saves" in parts_lower:
            return _FOLDER_HINTS["saves"]

        for limit, hint in _SIZE_HINTS:
            if self.size_bytes <= limit:
                return hint
        return "unbekannt"


def scan_for_saves(
    root: Path,
    extensions: frozenset[str] = SAVE_EXTENSIONS,
    excluded_dirs: frozenset[str] = EXCLUDED_DIRS,
) -> list[SaveFile]:
    """Durchsucht `root` rekursiv nach Spielständen.

    Ausgeschlossene Systemordner werden gar nicht erst betreten.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Kein gültiges Verzeichnis: {root}")

    exts = {e.lower() for e in extensions}
    saves: list[SaveFile] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=_log_walk_error):
        # Ausschlüsse direkt im Walk entfernen -> Ordner wird nie betreten
        dirnames[:] = [
            d for d in dirnames
            if d not in excluded_dirs and not d.startswith(".")
        ]

                # Kontext-Endungen und -Dateinamen (z.B. .bin/.eep nur in passenden Ordnern)
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
                logger.debug("Überspringe %s: %s", full_path, exc)
                continue
            saves.append(SaveFile(path=full_path, size_bytes=size, source_root=root))

    logger.info("%d Spielstände gefunden unter %s", len(saves), root)
    return saves


def _log_walk_error(error: OSError) -> None:
    logger.debug("Zugriffsfehler beim Scannen: %s", error)