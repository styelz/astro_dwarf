from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Return the directory containing packaged application resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def configure_qml_import_path() -> None:
    """Register both Windows and POSIX PySide6 QML layouts in frozen builds."""
    if not is_frozen():
        return
    meipass = Path(getattr(sys, "_MEIPASS"))
    candidates = [
        meipass / "PySide6" / "qml",
        meipass / "PySide6" / "Qt" / "qml",
    ]
    existing = [str(path) for path in candidates if path.is_dir()]
    if not existing:
        return
    current = [part for part in os.environ.get("QML2_IMPORT_PATH", "").split(os.pathsep) if part]
    os.environ["QML2_IMPORT_PATH"] = os.pathsep.join(
        existing + [part for part in current if part not in existing]
    )


def data_root() -> Path:
    """Return a writable data directory for the current execution mode."""
    if not is_frozen():
        return package_root() / "data"

    location = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if not location:
        location = str(Path.home() / ".astro-dwarf")
    path = Path(location)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ffmpeg_path() -> str:
    """Prefer the ffmpeg shipped with an installer, then use PATH."""
    executable = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    if is_frozen():
        candidates = [
            Path(getattr(sys, "_MEIPASS")) / executable,
            Path(sys.executable).resolve().parent / executable,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which(executable) or executable


def worker_command() -> tuple[str, list[str]]:
    if is_frozen():
        suffix = ".exe" if sys.platform == "win32" else ""
        helper = Path(sys.executable).resolve().parent / f"AstroDwarfWorker{suffix}"
        if helper.is_file():
            return str(helper), []
        return sys.executable, ["--worker"]
    return sys.executable, ["-u", "-m", "device_worker"]


def prepare_worker_environment(environment) -> None:
    """Make a second PyInstaller process start as a fresh application."""
    if is_frozen():
        environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
        environment.insert("ASTRO_DWARF_WORKER", "1")
