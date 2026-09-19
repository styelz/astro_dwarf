from __future__ import annotations

import http.client
import socket
import sys
import threading
import time
from typing import Optional
from urllib.parse import urlparse

from PySide6.QtCore import Property, QBuffer, QIODevice, QObject, QProcess, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QWindow
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from .runtime import PROCESS_CREATION_FLAGS, ffmpeg_mjpeg_command, ffmpeg_path, kill_pid_tree
from .services import mosaic_sheet_column, mosaic_sheet_row

_live_frames: LiveFrames | None = None
_mosaic_frames: MosaicFrames | None = None


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


def mosaic_frames() -> MosaicFrames | None:
    return _mosaic_frames


def set_mosaic_frames(hub: MosaicFrames | None) -> None:
    global _mosaic_frames
    _mosaic_frames = hub


def live_frame_data_url(image: QImage, max_edge: int = 480, quality: int = 55) -> str:
    """JPEG data URL for injecting a live frame into Stellarium Web's FOV overlay."""
    if image is None or image.isNull():
        return ""
    frame = image
    widest = max(int(image.width()), int(image.height()))
    if widest > max_edge:
        frame = image.scaled(
            max_edge,
            max_edge,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not frame.save(buffer, "JPEG", int(quality)):
        return ""
    encoded = bytes(buffer.data().toBase64()).decode("ascii")
    if not encoded:
        return ""
    return f"data:image/jpeg;base64,{encoded}"


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
            return self._images.get(key) or QImage()

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
    imageSizeChanged = Signal()

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
        self._image_w = 0.0
        self._image_h = 0.0
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

    def getImageWidth(self) -> float:
        return self._image_w

    imageWidth = Property(float, getImageWidth, notify=imageSizeChanged)

    def getImageHeight(self) -> float:
        return self._image_h

    imageHeight = Property(float, getImageHeight, notify=imageSizeChanged)

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
        image_w = 0.0
        image_h = 0.0
        if self._playing:
            hub = live_frames()
            image = hub.peek(self._camera) if hub is not None else QImage()
            if not image.isNull():
                image_w = float(image.width())
                image_h = float(image.height())
            rect = self._fit_rect(image)
            if rect is not None:
                width = rect.width()
                height = rect.height()
                left = rect.x()
                top = rect.y()
        if image_w != self._image_w or image_h != self._image_h:
            self._image_w = image_w
            self._image_h = image_h
            self.imageSizeChanged.emit()
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


class MosaicFrames(QObject):
    """Completed mosaic-pane stills plus the current-pane index."""

    changed = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._images: dict[int, QImage] = {}
        self._frozen: set[int] = set()
        self._columns = 1
        self._rows = 1
        self._current = 0
        self._active = False
        self._group = ""

    def snapshot(self) -> tuple[bool, int, int, int, dict[int, QImage]]:
        with self._lock:
            return (
                self._active,
                self._columns,
                self._rows,
                self._current,
                dict(self._images),
            )

    def group(self) -> str:
        with self._lock:
            return self._group

    def set_layout(
        self,
        columns: int,
        rows: int,
        current: int,
        active: bool,
        group: str = "",
    ) -> None:
        columns = max(1, int(columns or 1))
        rows = max(1, int(rows or 1))
        current = max(0, int(current or 0))
        active = bool(active)
        group = str(group or "")
        with self._lock:
            changed = (
                columns != self._columns
                or rows != self._rows
                or current != self._current
                or active != self._active
                or group != self._group
            )
            self._columns = columns
            self._rows = rows
            self._current = current
            self._active = active
            self._group = group
        if changed:
            self.changed.emit()

    def frozen(self, index: int) -> bool:
        with self._lock:
            return int(index or 0) in self._frozen

    def freeze(self, index: int) -> None:
        try:
            pane = int(index)
        except (TypeError, ValueError):
            return
        if pane < 1:
            return
        with self._lock:
            self._frozen.add(pane)

    def put(self, index: int, image: QImage, *, replace_frozen: bool = False) -> None:
        try:
            pane = int(index)
        except (TypeError, ValueError):
            return
        if pane < 1 or image is None or image.isNull():
            return
        shown = image.copy()
        with self._lock:
            if pane in self._frozen and not replace_frozen:
                return
            current = self._images.get(pane)
            if current is not None and not current.isNull() and current.cacheKey() == shown.cacheKey():
                return
            self._images[pane] = shown
        self.changed.emit()

    def peek(self, index: int) -> QImage:
        with self._lock:
            return self._images.get(int(index or 0)) or QImage()

    def indexes(self) -> list[int]:
        with self._lock:
            return sorted(self._images)

    def clear(self) -> None:
        with self._lock:
            if not self._images and not self._frozen and not self._active and self._current == 0:
                return
            self._images = {}
            self._frozen = set()
            self._current = 0
            self._active = False
            self._group = ""
        self.changed.emit()


class MosaicLiveItem(QQuickPaintedItem):
    """Contact-sheet live preview while a mosaic is capturing."""

    playingChanged = Signal()
    liveActiveChanged = Signal()
    livePaneChanged = Signal()
    cameraChanged = Signal()
    accentChanged = Signal()
    southUpChanged = Signal()
    positionAngleChanged = Signal()

    def __init__(self, parent: Optional[QQuickItem] = None):
        super().__init__(parent)
        self.setRenderTarget(QQuickPaintedItem.RenderTarget.Image)
        self.setFillColor(QColor(0, 0, 0, 0))
        self.setOpaquePainting(False)
        self.setAntialiasing(False)
        self._playing = False
        self._live_active = False
        self._live_pane = 0
        self._camera = "tele"
        self._accent = QColor(126, 224, 208)
        self._south_up = False
        self._position_angle = 0.0
        hub = live_frames()
        if hub is not None:
            hub.frameChanged.connect(self._on_live_frame)
        frames = mosaic_frames()
        if frames is not None:
            frames.changed.connect(self.update)

    def getPlaying(self) -> bool:
        return self._playing

    def setPlaying(self, value: bool) -> None:
        playing = bool(value)
        if playing == self._playing:
            return
        self._playing = playing
        self.playingChanged.emit()
        self.update()

    playing = Property(bool, getPlaying, setPlaying, notify=playingChanged)

    def getLiveActive(self) -> bool:
        return self._live_active

    def setLiveActive(self, value: bool) -> None:
        active = bool(value)
        if active == self._live_active:
            return
        self._live_active = active
        self.liveActiveChanged.emit()
        self.update()

    liveActive = Property(bool, getLiveActive, setLiveActive, notify=liveActiveChanged)

    def getLivePane(self) -> int:
        return self._live_pane

    def setLivePane(self, value: int) -> None:
        try:
            pane = int(value or 0)
        except (TypeError, ValueError):
            pane = 0
        if pane < 0:
            pane = 0
        if pane == self._live_pane:
            return
        self._live_pane = pane
        self.livePaneChanged.emit()
        self.update()

    livePane = Property(int, getLivePane, setLivePane, notify=livePaneChanged)

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
        self.update()

    camera = Property(str, getCamera, setCamera, notify=cameraChanged)

    def getAccent(self) -> QColor:
        return self._accent

    def setAccent(self, value: QColor) -> None:
        color = QColor(value) if value is not None else QColor(126, 224, 208)
        if color == self._accent:
            return
        self._accent = color
        self.accentChanged.emit()
        self.update()

    accent = Property(QColor, getAccent, setAccent, notify=accentChanged)

    def getSouthUp(self) -> bool:
        return self._south_up

    def setSouthUp(self, value: bool) -> None:
        on = bool(value)
        if on == self._south_up:
            return
        self._south_up = on
        self.southUpChanged.emit()
        self.update()

    southUp = Property(bool, getSouthUp, setSouthUp, notify=southUpChanged)

    def getPositionAngle(self) -> float:
        return self._position_angle

    def setPositionAngle(self, value: float) -> None:
        try:
            angle = float(value) % 360.0
        except (TypeError, ValueError):
            angle = 0.0
        if angle == self._position_angle:
            return
        self._position_angle = angle
        self.positionAngleChanged.emit()
        self.update()

    positionAngle = Property(float, getPositionAngle, setPositionAngle, notify=positionAngleChanged)

    @Slot(str)
    def _on_live_frame(self, key: str) -> None:
        if not self._playing or not self._live_active:
            return
        if key not in ("*", self._camera):
            return
        self.update()

    def _cell_rect(self, columns: int, rows: int, index: int) -> QRectF | None:
        if columns < 1 or rows < 1 or index < 1:
            return None
        width = float(self.width())
        height = float(self.height())
        if width <= 2 or height <= 2:
            return None
        gap = 2.0
        cell_w = (width - gap * (columns + 1)) / columns
        cell_h = (height - gap * (rows + 1)) / rows
        if cell_w <= 2 or cell_h <= 2:
            return None
        col = mosaic_sheet_column(
            index,
            columns,
            south_up=self._south_up,
            position_angle=self._position_angle,
        )
        row = mosaic_sheet_row(
            index,
            columns,
            rows,
            south_up=self._south_up,
            position_angle=self._position_angle,
        )
        if row >= rows:
            return None
        return QRectF(
            gap + col * (cell_w + gap),
            gap + row * (cell_h + gap),
            cell_w,
            cell_h,
        )

    def _fit_in(self, image: QImage, cell: QRectF) -> QRectF | None:
        if image.isNull() or cell.width() <= 0 or cell.height() <= 0:
            return None
        image_w = float(image.width())
        image_h = float(image.height())
        if image_w <= 0 or image_h <= 0:
            return None
        scale = min(cell.width() / image_w, cell.height() / image_h)
        draw_w = image_w * scale
        draw_h = image_h * scale
        return QRectF(
            cell.x() + (cell.width() - draw_w) / 2.0,
            cell.y() + (cell.height() - draw_h) / 2.0,
            draw_w,
            draw_h,
        )

    def paint(self, painter: QPainter) -> None:
        if not self._playing:
            return
        frames = mosaic_frames()
        if frames is None:
            return
        active, columns, rows, current, images = frames.snapshot()
        if not active or columns < 1 or rows < 1:
            return
        live = live_frames()
        live_image = live.peek(self._camera) if live is not None and self._live_active else QImage()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        font = QFont()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        count = columns * rows
        for index in range(1, count + 1):
            cell = self._cell_rect(columns, rows, index)
            if cell is None:
                continue
            painter.fillRect(cell, QColor(0, 0, 0, 160))
            image = images.get(index) or QImage()
            if index == self._live_pane and self._live_active and not live_image.isNull():
                image = live_image
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            else:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            fitted = self._fit_in(image, cell)
            if fitted is not None:
                painter.drawImage(fitted, image)
            else:
                painter.setPen(self._accent)
                painter.drawText(cell.toRect(), Qt.AlignmentFlag.AlignCenter, str(index))
            border = QPen(self._accent)
            highlight = self._live_pane if self._live_pane >= 1 else current
            border.setWidth(2 if index == highlight else 1)
            painter.setPen(border)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(cell.adjusted(0.5, 0.5, -0.5, -0.5))


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


def pop_jpegs(buffer: bytes, max_buffer: int = 20_000_000) -> tuple[bytes, list[bytes]]:
    """Pull complete JPEG payloads out of an MJPEG or image2pipe byte stream."""
    frames: list[bytes] = []
    while True:
        start = buffer.find(b"\xff\xd8")
        end = buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
        if start < 0 or end < 0:
            if start > 0:
                buffer = buffer[start:]
            elif start == 0 and len(buffer) > max_buffer:
                buffer = b""
            elif start < 0 and len(buffer) > max_buffer:
                buffer = buffer[-64_000:]
            break
        frames.append(buffer[start : end + 2])
        buffer = buffer[end + 2 :]
    return buffer, frames


def _close_http_conn(conn: http.client.HTTPConnection | None) -> None:
    if conn is None:
        return
    sock = getattr(conn, "sock", None)
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    try:
        conn.close()
    except OSError:
        pass


class StreamPlayer(QObject):
    """Live preview: ffmpeg for RTSP, native HTTP MJPEG for stacking snapshots."""

    frameReady = Signal(object)
    failed = Signal(str)
    statusChanged = Signal(str)
    _jpegBytes = Signal(object)

    _FIRST_FRAME_MS = 8000
    _HTTP_FIRST_FRAME_MS = 120000
    _HTTP_RECONNECT_MS = 1500
    _HTTP_RETRY_MS = 1500

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._url = ""
        self._transports: list[str | None] = [None]
        self._transport_index = 0
        self._http_mode = False
        self._keep_alive = False
        self._cancelled = False
        self._got_frame = False
        self._buffer = b""
        self._stderr = ""
        self._pid = 0
        self._pid_lock = threading.Lock()
        self._http_lock = threading.Lock()
        self._http_conn: http.client.HTTPConnection | None = None
        self._http_generation = 0
        self._latest_image: QImage | None = None
        self._flush_scheduled = False
        self._jpegBytes.connect(self._on_jpeg_bytes)
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._start_process)

    @Slot(str)
    def openStream(self, url: str) -> None:
        self._stop_http()
        self._teardown()
        self._cancelled = False
        self._url = url
        self._http_mode = url.startswith("http://")
        self._keep_alive = self._http_mode
        self._got_frame = False
        self._latest_image = None
        self._flush_scheduled = False
        if url.startswith("rtsp://"):
            # VLC typically uses TCP; UDP often never errors, it just stays blank.
            self._transports = ["tcp", "udp"]
        else:
            self._transports = [None]
        self._transport_index = 0
        self.statusChanged.emit(
            "Opening stacking preview…" if self._http_mode else "Opening camera stream…"
        )
        if self._http_mode:
            self._start_http()
            return
        self._start_process()

    @Slot()
    def closeStream(self) -> None:
        self._cancelled = True
        self._url = ""
        self._http_mode = False
        self._keep_alive = False
        self._watchdog.stop()
        self._reconnect_timer.stop()
        self._latest_image = None
        self._flush_scheduled = False
        self._stop_http()
        self._teardown()

    def _start_http(self) -> None:
        if self._cancelled or not self._url:
            return
        with self._http_lock:
            self._http_generation += 1
            generation = self._http_generation
        url = self._url
        self._watchdog.start(self._HTTP_FIRST_FRAME_MS)
        threading.Thread(
            target=self._http_loop,
            args=(url, generation),
            name="http-mjpeg",
            daemon=True,
        ).start()

    def _stop_http(self) -> None:
        with self._http_lock:
            self._http_generation += 1
            conn = self._http_conn
            self._http_conn = None
        _close_http_conn(conn)

    def _restart_http(self) -> None:
        if self._cancelled or not self._http_mode or not self._url:
            return
        self._stop_http()
        self._start_http()

    def _http_loop(self, url: str, generation: int) -> None:
        while generation == self._http_generation and not self._cancelled and url:
            try:
                self._http_read(url, generation)
            except Exception:
                if generation != self._http_generation or self._cancelled:
                    return
                self.statusChanged.emit("Waiting for stacking preview…")
            if generation != self._http_generation or self._cancelled:
                return
            time.sleep(self._HTTP_RECONNECT_MS / 1000)

    def _http_read(self, url: str, generation: int) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            raise RuntimeError("Stacking preview URL is missing a host")
        port = parsed.port or 8092
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        conn = http.client.HTTPConnection(host, port, timeout=5)
        with self._http_lock:
            if generation != self._http_generation:
                _close_http_conn(conn)
                return
            self._http_conn = conn
        try:
            conn.request("GET", path, headers={"Accept": "*/*", "Connection": "keep-alive"})
            response = conn.getresponse()
            if response.status != 200:
                raise RuntimeError(f"Stacking preview returned HTTP {response.status}")
            if conn.sock is not None:
                conn.sock.settimeout(1.0)
            buffer = b""
            announced = False
            while generation == self._http_generation and not self._cancelled:
                try:
                    chunk = response.read1(64 * 1024) if hasattr(response, "read1") else response.read(64 * 1024)
                except (TimeoutError, socket.timeout):
                    continue
                except (OSError, http.client.HTTPException):
                    break
                if not chunk:
                    break
                if not announced:
                    announced = True
                    if not self._got_frame:
                        self.statusChanged.emit("Downloading stacking preview…")
                buffer += chunk
                buffer, frames = pop_jpegs(buffer)
                for jpeg in frames:
                    self._jpegBytes.emit(jpeg)
        finally:
            with self._http_lock:
                if self._http_conn is conn:
                    self._http_conn = None
            _close_http_conn(conn)

    @Slot(object)
    def _on_jpeg_bytes(self, data: object) -> None:
        if self._cancelled or not isinstance(data, (bytes, bytearray)) or not data:
            return
        image = QImage.fromData(bytes(data), "JPG")
        if image.isNull():
            return
        self._queue_frame(image)

    def _start_process(self) -> None:
        if self._http_mode or self._cancelled or not self._url:
            return
        self._reconnect_timer.stop()
        self._teardown()
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
        process.started.connect(self._on_process_started)
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

    def abort(self) -> None:
        """Kill ffmpeg / HTTP from any thread without waiting on Qt."""
        self._cancelled = True
        self._stop_http()
        with self._pid_lock:
            pid = self._pid
            self._pid = 0
        if pid:
            kill_pid_tree(pid)

    def _teardown(self) -> None:
        self._watchdog.stop()
        self._reconnect_timer.stop()
        process = self._process
        self._process = None
        self._buffer = b""
        if process is None:
            return
        for signal_name in ("started", "readyReadStandardOutput", "readyReadStandardError", "errorOccurred", "finished"):
            try:
                getattr(process, signal_name).disconnect()
            except (RuntimeError, TypeError):
                pass
        pid = int(process.processId() or 0)
        with self._pid_lock:
            self._pid = 0
        running = process.state() != QProcess.ProcessState.NotRunning
        if running:
            process.kill()
            process.waitForFinished(400)
        if pid:
            kill_pid_tree(pid)
        process.deleteLater()

    def _on_process_started(self) -> None:
        if self._cancelled or self._process is None:
            return
        with self._pid_lock:
            self._pid = int(self._process.processId() or 0)
        self._watchdog.start(self._FIRST_FRAME_MS)

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        self._buffer, frames = pop_jpegs(self._buffer)
        if not frames:
            return
        image = QImage.fromData(frames[-1], "JPG")
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
            self._retry_or_fail(f"Could not start ffmpeg ({ffmpeg_path()})", fatal=True)

    def _on_finished(self) -> None:
        if self._cancelled or self._process is None:
            return
        detail = self._stderr.strip().splitlines()[-1] if self._stderr.strip() else "ffmpeg exited"
        self._retry_or_fail(detail)

    def _on_watchdog(self) -> None:
        if self._cancelled:
            return
        if self._http_mode:
            if self._got_frame:
                return
            self.statusChanged.emit("Waiting for stacking preview…")
            self._restart_http()
            return
        if self._got_frame:
            return
        self._retry_or_fail("No frames received from the camera stream")

    def _schedule_reconnect(self, delay_ms: int | None = None) -> None:
        if self._cancelled or not self._url:
            return
        self._watchdog.stop()
        if self._reconnect_timer.isActive():
            return
        wait = self._HTTP_RETRY_MS if delay_ms is None else delay_ms
        if wait <= 0:
            self._start_process()
            return
        self._reconnect_timer.start(wait)

    def _retry_or_fail(self, message: str, *, fatal: bool = False) -> None:
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
