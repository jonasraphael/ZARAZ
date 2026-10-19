ZARAZ - "Zero-hassle Archive & Restore Application Zone"

Your saves, instantly there.

Disclaimer:
This tool is not affiliated with or endorsed by Nintendo


About:
Your go-to tool. Plug in your SD card, select your save, done. From Game Boy to Switch – Zaraz handles save files across Nintendo's entire legacy.

How-to-use:
Launch Zaraz, plug in your SD Card, select your save and your destination.

## Features

- Detects removable drives on Windows, macOS and Linux (through psutil)
- Finds `.sav`, `.srm` and context-specific saves (Checkpoint, JKSV, EverDrive 64)
- Copies with SHA-256 verification, so a broken backup is reported immediately
- Collision handling: rename, overwrite or skip
- Light and dark theme, switchable inside the window and remembered for the next start
- Command line interface for scripts and headless use
- Optional uninstall button inside the app, using the uninstall files from the setup

## Installation (Windows)

1. Download `Zaraz-Setup-<version>.exe` from the
   [releases page](https://github.com/jonasraphael/ZARAZ/releases) or from the
   `releases` folder of the repository.
2. Run the setup. Windows asks for administrator permission because ZARAZ is
   installed for all users into `C:\Program Files\ZARAZ`.
3. Confirm the permission checkbox, then choose:
   - **Create a desktop shortcut**
   - **Create uninstall files (recommended)** – adds the entry in Windows
     Settings and the *Uninstall* button inside ZARAZ

Installing from source instead:

```bash
`# Run these commands from the project folder containing pyproject.toml`
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m zaraz.gui
```

## Command line

```bash
zaraz --list                 # only list detected save files
zaraz --all                  # transfer everything it finds
zaraz --drive E:\ --dest D:\Backups
zaraz --strategy rename      # rename | overwrite | skip
```

## Development

```bash
pip install ".[dev]"
pytest
python -m zaraz.gui
```

Building the Windows setup (needs [NSIS](https://nsis.sourceforge.io)):

```bash
python installer/build_installer.py   # writes releases/Zaraz-Setup-<version>.exe
```

The build downloads a self-contained Windows Python runtime (including
Tkinter), adds the application source and packages everything with NSIS. The
GitHub Actions workflow does the same and uploads the setup to the release
whenever a `v*` tag is pushed.
