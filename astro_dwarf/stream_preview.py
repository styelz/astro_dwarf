from __future__ import annotations

import socket
import sys
import threading
from typing import Optional

from PySide6.QtCore import Property, QObject, QProcess, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QWindow
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from .runtime import PROCESS_CREATION_FLAGS, ffmpeg_mjpeg_command, ffmpeg_path, kill_pid_tree

_live_frames: LiveFrames | None = None


def port_is_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def stream_port(url: str) -> int:
    if url.startswith("http://"):
        return 8092
    return 554


def live_frames() -> LiveFrames | None:
    return _live_frames


def set_live_frames(hub: LiveFrames | None) -> None:
    global _live_frames
    _live_frames = hub


class LiveFrames(QObject):
    """Latest tele/wide frames, updated from the GUI thread.

    Live view used to go through QQuickImageProvider. requestImage() runs on
    Qt's render thread, which in Python has to take the GIL. After alt-tab the
    GUI thread waits for a scene-graph sync while the render thread waits for
    the GIL, and the window never comes back.
    """

    frameChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._images = {"tele": QImage(), "wide": QImage()}

    def update(self, key: str, image: QImage) -> None:
        if key not in self._images:
            return
        with self._lock:
            self._images[key] = image

    def notify(self, key: str = "*") -> None:
        self.frameChanged.emit(key)

    def peek(self, key: str) -> QImage:
        with self._lock:
            stored = self._images.get(key) or QImage()
            return QImage(stored) if not stored.isNull() else QImage()

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key in self._images:
                self._images[key] = QImage()
            else:
                self._images = {"tele": QImage(), "wide": QImage()}
        self.frameChanged.emit(key or "*")

    def frame_size(self, key: str = "wide") -> tuple[int, int]:
        """Native (width, height) of the latest decoded frame; (0, 0) when empty."""
        with self._lock:
            image = self._images.get(key) or QImage()
            if image.isNull():
                return (0, 0)
            return (image.width(), image.height())


