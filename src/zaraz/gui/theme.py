"""Colour palettes and ttk style setup for the light and dark themes."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from tkinter.font import nametofont


@dataclass(frozen=True)
class Theme:
    """A complete colour set for the interface."""

    name: str
    label: str
    bg: str
    surface: str
    surface_alt: str
    text: str
    muted: str
    border: str
    primary: str
    primary_text: str
    primary_hover: str
    log_bg: str
    log_fg: str
    selection: str


LIGHT = Theme(
    name="light",
    label="Light",
    bg="#faf9f4",
    surface="#ffffff",
    surface_alt="#f1eee7",
    text="#1d1a16",
    muted="#6b6459",
    border="#ddd7cb",
    primary="#b3492a",
    primary_text="#ffffff",
    primary_hover="#9a3d22",
    log_bg="#ffffff",
    log_fg="#3b352e",
    selection="#e8d4cb",
)

DARK = Theme(
    name="dark",
    label="Dark",
    bg="#14120f",
    surface="#1c1916",
    surface_alt="#262019",
    text="#f0ece4",
    muted="#a49a8b",
    border="#3a332b",
    primary="#e07a4f",
    primary_text="#1b1512",
    primary_hover="#f08d61",
    log_bg="#191613",
    log_fg="#ded7cc",
    selection="#5a3a2b",
)

PALETTES = {theme.name: theme for theme in (LIGHT, DARK)}


def configure_styles(root: tk.Misc, style: ttk.Style, theme: Theme) -> None:
    """Applies a palette to every ttk widget class used by the interface."""
    base_font = nametofont("TkDefaultFont")
    title_font = base_font.copy()
    title_font.configure(size=16, weight="bold")
    section_font = base_font.copy()
    section_font.configure(size=8, weight="bold")

    style.theme_use("clam")
    root.configure(background=theme.bg)

    # ttk combobox dropdown lists are plain Tk listboxes, themed via options.
    root.option_add("*TCombobox*Listbox.background", theme.surface)
    root.option_add("*TCombobox*Listbox.foreground", theme.text)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.primary)
    root.option_add("*TCombobox*Listbox.selectForeground", theme.primary_text)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    style.configure(
        ".",
        background=theme.bg,
        foreground=theme.text,
        fieldbackground=theme.surface,
        bordercolor=theme.border,
        lightcolor=theme.surface_alt,
        darkcolor=theme.bg,
        troughcolor=theme.surface_alt,
        focuscolor=theme.primary,
        selectbackground=theme.primary,
        selectforeground=theme.primary_text,
    )
    style.configure("TFrame", background=theme.bg)
    style.configure("TLabel", background=theme.bg, foreground=theme.text)
    style.configure("Title.TLabel", font=title_font, foreground=theme.text,
                    background=theme.bg)
    style.configure("Tagline.TLabel", foreground=theme.muted,
                    background=theme.bg)
    style.configure("Section.TLabel", font=section_font, foreground=theme.muted,
                    background=theme.bg)
    style.configure("Muted.TLabel", foreground=theme.muted, background=theme.bg)
    style.configure("Status.TLabel", foreground=theme.muted, background=theme.bg)

    style.configure("TButton", padding=(12, 6))
    style.configure(
        "Accent.TButton",
        background=theme.primary,
        foreground=theme.primary_text,
        bordercolor=theme.primary,
        lightcolor=theme.primary,
        darkcolor=theme.primary,
        focuscolor=theme.primary,
        padding=(16, 8),
        relief="flat",
    )
    style.map(
        "Accent.TButton",
        background=[("active", theme.primary_hover), ("disabled", theme.surface_alt)],
        foreground=[("disabled", theme.muted)],
        bordercolor=[("active", theme.primary_hover)],
    )
    style.configure(
        "Secondary.TButton",
        background=theme.surface,
        foreground=theme.text,
        bordercolor=theme.border,
        lightcolor=theme.surface,
        darkcolor=theme.surface,
        padding=(12, 6),
        relief="flat",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", theme.surface_alt), ("disabled", theme.bg)],
        foreground=[("disabled", theme.muted)],
    )
    style.configure(
        "Ghost.TButton",
        background=theme.bg,
        foreground=theme.muted,
        bordercolor=theme.bg,
        lightcolor=theme.bg,
        darkcolor=theme.bg,
        relief="flat",
        padding=(8, 4),
    )
    style.map(
        "Ghost.TButton",
        background=[("active", theme.surface_alt)],
        foreground=[("active", theme.text)],
    )

    style.configure(
        "TEntry",
        fieldbackground=theme.surface,
        foreground=theme.text,
        insertcolor=theme.text,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        padding=5,
    )
    style.map("TEntry", fieldbackground=[("disabled", theme.surface_alt)])

    style.configure(
        "TCombobox",
        fieldbackground=theme.surface,
        background=theme.surface,
        foreground=theme.text,
        arrowcolor=theme.muted,
        bordercolor=theme.border,
        lightcolor=theme.border,
        darkcolor=theme.border,
        padding=4,
        arrowsize=14,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", theme.surface), ("disabled", theme.surface_alt)],
        foreground=[("readonly", theme.text), ("disabled", theme.muted)],
        background=[("readonly", theme.surface)],
        arrowcolor=[("disabled", theme.muted)],
    )

    style.configure(
        "List.TCheckbutton",
        background=theme.surface,
        foreground=theme.text,
        indicatorbackground=theme.surface,
        indicatorforeground=theme.primary,
        upperbordercolor=theme.border,
        lowerbordercolor=theme.border,
    )
    style.map(
        "List.TCheckbutton",
        background=[("active", theme.surface)],
        foreground=[("disabled", theme.muted)],
        indicatorbackground=[("selected", theme.surface), ("disabled", theme.surface_alt)],
    )
    style.configure(
        "TCheckbutton",
        background=theme.bg,
        foreground=theme.text,
        indicatorbackground=theme.surface,
        indicatorforeground=theme.primary,
        upperbordercolor=theme.border,
        lowerbordercolor=theme.border,
    )
    style.map(
        "TCheckbutton",
        background=[("active", theme.bg)],
        foreground=[("disabled", theme.muted)],
        indicatorbackground=[("selected", theme.surface), ("disabled", theme.surface_alt)],
    )

    style.configure(
        "Horizontal.TProgressbar",
        background=theme.primary,
        troughcolor=theme.surface_alt,
        bordercolor=theme.surface_alt,
        lightcolor=theme.primary,
        darkcolor=theme.primary,
        thickness=8,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=theme.surface_alt,
        troughcolor=theme.bg,
        bordercolor=theme.bg,
        arrowcolor=theme.muted,
        lightcolor=theme.surface_alt,
        darkcolor=theme.surface_alt,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", theme.border)],
    )
    style.configure("TSeparator", background=theme.border)
