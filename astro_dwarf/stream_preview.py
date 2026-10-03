from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from PySide6.QtCore import Property, QBuffer, QIODevice, QObject, QProcess, QRectF, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QWindow
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

from .domain import panorama_leave_index, panorama_shot_cell_px, panorama_stamp_live_ready
from .runtime import PROCESS_CREATION_FLAGS, ffmpeg_mjpeg_command, ffmpeg_path, kill_pid_tree
from .services import (
    device_mosaic_pane_norm,
    mosaic_camera_up_is_south,
    mosaic_sheet_column,
    mosaic_sheet_row,
)

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
        self._revision = {"tele": 0, "wide": 0}

    def update(self, key: str, image: QImage) -> None:
        if key not in self._images:
            return
        with self._lock:
            self._images[key] = image
            self._revision[key] = int(self._revision.get(key, 0)) + 1

    def notify(self, key: str = "*") -> None:
        self.frameChanged.emit(key)

    def peek(self, key: str) -> QImage:
        with self._lock:
            return self._images.get(key) or QImage()

    def revision(self, key: str) -> int:
        with self._lock:
            return int(self._revision.get(key, 0))

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key in self._images:
                self._images[key] = QImage()
                self._revision[key] = int(self._revision.get(key, 0)) + 1
            else:
                self._images = {"tele": QImage(), "wide": QImage()}
                self._revision = {
                    "tele": int(self._revision.get("tele", 0)) + 1,
                    "wide": int(self._revision.get("wide", 0)) + 1,
                }
        self.frameChanged.emit(key or "*")


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
        with self._lock:
            if pane in self._frozen and not replace_frozen:
                return
            current = self._images.get(pane)
            if current is not None and not current.isNull() and current.cacheKey() == image.cacheKey():
                return
            # A shallow copy shares pixels; a later write to the caller's image detaches.
            self._images[pane] = QImage(image)
        self.changed.emit()

    def peek(self, index: int) -> QImage:
        with self._lock:
            return self._images.get(int(index or 0)) or QImage()

    def indexes(self) -> list[int]:
        with self._lock:
            return sorted(self._images)

    def clear(self) -> None:
        with self._lock:
            if (
                not self._images
                and not self._frozen
                and not self._active
                and self._current == 0
                and self._columns <= 1
                and self._rows <= 1
                and not self._group
            ):
                return
            self._images = {}
            self._frozen = set()
            self._current = 0
            self._active = False
            self._group = ""
            self._columns = 1
            self._rows = 1
        self.changed.emit()


_MOSAIC_CACHE_TOKEN = re.compile(r"[^A-Za-z0-9_-]+")
_mosaic_cache_io = threading.Lock()


def mosaic_cache_token(value: str) -> str:
    """Filesystem-safe piece of a device id or mosaic group."""
    return _MOSAIC_CACHE_TOKEN.sub("_", str(value or "").strip()).strip("_")[:96]


def mosaic_pane_cache_dir(device_id: str, group: str, *, root: Path | None = None) -> Path | None:
    """Per-device, per-mosaic folder for pane JPEGs. Does not create it."""
    device = mosaic_cache_token(device_id)
    owner = mosaic_cache_token(group)
    if not device or not owner:
        return None
    base = root if root is not None else _default_mosaic_cache_root()
    return base / device / owner


def _default_mosaic_cache_root() -> Path:
    from .runtime import data_root

    return data_root() / "mosaic-cache"


def _mosaic_cache_meta_path(folder: Path) -> Path:
    return folder / "meta.json"


def _read_mosaic_cache_meta(folder: Path) -> dict:
    path = _mosaic_cache_meta_path(folder)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_mosaic_cache_meta(folder: Path, payload: dict) -> None:
    path = _mosaic_cache_meta_path(folder)
    temporary = folder / f"meta.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(temporary, path)


