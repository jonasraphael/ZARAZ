"""Hintergrund-Arbeiten für die GUI.

Scan und Transfer laufen in eigenen Threads, damit das Fenster
reaktiv bleibt. Ergebnisse werden über eine `queue.Queue` gemeldet,
die die GUI regelmäßig abfragt (tkinter ist nicht threadsicher –
nur der Haupt-Thread darf Widgets anfassen).

Nachrichtentypen:
    ("drives",  [Drive, ...])            – Laufwerksscan fertig
    ("saves",   [SaveFile, ...])         – Save-Scan fertig
    ("progress", TransferResult, i, n)   – eine Datei übertragen
    ("done",    [TransferResult, ...])   – Transfer abgeschlossen
    ("error",   str)                     – etwas ist schiefgelaufen
"""

from __future__ import annotations

import logging
import queue
import threading
from pathlib import Path
from typing import Callable

from zaraz.core.sd_scanner import Drive, find_removable_drives
from zaraz.core.save_extractor import SaveFile, scan_for_saves
from zaraz.core.transfer import CollisionStrategy, TransferResult, transfer_all

logger = logging.getLogger(__name__)


class Worker:
    """Führt Core-Aufgaben außerhalb des GUI-Threads aus."""

    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()

    def _start(self, target: Callable[..., None], *args) -> None:
        threading.Thread(target=target, args=args, daemon=True).start()

    def refresh_drives(self) -> None:
        def run() -> None:
            try:
                drives = find_removable_drives()
            except Exception as exc:  # Fehler soll die GUI erreichen, nicht der Thread
                self.queue.put(("error", f"Scan fehlgeschlagen: {exc}"))
            else:
                self.queue.put(("drives", drives))
        self._start(run)

    def scan(self, root: Path) -> None:
        def run() -> None:
            try:
                saves = scan_for_saves(root)
            except Exception as exc:
                self.queue.put(("error", f"Scan fehluschlagen: {exc}"))
            else:
                self.queue.put(("saves", saves))
        self._start(run)

    def transfer(
        self,
        saves: list[SaveFile],
        backup_dir: Path,
        strategy: CollisionStrategy,
    ) -> None:
        def report(result: TransferResult, i: int, n: int) -> None:
            self.queue.put(("progress", result, i, n))

        def run() -> None:
            try:
                results = transfer_all(saves, backup_dir, strategy, on_progress=report)
            except Exception as exc:
                self.queue.put(("error", f"Transfer fehlgeschlagen: {exc}"))
            else:
                self.queue.put(("done", results))
        self._start(run)