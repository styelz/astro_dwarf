from __future__ import annotations

import urllib.request
from urllib.parse import unquote

from PySide6.QtCore import QObject, QSize, Qt, QThreadPool, QUrl, QRunnable, Signal
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional until installed
    np = None  # type: ignore[assignment]


def enhance_image(image: QImage, *, denoise: bool = True) -> QImage:
    """Display-only stretch (and optional sky denoise) for stacked JPEGs."""
    if image is None or image.isNull() or np is None:
        return image
    rgb = _qimage_to_rgb(image)
    if rgb.size == 0:
        return image
    work = rgb.astype(np.float32) * (1.0 / 255.0)
    lum = work[..., 0] * 0.2126 + work[..., 1] * 0.7152 + work[..., 2] * 0.0722
    step = max(1, min(lum.shape) // 256)
    sample = lum[::step, ::step]
    if sample.size < 16:
        return image

    sky = float(np.median(sample))
    mad = float(np.median(np.abs(sample - sky))) * 1.4826
    # Sit the black point just under the sky so grey fog clips and faint structure stays.
    black = max(0.0, min(float(np.percentile(sample, 1.2)), sky - 1.6 * max(mad, 1e-4)))
    white = max(float(np.percentile(sample, 99.92)), black + 0.12)
    span = white - black
    if span < 1e-4:
        return image

    stretched = np.clip((work - black) / span, 0.0, 1.0)
    sky_n = max(0.0, min(1.0, (sky - black) / span))
    # Washed previews (high leftover sky) get a harder midtone crush; already-dark stacks stay gentle.
    mid = 0.62 if sky_n > 0.12 else 0.52
    stretched = _mtf(stretched, mid)
    if denoise:
        stretched = _sky_denoise(stretched)

    out = np.clip(stretched * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    return _rgb_to_qimage(out)


def _mtf(values, mid: float):
    mid = min(0.95, max(0.05, float(mid)))
    denom = (2.0 * mid - 1.0) * values - mid
    return np.clip(((mid - 1.0) * values) / denom, 0.0, 1.0)


def _sky_denoise(rgb):
    lum = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    padded = np.pad(lum, 1, mode="edge")
    blur = (
        padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
        + padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:]
        + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
    ) / 9.0
    star = lum > (blur + 0.035)
    mixed = np.where(star, lum, blur * 0.72 + lum * 0.28)
    scale = mixed / np.clip(lum, 1e-6, None)
    scale = np.clip(scale, 0.45, 1.55)
    return np.clip(rgb * scale[..., None], 0.0, 1.0)


def _qimage_to_rgb(image: QImage):
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    if width <= 0 or height <= 0:
        return np.empty((0, 0, 3), dtype=np.uint8)
    stride = converted.bytesPerLine()
    ptr = converted.constBits()
    buf = np.frombuffer(ptr, dtype=np.uint8, count=stride * height).reshape(height, stride)
    rgba = buf[:, : width * 4].reshape(height, width, 4)
    return np.ascontiguousarray(rgba[:, :, :3])


def _rgb_to_qimage(rgb) -> QImage:
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    height, width = rgb.shape[:2]
    out = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
    return out.copy()


def load_image(url: str) -> QImage:
    text = (url or "").strip()
    if not text:
        return QImage()
    parsed = QUrl(text)
    if parsed.isLocalFile():
        return QImage(parsed.toLocalFile())
    if text.startswith(("http://", "https://")):
        request = urllib.request.Request(text, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        return QImage.fromData(data)
    return QImage(text)


class _EnhanceSignals(QObject):
    finished = Signal(object, str)


class _EnhanceJob(QRunnable):
    def __init__(self, url: str, requested_size: QSize, signals: _EnhanceSignals):
        super().__init__()
        self._url = url
        self._requested_size = requested_size
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            image = load_image(self._url)
            if image.isNull():
                self._signals.finished.emit(None, "Could not load image")
                return
            size = self._requested_size
            if size.isValid() and size.width() > 0 and size.height() > 0:
                if image.width() > size.width() or image.height() > size.height():
                    image = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            enhanced = enhance_image(image, denoise=True)
            self._signals.finished.emit(enhanced, "")
        except Exception as exc:
            try:
                self._signals.finished.emit(None, str(exc) or "Enhance failed")
            except RuntimeError:
                pass


class EnhanceImageResponse(QQuickImageResponse):
    def __init__(self, url: str, requested_size: QSize):
        super().__init__()
        self._image = QImage()
        self._error = ""
        self._signals = _EnhanceSignals(self)
        self._signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(_EnhanceJob(url, requested_size, self._signals))

    def _on_finished(self, image: object, error: str) -> None:
        if isinstance(image, QImage) and not image.isNull():
            self._image = image
            self._error = ""
        else:
            self._error = error or "Could not enhance image"
        self.finished.emit()

    def textureFactory(self):
        return QQuickTextureFactory.textureFactoryForImage(self._image)

    def errorString(self) -> str:
        return self._error


class EnhanceImageProvider(QQuickAsyncImageProvider):
    """`image://enhance/<urlencoded-url>` — display-only stretch + denoise."""

    def requestImageResponse(self, identity: str, requested_size: QSize) -> QQuickImageResponse:
        url = unquote(str(identity or "").lstrip("/"))
        return EnhanceImageResponse(url, requested_size)
