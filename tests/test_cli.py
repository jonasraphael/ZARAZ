"""Tests für die Kommandozeilen-Logik (Auswahl-Parser, Argumente)."""

from __future__ import annotations

import pytest

from zaraz.main import build_parser, parse_selection


class TestParseSelection:
    def test_single_number(self):
        assert parse_selection("1", 10) == [0]

    def test_multiple_numbers(self):
        assert parse_selection("1,3", 10) == [0, 2]

    def test_range(self):
        assert parse_selection("2-5", 10) == [1, 2, 3, 4]

    def test_mixed(self):
        assert parse_selection("1,3-4", 10) == [0, 2, 3]

    def test_whitespace_and_duplicates(self):
        assert parse_selection(" 1 , 1 , 2 ", 10) == [0, 1]

    def test_all_keywords(self):
        for keyword in ("all", "a", "*", "ALL"):
            assert parse_selection(keyword, 3) == [0, 1, 2]

    def test_mixed_valid_and_invalid(self):
        assert parse_selection("1,99", 3) == [0]   # 99 fliegt raus, 1 bleibt

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            parse_selection("99", 3)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            parse_selection("0", 3)

    def test_descending_range_raises(self):
        with pytest.raises(ValueError):
            parse_selection("3-1", 3)

    def test_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_selection("abc", 3)

    def test_partial_garbage_raises(self):
        with pytest.raises(ValueError):
            parse_selection("1-x", 3)


class TestBuildParser:
    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.drive is None
        assert args.all is False
        assert args.list is False

    def test_list_flag(self):
        assert build_parser().parse_args(["--list"]).list is True
        assert build_parser().parse_args(["-l"]).list is True

    def test_drive_and_dest(self):
        args = build_parser().parse_args(["--drive", "E:\\", "--dest", "C:/Backups"])
        assert args.drive == "E:\\"
        assert args.dest == "C:/Backups"

    def test_invalid_strategy_rejected(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--strategy", "bitte-nicht"])

    def test_version_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args(["--version"])
        assert excinfo.value.code == 0
        assert "zaraz" in capsys.readouterr().out.lower()