class LiveFrameItem(QQuickPaintedItem):
    """Paints a live camera frame on the GUI thread (PreserveAspectFit)."""

    cameraChanged = Signal()
    playingChanged = Signal()
    paintedSizeChanged = Signal()

    def __init__(self, parent: Optional[QQuickItem] = None):
        super().__init__(parent)
        self.setRenderTarget(QQuickPaintedItem.RenderTarget.Image)
        self.setFillColor(QColor(0, 0, 0, 0))
        self.setOpaquePainting(False)
        self.setAntialiasing(False)
        self.setMipmap(False)
        self._camera = "tele"
        self._playing = False
        self._painted_w = 0.0
        self._painted_h = 0.0
        self._painted_x = 0.0
        self._painted_y = 0.0
        hub = live_frames()
        if hub is not None:
            hub.frameChanged.connect(self._on_hub_frame)

    def _camera_key(self) -> str:
        return self._camera

    def getCamera(self) -> str:
        return self._camera

    def setCamera(self, value: str) -> None:
        key = (value or "tele").strip().lower()
        if key not in ("tele", "wide"):
            key = "tele"
        if key == self._camera:
            return
        self._camera = key
        self.cameraChanged.emit()
        self._sync_painted_size()
        self.update()

    camera = Property(str, getCamera, setCamera, notify=cameraChanged)

    def getPlaying(self) -> bool:
        return self._playing

    def setPlaying(self, value: bool) -> None:
        playing = bool(value)
        if playing == self._playing:
            return
        self._playing = playing
        self.playingChanged.emit()
        self._sync_painted_size()
        self.update()

    playing = Property(bool, getPlaying, setPlaying, notify=playingChanged)

    def getPaintedWidth(self) -> float:
        return self._painted_w

    paintedWidth = Property(float, getPaintedWidth, notify=paintedSizeChanged)

    def getPaintedHeight(self) -> float:
        return self._painted_h

    paintedHeight = Property(float, getPaintedHeight, notify=paintedSizeChanged)

    def getPaintedX(self) -> float:
        return self._painted_x

    paintedX = Property(float, getPaintedX, notify=paintedSizeChanged)

    def getPaintedY(self) -> float:
        return self._painted_y

    paintedY = Property(float, getPaintedY, notify=paintedSizeChanged)

    @Slot(float, float, result="QVariant")
    def mapToFrame(self, px: float, py: float) -> dict:
        """Map item-local coords onto the frame drawn by paint().

        Uses the same fit rect the painter uses, so a tap and the pixel under
        it cannot drift apart. Returns nx/ny in 0-1 of the frame plus the
        numbers needed to audit the mapping.
        """
        hub = live_frames()
        image = hub.peek(self._camera) if hub is not None else QImage()
        rect = self._fit_rect(image)
        window = self.window()
        dpr = float(window.devicePixelRatio()) if window is not None else 1.0
        result = {
            "inside": False,
            "nx": 0.5,
            "ny": 0.5,
            "px": float(px),
            "py": float(py),
            "itemW": float(self.width()),
            "itemH": float(self.height()),
            "imageW": int(image.width()),
            "imageH": int(image.height()),
            "dpr": dpr,
            "rectX": 0.0,
            "rectY": 0.0,
            "rectW": 0.0,
            "rectH": 0.0,
        }
        if rect is None or rect.width() <= 0 or rect.height() <= 0:
            return result
        fx = float(px) - rect.x()
        fy = float(py) - rect.y()
        result.update(
            {
                "rectX": rect.x(),
                "rectY": rect.y(),
                "rectW": rect.width(),
                "rectH": rect.height(),
                "nx": fx / rect.width(),
                "ny": fy / rect.height(),
                "inside": 0 <= fx <= rect.width() and 0 <= fy <= rect.height(),
            }
        )
        return result

    def geometryChange(self, new_geometry, old_geometry) -> None:
        super().geometryChange(new_geometry, old_geometry)
        width = int(max(0.0, float(self.width())))
        height = int(max(0.0, float(self.height())))
        if width > 0 and height > 0:
            self.setContentsSize(QSize(width, height))
        self._sync_painted_size()

    @Slot(str)
    def _on_hub_frame(self, key: str) -> None:
        if not self._playing:
            return
        if key not in ("*", self._camera):
            return
        self._sync_painted_size()
        self.update()

    def _fit_rect(self, image: QImage) -> QRectF | None:
        if image.isNull() or self.width() <= 0 or self.height() <= 0:
            return None
        image_w = float(image.width())
        image_h = float(image.height())
        if image_w <= 0 or image_h <= 0:
            return None
        scale = min(self.width() / image_w, self.height() / image_h)
        draw_w = image_w * scale
        draw_h = image_h * scale
        return QRectF((self.width() - draw_w) / 2.0, (self.height() - draw_h) / 2.0, draw_w, draw_h)

    def _sync_painted_size(self) -> None:
        width = 0.0
        height = 0.0
        left = 0.0
        top = 0.0
        if self._playing:
            hub = live_frames()
            image = hub.peek(self._camera) if hub is not None else QImage()
            rect = self._fit_rect(image)
            if rect is not None:
                width = rect.width()
                height = rect.height()
                left = rect.x()
                top = rect.y()
        if (
            width == self._painted_w
            and height == self._painted_h
            and left == self._painted_x
            and top == self._painted_y
        ):
            return
        self._painted_w = width
        self._painted_h = height
        self._painted_x = left
        self._painted_y = top
        self.paintedSizeChanged.emit()

    def paint(self, painter: QPainter) -> None:
        if not self._playing:
            return
        hub = live_frames()
        if hub is None:
            return
        image = hub.peek(self._camera)
        rect = self._fit_rect(image)
        if rect is None:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(rect, image)


def preview_window_is_live(window) -> bool:
    """False when the window is hidden, minimized, or in the background."""
    app = QGuiApplication.instance()
    if app is not None:
        try:
            if app.applicationState() != Qt.ApplicationState.ApplicationActive:
                return False
        except RuntimeError:
            return False
    if window is None:
        return True
    try:
        if hasattr(window, "isExposed") and not window.isExposed():
            return False
        visibility = window.visibility()
        hidden = (QWindow.Visibility.Minimized, QWindow.Visibility.Hidden)
        return visibility not in hidden
    except RuntimeError:
        return False