def _cache_jpeg_source(image: QImage) -> QImage:
    """Detach a pane still so the JPEG write does not race the decoder."""
    source = image.convertToFormat(QImage.Format.Format_RGB32)
    if source.isNull():
        return QImage()
    if source.width() <= 960 and source.height() <= 960:
        return source
    return source.scaled(
        960,
        960,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def save_mosaic_pane_cache(
    device_id: str,
    group: str,
    index: int,
    image: QImage,
    *,
    frozen: bool = False,
    current: int = 0,
    columns: int = 0,
    rows: int = 0,
    root: Path | None = None,
) -> bool:
    """Write one pane still so a restart or reconnect can paint it again."""
    try:
        pane = int(index)
    except (TypeError, ValueError):
        return False
    if pane < 1 or image is None or image.isNull():
        return False
    folder = mosaic_pane_cache_dir(device_id, group, root=root)
    if folder is None:
        return False
    encoded = _cache_jpeg_source(image)
    if encoded.isNull():
        return False
    with _mosaic_cache_io:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        temporary = folder / f"{pane}.{os.getpid()}.tmp.jpg"
        path = folder / f"{pane}.jpg"
        if not encoded.save(str(temporary), "JPG", 80):
            temporary.unlink(missing_ok=True)
            return False
        try:
            os.replace(temporary, path)
        except OSError:
            temporary.unlink(missing_ok=True)
            return False
        meta = _read_mosaic_cache_meta(folder)
        frozen_panes = []
        for item in list(meta.get("frozen") or []):
            try:
                stored = int(item)
            except (TypeError, ValueError):
                continue
            if stored >= 1 and stored not in frozen_panes:
                frozen_panes.append(stored)
        if frozen and pane not in frozen_panes:
            frozen_panes.append(pane)
        elif not frozen and pane in frozen_panes:
            frozen_panes.remove(pane)
        meta["frozen"] = frozen_panes
        if int(current or 0) >= 1:
            meta["current"] = int(current)
        if int(columns or 0) >= 1:
            meta["columns"] = int(columns)
        if int(rows or 0) >= 1:
            meta["rows"] = int(rows)
        try:
            _write_mosaic_cache_meta(folder, meta)
        except OSError:
            pass
    return True


def load_mosaic_pane_cache(
    device_id: str,
    group: str,
    *,
    root: Path | None = None,
) -> dict:
    """Return cached pane stills plus which indexes were frozen."""
    folder = mosaic_pane_cache_dir(device_id, group, root=root)
    empty = {"images": {}, "frozen": set(), "current": 0, "columns": 0, "rows": 0}
    if folder is None or not folder.is_dir():
        return empty
    images: dict[int, QImage] = {}
    with _mosaic_cache_io:
        meta = _read_mosaic_cache_meta(folder)
        for path in folder.glob("*.jpg"):
            if not path.stem.isdigit():
                continue
            pane = int(path.stem)
            if pane < 1:
                continue
            image = QImage(str(path))
            if image.isNull():
                continue
            images[pane] = image
    frozen: set[int] = set()
    for item in list(meta.get("frozen") or []):
        try:
            pane = int(item)
        except (TypeError, ValueError):
            continue
        if pane >= 1:
            frozen.add(pane)
    try:
        current = int(meta.get("current") or 0)
    except (TypeError, ValueError):
        current = 0
    try:
        columns = int(meta.get("columns") or 0)
    except (TypeError, ValueError):
        columns = 0
    try:
        rows = int(meta.get("rows") or 0)
    except (TypeError, ValueError):
        rows = 0
    return {
        "images": images,
        "frozen": frozen,
        "current": current,
        "columns": columns,
        "rows": rows,
    }


def mosaic_cache_has_panes(device_id: str, group: str, *, root: Path | None = None) -> bool:
    folder = mosaic_pane_cache_dir(device_id, group, root=root)
    if folder is None or not folder.is_dir():
        return False
    return any(path.stem.isdigit() for path in folder.glob("*.jpg"))


def mosaic_cache_current(device_id: str, group: str, *, root: Path | None = None) -> int:
    """Pane index stored beside the cached stills. 0 when the mosaic has no cache."""
    folder = mosaic_pane_cache_dir(device_id, group, root=root)
    if folder is None or not folder.is_dir():
        return 0
    try:
        current = int(_read_mosaic_cache_meta(folder).get("current") or 0)
    except (TypeError, ValueError):
        return 0
    return current if current >= 1 else 0


def clear_mosaic_pane_cache(device_id: str, group: str = "", *, root: Path | None = None) -> None:
    """Drop one mosaic's stills, or every cached mosaic for the device."""
    device = mosaic_cache_token(device_id)
    if not device:
        return
    base = root if root is not None else _default_mosaic_cache_root()
    owner = mosaic_cache_token(group)
    target = base / device / owner if owner else base / device
    with _mosaic_cache_io:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)


