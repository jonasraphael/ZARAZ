"""Background work for the GUI.

Scanning and transfers run in their own threads so the window stays
responsive. Results are reported through a `queue.Queue` that the GUI polls
regularly (tkinter is not thread-safe – only the main thread may touch
widgets).

Message types:
    ("drives",  [Drive, ...])            – drive scan finished
    ("saves",   [SaveFile, ...])         – save scan finished
    ("progress", TransferResult, i, n)   – one file transferred
    ("done",    [TransferResult, ...])   – transfer finished
    ("error",   str)                     – something went wrong
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
    """Runs core tasks outside the GUI thread."""

    def __init__(self) -> None:
        self.queue: queue.Queue = queue.Queue()

    def _start(self, target: Callable[..., None], *args) -> None:
        threading.Thread(target=target, args=args, daemon=True).start()

    def refresh_drives(self) -> None:
        def run() -> None:
            try:
                drives = find_removable_drives()
            except Exception as exc:  # the error belongs to the GUI, not the thread
                self.queue.put(("error", f"Drive scan failed: {exc}"))
            else:
                self.queue.put(("drives", drives))
        self._start(run)

    def scan(self, root: Path) -> None:
        def run() -> None:
            try:
                saves = scan_for_saves(root)
            except Exception as exc:
                self.queue.put(("error", f"Save scan failed: {exc}"))
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
                self.queue.put(("error", f"Transfer failed: {exc}"))
            else:
                self.queue.put(("done", results))
        self._start(run)
