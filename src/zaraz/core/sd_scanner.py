"""Detects SD cards and other removable drives.

Cross-platform (Windows / macOS / Linux) through psutil, with per-platform
refinements.
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
    """A detected removable drive (SD card, USB stick, ...)."""

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
        return (
            f"{self.mountpoint}{label} "
            f"({self.free_gb:.1f} GB free / {self.total_gb:.1f} GB)"
        )


def _is_removable(partition) -> bool:
    """Decides whether a partition is a removable drive."""
    mountpoint = partition.mountpoint
    opts = partition.opts.lower()

    if sys.platform.startswith("win"):
        # psutil reports the Windows drive type (GetDriveTypeW)
        return "removable" in opts

    if sys.platform == "darwin":
        return mountpoint.startswith("/Volumes/") and mountpoint != "/"

    # Linux: mounted removable media usually lives here
    return (
        mountpoint.startswith("/media/")
        or mountpoint.startswith("/run/media/")
        or mountpoint.startswith("/mnt/")
    )


def _windows_volume_label(mountpoint: Path) -> str:
    """Reads the volume label on Windows (through ctypes, no extra package)."""
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
    except Exception:  # the label is optional – never abort because of it
        return ""


def _label_for(partition, mountpoint: Path) -> str:
    """Best-effort label for a drive."""
    if sys.platform.startswith("win"):
        return _windows_volume_label(mountpoint)
    # macOS/Linux: the folder name under /Volumes or /media IS the label
    return mountpoint.name or partition.device


def find_removable_drives() -> list[Drive]:
    """Finds all removable drives and returns them as Drive objects."""
    drives: list[Drive] = []
    for partition in psutil.disk_partitions(all=True):
        if not _is_removable(partition):
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (OSError, PermissionError) as exc:
            logger.debug("Skipping %s: %s", partition.mountpoint, exc)
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
        logger.debug("Found: %s", drives[-1])
    return drives
