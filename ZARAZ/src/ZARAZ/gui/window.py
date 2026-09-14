"""Zaraz – Grafische Oberfläche.

Aufbau (von oben nach unten):
    1. Laufwerksauswahl + Aktualisieren
    2. Spielstände (anklickbare Liste, scrollbar)
    3. Backup-Ziel (mit Durchsuchen/Öffnen)
    4. Konflikt-Strategie + Transfer-Button
    5. Fortschrittsbalken + Protokoll

Scan und Transfer laufen in einem Hintergrund-Thread (siehe worker.py),
das Fenster bleibt jederzeit bedienbar.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.font import nametofont

from zaraz import __version__
from zaraz.config import DEFAULT_BACKUP_DIR
from zaraz.core.sd_scanner import Drive
from zaraz.core.save_extractor import SaveFile
from zaraz.core.transfer import STATUS_LABELS, CollisionStrategy, summarize
from zaraz.gui.worker import Worker

APP_TITLE = f"Zaraz {__version__} – Deine Spielstände, sofort da."
DISCLAIMER = "Zaraz steht in keiner Verbindung zu Nintendo."
CHOOSE_FOLDER = "Anderen Ordner wählen …"

STRATEGY_LABELS = {
    "Umbenennen": CollisionStrategy.RENAME,
    "Überschreiben": CollisionStrategy.OVERWRITE,
    "Überspringen": CollisionStrategy.SKIP,
}


def human_size(num_bytes: int) -> str:
    """832 → '832 B', 65_536 → '64.0 KiB', 5_000_000 → '4.8 MiB'."""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


class ZarazApp(tk.Tk):
    """Hauptfenster von Zaraz."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(720, 520)

        self.worker = Worker()
        self._drives: list[Drive] = []
        self._saves: list[SaveFile] = []
        self._check_vars: list[tk.BooleanVar] = []
        self._busy = False

        self._build_ui()
        self.after(100, self._poll_queue)
        self._refresh_drives()

    # ------------------------------------------------------------------
    # Oberfläche aufbauen
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        # 1) Laufwerk
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="SD-Karte:").pack(side="left")
        self.drive_box = ttk.Combobox(top, state="readonly", width=52)
        self.drive_box.pack(side="left", padx=8, fill="x", expand=True)
        self.drive_box.bind("<<ComboboxSelected>>", self._on_drive_selected)
        self.refresh_btn = ttk.Button(top, text="Aktualisieren",
                                      command=self._refresh_drives)
        self.refresh_btn.pack(side="left")

        # 2) Spielstands-Liste (scrollbar, mit Checkboxen)
        list_frame = ttk.LabelFrame(self, text="Gefundene Spielstände")
        list_frame.pack(fill="both", expand=True, **pad)

        header = ttk.Frame(list_frame)
        header.pack(fill="x", padx=6, pady=(6, 0))
        self.all_var = tk.BooleanVar(value=False)
        self.all_check = ttk.Checkbutton(header, text="Alle auswählen",
                                         variable=self.all_var,
                                         command=self._toggle_all)
        self.all_check.pack(side="left")

        self.list_canvas = tk.Canvas(list_frame, highlightthickness=0)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical",
                                    command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=list_scroll.set)
        self.save_list = ttk.Frame(self.list_canvas)
        self.save_list.bind(
            "<Configure>",
            lambda e: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")))
        # Fenster in der Canvas auf volle Breite halten (sonst kurze Zeilen):
        self.list_canvas.create_window((0, 0), window=self.save_list,
                                       anchor="nw", tags=("inner",))
        self.list_canvas.bind(
            "<Configure>",
            lambda e: self.list_canvas.itemconfigure("inner", width=e.width))
        self.list_canvas.pack(side="left", fill="both", expand=True,
                              padx=(6, 0), pady=6)
        list_scroll.pack(side="right", fill="y", pady=6, padx=(0, 6))

        # Mausrad-Scollen (Windows/macOS: <MouseWheel>, Linux: Button-4/5)
        for widget in (self.list_canvas, self.save_list):
            widget.bind("<Enter>", lambda e: self._bind_wheel())
            widget.bind("<Leave>", lambda e: self._unbind_wheel())

        # Statuszeile
        self.status_var = tk.StringVar(value="Bitte SD-Karte einstecken …")
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(fill="x", **pad)

        # 3) Backup-Ziel
        dest_frame = ttk.LabelFrame(self, text="Backup-Ziel")
        dest_frame.pack(fill="x", **pad)
        self.dest_var = tk.StringVar(value=str(DEFAULT_BACKUP_DIR))
        ttk.Entry(dest_frame, textvariable=self.dest_var).pack(
            side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(dest_frame, text="Durchsuchen …",
                   command=self._browse_dest).pack(side="left", padx=(0, 6), pady=6)
        ttk.Button(dest_frame, text="Öffnen",
                   command=self._open_dest).pack(side="left", padx=(0, 6), pady=6)

        # 4) Aktionen
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", **pad)
        ttk.Label(action_frame, text="Bei Namenskonflikt:").pack(side="left")
        self.strategy_box = ttk.Combobox(action_frame, state="readonly",
                                         width=16, values=list(STRATEGY_LABELS))
        self.strategy_box.current(0)
        self.strategy_box.pack(side="left", padx=8)
        self.transfer_btn = ttk.Button(action_frame, text="Spielstände übertragen",
                                       command=self._start_transfer)
        self.transfer_btn.pack(side="right")

        # 5) Fortschritt + Protokoll
        progress_frame = ttk.LabelFrame(self, text="Fortschritt")
        progress_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress.pack(fill="x", padx=6, pady=(6, 2))
        self.log_box = tk.Text(progress_frame, height=5, state="disabled",
                               font=nametofont("TkFixedFont"))
        self.log_box.pack(fill="x", padx=6, pady=(2, 6))

        # rechtlicher Hinweis (gemäß readme.txt)
        ttk.Label(self, text=DISCLAIMER, foreground="#888").pack(pady=(0, 8))

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.drive_box.configure(state="disabled" if busy else "readonly")
        for btn in (self.refresh_btn, self.transfer_btn, self.all_check):
            btn.configure(state="disabled" if busy else "normal")

    def _bind_wheel(self) -> None:
        self.list_canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.list_canvas.bind_all("<Button-4>", self._on_wheel)
        self.list_canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self) -> None:
        self.list_canvas.unbind_all("<MouseWheel>")
        self.list_canvas.unbind_all("<Button-4>")
        self.list_canvas.unbind_all("<Button-5>")

    def _on_wheel(self, event: tk.Event) -> None:
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.list_canvas.yview_scroll(-1, "units")
        else:
            self.list_canvas.yview_scroll(1, "units")

    # ------------------------------------------------------------------
    # Laufwerke & Scan
    # ------------------------------------------------------------------

    def _refresh_drives(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.status_var.set("Suche Datenträger …")
        self.drive_box.set("")
        self.worker.refresh_drives()

    def _on_drives(self, drives: list[Drive]) -> None:
        self._drives = drives
        self._set_busy(False)
        labels = [str(d) for d in drives]
        if labels:
            self.drive_box["values"] = labels + [CHOOSE_FOLDER]
            self.drive_box.current(0)
            self.status_var.set(f"{len(drives)} Datenträger gefunden – wird gescannt …")
            self._begin_scan(drives[0].mountpoint)  # erstes Laufwerk automatisch scannen
        else:
            self.drive_box["values"] = [CHOOSE_FOLDER]
            self.status_var.set("Kein Wechseldatenträger gefunden. Karte einstecken "
                                "und 'Aktualisieren' klicken – oder einen Ordner wählen.")

    def _on_drive_selected(self, _event=None) -> None:
        if self._busy:
            return
        index = self.drive_box.current()
        values = list(self.drive_box["values"])
        if index < 0 or index >= len(values):
            return
        if values[index] == CHOOSE_FOLDER:
            folder = filedialog.askdirectory(title="Ordner mit Spielständen wählen")
            if folder:
                self._begin_scan(Path(folder))
            return
        if index < len(self._drives):
            self._begin_scan(self._drives[index].mountpoint)

    def _begin_scan(self, root: Path) -> None:
        self._set_busy(True)
        self.status_var.set(f"Scanne {root} …")
        self.worker.scan(root)

    def _render_saves(self, saves: list[SaveFile]) -> None:
        for child in self.save_list.winfo_children():
            child.destroy()
        self._saves = saves
        self._check_vars = []
        self.all_var.set(bool(saves))

        if not saves:
            ttk.Label(self.save_list, text="(keine Spielstände gefunden)",
                      foreground="#888").pack(anchor="w", padx=8, pady=8)
            self.status_var.set("Keine Spielstände gefunden.")
            self._set_busy(False)
            return

        for save in saves:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            text = (f"{save.relative_path}   ·   "
                    f"{human_size(save.size_bytes)} · {save.guess_console()}")
            ttk.Checkbutton(self.save_list, text=text, variable=var,
                            command=self._sync_all_var).pack(
                                anchor="w", fill="x", padx=8, pady=1)

        self.list_canvas.yview_moveto(0)
        self.status_var.set(f"{len(saves)} Spielstände gefunden.")
        self._set_busy(False)

    # ------------------------------------------------------------------
    # Auswahl & Transfer
    # ------------------------------------------------------------------

    def _toggle_all(self) -> None:
        value = self.all_var.get()
        for var in self._check_vars:
            var.set(value)

    def _sync_all_var(self) -> None:
        if self._check_vars:
            self.all_var.set(all(v.get() for v in self._check_vars))

    def _selected_saves(self) -> list[SaveFile]:
        return [s for s, var in zip(self._saves, self._check_vars) if var.get()]

    def _browse_dest(self) -> None:
        folder = filedialog.askdirectory(title="Backup-Zielordner wählen")
        if folder:
            self.dest_var.set(folder)

    def _open_dest(self) -> None:
        path = Path(self.dest_var.get().strip() or str(DEFAULT_BACKUP_DIR))
        try:
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(path)  # nur unter Windows vorhanden
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Zaraz", f"Ordner konnte nicht geöffnet werden:\n{exc}")

    def _start_transfer(self) -> None:
        if self._busy:
            return
        chosen = self._selected_saves()
        if not chosen:
            messagebox.showinfo("Zaraz", "Bitte mindestens einen Spielstand auswählen.")
            return
        raw_dest = self.dest_var.get().strip()
        if not raw_dest:
            messagebox.showwarning("Zaraz", "Bitte ein Backup-Ziel angeben.")
            return

        strategy = STRATEGY_LABELS[self.strategy_box.get()]
        self._set_busy(True)
        self.progress.configure(maximum=len(chosen), value=0)
        self._log(f"— Transfer gestartet: {len(chosen)} Spielstände → {raw_dest}")
        self.status_var.set(f"Übertrage 0/{len(chosen)} …")
        self.worker.transfer(chosen, Path(raw_dest), strategy)

    def _on_progress(self, result, i: int, n: int) -> None:
        self.progress.configure(value=i)
        label = STATUS_LABELS.get(result.status, result.status)
        if not result.verified and result.status not in ("identical", "skipped"):
            label += "  [WARNUNG: Verifizierung fehlgeschlagen!]"
        self._log(f"[{i}/{n}] {result.source.name}: {label}")
        self.status_var.set(f"Übertrage {i}/{n} …")

    def _on_done(self, results) -> None:
        self._set_busy(False)
        self.progress.configure(value=len(results))
        summary = summarize(results)
        self._log(f"— Fertig: {summary}")
        self.status_var.set(f"Fertig! {summary}")

        errors = [r for r in results if r.status == "error"]
        warns = [r for r in results
                 if not r.verified and r.status not in ("identical", "skipped")]
        if errors:
            lines = "\n".join(f"• {r.source.name}" for r in errors)
            messagebox.showerror("Zaraz", "Fehler beim Übertragen:\n" + lines)
        elif warns:
            messagebox.showwarning(
                "Zaraz", "Einige Dateien konnten nicht verifiziert werden –\n"
                         "Details stehen im Protokoll.")
        else:
            messagebox.showinfo("Zaraz", f"Fertig!\n{summary}")

    # ------------------------------------------------------------------
    # Warteschlange (Kommunikation Worker -> GUI)
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        try:
            while True:
                self._handle_message(self.worker.queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_message(self, message: tuple) -> None:
        kind = message[0]
        if kind == "drives":
            self._on_drives(message[1])
        elif kind == "saves":
            self._render_saves(message[1])
        elif kind == "progress":
            self._on_progress(message[1], message[2], message[3])
        elif kind == "done":
            self._on_done(message[1])
        elif kind == "error":
            self._set_busy(False)
            self.status_var.set("Fehler.")
            messagebox.showerror("Zaraz", message[1])


def run() -> None:
    app = ZarazApp()
    app.mainloop()


if __name__ == "__main__":
    run()