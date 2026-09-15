"""Tests für zaraz.core.transfer (Kopiervorgänge & Konfliktlogik)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from zaraz.core.save_extractor import SaveFile
from zaraz.core.transfer import (
    CollisionStrategy,
    TransferResult,
    _safe_folder_name,
    summarize,
    transfer_all,
    transfer_save,
)


def make_save(card: Path, rel: str = "EDGB/SAVES/pokemon.sav",
              content: bytes = b"PB-SAVE-1") -> SaveFile:
    path = card / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return SaveFile(path=path, size_bytes=len(content), source_root=card)


@pytest.fixture
def card(tmp_path: Path) -> Path:
    return tmp_path / "KARTE"


@pytest.fixture
def backup(tmp_path: Path) -> Path:
    return tmp_path / "BACKUP"


def test_copies_new_file_and_verifies(card: Path, backup: Path) -> None:
    save = make_save(card)
    result = transfer_save(save, backup)
    assert result.status == "copied"
    assert result.verified is True
    assert (backup / "KARTE" / "EDGB/SAVES/pokemon.sav").read_bytes() == b"PB-SAVE-1"


def test_creates_missing_destination_folders(card: Path, backup: Path) -> None:
    save = make_save(card, "EDGBA/SAVES/tiefe/struktur/zelda.sav")
    result = transfer_save(save, backup)
    assert result.status == "copied"
    assert (backup / "KARTE" / "EDGBA/SAVES/tiefe/struktur/zelda.sav").exists()


def test_identical_existing_file_is_not_recopied(card: Path, backup: Path) -> None:
    save = make_save(card)
    first = transfer_save(save, backup)
    second = transfer_save(save, backup)
    assert first.status == "copied"
    assert second.status == "identical"
    assert second.verified is True
    assert len(list(backup.rglob("*.sav"))) == 1  # keine zweite Kopie entstanden


def test_collision_rename_keeps_both(card: Path, backup: Path) -> None:
    save = make_save(card, content=b"NEU")
    dest = backup / "KARTE" / "EDGB/SAVES/pokemon.sav"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"ALT")

    result = transfer_save(save, backup, CollisionStrategy.RENAME)

    assert result.status == "renamed"
    assert dest.read_bytes() == b"ALT"                        # Original unangetastet
    assert re.fullmatch(r"pokemon_\d{8}-\d{6}\.sav", result.destination.name)
    assert result.destination.read_bytes() == b"NEU"
    assert len(list(backup.rglob("*.sav"))) == 2


def test_collision_overwrite_replaces(card: Path, backup: Path) -> None:
    save = make_save(card, content=b"NEU")
    dest = backup / "KARTE" / "EDGB/SAVES/pokemon.sav"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"ALT")

    result = transfer_save(save, backup, CollisionStrategy.OVERWRITE)

    assert result.status == "overwritten"
    assert dest.read_bytes() == b"NEU"
    assert len(list(backup.rglob("*.sav"))) == 1


def test_collision_skip_leaves_destination(card: Path, backup: Path) -> None:
    save = make_save(card, content=b"NEU")
    dest = backup / "KARTE" / "EDGB/SAVES/pokemon.sav"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"ALT")

    result = transfer_save(save, backup, CollisionStrategy.SKIP)

    assert result.status == "skipped"
    assert dest.read_bytes() == b"ALT"
    assert len(list(backup.rglob("*.sav"))) == 1


def test_corrupted_copy_is_detected(card: Path, backup: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """Fällt der Kopiervorgang stillschweigend kaputt, muss Zaraz es melden."""
    import zaraz.core.transfer as transfer_module

    def broken_copy(src, dst, **kwargs):
        Path(dst).write_bytes(Path(src).read_bytes() + b"KAPUTT")

    monkeypatch.setattr(transfer_module.shutil, "copy2", broken_copy)

    result = transfer_save(make_save(card), backup)
    assert result.status == "copied"
    assert result.verified is False


def test_transfer_all_reports_progress(card: Path, backup: Path) -> None:
    saves = [make_save(card, f"SAVES/spiel{i}.sav") for i in range(3)]
    seen: list[tuple[int, int]] = []

    def on_progress(_result, i, n):
        seen.append((i, n))

    results = transfer_all(saves, backup, on_progress=on_progress)

    assert seen == [(1, 3), (2, 3), (3, 3)]
    assert [r.status for r in results] == ["copied"] * 3


def test_summarize_translates_statuses() -> None:
    def res(status: str) -> TransferResult:
        return TransferResult(Path("a"), Path("b"), status, True)

    summary = summarize([res("copied"), res("copied"), res("identical")])
    assert summary == "2x kopiert, 1x identisch vorhanden"


def test_summarize_empty() -> None:
    assert summarize([]) == "nichts zu tun"


def test_safe_folder_name() -> None:
    assert _safe_folder_name(Path("KARTE")) == "KARTE"
    assert _safe_folder_name(Path("/")) == "quelle"
    assert _safe_folder_name(Path("E:\\")) == "E"   # Laufwerksbuchstabe unter Windows