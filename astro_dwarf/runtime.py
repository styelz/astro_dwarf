from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
# Hidden child processes that must not receive the parent's Ctrl-C.
PROCESS_CREATION_FLAGS = (
    CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Return the directory containing packaged application resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def configure_quick_runtime() -> None:
    """Must run before QGuiApplication. Keeps live view from freezing on alt-tab.

    PySide paints live frames in Python. Qt's default threaded scene-graph
    loop can deadlock the GIL against the render thread when Windows restores
    an occluded window, which leaves the UI stuck until the process is killed.
    """
    from .qt_display import configure_qt_display

    configure_qt_display()
    os.environ.setdefault("QSG_RENDER_LOOP", "basic")


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
        return Path(__file__).resolve().parent.parent / "data"

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


def ffmpeg_mjpeg_command(url: str, rtsp_transport: str | None = None) -> list[str]:
    """Decode a live MJPEG/RTSP URL to a JPEG pipe using software ffmpeg.

    Hardware decode is disabled on purpose: NVIDIA Instant Replay / overlay
    hooks CUDA and D3D11 video paths, and Qt's media plugin was tripping them.
    Dwarf RTSP also behaves like VLC when forced to TCP first.
    """
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-an",
        "-fflags", "+nobuffer+discardcorrupt",
        "-flags", "low_delay",
        "-probesize", "512k",
        "-analyzeduration", "500000",
    ]
    if rtsp_transport:
        command.extend(["-rtsp_transport", rtsp_transport])
    command.extend(
        [
            "-i",
            url,
            "-vf",
            "fps=15",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "5",
            "-",
        ]
    )
    return command


def kill_pid_tree(pid: int) -> None:
    """Force-kill a process and its descendants. Safe if the pid is already gone."""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def worker_command() -> tuple[str, list[str]]:
    if is_frozen():
        suffix = ".exe" if sys.platform == "win32" else ""
        helper = Path(sys.executable).resolve().parent / f"AstroDwarfWorker{suffix}"
        if helper.is_file():
            return str(helper), []
        return sys.executable, ["--worker"]
    return sys.executable, ["-u", "-m", "astro_dwarf.device_worker"]


def prepare_worker_environment(environment) -> None:
    """Make a second PyInstaller process start as a fresh application."""
    if is_frozen():
        environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
        environment.insert("ASTRO_DWARF_WORKER", "1")
