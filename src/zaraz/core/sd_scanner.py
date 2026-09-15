"""Erkennt SD-Karten und andere Wechseldatenträger.

Plattformübergreifend (Windows / macOS / Linux) über psutil,
mit Feinjustierung pro Plattform.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Drive:
    """Ein erkannter Wechseldatenträger (SD-Karte, USB-Stick, ...)."""

    mountpoint: Path
    label: str
    file_system: str
    total_bytes: int
    free_bytes: int

    @property
    def total_gb(self) -> float:
        return self.total_bytes / 1024**3

    @property
    def free_gb(self) -> float:
        return self.free_bytes / 1024**3

    def __str__(self) -> str:
        label = f" · {self.label}" if self.label else ""
        return f"{self.mountpoint}{label} ({self.free_gb:.1f} GB frei / {self.total_gb:.1f} GB)"


def _is_removable(partition) -> bool:
    """Entscheidet, ob eine Partition ein Wechseldatenträger ist."""
    mountpoint = partition.mountpoint
    opts = partition.opts.lower()

    if sys.platform.startswith("win"):
        # psutil liest unter Windows den Drive-Typ (GetDriveTypeW)
        return "removable" in opts

    if sys.platform == "darwin":
        return mountpoint.startswith("/Volumes/") and mountpoint != "/"

    # Linux: eingehängte Wechselmedien liegen typischerweise hier
    return (
        mountpoint.startswith("/media/")
        or mountpoint.startswith("/run/media/")
        or mountpoint.startswith("/mnt/")
    )


def _windows_volume_label(mountpoint: Path) -> str:
    """Liest das Volume-Label unter Windows (über ctypes, ohne Extra-Paket)."""
    try:
        import ctypes

        name_buf = ctypes.create_unicode_buffer(1024)
        fs_buf = ctypes.create_unicode_buffer(1024)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(str(mountpoint)),
            name_buf, len(name_buf),
            None, None, None,
            fs_buf, len(fs_buf),
        )
        return name_buf.value if ok else ""
    except Exception:  # Label ist optional – niemals abbrechen
        return ""


def _label_for(partition, mountpoint: Path) -> str:
    """Bestmögliches Label für einen Datenträger ermitteln."""
    if sys.platform.startswith("win"):
        return _windows_volume_label(mountpoint)
    # macOS/Linux: Der Ordnername unter /Volumes bzw. /media IST das Label
    return mountpoint.name or partition.device


def find_removable_drives() -> list[Drive]:
    """Sucht alle Wechseldatenträger und gibt sie als Drive-Objekte zurück."""
    drives: list[Drive] = []
    for partition in psutil.disk_partitions(all=True):
        if not _is_removable(partition):
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (OSError, PermissionError) as exc:
            logger.debug("Überspringe %s: %s", partition.mountpoint, exc)
            continue

        mountpoint = Path(partition.mountpoint)
        drives.append(
            Drive(
                mountpoint=mountpoint,
                label=_label_for(partition, mountpoint),
                file_system=partition.fstype or "?",
                total_bytes=usage.total,
                free_bytes=usage.free,
            )
        )
        logger.debug("Gefunden: %s", drives[-1])
    return drives