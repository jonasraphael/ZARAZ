#!/usr/bin/env python3
"""Zaraz – Kommandozeilen-Einstiegspunkt.

"Deine Spielstände, sofort da."
SD-Karte einstecken, Spielstand wählen, fertig.
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
    transfer_all,
    summarize,
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
        description="Überträgt Spielstände (.sav, .srm, ...) von deiner SD-Karte "
                    "auf den PC – von Game Boy bis Switch.",
        epilog="Beispiel: zaraz --drive E:\\ --all",
    )
    parser.add_argument("--drive", metavar="PFAD",
                        help="Datenträger/Ordner direkt angeben (überspringt die automatische Erkennung)")
    parser.add_argument("--dest", metavar="PFAD",
                        help=f"Backup-Zielordner (Standard: {DEFAULT_BACKUP_DIR})")
    parser.add_argument("-a", "--all", action="store_true",
                        help="alle gefundenen Spielstände übertragen (keine Auswahl)")
    parser.add_argument("--strategy", choices=[s.value for s in CollisionStrategy],
                        help="bei Namenskonflikt: rename, overwrite oder skip")
    parser.add_argument("-l", "--list", action="store_true",
                        help="nur anzeigen, nichts kopieren")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="ausführliche Log-Ausgaben (für Fehlersuche)")
    parser.add_argument("--version", action="version", version=f"zaraz {__version__}")
    return parser


def choose_drive(args: argparse.Namespace) -> Path | None:
    """Liefert das zu scannende Laufwerk – per Argument, Erkennung oder Auswahl."""
    if args.drive:
        path = Path(args.drive)
        if not path.is_dir():
            print(f"FEHLER: Angegebener Pfad ist kein Verzeichnis: {path}")
            return None
        return path

    drives = find_removable_drives()
    if not drives:
        print("Keine SD-Karte / keinen Wechseldatenträger gefunden.")
        print("Karte eingesteckt? Alternativ:  zaraz --drive <Pfad>")
        return None

    if len(drives) == 1:
        print(f"SD-Karte erkannt: {drives[0]}")
        return drives[0].mountpoint

    print("\nMehrere Datenträger gefunden:")
    for i, drive in enumerate(drives, start=1):
        print(f"  [{i}] {drive}")
    while True:
        raw = input("Welchen Datenträger? [1]: ").strip()
        if not raw:
            return drives[0].mountpoint
        if raw.isdigit() and 1 <= int(raw) <= len(drives):
            return drives[int(raw) - 1].mountpoint
        print("Ungültige Eingabe, bitte erneut.")


def display_saves(saves: list[SaveFile]) -> None:
    print(f"\n{len(saves)} Spielstände gefunden:\n")
    for i, s in enumerate(saves, start=1):
        print(f"  [{i:>2}] {s.relative_path}  ({s.size_kb:.0f} KiB · {s.guess_console()})")
    print()


def parse_selection(text: str, count: int) -> list[int]:
    """Übersetzt eine Auswahl wie '1,3-5' oder 'all' in 0-basierte Indizes."""
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
                raise ValueError(f"Ungültiger Bereich: '{part}'") from None
            indices.update(range(start - 1, end))
        else:
            try:
                indices.add(int(part) - 1)
            except ValueError:
                raise ValueError(f"Ungültige Zahl: '{part}'") from None

    valid = [i for i in sorted(indices) if 0 <= i < count]
    if not valid:
        raise ValueError("Keine gültige Auswahl dabei.")
    return valid


def select_saves(saves: list[SaveFile], choose_all: bool) -> list[int]:
    if choose_all:
        return list(range(len(saves)))
    print("Auswahl: z.B. '1', '1,3', '2-5' oder 'all'")
    while True:
        raw = input("Welche Spielstände? [all]: ").strip() or "all"
        try:
            return parse_selection(raw, len(saves))
        except ValueError as exc:
            print(f"Ungültige Eingabe: {exc}")


def choose_destination(args: argparse.Namespace) -> Path:
    if args.dest:
        return Path(args.dest)
    raw = input(f"Backup-Ziel [{DEFAULT_BACKUP_DIR}]: ").strip()
    return Path(raw) if raw else DEFAULT_BACKUP_DIR


def _print_progress(result: TransferResult, i: int, n: int) -> None:
    label = STATUS_LABELS.get(result.status, result.status)
    if not result.verified and result.status not in ("identical", "skipped"):
        label += "  [WARNUNG: Verifizierung fehlgeschlagen!]"
    print(f"  [{i}/{n}] {result.source.name}: {label}")


def _run(args: argparse.Namespace) -> int:
    drive = choose_drive(args)
    if drive is None:
        return 1

    print(f"\nScanne {drive} ...")
    try:
        saves = scan_for_saves(drive)
    except NotADirectoryError as exc:
        print(f"FEHLER: {exc}")
        return 1

    if not saves:
        exts = ", ".join(sorted(SAVE_EXTENSIONS))
        print(f"Keine Spielstände gefunden (Endungen: {exts}, plus .bin in Checkpoint-Ordnern).")
        return 0

    saves.sort(key=lambda s: str(s.relative_path).lower())
    display_saves(saves)

    if args.list:
        return 0

    indices = select_saves(saves, choose_all=args.all)
    chosen = [saves[i] for i in indices]

    backup_dir = choose_destination(args)
    strategy = CollisionStrategy(args.strategy) if args.strategy else default_strategy()

    print(f"\nÜbertrage {len(chosen)} Spielstände nach: {backup_dir}\n")
    results = transfer_all(chosen, backup_dir, strategy, on_progress=_print_progress)

    print(f"\nFertig! {summarize(results)}")
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
    print(f"Zaraz v{__version__} – Deine Spielstände, sofort da.")
    print("Zaraz steht in keiner Verbindung zu Nintendo.\n")

    try:
        return _run(args)
    except (KeyboardInterrupt, EOFError):
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())