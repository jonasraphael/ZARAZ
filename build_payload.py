"""Assembles the Windows payload that the NSIS installer ships.

The payload contains a self-contained CPython runtime for Windows (including
Tkinter), the psutil dependency, the Zaraz application source and a small
launcher. Everything is downloaded and assembled, so the setup executable can
be built on Windows, Linux or macOS without cross-compiling Python.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PYTHON_VERSION = "3.12.15"
PYTHON_RELEASE = "20261013"
PYTHON_ASSET = (
    f"cpython-{PYTHON_VERSION}+{PYTHON_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
)
PYTHON_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_RELEASE}/{PYTHON_ASSET}".replace("+", "%2B")
)
PSUTIL_JSON_URL = "https://pypi.org/pypi/psutil/json"

LAUNCHER = '''"""Starts the ZARAZ graphical interface from the installed application folder."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SOURCE_DIR = APP_DIR / "src"

if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

# Keep the working directory inside the installation folder.
os.chdir(APP_DIR)

from zaraz.gui.window import run  # noqa: E402


if __name__ == "__main__":
    run()
'''

REPO_ROOT = Path(__file__).resolve().parents[1]


def _download(url: str, target: Path, label: str) -> Path:
    if target.is_file() and target.stat().st_size > 0:
        print(f"Using cached {label}: {target}")
        return target
    print(f"Downloading {label} …")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "zaraz-setup"})
    with urllib.request.urlopen(request, timeout=180) as response:
        with open(target, "wb") as fh:
            shutil.copyfileobj(response, fh)
    return target


def _fetch_windows_runtime(cache_dir: Path, runtime_dir: Path) -> None:
    archive = _download(PYTHON_URL, cache_dir / "python-win.tar.gz", "Python runtime")
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        with tarfile.open(archive, "r:gz") as tar:
            try:
                tar.extractall(temp_dir, filter="data")
            except TypeError:  # Python < 3.12 has no filter argument
                tar.extractall(temp_dir)

        extracted = temp_dir / "python"
        if not extracted.is_dir():
            raise RuntimeError("Unexpected Python archive layout")

        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        shutil.move(str(extracted), str(runtime_dir))


def _fetch_psutil(cache_dir: Path, runtime_dir: Path) -> None:
    request = urllib.request.Request(
        PSUTIL_JSON_URL, headers={"User-Agent": "zaraz-setup"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.load(response)

    wheel_url = None
    wheel_name = None
    candidates = []
    for entry in data.get("urls", []):
        name = entry.get("filename", "")
        if not name.endswith("win_amd64.whl"):
            continue
        candidates.append((name, entry["url"]))
        if "abi3" in name or "cp312" in name or "cp39" in name:
            wheel_url = entry["url"]
            wheel_name = name
            break
    if wheel_url is None and candidates:
        wheel_name, wheel_url = candidates[0]
    if wheel_url is None:
        raise RuntimeError("No psutil wheel for Windows found on PyPI")

    wheel = _download(wheel_url, cache_dir / wheel_name, "psutil wheel")
    site_packages = runtime_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(site_packages)


def _copy_application(payload_dir: Path) -> None:
    app_dir = payload_dir / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    (app_dir / "src").mkdir(parents=True, exist_ok=True)

    shutil.copytree(
        REPO_ROOT / "src" / "zaraz",
        app_dir / "src" / "zaraz",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (app_dir / "Zaraz.pyw").write_text(LAUNCHER, encoding="utf-8")

    icon = REPO_ROOT / "installer" / "zaraz.ico"
    if not icon.is_file():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import make_icon

        make_icon.main()
    shutil.copy2(icon, payload_dir / "Zaraz.ico")


def _trim_runtime(runtime_dir: Path) -> None:
    """Removes runtime parts the application never uses (smaller installer)."""
    for pdb in runtime_dir.rglob("*.pdb"):
        try:
            pdb.unlink()
        except OSError:
            pass

    for relative in (
        "Scripts",
        "include",
        "libs",
        "Lib/test",
        "Lib/idlelib",
        "Lib/turtledemo",
        "Lib/lib2to3",
        "Lib/ensurepip",
        "Lib/venv",
        "Lib/site-packages/pip",
        "Lib/site-packages/setuptools",
    ):
        shutil.rmtree(runtime_dir / relative, ignore_errors=True)
    for stale in runtime_dir.glob("Lib/site-packages/pip-*.dist-info"):
        shutil.rmtree(stale, ignore_errors=True)
    for stale in runtime_dir.glob("Lib/site-packages/setuptools-*.dist-info"):
        shutil.rmtree(stale, ignore_errors=True)


def _patch_embed_path(runtime_dir: Path) -> None:
    """Makes sure site-packages is importable if a ._pth file is present."""
    for pth in runtime_dir.glob("python*._pth"):
        content = pth.read_text(encoding="utf-8")
        if "Lib\\site-packages" not in content:
            pth.write_text(content + "\nLib\\site-packages\n", encoding="utf-8")


def app_version() -> str:
    """Reads __version__ from the package without importing it."""
    source = (REPO_ROOT / "src" / "zaraz" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', source)
    return match.group(1) if match else "0.0.0"


def build(payload_dir: Path | None = None, cache_dir: Path | None = None) -> Path:
    """Assembles the complete payload and returns its directory."""
    payload_dir = payload_dir or REPO_ROOT / "installer" / "payload"
    cache_dir = cache_dir or REPO_ROOT / "installer" / ".cache"
    payload_dir.mkdir(parents=True, exist_ok=True)

    runtime_dir = payload_dir / "runtime"
    _fetch_windows_runtime(cache_dir, runtime_dir)
    _fetch_psutil(cache_dir, runtime_dir)
    _trim_runtime(runtime_dir)
    _patch_embed_path(runtime_dir)
    _copy_application(payload_dir)
    (payload_dir / "VERSION").write_text(app_version() + "\n", encoding="utf-8")

    total = sum(f.stat().st_size for f in payload_dir.rglob("*") if f.is_file())
    print(f"Payload ready: {payload_dir} ({total / 1024 / 1024:.1f} MiB)")
    return payload_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None,
                        help="payload directory (default: installer/payload)")
    parser.add_argument("--cache", type=Path, default=None,
                        help="download cache (default: installer/.cache)")
    args = parser.parse_args()
    build(args.out, args.cache)


if __name__ == "__main__":
    main()
