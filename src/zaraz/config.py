"""Central configuration for Zaraz.

Every module reads its settings from here, so behaviour can be adjusted in a
single place.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --- Save-file detection ---------------------------------------------------

# File extensions that are treated as save files:
#   .sav – standard for EverDrive, DS/GBA flash cards, GodMode9, many emulators
#   .srm – RetroArch / libretro
SAVE_EXTENSIONS: frozenset[str] = frozenset({".sav", ".srm"})

# System folders that are skipped while scanning. This keeps scans fast and
# avoids false positives (firmware, encrypted data).
EXCLUDED_DIRS: frozenset[str] = frozenset({
    "System Volume Information",  # Windows
    "$RECYCLE.BIN",               # Windows recycle bin
    ".Trashes",                   # macOS trash
    ".fseventsd",                 # macOS metadata
    ".Spotlight-V100",            # macOS search index
    "APStore",                    # 3DS system data
    "Nintendo 3DS",               # 3DS contents (encrypted; Checkpoint exports to /3ds/)
    "Nintendo",                   # Switch contents (encrypted)
})

# --- Backup destination ----------------------------------------------------

# Default destination folder inside the user's home directory.
DEFAULT_BACKUP_DIR: Path = Path.home() / "Zaraz" / "Backups"

# --- Transfer --------------------------------------------------------------

# Behaviour on name collisions at the destination: "rename" | "overwrite" | "skip"
COLLISION_STRATEGY: str = "rename"

# Block size used for reading and hashing (1 MiB).
TRANSFER_CHUNK_SIZE: int = 1024 * 1024

# --- Application settings --------------------------------------------------

APP_NAME = "Zaraz"
DEFAULT_THEME = "light"
THEME_NAMES = ("light", "dark")


def user_config_dir() -> Path:
    """Per-user configuration folder for the current platform."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME


SETTINGS_FILE = user_config_dir() / "settings.json"


def load_settings() -> dict:
    """Reads the user settings file. Returns an empty dict on any problem."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    """Writes the user settings file, ignoring write failures."""
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, indent=2)
    except OSError:
        pass


def load_theme() -> str:
    """Returns the last saved theme name, falling back to the default."""
    theme = load_settings().get("theme")
    return theme if theme in THEME_NAMES else DEFAULT_THEME


def save_theme(theme: str) -> None:
    """Persists the selected theme for the next start."""
    if theme not in THEME_NAMES:
        return
    settings = load_settings()
    settings["theme"] = theme
    save_settings(settings)
