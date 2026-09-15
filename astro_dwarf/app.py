from __future__ import annotations

import ctypes
import os
import signal
import sys
import threading
import time
from pathlib import Path

from .qt_display import configure_qt_display

configure_qt_display()

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon, QPixmap
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterType

from .image_enhance import EnhanceImageProvider
from .qt_backend import AppBackend
from .runtime import (
    configure_qml_import_path,
    configure_quick_runtime,
    data_root,
    is_frozen,
    kill_pid_tree,
    package_root,
)
from .stream_preview import LiveFrameItem
from .version import __version__

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1 = 19
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> ctypes.c_int:
    value = str(hex_color).strip().removeprefix("#")
    if len(value) == 8:
        # Qt QML String(color) is typically #AARRGGBB.
        value = value[2:]
    elif len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return ctypes.c_int(red | (green << 8) | (blue << 16))


def _app_icon_candidates(
    resources: Path,
    *,
    frozen: bool | None = None,
    executable: Path | None = None,
    meipass: Path | None = None,
    source_root: Path | None = None,
) -> list[Path]:
    """Paths Qt can load as a window icon. The frozen EXE resource is not one of them."""
    frozen = is_frozen() if frozen is None else frozen
    source_root = source_root or Path(__file__).resolve().parent.parent
    meipass = meipass or Path(getattr(sys, "_MEIPASS", "") or ".")
    names = ("astro-dwarf.ico", "astro-dwarf.png")
    ordered: list[Path] = []
    for name in names:
        ordered.append(resources / "qml" / "assets" / name)
    for name in names:
        ordered.append(source_root / "packaging" / "icons" / name)
    if frozen:
        for name in names:
            ordered.append(meipass / name)
        if executable is None:
            executable = Path(sys.executable)
        ordered.append(executable)
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in ordered:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _icon_from_windows_executable(path: Path) -> QIcon:
    """Read the PE icon resource. QIcon(path_to_exe) cannot decode an .exe as an image."""
    if sys.platform != "win32" or not path.is_file():
        return QIcon()
    try:
        large = ctypes.c_void_p()
        small = ctypes.c_void_p()
        extracted = ctypes.windll.shell32.ExtractIconExW(
            str(path), 0, ctypes.byref(large), ctypes.byref(small), 1
        )
        if not extracted:
            return QIcon()
        icon = QIcon()
        destroy = ctypes.windll.user32.DestroyIcon
        try:
            for handle in (small, large):
                if not handle.value:
                    continue
                pixmap = QPixmap.fromHICON(int(handle.value))
                if not pixmap.isNull():
                    icon.addPixmap(pixmap)
        finally:
            if small.value:
                destroy(small.value)
            if large.value:
                destroy(large.value)
        return icon
    except Exception:
        return QIcon()


def _app_icon(resources: Path) -> QIcon:
    for candidate in _app_icon_candidates(resources):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() in {".exe", ".dll"}:
            icon = _icon_from_windows_executable(candidate)
        else:
            icon = QIcon(str(candidate))
        if not icon.isNull():
            return icon
    if is_frozen():
        return _icon_from_windows_executable(Path(sys.executable))
    return QIcon()


def _configure_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.astrodwarf.app")
    except Exception:
        pass


def _apply_native_window_icon(window, icon: QIcon) -> None:
    if icon.isNull():
        return
    if hasattr(window, "setIcon"):
        window.setIcon(icon)
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1
        small = icon.pixmap(user32.GetSystemMetrics(49), user32.GetSystemMetrics(50))
        big = icon.pixmap(user32.GetSystemMetrics(11), user32.GetSystemMetrics(12))
        if not small.isNull():
            user32.SendMessageW(hwnd, wm_seticon, icon_small, small.toHICON())
        if not big.isNull():
            user32.SendMessageW(hwnd, wm_seticon, icon_big, big.toHICON())
    except Exception:
        pass


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


def _initialize_webview() -> None:
    """Use the OS web view (WebView2 / WKWebView). Must run before QGuiApplication."""
    os.environ.setdefault("QTWEBVIEW_BACKEND", "native")
    os.environ.setdefault("QT_WEBVIEW_PLUGIN", "native")
    try:
        from PySide6.QtWebView import QtWebView
        QtWebView.initialize()
    except Exception:
        pass


