"""Tests for the persisted user settings (theme choice)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zaraz import config


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", target)
    return target


def test_default_theme_without_settings_file(settings_file: Path) -> None:
    assert config.load_theme() == config.DEFAULT_THEME == "light"


def test_save_and_load_theme(settings_file: Path) -> None:
    config.save_theme("dark")
    assert settings_file.is_file()
    assert config.load_theme() == "dark"

    config.save_theme("light")
    assert config.load_theme() == "light"


def test_invalid_theme_is_not_saved(settings_file: Path) -> None:
    config.save_theme("neon")
    assert not settings_file.exists()


def test_unknown_saved_theme_falls_back(settings_file: Path) -> None:
    settings_file.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")
    assert config.load_theme() == "light"


def test_corrupt_settings_file_falls_back(settings_file: Path) -> None:
    settings_file.write_text("{not json", encoding="utf-8")
    assert config.load_settings() == {}
    assert config.load_theme() == "light"


def test_existing_settings_are_kept(settings_file: Path) -> None:
    settings_file.write_text(json.dumps({"theme": "light", "other": 42}),
                             encoding="utf-8")
    config.save_theme("dark")
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data == {"theme": "dark", "other": 42}
