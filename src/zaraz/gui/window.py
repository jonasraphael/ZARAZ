"""Zaraz – graphical user interface.

Layout from top to bottom:
1. Header with the app name and the light/dark switch
2. Drive selection + refresh
3. Detected save files (scrollable list with check boxes)
4. Backup destination (with Browse / Open)
5. Collision strategy + transfer button
6. Progress bar and log

Scanning and transfer run in a background thread (see worker.py), so the
window stays usable the whole time.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from zaraz import __version__
from zaraz.config import DEFAULT_BACKUP_DIR, load_theme, save_theme
from zaraz.core.save_extractor import SaveFile
from zaraz.core.sd_scanner import Drive
from zaraz.core.transfer import STATUS_LABELS, CollisionStrategy, summarize
from zaraz.gui.theme import PALETTES, configure_styles
from zaraz.gui.uninstall import find_uninstaller, start_uninstaller
from zaraz.gui.worker import Worker

APP_TITLE = f"ZARAZ {__version__}"
TAGLINE = "Your saves, instantly there."
DISCLAIMER = "Zaraz is not affiliated with or endorsed by Nintendo."
CHOOSE_FOLDER = "Choose another folder …"
STRATEGY_LABELS = {
    "Rename": CollisionStrategy.RENAME,
    "Overwrite": CollisionStrategy.OVERWRITE,
    "Skip": CollisionStrategy.SKIP,
}


def human_size(num_bytes: int) -> str:
    """832 -> '832 B', 65_536 -> '64.0 KiB', 5_000_000 -> '4.8 MiB'."""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


class ZarazApp(tk.Tk):
    """Main window of Zaraz."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(760, 560)

        self.worker = Worker()
        self.theme = PALETTES[load_theme()]
        self.style = ttk.Style(self)

        self._drives: list[Drive] = []
        self._saves: list[SaveFile] = []
        self._check_vars: list[tk.BooleanVar] = []
        self._busy = False

        self._build_ui()
        self._apply_theme()
        self.after(100, self._poll_queue)
        self._refresh_drives()

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=18, pady=(16, 12))

        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text="ZARAZ", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=TAGLINE, style="Tagline.TLabel").pack(anchor="w")

        self.theme_btn = ttk.Button(
            header, text="", style="Secondary.TButton", command=self._toggle_theme
        )
        self.theme_btn.pack(side="right")

        ttk.Separator(self).pack(fill="x")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # 1) Drive selection
        ttk.Label(body, text="SD card", style="Section.TLabel").pack(anchor="w")
        drive_row = ttk.Frame(body)
        drive_row.pack(fill="x", pady=(6, 0))
        self.drive_box = ttk.Combobox(drive_row, state="readonly")
        self.drive_box.pack(side="left", fill="x", expand=True)
        self.drive_box.bind("<<ComboboxSelected>>", self._on_drive_selected)
        self.refresh_btn = ttk.Button(
            drive_row,
            text="Refresh",
            style="Secondary.TButton",
            command=self._refresh_drives,
        )
        self.refresh_btn.pack(side="left", padx=(8, 0))
        self.drive_info_var = tk.StringVar(value="")
        ttk.Label(
            body, textvariable=self.drive_info_var, style="Muted.TLabel"
        ).pack(anchor="w", pady=(4, 0))

        # 2) Save files
        saves_header = ttk.Frame(body)
        saves_header.pack(fill="x", pady=(16, 6))
        ttk.Label(saves_header, text="Save files found", style="Section.TLabel").pack(
            side="left"
        )
        self.count_var = tk.StringVar(value="none yet")
        ttk.Label(
            saves_header, textvariable=self.count_var, style="Muted.TLabel"
        ).pack(side="left", padx=(8, 0))
        self.all_var = tk.BooleanVar(value=False)
        self.all_check = ttk.Checkbutton(
            saves_header,
            text="Select all",
            variable=self.all_var,
            command=self._toggle_all,
        )
        self.all_check.pack(side="right")

        self.list_border = tk.Frame(body, highlightthickness=1, bd=0)
        self.list_border.pack(fill="both", expand=True)
        self.list_canvas = tk.Canvas(self.list_border, highlightthickness=0, bd=0)
        list_scroll = ttk.Scrollbar(
            self.list_border, orient="vertical", command=self.list_canvas.yview
        )
        self.list_canvas.configure(yscrollcommand=list_scroll.set)
        self.save_list = ttk.Frame(self.list_canvas)
        self.save_list.bind(
            "<Configure>",
            lambda e: self.list_canvas.configure(
                scrollregion=self.list_canvas.bbox("all")
            ),
        )
        self.list_canvas.create_window(
            (0, 0), window=self.save_list, anchor="nw", tags=("inner",)
        )
        self.list_canvas.bind(
            "<Configure>",
            lambda e: self.list_canvas.itemconfigure("inner", width=e.width),
        )
        self.list_canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        list_scroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

        # Mouse wheel scrolling (Windows/macOS: <MouseWheel>, Linux: Button-4/5)
        for widget in (self.list_canvas, self.save_list):
            widget.bind("<Enter>", lambda e: self._bind_wheel())
            widget.bind("<Leave>", lambda e: self._unbind_wheel())

        # 3) Backup destination
        ttk.Label(body, text="Backup destination", style="Section.TLabel").pack(
            anchor="w", pady=(16, 6)
        )
        dest_row = ttk.Frame(body)
        dest_row.pack(fill="x")
        self.dest_var = tk.StringVar(value=str(DEFAULT_BACKUP_DIR))
        self.dest_entry = ttk.Entry(dest_row, textvariable=self.dest_var)
        self.dest_entry.pack(side="left", fill="x", expand=True)
        self.browse_btn = ttk.Button(
            dest_row,
            text="Browse …",
            style="Secondary.TButton",
            command=self._browse_dest,
        )
        self.browse_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ttk.Button(
            dest_row, text="Open", style="Secondary.TButton", command=self._open_dest
        )
        self.open_btn.pack(side="left", padx=(8, 0))

        # 4) Actions
        action_row = ttk.Frame(body)
        action_row.pack(fill="x", pady=(16, 0))
        ttk.Label(action_row, text="On name collision", style="Section.TLabel").pack(
            side="left"
        )
        self.strategy_box = ttk.Combobox(
            action_row,
            state="readonly",
            width=14,
            values=list(STRATEGY_LABELS),
        )
        self.strategy_box.current(0)
        self.strategy_box.pack(side="left", padx=(10, 0))
        self.transfer_btn = ttk.Button(
            action_row,
            text="Transfer save files",
            style="Accent.TButton",
            command=self._start_transfer,
        )
        self.transfer_btn.pack(side="right")

        # 5) Progress and log
        ttk.Label(body, text="Progress", style="Section.TLabel").pack(
            anchor="w", pady=(16, 6)
        )
        self.progress = ttk.Progressbar(body, mode="determinate")
        self.progress.pack(fill="x")
        self.log_box = tk.Text(
            body, height=6, wrap="word", relief="flat", bd=0, padx=8, pady=6
        )
        self.log_box.configure(state="disabled")
        self.log_box.pack(fill="x", pady=(8, 0))

        # Footer
        ttk.Separator(self).pack(fill="x")
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=18, pady=(8, 12))
        self.status_var = tk.StringVar(value="Plug in your SD card to begin.")
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").pack(
            side="left"
        )

        self.uninstaller_path = find_uninstaller()
        if self.uninstaller_path is not None:
            ttk.Button(
                footer,
                text="Uninstall",
                style="Ghost.TButton",
                command=self._uninstall,
            ).pack(side="right")
        ttk.Label(footer, text=DISCLAIMER, style="Muted.TLabel").pack(
            side="right", padx=(0, 14)
        )

    def _apply_theme(self) -> None:
        configure_styles(self, self.style, self.theme)
        self.theme_btn.configure(text=f"{self.theme.label} theme")
        self.list_border.configure(
            background=self.theme.border, highlightbackground=self.theme.border
        )
        self.list_canvas.configure(background=self.theme.surface)
        self.log_box.configure(
            background=self.theme.log_bg,
            foreground=self.theme.log_fg,
            insertbackground=self.theme.text,
            selectbackground=self.theme.selection,
            selectforeground=self.theme.text,
        )

    def _toggle_theme(self) -> None:
        name = "dark" if self.theme.name == "light" else "light"
        self.theme = PALETTES[name]
        save_theme(name)
        self._apply_theme()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        readonly = "disabled" if busy else "readonly"
        self.drive_box.configure(state=readonly)
        self.strategy_box.configure(state=readonly)
        for widget in (
            self.refresh_btn,
            self.transfer_btn,
            self.all_check,
            self.browse_btn,
            self.open_btn,
        ):
            widget.configure(state=state)
        self.dest_entry.configure(state=state)

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
    # Drives and scanning
    # ------------------------------------------------------------------
    def _refresh_drives(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.status_var.set("Looking for removable drives …")
        self.drive_box.set("")
        self.worker.refresh_drives()

    def _on_drives(self, drives: list[Drive]) -> None:
        self._drives = drives
        self._set_busy(False)
        labels = [str(d) for d in drives]
        if labels:
            self.drive_box["values"] = labels + [CHOOSE_FOLDER]
            self.drive_box.current(0)
            self.drive_info_var.set("")
            self.status_var.set(f"{len(drives)} drive(s) found – scanning …")
            self._begin_scan(drives[0].mountpoint)  # scan the first drive automatically
        else:
            self.drive_box["values"] = [CHOOSE_FOLDER]
            self.drive_box.set("")
            self.drive_info_var.set("No removable drive found.")
            self.status_var.set(
                "No removable drive found. Plug in the card and click "
                "'Refresh' – or choose another folder."
            )

    def _on_drive_selected(self, _event=None) -> None:
        if self._busy:
            return
        index = self.drive_box.current()
        values = list(self.drive_box["values"])
        if index < 0 or index >= len(values):
            return
        if values[index] == CHOOSE_FOLDER:
            folder = filedialog.askdirectory(
                parent=self, title="Choose a folder with save files"
            )
            self.drive_box.set("")
            if folder:
                self.drive_info_var.set(f"Custom folder: {folder}")
                self._begin_scan(Path(folder))
            return
        if index < len(self._drives):
            drive = self._drives[index]
            self.drive_info_var.set(str(drive))
            self._begin_scan(drive.mountpoint)

    def _begin_scan(self, root: Path) -> None:
        self._set_busy(True)
        self.status_var.set(f"Scanning {root} …")
        self.worker.scan(root)

    def _render_saves(self, saves: list[SaveFile]) -> None:
        for child in self.save_list.winfo_children():
            child.destroy()
        self._saves = saves
        self._check_vars = []
        self.all_var.set(bool(saves))

        if not saves:
            ttk.Label(
                self.save_list,
                text="(no save files found)",
                style="Muted.TLabel",
            ).pack(anchor="w", padx=8, pady=8)
            self.count_var.set("0 entries")
            self.status_var.set("No save files found.")
            self._set_busy(False)
            return

        for save in saves:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            text = (
                f"{save.relative_path} · "
                f"{human_size(save.size_bytes)} · {save.guess_console()}"
            )
            ttk.Checkbutton(
                self.save_list,
                text=text,
                variable=var,
                command=self._sync_all_var,
                style="List.TCheckbutton",
            ).pack(anchor="w", fill="x", padx=8, pady=1)

        self.list_canvas.yview_moveto(0)
        self.count_var.set(f"{len(saves)} entries")
        self.status_var.set(f"{len(saves)} save files found.")
        self._set_busy(False)

    # ------------------------------------------------------------------
    # Selection and transfer
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
        folder = filedialog.askdirectory(
            parent=self, title="Choose the backup destination folder"
        )
        if folder:
            self.dest_var.set(folder)

    def _open_dest(self) -> None:
        path = Path(
            self.dest_var.get().strip() or str(DEFAULT_BACKUP_DIR)
        ).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(path)  # Windows only
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE, f"Could not open the folder:\n{exc}", parent=self
            )

    def _start_transfer(self) -> None:
        if self._busy:
            return
        chosen = self._selected_saves()
        if not chosen:
            messagebox.showinfo(
                APP_TITLE, "Please select at least one save file.", parent=self
            )
            return
        raw_dest = self.dest_var.get().strip()
        if not raw_dest:
            messagebox.showwarning(
                APP_TITLE, "Please enter a backup destination.", parent=self
            )
            return
        backup_dir = Path(raw_dest).expanduser()
        self.dest_var.set(str(backup_dir))

        strategy = STRATEGY_LABELS[self.strategy_box.get()]
        self._set_busy(True)
        self.progress.configure(maximum=len(chosen), value=0)
        self._log(f"— Transfer started: {len(chosen)} save files → {backup_dir}")
        self.status_var.set(f"Transferring 0/{len(chosen)} …")
        self.worker.transfer(chosen, backup_dir, strategy)

    def _on_progress(self, result, i: int, n: int) -> None:
        self.progress.configure(value=i)
        label = STATUS_LABELS.get(result.status, result.status)
        if not result.verified and result.status not in ("identical", "skipped"):
            label += " [WARNING: verification failed!]"
        self._log(f"[{i}/{n}] {result.source.name}: {label}")
        self.status_var.set(f"Transferring {i}/{n} …")

    def _on_done(self, results) -> None:
        self._set_busy(False)
        self.progress.configure(value=len(results))
        summary = summarize(results)
        self._log(f"— Finished: {summary}")
        self.status_var.set(f"Done! {summary}")
        errors = [r for r in results if r.status == "error"]
        warns = [
            r
            for r in results
            if not r.verified and r.status not in ("identical", "skipped")
        ]
        if errors:
            lines = "\n".join(f"• {r.source.name}" for r in errors)
            messagebox.showerror(
                APP_TITLE, "Errors while transferring:\n" + lines, parent=self
            )
        elif warns:
            messagebox.showwarning(
                APP_TITLE,
                "Some files could not be verified –\n"
                "see the log for details.",
                parent=self,
            )
        else:
            messagebox.showinfo(APP_TITLE, f"Done!\n{summary}", parent=self)

    # ------------------------------------------------------------------
    # Uninstall
    # ------------------------------------------------------------------
    def _uninstall(self) -> None:
        if self.uninstaller_path is None:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "ZARAZ will close and the uninstaller will remove the "
            "application from this computer.\n\nUninstall now?",
            parent=self,
        ):
            return
        try:
            start_uninstaller(self.uninstaller_path)
        except OSError as exc:
            messagebox.showerror(
                APP_TITLE, f"Could not start the uninstaller:\n{exc}", parent=self
            )
            return
        self.destroy()

    # ------------------------------------------------------------------
    # Queue (worker -> GUI)
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
            self.status_var.set("Error.")
            messagebox.showerror(APP_TITLE, message[1], parent=self)


def _icon_candidates() -> list[Path]:
    candidates: list[Path] = []
    for base in (Path(sys.executable).resolve().parent, Path(__file__).resolve().parent):
        candidates.append(base / "Zaraz.ico")
        candidates.append(base / "zaraz.ico")
        candidates.append(base.parent / "Zaraz.ico")
        candidates.append(base.parent / "zaraz.ico")
    return candidates


def _set_window_icon(app: tk.Tk) -> None:
    for icon in _icon_candidates():
        try:
            if icon.is_file():
                app.iconbitmap(str(icon))
                return
        except (OSError, tk.TclError):
            continue


def _enable_windows_dpi_awareness() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def run() -> None:
    _enable_windows_dpi_awareness()
    app = ZarazApp()
    _set_window_icon(app)
    app.mainloop()


if __name__ == "__main__":
    run()