def mosaic_live_overlay_ready(image: QImage | None, stale_key: int) -> bool:
    """True when this live frame belongs to the current pane, not the previous one.

    Switching live_pane used to paint the leftover stacked.jpg of pane N into
    N+1 until a new HTTP/RTSP frame arrived.
    """
    if image is None or image.isNull():
        return False
    try:
        stale = int(stale_key or 0)
    except (TypeError, ValueError):
        stale = 0
    if not stale:
        return True
    return image.cacheKey() != stale


class MosaicLiveItem(QQuickPaintedItem):
    """Contact-sheet live preview while a mosaic is capturing."""

    playingChanged = Signal()
    liveActiveChanged = Signal()
    livePaneChanged = Signal()
    cameraChanged = Signal()
    accentChanged = Signal()
    southUpChanged = Signal()
    positionAngleChanged = Signal()
    zenithCameraChanged = Signal()
    fontPixelSizeChanged = Signal()
    composedChanged = Signal()
    horizontalScaleChanged = Signal()
    verticalScaleChanged = Signal()

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
        self._zenith_camera = False
        self._font_pixel_size = 11
        self._composed = False
        self._horizontal_scale = 100
        self._vertical_scale = 100
        self._held_pane = 0
        self._held_image = QImage()
        self._await_live_frame = False
        self._stale_live_key = 0
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
        if not active:
            self._capture_hold()
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
        if pane < 1:
            self._capture_hold()
            self._await_live_frame = False
            self._stale_live_key = 0
        else:
            if pane != self._held_pane:
                self._held_pane = 0
                self._held_image = QImage()
            live = live_frames()
            current = live.peek(self._camera) if live is not None else QImage()
            self._stale_live_key = 0 if current is None or current.isNull() else current.cacheKey()
            self._await_live_frame = True
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

    def getZenithCamera(self) -> bool:
        return self._zenith_camera

    def setZenithCamera(self, value: bool) -> None:
        on = bool(value)
        if on == self._zenith_camera:
            return
        self._zenith_camera = on
        self.zenithCameraChanged.emit()
        self.update()

    zenithCamera = Property(bool, getZenithCamera, setZenithCamera, notify=zenithCameraChanged)

    def getFontPixelSize(self) -> int:
        return self._font_pixel_size

    def setFontPixelSize(self, value: int) -> None:
        try:
            size = int(value or 0)
        except (TypeError, ValueError):
            size = 11
        if size < 1:
            size = 11
        if size == self._font_pixel_size:
            return
        self._font_pixel_size = size
        self.fontPixelSizeChanged.emit()
        self.update()

    fontPixelSize = Property(int, getFontPixelSize, setFontPixelSize, notify=fontPixelSizeChanged)

    def getComposed(self) -> bool:
        return self._composed

    def setComposed(self, value: bool) -> None:
        on = bool(value)
        if on == self._composed:
            return
        self._composed = on
        self.composedChanged.emit()
        self.update()

    composed = Property(bool, getComposed, setComposed, notify=composedChanged)

    def getHorizontalScale(self) -> int:
        return self._horizontal_scale

    def setHorizontalScale(self, value: int) -> None:
        try:
            scale = int(value or 100)
        except (TypeError, ValueError):
            scale = 100
        if scale == self._horizontal_scale:
            return
        self._horizontal_scale = scale
        self.horizontalScaleChanged.emit()
        self.update()

    horizontalScale = Property(int, getHorizontalScale, setHorizontalScale, notify=horizontalScaleChanged)

    def getVerticalScale(self) -> int:
        return self._vertical_scale

    def setVerticalScale(self, value: int) -> None:
        try:
            scale = int(value or 100)
        except (TypeError, ValueError):
            scale = 100
        if scale == self._vertical_scale:
            return
        self._vertical_scale = scale
        self.verticalScaleChanged.emit()
        self.update()

    verticalScale = Property(int, getVerticalScale, setVerticalScale, notify=verticalScaleChanged)

    def _capture_hold(self) -> None:
        """Keep the last painted live frame after stacking takes the stream."""
        if self._live_pane < 1:
            return
        live = live_frames()
        image = live.peek(self._camera) if live is not None else QImage()
        if image is None or image.isNull():
            return
        self._held_pane = self._live_pane
        self._held_image = image.copy()

    @Slot(str)
    def _on_live_frame(self, key: str) -> None:
        if not self._playing or not self._live_active:
            return
        if key not in ("*", self._camera):
            return
        if self._await_live_frame:
            live = live_frames()
            image = live.peek(self._camera) if live is not None else QImage()
            if not mosaic_live_overlay_ready(image, self._stale_live_key):
                return
            self._await_live_frame = False
            self._stale_live_key = 0
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
            zenith_camera=self._zenith_camera,
        )
        row = mosaic_sheet_row(
            index,
            columns,
            rows,
            south_up=self._south_up,
            position_angle=self._position_angle,
            zenith_camera=self._zenith_camera,
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

    def _cover_in(self, image: QImage, cell: QRectF) -> QRectF | None:
        if image.isNull() or cell.width() <= 0 or cell.height() <= 0:
            return None
        image_w = float(image.width())
        image_h = float(image.height())
        if image_w <= 0 or image_h <= 0:
            return None
        scale = max(cell.width() / image_w, cell.height() / image_h)
        draw_w = image_w * scale
        draw_h = image_h * scale
        return QRectF(
            cell.x() + (cell.width() - draw_w) / 2.0,
            cell.y() + (cell.height() - draw_h) / 2.0,
            draw_w,
            draw_h,
        )

    def _pane_image_aspect(self, images: dict, live_image: QImage) -> float:
        for image in (live_image, *images.values()):
            if image is not None and not image.isNull() and image.height() > 0:
                return float(image.width()) / float(image.height())
        return 2.95 / 1.66

    def _composed_canvas(self, aspect: float) -> QRectF | None:
        width = float(self.width())
        height = float(self.height())
        if width <= 2 or height <= 2 or aspect <= 0:
            return None
        if width / height > aspect:
            draw_h = height
            draw_w = height * aspect
        else:
            draw_w = width
            draw_h = width / aspect
        return QRectF((width - draw_w) / 2.0, (height - draw_h) / 2.0, draw_w, draw_h)

    def _composed_cell(self, canvas: QRectF, columns: int, rows: int, index: int) -> QRectF | None:
        x, y, pane_w, pane_h = device_mosaic_pane_norm(
            index,
            columns,
            rows,
            self._horizontal_scale,
            self._vertical_scale,
            south_up=self._south_up,
            position_angle=self._position_angle,
            zenith_camera=self._zenith_camera,
        )
        if pane_w <= 0 or pane_h <= 0:
            return None
        return QRectF(
            canvas.x() + x * canvas.width(),
            canvas.y() + y * canvas.height(),
            pane_w * canvas.width(),
            pane_h * canvas.height(),
        )

    def _draw_pane_image(self, painter: QPainter, image: QImage, cell: QRectF, *, cover: bool) -> None:
        fitted = self._cover_in(image, cell) if cover else self._fit_in(image, cell)
        if fitted is None:
            return
        painter.save()
        painter.setClipRect(cell)
        painter.drawImage(fitted, image)
        painter.restore()

    def _paint_composed(
        self,
        painter: QPainter,
        columns: int,
        rows: int,
        current: int,
        images: dict,
        live_image: QImage,
    ) -> None:
        aspect = self._pane_image_aspect(images, live_image)
        horizontal = max(100, int(self._horizontal_scale or 100)) / 100.0
        vertical = max(100, int(self._vertical_scale or 100)) / 100.0
        canvas = self._composed_canvas(aspect * horizontal / vertical)
        if canvas is None:
            return
        painter.fillRect(canvas, QColor(0, 0, 0, 180))
        flip = (
            False
            if self._zenith_camera
            else mosaic_camera_up_is_south(self._south_up, self._position_angle)
        )
        count = columns * rows
        highlight = self._live_pane if self._live_pane >= 1 else (
            self._held_pane if self._held_pane >= 1 else current
        )
        order = [index for index in range(1, count + 1) if index != self._live_pane]
        if self._live_pane >= 1:
            order.append(self._live_pane)
        for index in order:
            cell = self._composed_cell(canvas, columns, rows, index)
            if cell is None:
                continue
            image = images.get(index) or QImage()
            cover = False
            if (
                index == self._live_pane
                and self._live_active
                and not self._await_live_frame
                and mosaic_live_overlay_ready(live_image, self._stale_live_key)
            ):
                image = live_image
                cover = True
            elif image.isNull() and index == self._held_pane and not self._held_image.isNull():
                image = self._held_image
                cover = True
            elif not image.isNull():
                cover = True
            if flip and not image.isNull():
                image = image.flipped(Qt.Orientation.Horizontal | Qt.Orientation.Vertical)
            if image.isNull():
                painter.setPen(self._accent)
                painter.drawText(cell.toRect(), Qt.AlignmentFlag.AlignCenter, str(index))
            else:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not cover)
                self._draw_pane_image(painter, image, cell, cover=cover)
            border = QPen(self._accent)
            border.setWidth(2 if index == highlight else 1)
            painter.setPen(border)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(cell.adjusted(0.5, 0.5, -0.5, -0.5))
        frame = QPen(self._accent)
        frame.setWidth(2)
        painter.setPen(frame)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(canvas.adjusted(0.5, 0.5, -0.5, -0.5))

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
        font.setPixelSize(max(1, int(self._font_pixel_size or 11)))
        font.setBold(True)
        painter.setFont(font)
        if self._composed and (columns > 1 or rows > 1):
            self._paint_composed(painter, columns, rows, current, images, live_image)
            return
        flip = (
            False
            if self._zenith_camera
            else mosaic_camera_up_is_south(self._south_up, self._position_angle)
        )
        count = columns * rows
        for index in range(1, count + 1):
            cell = self._cell_rect(columns, rows, index)
            if cell is None:
                continue
            painter.fillRect(cell, QColor(0, 0, 0, 160))
            image = images.get(index) or QImage()
            if (
                index == self._live_pane
                and self._live_active
                and not self._await_live_frame
                and mosaic_live_overlay_ready(live_image, self._stale_live_key)
            ):
                image = live_image
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            elif (
                image.isNull()
                and index == self._held_pane
                and not self._held_image.isNull()
            ):
                image = self._held_image
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            else:
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            fitted = self._fit_in(image, cell)
            if fitted is not None:
                if flip:
                    image = image.flipped(Qt.Orientation.Horizontal | Qt.Orientation.Vertical)
                painter.drawImage(fitted, image)
            else:
                painter.setPen(self._accent)
                painter.drawText(cell.toRect(), Qt.AlignmentFlag.AlignCenter, str(index))
            border = QPen(self._accent)
            highlight = self._live_pane if self._live_pane >= 1 else (
                self._held_pane if self._held_pane >= 1 else current
            )
            border.setWidth(2 if index == highlight else 1)
            painter.setPen(border)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(cell.adjusted(0.5, 0.5, -0.5, -0.5))


