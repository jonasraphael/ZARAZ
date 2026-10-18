"""Builds the Windows setup executable: releases/Zaraz-Setup-<version>.exe.

Usage (any platform):
    python installer/build_installer.py

Requires NSIS for the actual installer compilation:
    Windows        winget install NSIS   (or: choco install nsis)
    Debian/Ubuntu  sudo apt-get install nsis
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import build_payload  # noqa: E402


def find_makensis() -> str:
    for name in ("makensis", "makensis.exe"):
        found = shutil.which(name)
        if found:
            return found

    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "NSIS" / "makensis.exe"
        if candidate.is_file():
            return str(candidate)

    raise SystemExit(
        "makensis was not found. Install NSIS first "
        "(https://nsis.sourceforge.io) and run this script again."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-payload", action="store_true",
                        help="reuse the existing installer/payload directory")
    parser.add_argument("--payload-dir", type=Path, default=None,
                        help="payload directory to package")
    args = parser.parse_args()

    payload_dir = args.payload_dir or HERE / "payload"
    if not args.skip_payload:
        build_payload.build(payload_dir)

    version = build_payload.app_version()
    releases_dir = REPO_ROOT / "releases"
    releases_dir.mkdir(parents=True, exist_ok=True)

    makensis = find_makensis()
    command = [
        makensis,
        "-DPAYLOAD_DIR=payload",
        f"-DAPP_VERSION={version}",
        "zaraz.nsi",
    ]
    print("Running:", " ".join(command))
    subprocess.run(command, cwd=HERE, check=True)

    setup = releases_dir / f"Zaraz-Setup-{version}.exe"
    if not setup.is_file():
        raise SystemExit(f"Installer was not created: {setup}")
    print(f"Installer ready: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
