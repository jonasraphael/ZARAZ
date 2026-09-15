"""Zentrale Konfiguration für Zaraz.

Alle Module beziehen ihre Einstellungen von hier –
Verhalten lässt sich so an einer einzigen Stelle anpassen.
"""

from __future__ import annotations

from pathlib import Path

# --- Spielstand-Erkennung -------------------------------------------------

# Dateiendungen, die als Spielstände erkannt werden:
#   .sav – Standard bei EverDrive, DS/GBA-Flashcards, GodMode9, vielen Emulatoren
#   .srm – RetroArch / libretro
SAVE_EXTENSIONS: frozenset[str] = frozenset({".sav", ".srm"})

# Systemordner, die beim Scannen übergangen werden.
# Spart Zeit und verhindert Fehltreffer (Firmware, verschlüsselte Daten).
EXCLUDED_DIRS: frozenset[str] = frozenset({
    "System Volume Information",  # Windows
    "$RECYCLE.BIN",               # Windows-Papierkorb
    ".Trashes",                   # macOS-Papierkorb
    ".fseventsd",                 # macOS-Metadaten
    ".Spotlight-V100",            # macOS-Suchindex
    "APStore",                    # 3DS-Systemdaten
    "Nintendo 3DS",               # 3DS-Inhalte (verschlüsselt; Checkpoint exportiert nach /3ds/)
    "Nintendo",                   # Switch-Inhalte (verschlüsselt)
})

# --- Backup-Ziel ----------------------------------------------------------

# Standard-Zielordner im Home-Verzeichnis.
DEFAULT_BACKUP_DIR: Path = Path.home() / "Zaraz" / "Backups"

# --- Transfer -------------------------------------------------------------

# Verhalten bei Namenskonflikten am Ziel: "rename" | "overwrite" | "skip"
COLLISION_STRATEGY: str = "rename"

# Blockgröße beim Lesen/Hashen (1 MiB).
TRANSFER_CHUNK_SIZE: int = 1024 * 1024