class PanoramaStampItem(QQuickPaintedItem):
    """Leave a tele still in each panorama cell as the yellow tracker moves."""

    activeChanged = Signal()
    shootingChanged = Signal()
    playingChanged = Signal()
    tileIndexChanged = Signal()
    gridColumnsChanged = Signal()
    gridRowsChanged = Signal()

    def __init__(self, parent: Optional[QQuickItem] = None):
        super().__init__(parent)
        self.setRenderTarget(QQuickPaintedItem.RenderTarget.Image)
        self.setFillColor(QColor(0, 0, 0, 0))
        self.setOpaquePainting(False)
        self.setAntialiasing(False)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setImplicitWidth(0)
        self.setImplicitHeight(0)
        self._active = False
        self._shooting = False
        self._playing = False
        self._camera = "tele"
        self._tile_index = 0
        self._columns = 1
        self._rows = 1
        self._fit_x = 0.0
        self._fit_y = 0.0
        self._fit_w = 0.0
        self._fit_h = 0.0
        self._box_x1 = 0.0
        self._box_y1 = 0.0
        self._box_x2 = 1.0
        self._box_y2 = 1.0
        self._limit_left = 0.0
        self._limit_top = 0.0
        self._span_x = 1.0
        self._span_y = 1.0
        self._sheet = QImage()
        self._stamped: set[int] = set()
        self._await_live_frame = False
        self._stale_live_key = 0
        hub = live_frames()
        if hub is not None:
            hub.frameChanged.connect(self._on_live_frame)

    def getActive(self) -> bool:
        return self._active

    def setActive(self, value: bool) -> None:
        on = bool(value)
        if on == self._active:
            return
        if not on:
            self._reset_sheet()
            self._await_live_frame = False
            self._stale_live_key = 0
        self._active = on
        self.activeChanged.emit()
        self.update()

    active = Property(bool, getActive, setActive, notify=activeChanged)

    def getShooting(self) -> bool:
        return self._shooting

    def setShooting(self, value: bool) -> None:
        on = bool(value)
        if on == self._shooting:
            return
        if on:
            self._reset_sheet()
            self._await_live_frame = False
            self._stale_live_key = 0
        else:
            self._stamp_cell(self._tile_index, self._peek_tele())
            self._await_live_frame = False
            self._stale_live_key = 0
        self._shooting = on
        self.shootingChanged.emit()
        self.update()

    shooting = Property(bool, getShooting, setShooting, notify=shootingChanged)

    def getPlaying(self) -> bool:
        return self._playing

    def setPlaying(self, value: bool) -> None:
        on = bool(value)
        if on == self._playing:
            return
        self._playing = on
        self.playingChanged.emit()
        self.update()

    playing = Property(bool, getPlaying, setPlaying, notify=playingChanged)

    def getTileIndex(self) -> int:
        return self._tile_index

    def setTileIndex(self, value: int) -> None:
        try:
            index = max(0, int(value or 0))
        except (TypeError, ValueError):
            index = 0
        if index == self._tile_index:
            return
        previous = self._tile_index
        if self._shooting:
            leave = panorama_leave_index(previous, index)
            if leave is not None:
                self._stamp_cell(leave, self._peek_tele())
            live = self._peek_tele()
            self._stale_live_key = 0 if live is None or live.isNull() else live.cacheKey()
            self._await_live_frame = bool(self._stale_live_key)
        self._tile_index = index
        self.tileIndexChanged.emit()
        self.update()

    tileIndex = Property(int, getTileIndex, setTileIndex, notify=tileIndexChanged)

    def getGridColumns(self) -> int:
        return self._columns

    def setGridColumns(self, value: int) -> None:
        try:
            cols = max(1, int(value or 1))
        except (TypeError, ValueError):
            cols = 1
        if cols == self._columns:
            return
        self._columns = cols
        self.gridColumnsChanged.emit()
        self.update()

    gridColumns = Property(int, getGridColumns, setGridColumns, notify=gridColumnsChanged)

    def getGridRows(self) -> int:
        return self._rows

    def setGridRows(self, value: int) -> None:
        try:
            rows = max(1, int(value or 1))
        except (TypeError, ValueError):
            rows = 1
        if rows == self._rows:
            return
        self._rows = rows
        self.gridRowsChanged.emit()
        self.update()

    gridRows = Property(int, getGridRows, setGridRows, notify=gridRowsChanged)

    def _set_geom(self, attr: str, value: float) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        if number == getattr(self, attr):
            return
        setattr(self, attr, number)
        self.update()

    def getFitX(self) -> float:
        return self._fit_x

    def setFitX(self, value: float) -> None:
        self._set_geom("_fit_x", value)

    fitX = Property(float, getFitX, setFitX)

    def getFitY(self) -> float:
        return self._fit_y

    def setFitY(self, value: float) -> None:
        self._set_geom("_fit_y", value)

    fitY = Property(float, getFitY, setFitY)

    def getFitW(self) -> float:
        return self._fit_w

    def setFitW(self, value: float) -> None:
        self._set_geom("_fit_w", value)

    fitW = Property(float, getFitW, setFitW)

    def getFitH(self) -> float:
        return self._fit_h

    def setFitH(self, value: float) -> None:
        self._set_geom("_fit_h", value)

    fitH = Property(float, getFitH, setFitH)

    def getBoxX1(self) -> float:
        return self._box_x1

    def setBoxX1(self, value: float) -> None:
        self._set_geom("_box_x1", value)

    boxX1 = Property(float, getBoxX1, setBoxX1)

    def getBoxY1(self) -> float:
        return self._box_y1

    def setBoxY1(self, value: float) -> None:
        self._set_geom("_box_y1", value)

    boxY1 = Property(float, getBoxY1, setBoxY1)

    def getBoxX2(self) -> float:
        return self._box_x2

    def setBoxX2(self, value: float) -> None:
        self._set_geom("_box_x2", value)

    boxX2 = Property(float, getBoxX2, setBoxX2)

    def getBoxY2(self) -> float:
        return self._box_y2

    def setBoxY2(self, value: float) -> None:
        self._set_geom("_box_y2", value)

    boxY2 = Property(float, getBoxY2, setBoxY2)

    def getLimitLeft(self) -> float:
        return self._limit_left

    def setLimitLeft(self, value: float) -> None:
        self._set_geom("_limit_left", value)

    limitLeft = Property(float, getLimitLeft, setLimitLeft)

    def getLimitTop(self) -> float:
        return self._limit_top

    def setLimitTop(self, value: float) -> None:
        self._set_geom("_limit_top", value)

    limitTop = Property(float, getLimitTop, setLimitTop)

    def getSpanX(self) -> float:
        return self._span_x

    def setSpanX(self, value: float) -> None:
        self._set_geom("_span_x", value)

    spanX = Property(float, getSpanX, setSpanX)

    def getSpanY(self) -> float:
        return self._span_y

    def setSpanY(self, value: float) -> None:
        self._set_geom("_span_y", value)

    spanY = Property(float, getSpanY, setSpanY)

    def geometryChange(self, new_geometry, old_geometry) -> None:
        super().geometryChange(new_geometry, old_geometry)
        width = int(max(0.0, float(self.width())))
        height = int(max(0.0, float(self.height())))
        if width > 0 and height > 0:
            self.setContentsSize(QSize(width, height))

    def stampedIndexes(self) -> list[int]:
        return sorted(self._stamped)

    def sheetImage(self) -> QImage:
        return self._sheet

    def _peek_tele(self) -> QImage:
        hub = live_frames()
        if hub is None:
            return QImage()
        return hub.peek(self._camera)

    def _reset_sheet(self) -> None:
        self._sheet = QImage()
        self._stamped = set()

    def _ensure_sheet(self) -> QImage | None:
        width = int(round(self._fit_w))
        height = int(round(self._fit_h))
        if width < 2 or height < 2:
            return None
        if self._sheet.isNull() or self._sheet.width() != width or self._sheet.height() != height:
            nxt = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
            nxt.fill(Qt.GlobalColor.transparent)
            if not self._sheet.isNull():
                painter = QPainter(nxt)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                painter.drawImage(QRectF(0, 0, width, height), self._sheet)
                painter.end()
            self._sheet = nxt
        return self._sheet

    def _cell_rect(self, index: int) -> QRectF | None:
        px = panorama_shot_cell_px(
            index,
            self._columns,
            self._rows,
            x1=self._box_x1,
            y1=self._box_y1,
            x2=self._box_x2,
            y2=self._box_y2,
            limit_left=self._limit_left,
            limit_top=self._limit_top,
            span_x=self._span_x,
            span_y=self._span_y,
            fit_x=self._fit_x,
            fit_y=self._fit_y,
            fit_w=self._fit_w,
            fit_h=self._fit_h,
        )
        if px is None:
            return None
        return QRectF(px[0], px[1], px[2], px[3])

    def _stamp_cell(self, index: int, image: QImage | None) -> None:
        if not panorama_stamp_live_ready(self._columns, self._rows):
            return
        if index in self._stamped:
            return
        if image is None or image.isNull():
            return
        rect = self._cell_rect(index)
        if rect is None or rect.width() < 1 or rect.height() < 1:
            return
        sheet = self._ensure_sheet()
        if sheet is None:
            return
        dest = QRectF(
            rect.x() - self._fit_x,
            rect.y() - self._fit_y,
            rect.width(),
            rect.height(),
        )
        painter = QPainter(sheet)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(dest, image)
        painter.end()
        self._stamped.add(int(index))

    @Slot(str)
    def _on_live_frame(self, key: str) -> None:
        if not self._active or not self._shooting or not self._playing:
            return
        if not panorama_stamp_live_ready(self._columns, self._rows):
            return
        if key not in ("*", self._camera):
            return
        if self._await_live_frame:
            live = self._peek_tele()
            if not mosaic_live_overlay_ready(live, self._stale_live_key):
                return
            self._await_live_frame = False
            self._stale_live_key = 0
        self.update()

    def paint(self, painter: QPainter) -> None:
        if not self._active:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        if not self._sheet.isNull():
            painter.drawImage(
                QRectF(self._fit_x, self._fit_y, self._fit_w, self._fit_h),
                self._sheet,
            )
        if not panorama_stamp_live_ready(self._columns, self._rows):
            return
        if not self._shooting or not self._playing:
            return
        live = self._peek_tele()
        if self._await_live_frame and not mosaic_live_overlay_ready(live, self._stale_live_key):
            return
        rect = self._cell_rect(self._tile_index)
        if rect is None or live is None or live.isNull():
            return
        painter.drawImage(rect, live)


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


