#!/usr/bin/env python3
"""Zaraz – command line entry point.

"Your saves, instantly there."
Plug in the SD card, pick the save files, done.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from zaraz import __version__
from zaraz.config import DEFAULT_BACKUP_DIR, SAVE_EXTENSIONS
from zaraz.core.sd_scanner import find_removable_drives
from zaraz.core.save_extractor import SaveFile, scan_for_saves
from zaraz.core.transfer import (
    STATUS_LABELS,
    CollisionStrategy,
    TransferResult,
    default_strategy,
    summarize,
    transfer_all,
)

BANNER = r"""
zzzzzzzzzzzzzzzzz  aaaaaaaaaaaaa  rrrrr   rrrrrrrrr   aaaaaaaaaaaaa   zzzzzzzzzzzzzzzzz
z:::::::::::::::z  a::::::::::::a r::::rrr:::::::::r  a::::::::::::a  z:::::::::::::::z
z::::::::::::::z   aaaaaaaaa:::::ar:::::::::::::::::r aaaaaaaaa:::::a z::::::::::::::z
zzzzzzzz::::::z             a::::arr::::::rrrrr::::::r         a::::a zzzzzzzz::::::z
      z::::::z       aaaaaaa:::::a r:::::r     r:::::r  aaaaaaa:::::a       z::::::z
     z::::::z      aa::::::::::::a r:::::r     rrrrrrraa::::::::::::a      z::::::z
    z::::::z      a::::aaaa::::::a r:::::r           a::::aaaa::::::a     z::::::z
   z::::::z      a::::a    a:::::a r:::::r          a::::a    a:::::a    z::::::z
  z::::::zzzzzzzza::::a    a:::::a r:::::r          a::::a    a:::::a   z::::::zzzzzzzz
 z::::::::::::::za:::::aaaa::::::a r:::::r          a:::::aaaa::::::a  z::::::::::::::z
z:::::::::::::::z a::::::::::aa:::ar:::::r           a::::::::::aa:::az:::::::::::::::z
zzzzzzzzzzzzzzzzz  aaaaaaaaaa  aaaarrrrrrr            aaaaaaaaaa  aaaazzzzzzzzzzzzzzzzz
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zaraz",
        description="Transfers save files (.sav, .srm, ...) from your SD card "
                    "to the PC – from Game Boy to Switch.",
        epilog="Example: zaraz --drive E:\\ --all",
    )
    parser.add_argument("--drive", metavar="PATH",
                        help="use this drive/folder directly (skips automatic detection)")
    parser.add_argument("--dest", metavar="PATH",
                        help=f"backup destination folder (default: {DEFAULT_BACKUP_DIR})")
    parser.add_argument("-a", "--all", action="store_true",
                        help="transfer every detected save file (no selection)")
    parser.add_argument("--strategy", choices=[s.value for s in CollisionStrategy],
                        help="on a name collision: rename, overwrite or skip")
    parser.add_argument("-l", "--list", action="store_true",
                        help="only list the results, do not copy anything")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="verbose log output (for troubleshooting)")
    parser.add_argument("--version", action="version", version=f"zaraz {__version__}")
    return parser


def choose_drive(args: argparse.Namespace) -> Path | None:
    """Returns the drive to scan – from the argument, detection or a prompt."""
    if args.drive:
        path = Path(args.drive).expanduser()
        if not path.is_dir():
            print(f"ERROR: The given path is not a directory: {path}")
            return None
        return path

    drives = find_removable_drives()
    if not drives:
        print("No SD card / removable drive found.")
        print("Is the card plugged in? Alternatively:  zaraz --drive <path>")
        return None

    if len(drives) == 1:
        print(f"SD card detected: {drives[0]}")
        return drives[0].mountpoint

    print("\nMultiple drives found:")
    for i, drive in enumerate(drives, start=1):
        print(f"  [{i}] {drive}")
    while True:
        raw = input("Which drive? [1]: ").strip()
        if not raw:
            return drives[0].mountpoint
        if raw.isdigit() and 1 <= int(raw) <= len(drives):
            return drives[int(raw) - 1].mountpoint
        print("Invalid input, please try again.")


def display_saves(saves: list[SaveFile]) -> None:
    print(f"\n{len(saves)} save files found:\n")
    for i, s in enumerate(saves, start=1):
        print(f"  [{i:>2}] {s.relative_path}  ({s.size_kb:.0f} KiB · {s.guess_console()})")
    print()


def parse_selection(text: str, count: int) -> list[int]:
    """Turns a selection such as '1,3-5' or 'all' into zero-based indexes."""
    text = text.strip().lower()
    if text in {"all", "a", "*"}:
        return list(range(count))

    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, _, end_s = part.partition("-")
            try:
                start, end = int(start_s), int(end_s)
            except ValueError:
                raise ValueError(f"Invalid range: '{part}'") from None
            indices.update(range(start - 1, end))
        else:
            try:
                indices.add(int(part) - 1)
            except ValueError:
                raise ValueError(f"Invalid number: '{part}'") from None

    valid = [i for i in sorted(indices) if 0 <= i < count]
    if not valid:
        raise ValueError("No valid selection in the input.")
    return valid


def select_saves(saves: list[SaveFile], choose_all: bool) -> list[int]:
    if choose_all:
        return list(range(len(saves)))
    print("Selection: e.g. '1', '1,3', '2-5' or 'all'")
    while True:
        raw = input("Which save files? [all]: ").strip() or "all"
        try:
            return parse_selection(raw, len(saves))
        except ValueError as exc:
            print(f"Invalid input: {exc}")


def choose_destination(args: argparse.Namespace) -> Path:
    if args.dest:
        return Path(args.dest).expanduser()
    raw = input(f"Backup destination [{DEFAULT_BACKUP_DIR}]: ").strip()
    return Path(raw).expanduser() if raw else DEFAULT_BACKUP_DIR


def _print_progress(result: TransferResult, i: int, n: int) -> None:
    label = STATUS_LABELS.get(result.status, result.status)
    if not result.verified and result.status not in ("identical", "skipped"):
        label += "  [WARNING: verification failed!]"
    print(f"  [{i}/{n}] {result.source.name}: {label}")


def _run(args: argparse.Namespace) -> int:
    drive = choose_drive(args)
    if drive is None:
        return 1

    print(f"\nScanning {drive} ...")
    try:
        saves = scan_for_saves(drive)
    except NotADirectoryError as exc:
        print(f"ERROR: {exc}")
        return 1

    if not saves:
        exts = ", ".join(sorted(SAVE_EXTENSIONS))
        print(f"No save files found (extensions: {exts}, plus .bin inside "
              "Checkpoint folders).")
        return 0

    saves.sort(key=lambda s: str(s.relative_path).lower())
    display_saves(saves)

    if args.list:
        return 0

    indices = select_saves(saves, choose_all=args.all)
    chosen = [saves[i] for i in indices]

    backup_dir = choose_destination(args)
    strategy = CollisionStrategy(args.strategy) if args.strategy else default_strategy()

    print(f"\nTransferring {len(chosen)} save files to: {backup_dir}\n")
    results = transfer_all(chosen, backup_dir, strategy, on_progress=_print_progress)

    print(f"\nDone! {summarize(results)}")
    if any(r.status == "error" for r in results):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    print(BANNER)
    print(f"Zaraz v{__version__} – Your saves, instantly there.")
    print("Zaraz is not affiliated with or endorsed by Nintendo.\n")

    try:
        return _run(args)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
