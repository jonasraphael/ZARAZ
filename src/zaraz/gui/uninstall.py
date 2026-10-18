"""Locating and launching the uninstaller created by the Windows setup.

The setup only writes the uninstaller and its registry entry when the user
ticks "Create uninstall files". Without those files this module simply finds
nothing and the GUI hides its uninstall button.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

UNINSTALLER_NAMES = (
    "Uninstall ZARAZ.exe",
    "Uninstall Zaraz.exe",
    "unins000.exe",
)

REGISTRY_KEYS = (
    r"Software\ZARAZ",
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ZARAZ",
)


def _command_to_path(value: str) -> Path | None:
    """Turns an UninstallString such as '"C:\\...\\Uninstall ZARAZ.exe" /S' into a path."""
    value = value.strip()
    if not value:
        return None
    if value.startswith('"'):
        end = value.find('"', 1)
        if end > 0:
            return Path(value[1:end])
    index = value.lower().find(".exe")
    if index != -1:
        return Path(value[: index + 4])
    return Path(value)


def _registry_candidates() -> list[Path]:
    if not sys.platform.startswith("win"):
        return []
    import winreg

    found: list[Path] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub_key in REGISTRY_KEYS:
            try:
                with winreg.OpenKey(hive, sub_key) as key:
                    for value_name in ("Uninstaller", "UninstallString"):
                        try:
                            raw, _ = winreg.QueryValueEx(key, value_name)
                        except OSError:
                            continue
                        path = _command_to_path(str(raw))
                        if path is not None:
                            found.append(path)
            except OSError:
                continue
    return found


def _folder_candidates() -> list[Path]:
    """Looks for an uninstaller next to the running app or the launcher."""
    roots: list[Path] = []
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except OSError:
        pass
    try:
        roots.append(Path(__file__).resolve().parent)
    except OSError:
        pass

    candidates: list[Path] = []
    for root in roots:
        current = root
        for _ in range(4):
            for name in UNINSTALLER_NAMES:
                candidates.append(current / name)
            current = current.parent
    return candidates


def find_uninstaller() -> Path | None:
    """Returns the uninstaller executable, or None when it does not exist."""
    for path in (*_registry_candidates(), *_folder_candidates()):
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def start_uninstaller(path: Path) -> None:
    """Starts the uninstaller detached so Zaraz can close beforehand."""
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen([str(path)], creationflags=flags, close_fds=True)
    else:
        subprocess.Popen([str(path)], close_fds=True)