def preview_should_ingest_frame(
    window_live: bool,
    *,
    first_frame: bool = False,
    camera: str = "",
    panorama_running: bool = False,
) -> bool:
    """Copy this JPEG into the live hub, even if the window will not repaint.

    Hidden, minimized, and background frames stay dropped so the GUI thread
    does not copy or enhance them. Tele frames during a panorama shoot are
    the FOV stamps on the canvas, so those still have to land in the hub.
    """
    if first_frame or window_live:
        return True
    return bool(panorama_running) and str(camera) == "tele"


class JpegSplitter:
    """Pull complete JPEG payloads out of an MJPEG or image2pipe byte stream.

    Each byte is searched once: the scan resumes where the last chunk ended,
    so a multi-megabyte stacking JPEG arriving in 64 KB reads stays linear.
    """

    def __init__(self, max_buffer: int = 20_000_000):
        self._max_buffer = max_buffer
        self._buffer = bytearray()
        self._in_frame = False
        self._scan = 0

    def clear(self) -> None:
        self._buffer = bytearray()
        self._in_frame = False
        self._scan = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        buffer = self._buffer
        buffer += chunk
        frames: list[bytes] = []
        while True:
            if not self._in_frame:
                start = buffer.find(b"\xff\xd8", self._scan)
                if start < 0:
                    if len(buffer) > self._max_buffer:
                        del buffer[:-64_000]
                    self._scan = max(0, len(buffer) - 1)
                    break
                del buffer[:start]
                self._in_frame = True
                self._scan = 2
            end = buffer.find(b"\xff\xd9", self._scan)
            if end < 0:
                if len(buffer) > self._max_buffer:
                    self.clear()
                else:
                    self._scan = max(2, len(buffer) - 1)
                break
            frames.append(bytes(buffer[: end + 2]))
            del buffer[: end + 2]
            self._in_frame = False
            self._scan = 0
        return frames


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
        self._splitter = JpegSplitter()
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

    def _stream_alive(self) -> bool:
        if self._cancelled or not self._url:
            return False
        if self._http_mode:
            return True
        process = self._process
        if process is None:
            return False
        return process.state() != QProcess.ProcessState.NotRunning

    @Slot(str)
    def openStream(self, url: str) -> None:
        if (
            url
            and url == self._url
            and url.startswith("rtsp://")
            and not self._cancelled
            and self._stream_alive()
        ):
            return
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
            splitter = JpegSplitter()
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
                frames = splitter.feed(chunk)
                if frames:
                    self._jpegBytes.emit(frames[-1])
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
        self._splitter.clear()
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
        process = self._process
        self._process = None
        self._splitter.clear()
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
        frames = self._splitter.feed(bytes(self._process.readAllStandardOutput()))
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
