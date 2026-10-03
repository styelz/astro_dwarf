"""Splash screen shown while Astro Dwarf's Qt/QML engine loads.

This module is imported *before* :mod:`astro_dwarf.app`, so it must stay free
of the QML/backend/cv2/numpy import chain - that is what lets the splash
process start and paint almost instantly. The splash launches the real app
as a child process (passing ``--child``) and hides itself the moment that
child reports its first rendered frame over stdout, instead of waiting a
fixed delay. An AppImage keeps this process alive until that child exits:
the runtime unmounts the squashfs when the splash process exits, and the
real app then faults with SIGBUS.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

READY_MARKER = "ASTRO_DWARF_READY"
_FALLBACK_MS = 25_000

# ASTRO theme colours from Theme.qml (hue 0.506, brightness -0.12), so the
# splash matches the default HUD without pulling in the QML engine.
_SURFACE = "#0B171F"
_OUTLINE_STRONG = "#315A73"
_ACCENT = "#8C905A"
_TEXT_SECONDARY = "#74A2B2"
_TITLE = "#8C905A"


def _appimage_runtime_owns_mount() -> bool:
    """True when exiting this process makes the AppImage runtime drop the squashfs.

    type2-runtime lazy-unmounts as soon as its direct child (this splash)
    exits. The real app is started in a new session, so it keeps running
    with libraries still mapped from that mount. The next page fault is
    SIGBUS (BUS_ADRERR), which is the AppImage crash. A normal install
    has the same files on disk and can let the splash exit immediately.
    """
    if os.environ.get("APPIMAGE") or os.environ.get("APPDIR"):
        return True
    return "/.mount_" in os.path.realpath(sys.executable).replace("\\", "/")


def _wait_for_detached_child(child: subprocess.Popen) -> int:
    """Block until the real app exits, and pass terminal signals through to it."""
    forwarded = [
        signum
        for name in ("SIGTERM", "SIGINT", "SIGHUP")
        if (signum := getattr(signal, name, None)) is not None
    ]
    previous = {signum: signal.getsignal(signum) for signum in forwarded}

    def _forward(signum, _frame) -> None:
        if child.poll() is None:
            child.send_signal(signum)

    for signum in forwarded:
        signal.signal(signum, _forward)
    try:
        while True:
            try:
                return child.wait()
            except InterruptedError:
                continue
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _should_skip_splash() -> bool:
    """Modes that must stay a single, direct process: the respawned child,
    the device-worker helper, and automated test/harness launches."""
    if "--child" in sys.argv:
        return True
    if "--worker" in sys.argv or os.environ.get("ASTRO_DWARF_WORKER") == "1":
        return True
    if os.environ.get("ASTRO_DWARF_NO_SPLASH") == "1":
        return True
    if os.environ.get("ASTRO_DWARF_TEST_HARNESS") == "1":
        return True
    if os.environ.get("ASTRO_DWARF_TEST_EXIT_MS"):
        return True
    return False


def launch(script_path: str | None = None) -> int:
    """Entry point shared by the dev script, the console-script, and the frozen exe."""
    if _should_skip_splash():
        if "--child" in sys.argv:
            sys.argv.remove("--child")
        from astro_dwarf.app import main

        return main() or 0
    return _run_with_splash(script_path)


def _launch_command(script_path: str | None) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--child", *sys.argv[1:]]
    script = script_path or sys.argv[0]
    return [sys.executable, os.path.abspath(script), "--child", *sys.argv[1:]]


def _spawn_child(command: list[str]):
    """Start the real app detached from the splash's job object/session.

    The splash quits as soon as it sees the ready marker, well before the
    real app closes. If the child stayed tied to the splash's process group
    or Windows job object, a terminal/IDE that kills that tree on "command
    finished" would take the still-running app down with it.
    """
    kwargs: dict = {"stdout": subprocess.PIPE, "text": True, "bufsize": 1}
    if sys.platform == "win32":
        create_new_group = subprocess.CREATE_NEW_PROCESS_GROUP
        breakaway = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        try:
            return subprocess.Popen(command, creationflags=create_new_group | breakaway, **kwargs)
        except OSError:
            pass
        try:
            return subprocess.Popen(command, creationflags=create_new_group, **kwargs)
        except OSError as exc:
            print(f"Failed to launch Astro Dwarf: {exc}", file=sys.stderr)
            return None
    try:
        return subprocess.Popen(command, start_new_session=True, **kwargs)
    except OSError as exc:
        print(f"Failed to launch Astro Dwarf: {exc}", file=sys.stderr)
        return None


def _logo_path():
    from .runtime import package_root

    candidate = package_root() / "qml" / "assets" / "astro-dwarf.png"
    return candidate if candidate.is_file() else None


def _load_logo_pixmap(path, size: int = 48):
    """Load the app icon with its square backdrop keyed out to transparent.

    The shipped icon fills its canvas with a solid #05080f square behind the
    circular badge (see packaging/build_icons.py). QPixmap.setMask() is
    undefined on images that already carry an alpha channel, so strip that
    exact background color pixel-by-pixel on the *unscaled* image first
    (its edges are hard, unblended) and only then smooth-scale the result.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QImage, QPixmap

    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    background = QColor("#05080f").rgb() & 0x00FFFFFF
    for y in range(image.height()):
        for x in range(image.width()):
            if (image.pixel(x, y) & 0x00FFFFFF) == background:
                image.setPixel(x, y, 0)
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    return QPixmap.fromImage(image).scaled(
        size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def _chamfer_path(rect, cut: float):
    """Octagon path with straight corner cuts, matching HudPanel's frame shape."""
    from PySide6.QtGui import QPainterPath

    x0, y0 = rect.left(), rect.top()
    x1, y1 = rect.right(), rect.bottom()
    path = QPainterPath()
    path.moveTo(x0 + cut, y0)
    path.lineTo(x1 - cut, y0)
    path.lineTo(x1, y0 + cut)
    path.lineTo(x1, y1 - cut)
    path.lineTo(x1 - cut, y1)
    path.lineTo(x0 + cut, y1)
    path.lineTo(x0, y1 - cut)
    path.lineTo(x0, y0 + cut)
    path.closeSubpath()
    return path


class _HudFrame:
    """Mixin providing the app's chamfered-card paint: surface fill, a soft
    top vignette, and an outlineStrong stroke (see HudPanel/window frame)."""

    _CUT = 12.0

    def paintEvent(self, event):  # noqa: N802 - Qt override
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inset = 0.75
        rect = QRectF(inset, inset, self.width() - 2 * inset, self.height() - 2 * inset)
        path = _chamfer_path(rect, self._CUT)

        painter.fillPath(path, QColor(_SURFACE))

        painter.save()
        painter.setClipPath(path)
        vignette = QLinearGradient(0, 0, 0, rect.height() * 0.4)
        top = QColor(_ACCENT)
        top.setAlphaF(0.08)
        bottom = QColor(_ACCENT)
        bottom.setAlphaF(0.0)
        vignette.setColorAt(0.0, top)
        vignette.setColorAt(1.0, bottom)
        painter.fillRect(QRectF(0, 0, rect.width(), rect.height() * 0.4), vignette)
        painter.restore()

        pen = QPen(QColor(_OUTLINE_STRONG))
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.drawPath(path)


class _AccentDivider:
    """Mixin painting the title bar's bottom-edge accent gradient line."""

    def paintEvent(self, event):  # noqa: N802 - Qt override
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter

        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        accent = QColor(_ACCENT)
        accent.setAlphaF(0.7)
        transparent = QColor(_ACCENT)
        transparent.setAlphaF(0.0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.15, accent)
        gradient.setColorAt(0.85, accent)
        gradient.setColorAt(1.0, transparent)
        painter.fillRect(QRectF(0, 0, self.width(), self.height()), gradient)


def _make_pulse_dot(parent, color: str, size: int = 10):
    """A small LED dot with a pulsing outer ring, matching components/LedDot.qml."""
    from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, Qt, Property
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QWidget

    class _PulseDot(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self._color = QColor(color)
            self._glow = 0.0
            self.setFixedSize(size, size)

        def _get_glow(self):
            return self._glow

        def _set_glow(self, value):
            self._glow = value
            self.update()

        glow = Property(float, _get_glow, _set_glow)

        def paintEvent(self, event):  # noqa: N802 - Qt override
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            center = QPointF(self.width() / 2, self.height() / 2)
            core_radius = size * 0.28
            ring_radius = core_radius + self._glow * (size * 0.42)
            ring_color = QColor(self._color)
            ring_color.setAlphaF(max(0.0, 0.6 * (1 - self._glow)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(ring_color)
            painter.drawEllipse(center, ring_radius, ring_radius)
            painter.setBrush(self._color)
            painter.drawEllipse(center, core_radius, core_radius)

    dot = _PulseDot(parent)
    anim = QPropertyAnimation(dot, b"glow", dot)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(1200)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    anim.setLoopCount(-1)
    anim.start()
    dot._anim = anim  # keep alive
    return dot


def _make_progress_bar(parent):
    """Indeterminate Qt progress bar: faint track, sweeping accent gradient."""
    from PySide6.QtWidgets import QProgressBar

    progress = QProgressBar(parent)
    progress.setRange(0, 0)
    progress.setTextVisible(False)
    progress.setFixedHeight(6)
    progress.setStyleSheet(
        "QProgressBar {"
        "  background-color: rgba(255, 255, 255, 18);"
        f"  border: 1px solid {_OUTLINE_STRONG};"
        "  border-radius: 3px;"
        "}"
        "QProgressBar::chunk {"
        "  border-radius: 3px;"
        "  background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f"    stop:0 rgba(140, 144, 90, 0), stop:0.5 {_ACCENT}, stop:1 rgba(140, 144, 90, 0));"
        "}"
    )
    return progress


def _build_splash():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    width, height = 380, 150
    splash = QWidget(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    splash.resize(width, height)

    frame = type("_SplashFrame", (_HudFrame, QWidget), {})(splash)
    frame.setGeometry(0, 0, width, height)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 16)
    layout.setSpacing(12)

    # Header: logo + wordmark, styled like Main.qml's title bar brand block.
    header = QHBoxLayout()
    header.setSpacing(12)
    logo_path = _logo_path()
    if logo_path is not None:
        logo_pixmap = _load_logo_pixmap(logo_path, size=40)
        if logo_pixmap is not None:
            logo = QLabel(frame)
            logo.setPixmap(logo_pixmap)
            logo.setStyleSheet("background: transparent; border: none;")
            header.addWidget(logo)

    from .version import __version__

    text_col = QVBoxLayout()
    text_col.setSpacing(2)

    title = QLabel("ASTRO DWARF", frame)
    title_font = QFont("Segoe UI", 15, QFont.Weight.Bold)
    title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
    title.setFont(title_font)
    title.setStyleSheet(f"color: {_TITLE}; background: transparent; border: none;")
    text_col.addWidget(title)

    subtitle = QLabel(f"OBSERVATORY COMMAND  ·  v{__version__}", frame)
    subtitle_font = QFont("Segoe UI", 9)
    subtitle_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1)
    subtitle.setFont(subtitle_font)
    subtitle.setStyleSheet(f"color: {_TEXT_SECONDARY}; background: transparent; border: none;")
    text_col.addWidget(subtitle)

    header.addLayout(text_col)
    header.addStretch(1)
    layout.addLayout(header)

    divider = type("_SplashDivider", (_AccentDivider, QWidget), {})(frame)
    divider.setFixedHeight(2)
    layout.addWidget(divider)

    layout.addStretch(1)

    # Loading readout: pulsing status LED + label, then the sweeping bar.
    status_row = QHBoxLayout()
    status_row.setSpacing(8)
    status_row.addWidget(_make_pulse_dot(frame, _ACCENT))

    loading_label = QLabel("LOADING", frame)
    loading_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
    loading_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
    loading_label.setFont(loading_font)
    loading_label.setStyleSheet(f"color: {_ACCENT}; background: transparent; border: none;")
    status_row.addWidget(loading_label)
    status_row.addStretch(1)
    layout.addLayout(status_row)

    layout.addWidget(_make_progress_bar(frame))

    screen = QApplication.primaryScreen()
    if screen is not None:
        geo = screen.availableGeometry()
        splash.move(
            geo.x() + (geo.width() - splash.width()) // 2,
            geo.y() + (geo.height() - splash.height()) // 2,
        )

    splash.show()
    return splash


def _run_with_splash(script_path: str | None) -> int:
    from .qt_display import configure_qt_display

    configure_qt_display()

    from PySide6.QtCore import QObject, QTimer, Signal
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    splash = _build_splash()

    child = _spawn_child(_launch_command(script_path))
    if child is None:
        splash.close()
        return 1

    # QTimer.singleShot(0, callable) posted from a plain Python thread has no
    # event loop to deliver on and may never fire. A signal emitted from the
    # reader thread crosses into the GUI thread via a real queued connection.
    class _Done(QObject):
        done = Signal()

    signal = _Done()

    def _dismiss() -> None:
        splash.hide()
        splash.close()
        app.processEvents()
        app.quit()

    signal.done.connect(_dismiss)

    def _reader() -> None:
        stdout = child.stdout
        if stdout is not None:
            for line in stdout:
                if READY_MARKER in line:
                    break
            stdout.close()
        signal.done.emit()

    threading.Thread(target=_reader, daemon=True, name="splash-reader").start()
    QTimer.singleShot(_FALLBACK_MS, _dismiss)

    app.exec()
    splash.hide()
    splash.close()
    if _appimage_runtime_owns_mount():
        return _wait_for_detached_child(child)
    exit_code = child.poll()
    return exit_code if exit_code is not None else 0