class StreamPlayer(QObject):
    """Live preview via ffmpeg CLI so RTSP matches VLC and stays off Qt Multimedia."""

    frameReady = Signal(object)
    failed = Signal(str)
    statusChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._url = ""
        self._transports: list[str | None] = [None]
        self._transport_index = 0
        self._cancelled = False
        self._got_frame = False
        self._buffer = b""
        self._stderr = ""
        self._pid = 0
        self._pid_lock = threading.Lock()
        self._latest_image: QImage | None = None
        self._flush_scheduled = False
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)

    @Slot(str)
    def openStream(self, url: str) -> None:
        self._cancelled = False
        self._url = url
        if url.startswith("rtsp://"):
            # VLC typically uses TCP; UDP often never errors, it just stays blank.
            self._transports = ["tcp", "udp"]
        else:
            self._transports = [None]
        self._transport_index = 0
        self.statusChanged.emit("Opening camera stream…")
        self._start_process()

    @Slot()
    def closeStream(self) -> None:
        self._cancelled = True
        self._url = ""
        self._watchdog.stop()
        self._latest_image = None
        self._flush_scheduled = False
        self._teardown()

    def _start_process(self) -> None:
        self._teardown()
        if self._cancelled or not self._url:
            return
        transport = self._transports[self._transport_index]
        if transport == "tcp":
            self.statusChanged.emit("Opening camera stream over TCP…")
        elif transport == "udp":
            self.statusChanged.emit("TCP stream failed, retrying over UDP…")
        command = ffmpeg_mjpeg_command(self._url, transport)
        program, arguments = command[0], command[1:]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        if sys.platform == "win32" and hasattr(
            process, "setCreateProcessArgumentsModifier"
        ):
            process.setCreateProcessArgumentsModifier(
                lambda args: args.setCreateFlags(int(args.createFlags()) | PROCESS_CREATION_FLAGS)
            )
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_finished)
        self._process = process
        self._got_frame = False
        self._buffer = b""
        self._stderr = ""
        self._latest_image = None
        self._flush_scheduled = False
        process.start(program, arguments)
        if not process.waitForStarted(4000):
            if not self._cancelled:
                self._retry_or_fail(f"Could not start ffmpeg ({ffmpeg_path()})")
            return
        with self._pid_lock:
            self._pid = int(process.processId() or 0)
        self._watchdog.start(8000)

    def abort(self) -> None:
        """Kill ffmpeg from any thread without waiting on Qt."""
        with self._pid_lock:
            pid = self._pid
            self._pid = 0
        if pid:
            kill_pid_tree(pid)

    def _teardown(self) -> None:
        self._watchdog.stop()
        process = self._process
        self._process = None
        self._buffer = b""
        if process is None:
            return
        for signal_name in ("readyReadStandardOutput", "readyReadStandardError", "errorOccurred", "finished"):
            try:
                getattr(process, signal_name).disconnect()
            except (RuntimeError, TypeError):
                pass
        pid = int(process.processId() or 0)
        with self._pid_lock:
            self._pid = 0
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
        if pid:
            kill_pid_tree(pid)
        process.deleteLater()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        last = None
        while True:
            start = self._buffer.find(b"\xff\xd8")
            end = self._buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
            if start < 0 or end < 0:
                if start > 0:
                    self._buffer = self._buffer[start:]
                elif len(self._buffer) > 5_000_000:
                    self._buffer = self._buffer[-64_000:]
                break
            last = self._buffer[start : end + 2]
            self._buffer = self._buffer[end + 2 :]
        if last is None:
            return
        image = QImage.fromData(last, "JPG")
        if image.isNull():
            return
        self._queue_frame(image)

    def _queue_frame(self, image: QImage) -> None:
        self._latest_image = image
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        QTimer.singleShot(0, self._flush_frame)

    def _flush_frame(self) -> None:
        self._flush_scheduled = False
        image = self._latest_image
        self._latest_image = None
        if image is None or image.isNull() or self._cancelled:
            return
        self._got_frame = True
        self._watchdog.stop()
        self.frameReady.emit(image)

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        self._stderr = (self._stderr + text)[-4000:]

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if self._cancelled or self._process is None:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._retry_or_fail(f"Could not start ffmpeg ({ffmpeg_path()})")

    def _on_finished(self) -> None:
        if self._cancelled or self._process is None:
            return
        detail = self._stderr.strip().splitlines()[-1] if self._stderr.strip() else "ffmpeg exited"
        self._retry_or_fail(detail)

    def _on_watchdog(self) -> None:
        if self._cancelled or self._got_frame:
            return
        self._retry_or_fail("No frames received from the camera stream")

    def _retry_or_fail(self, message: str) -> None:
        if self._cancelled:
            return
        if self._got_frame:
            return
        if self._transport_index + 1 < len(self._transports):
            self._transport_index += 1
            self._start_process()
            return
        text = message or "Stream failed"
        self.failed.emit(text)