def run() -> int:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    os.environ["QML_DISABLE_DISK_CACHE"] = "1"
    configure_quick_runtime()
    configure_qml_import_path()
    _configure_windows_app_id()
    _initialize_webview()
    application = QGuiApplication(sys.argv)
    application.setApplicationName("Astro Dwarf")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("Astro Dwarf")
    application.setDesktopFileName("astro-dwarf")

    resources = package_root()
    icon = _app_icon(resources)
    if not icon.isNull():
        application.setWindowIcon(icon)
    backend = AppBackend(data_root())
    qmlRegisterType(LiveFrameItem, "AstroDwarf", 1, 0, "LiveFrameItem")
    engine = QQmlApplicationEngine()
    engine.addImageProvider("enhance", EnhanceImageProvider())
    engine.warnings.connect(lambda warnings: [print(warning.toString(), file=sys.stderr) for warning in warnings])
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(resources / "qml" / "Main.qml")))

    if not engine.rootObjects():
        backend.shutdown()
        return 1
    window = engine.rootObjects()[0]
    _apply_native_window_icon(window, icon)
    persist_scene = getattr(window, "setPersistentSceneGraph", None)
    persist_graphics = getattr(window, "setPersistentGraphics", None)
    if callable(persist_scene):
        persist_scene(True)
    if callable(persist_graphics):
        persist_graphics(True)

    def _release_graphics() -> None:
        try:
            if callable(persist_scene):
                persist_scene(False)
            if callable(persist_graphics):
                persist_graphics(False)
        except RuntimeError:
            pass

    backend.bindPreviewWindow(window)

    def _apply_frame(caption: str, border: str, text: str) -> None:
        _apply_windows_frame(window, caption, border, text)
        # DWM caption coloring can recreate the native frame; re-apply the icon after.
        _apply_native_window_icon(window, icon)

    # Wire the hook after load: QML already queued the saved theme during onCompleted.
    backend.bindWindowFrame(_apply_frame)

    interrupt = threading.Event()
    quitting = {"done": False}

    def _mark_quit() -> None:
        quitting["done"] = True

    def _request_quit() -> None:
        if quitting["done"]:
            return
        quitting["done"] = True
        application.quit()

    def _watchdog() -> None:
        interrupt.wait()
        time.sleep(2.0)
        try:
            kill_pid_tree(os.getpid())
        except Exception:
            pass
        os._exit(1)

    def _handle_interrupt(*_args) -> None:
        interrupt.set()
        if threading.current_thread() is threading.main_thread():
            _request_quit()

    def _poll_interrupt() -> None:
        if interrupt.is_set():
            _request_quit()

    application.aboutToQuit.connect(_mark_quit)
    application.aboutToQuit.connect(_release_graphics)
    application.aboutToQuit.connect(backend.shutdown)
    threading.Thread(target=_watchdog, daemon=True, name="force-exit").start()

    # Let Ctrl-C in the launching console close the app cleanly. Qt's event loop
    # otherwise swallows SIGINT, so route it to a clean quit and run a lightweight
    # timer that keeps giving the Python interpreter a chance to service signals.
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    sigint_heartbeat = QTimer()
    sigint_heartbeat.setInterval(200)
    sigint_heartbeat.timeout.connect(_poll_interrupt)
    sigint_heartbeat.start()

    if sys.platform == "win32":
        # Only set a flag here. Calling Qt or ExitProcess from the console control
        # thread closes the window but deadlocks the process, which leaves the
        # launching terminal stuck after Ctrl-C.
        handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

        def _console_ctrl(ctrl_type: int) -> bool:
            if ctrl_type in (0, 1, 2):  # CTRL_C, CTRL_BREAK, CTRL_CLOSE
                interrupt.set()
                return True
            return False

        console_handler = handler_type(_console_ctrl)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(console_handler, True)
        application._console_ctrl_handler = console_handler

    test_exit_ms = int(os.getenv("ASTRO_DWARF_TEST_EXIT_MS", "0"))
    if test_exit_ms:
        QTimer.singleShot(test_exit_ms, application.quit)
    code = application.exec()
    try:
        backend.shutdown()
    except Exception:
        pass
    os._exit(int(code or 0))


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
