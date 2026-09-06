from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from qt_backend import AppBackend
from runtime import configure_qml_import_path, data_root, package_root
from version import __version__


def _sync_work_area(window) -> None:
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    window.setProperty("workX", int(geo.x()))
    window.setProperty("workY", int(geo.y()))
    window.setProperty("workW", int(geo.width()))
    window.setProperty("workH", int(geo.height()))


def _apply_windows_frame(window) -> None:
    """Match leftover DWM caption/border pixels to the dark HUD chrome."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        for attribute in (20, 19):
            dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark))
        caption = ctypes.c_int(0x000F0805)
        border = ctypes.c_int(0x00826E3F)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption))
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), ctypes.sizeof(border))
    except Exception:
        pass


def run() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    configure_qml_import_path()
    application = QGuiApplication(sys.argv)
    application.setApplicationName("Astro Dwarf")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("Astro Dwarf")

    resources = package_root()
    backend = AppBackend(data_root())
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda warnings: [print(warning.toString(), file=sys.stderr) for warning in warnings])
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(resources / "qml" / "Main.qml")))

    if not engine.rootObjects():
        backend.shutdown()
        return 1
    window = engine.rootObjects()[0]
    _sync_work_area(window)
    if hasattr(window, "screenChanged"):
        window.screenChanged.connect(lambda *_args: _sync_work_area(window))
    _apply_windows_frame(window)
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
        from device_worker import main as worker_main

        worker_main()
        return None
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
