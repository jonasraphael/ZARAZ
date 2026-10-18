"""Shared fixtures for the Zaraz tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_card(tmp_path: Path) -> Path:
    """Builds a fake SD card with a realistic folder structure.

    It deliberately contains files that must NOT be found (system folders,
    hidden folders, .bin/.sra/main outside of their contexts).
    """
    card = tmp_path / "CARD"

    def write(rel_path: str, size: int) -> Path:
        target = card / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x00" * size)
        return target

    # --- expected to be found -------------------------------------------
    write("EDGB/SAVES/pokemon-blue.sav", 32 * 1024)                 # Game Boy (EverDrive)
    write("EDGBA/SAVES/zelda-minish.sav", 128 * 1024)               # GBA (EverDrive)
    write("ED64/SAVE/paper-mario.sra", 512 * 1024)                  # N64 (EverDrive 64)
    write("saves/retro.srm", 64 * 1024)                             # SD2SNES / RetroArch
    write("3ds/Checkpoint/saves/Animal Crossing/main", 256 * 1024)  # Checkpoint (3DS)
    write("3ds/Checkpoint/saves/OtherGame/0001.bin", 64 * 1024)     # Checkpoint (3DS)
    write("JKSV/Zelda/main.bin", 256 * 1024)                        # JKSV (Switch)
    write("loose-8k.sav", 8 * 1024)                                 # orphaned, GB size
    write("loose-100k.sav", 100 * 1024)                             # orphaned, GBA size
    write("big.sav", 2 * 1024 * 1024)                               # orphaned, unknown

    # --- must NOT be found ----------------------------------------------
    write("Nintendo 3DS/0123456789abcdef/0123456789abcdef/title/00040000/00175e00/data/00000001.sav", 512)
    write("System Volume Information/trash.sav", 128)
    write(".Trashes/junk.sav", 128)
    write(".hidden/secret.sav", 128)
    write("roms/game.nds", 1024 * 1024)   # not a save extension
    write("firmware.bin", 64)             # .bin outside of any context
    write("main", 128)                    # "main" only inside the Checkpoint context
    write("other/backup.sra", 128)        # N64 extensions only in the ED64 context

    return card
