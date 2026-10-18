"""Tests for zaraz.core.save_extractor (scan logic and context rules)."""

from __future__ import annotations

from pathlib import Path

import pytest

from zaraz.core.save_extractor import scan_for_saves

EXPECTED_REL_PATHS = {
    "EDGB/SAVES/pokemon-blue.sav",
    "EDGBA/SAVES/zelda-minish.sav",
    "ED64/SAVE/paper-mario.sra",
    "saves/retro.srm",
    "3ds/Checkpoint/saves/Animal Crossing/main",
    "3ds/Checkpoint/saves/OtherGame/0001.bin",
    "JKSV/Zelda/main.bin",
    "loose-8k.sav",
    "loose-100k.sav",
    "big.sav",
}


def test_finds_exactly_the_expected_saves(fake_card: Path) -> None:
    found = {s.path for s in scan_for_saves(fake_card)}
    expected = {fake_card / rel for rel in EXPECTED_REL_PATHS}
    assert found == expected


def test_ignores_system_and_hidden_folders(fake_card: Path) -> None:
    for save in scan_for_saves(fake_card):
        parts = {p.lower() for p in save.path.parts}
        assert "nintendo 3ds" not in parts
        assert "system volume information" not in parts
        assert ".trashes" not in parts
        assert ".hidden" not in parts


def test_bin_only_in_context_folders(fake_card: Path) -> None:
    names = {s.path.name for s in scan_for_saves(fake_card)}
    assert "main.bin" in names          # JKSV context
    assert "0001.bin" in names          # Checkpoint context
    assert "firmware.bin" not in names  # outside -> too many false positives


def test_filename_main_only_in_checkpoint(fake_card: Path) -> None:
    found = {s.path for s in scan_for_saves(fake_card)}
    assert fake_card / "3ds/Checkpoint/saves/Animal Crossing/main" in found
    assert fake_card / "main" not in found


def test_n64_extensions_only_in_ed64(fake_card: Path) -> None:
    found = {s.path for s in scan_for_saves(fake_card)}
    assert fake_card / "ED64/SAVE/paper-mario.sra" in found
    assert fake_card / "other/backup.sra" not in found


def test_context_matching_is_case_insensitive(tmp_path: Path) -> None:
    card = tmp_path / "card"
    for rel in ("jksv/Game/file.bin", "ed64/SAVE/xyz.eep"):
        target = card / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x" * 16)

    found = {s.path for s in scan_for_saves(card)}
    assert card / "jksv/Game/file.bin" in found
    assert card / "ed64/SAVE/xyz.eep" in found


def test_empty_card_yields_no_saves(tmp_path: Path) -> None:
    card = tmp_path / "empty"
    card.mkdir()
    assert scan_for_saves(card) == []


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        scan_for_saves(tmp_path / "does-not-exist")


def test_guess_console_from_folder(fake_card: Path) -> None:
    by_name = {s.path.name: s for s in scan_for_saves(fake_card)}
    assert by_name["pokemon-blue.sav"].guess_console() == "Game Boy (EverDrive)"
    assert by_name["zelda-minish.sav"].guess_console() == "Game Boy Advance (EverDrive)"
    assert by_name["paper-mario.sra"].guess_console() == "Nintendo 64 (EverDrive 64)"
    assert by_name["main"].guess_console() == "Nintendo 3DS (Checkpoint)"
    assert by_name["main.bin"].guess_console() == "Nintendo Switch (JKSV)"
    assert by_name["retro.srm"].guess_console() == "Flashcard / Emulator"


def test_guess_console_from_size_fallback(fake_card: Path) -> None:
    by_name = {s.path.name: s for s in scan_for_saves(fake_card)}
    assert "Game Boy" in by_name["loose-8k.sav"].guess_console()
    assert "Game Boy Advance" in by_name["loose-100k.sav"].guess_console()
    assert by_name["big.sav"].guess_console() == "unknown"


def test_relative_path_is_relative_to_root(fake_card: Path) -> None:
    saves = scan_for_saves(fake_card)
    assert all(not s.relative_path.is_absolute() for s in saves)
