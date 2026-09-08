from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

from .qt_backend import AppBackend
from .runtime import configure_qml_import_path, data_root, is_frozen, package_root
from .version import __version__

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> ctypes.c_int:
    value = hex_color.removeprefix("#")
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return ctypes.c_int(red | (green << 8) | (blue << 16))


def _app_icon(resources: Path) -> QIcon:
    candidates = [
        resources / "qml" / "assets" / "astro-dwarf.png",
        Path(__file__).resolve().parent.parent / "packaging" / "icons" / "astro-dwarf.ico",
        Path(__file__).resolve().parent.parent / "packaging" / "icons" / "astro-dwarf.png",
    ]
    if is_frozen():
        candidates.extend(
            [
                Path(sys.executable),
                Path(getattr(sys, "_MEIPASS", "")) / "astro-dwarf.png",
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    return QIcon()


def _apply_windows_frame(window, caption_hex: str = "#0B1520", border_hex: str = "#3F6E82", text_hex: str = "#4DE8FF") -> None:
    """Color the native caption to match the HUD chrome. QML re-calls this when the theme hue changes."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark))
        caption = _colorref(caption_hex)
        border = _colorref(border_hex)
        text = _colorref(text_hex)
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_CAPTION_COLOR, ctypes.byref(caption), ctypes.sizeof(caption))
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_BORDER_COLOR, ctypes.byref(border), ctypes.sizeof(border))
        dwm.DwmSetWindowAttribute(hwnd, _DWMWA_TEXT_COLOR, ctypes.byref(text), ctypes.sizeof(text))
    except Exception:
        pass


def run() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    configure_qml_import_path()
    application = QGuiApplication(sys.argv)
    application.setApplicationName("Astro Dwarf")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("Astro Dwarf")

    resources = package_root()
    icon = _app_icon(resources)
    if not icon.isNull():
        application.setWindowIcon(icon)
    backend = AppBackend(data_root())
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warnings: [print(warning.toString(), file=sys.stderr) for warning in warnings])
    engine.rootContext().setContextProperty("backend", backend)
    engine.addImageProvider("live", backend.live_images)
    engine.load(QUrl.fromLocalFile(str(resources / "qml" / "Main.qml")))

    if not engine.rootObjects():
        backend.shutdown()
        return 1
    window = engine.rootObjects()[0]
    if not icon.isNull() and hasattr(window, "setIcon"):
        window.setIcon(icon)
    _apply_windows_frame(window)
    backend.window_frame_hook = lambda caption, border, text: _apply_windows_frame(window, caption, border, text)
    application.aboutToQuit.connect(backend.shutdown)
    test_exit_ms = int(os.getenv("ASTRO_DWARF_TEST_EXIT_MS", "0"))
    if test_exit_ms:
        QTimer.singleShot(test_exit_ms, application.quit)
    return application.exec()


def _ensure_standard_streams() -> None:
    # PyInstaller's Windows GUI bootloader intentionally leaves these unset.
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int | None:
    _ensure_standard_streams()
    if "--worker" in sys.argv or os.getenv("ASTRO_DWARF_WORKER") == "1":
        from .device_worker import main as worker_main

        worker_main()
        return None
    return run()
