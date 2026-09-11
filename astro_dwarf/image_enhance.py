from __future__ import annotations

import hashlib
import logging
import threading
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QObject, QSize, Qt, QThreadPool, QUrl, QRunnable, Signal
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

_log = logging.getLogger(__name__)

_URLS: dict[str, str] = {}
_URL_LOCK = threading.Lock()
_DISPLAY_EDGE = 1920


def set_model_dir(path: Path | str | None) -> None:
    """Kept so older callers still import; models are no longer downloaded."""
    return


def register_enhance_url(url: str) -> str:
    """Store a file/http URL and return a slash-free token for image://enhance."""
    text = (url or "").strip()
    key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
    with _URL_LOCK:
        _URLS[key] = text
    return key


def lookup_enhance_url(key: str) -> str:
    with _URL_LOCK:
        return _URLS.get(str(key or "").strip(), "")


def enhance_cache_key(url: str, profile: str) -> str:
    kind = "deep" if str(profile or "").strip().lower() == "deep" else "std"
    return hashlib.sha1(f"v5:{kind}:{url}".encode("utf-8", "replace")).hexdigest()


def enhance_image(image: QImage, *, denoise: bool = True, profile: str = "standard") -> QImage:
    """Display-only: smooth grain, clip the sky to black, keep nebula/stars."""
    if image is None or image.isNull():
        return image
    if np is None:
        _log.warning("numpy is not installed; enhance cannot run")
        return image
    image = _fit_display(image)
    rgb = _qimage_to_rgb(image)
    if rgb.size == 0:
        return image
    work = rgb.astype(np.float32) * (1.0 / 255.0)
    deep = str(profile or "standard").strip().lower() == "deep"
    if denoise:
        work = _smooth_noise(work, deep=deep)
    work = _crush_sky(work, deep=deep)
    out = np.clip(work * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    return _rgb_to_qimage(out)


def _fit_display(image: QImage, max_edge: int = _DISPLAY_EDGE) -> QImage:
    width, height = image.width(), image.height()
    if max(width, height) <= max_edge:
        return image
    return image.scaled(
        max_edge,
        max_edge,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _smooth_noise(rgb, *, deep: bool):
    cleaned = _nlmeans(rgb, h=20.0 if deep else 14.0, search=21)
    if cv2 is not None:
        u8 = np.clip(cleaned * 255.0, 0, 255).astype(np.uint8)
        blur = cv2.bilateralFilter(u8, 11 if deep else 9, 56 if deep else 48, 56 if deep else 48)
        blur = blur.astype(np.float32) * (1.0 / 255.0)
        lum = _luminance(cleaned)
        sky = np.clip(1.0 - lum * 3.2, 0.0, 1.0)[..., None]
        cleaned = blur * sky + cleaned * (1.0 - sky)
    return np.clip(cleaned, 0.0, 1.0)


def _crush_sky(rgb, *, deep: bool):
    """Clip through the noisy sky floor. Gamma < 1 brings nebula back; clipped sky stays black."""
    lum = _luminance(rgb)
    step = max(1, min(lum.shape) // 280)
    sample = lum[::step, ::step]
    if sample.size < 16:
        return rgb
    sky = float(np.percentile(sample, 20 if deep else 18))
    mad = float(np.median(np.abs(sample - np.median(sample)))) * 1.4826
    extra = 0.90 if deep else 0.65
    cap = float(np.percentile(sample, 38 if deep else 35))
    black = min(sky + extra * max(mad, 1e-4), cap)
    crushed = np.clip(rgb - black, 0.0, 1.0)
    gamma = 0.90 if deep else 0.88
    return np.clip(np.power(np.maximum(crushed, 0.0), gamma), 0.0, 1.0)


def _nlmeans(rgb, *, h: float, search: int):
    if cv2 is not None:
        u8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
        bgr = cv2.cvtColor(u8, cv2.COLOR_RGB2BGR)
        out = cv2.fastNlMeansDenoisingColored(bgr, None, float(h), float(h), 7, int(search))
        return cv2.cvtColor(out, cv2.COLOR_BGR2RGB).astype(np.float32) * (1.0 / 255.0)
    return _numpy_sky_blur(rgb)


def _numpy_sky_blur(rgb):
    lum = _luminance(rgb)
    padded = np.pad(lum, 2, mode="edge")
    acc = np.zeros_like(lum)
    for dy in range(5):
        for dx in range(5):
            acc += padded[dy : dy + lum.shape[0], dx : dx + lum.shape[1]]
    blur = acc / 25.0
    star = lum > (blur + 0.03)
    mixed = np.where(star, lum, blur * 0.78 + lum * 0.22)
    scale = mixed / np.clip(lum, 1e-6, None)
    return np.clip(rgb * np.clip(scale, 0.4, 1.6)[..., None], 0.0, 1.0)


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


def parse_enhance_id(identity: str) -> tuple[str, str]:
    text = unquote(str(identity or "").lstrip("/"))
    for prefix, profile in (("deep--", "deep"), ("std--", "standard"), ("deep/", "deep"), ("std/", "standard")):
        if text.startswith(prefix):
            rest = unquote(text[len(prefix) :])
            return profile, lookup_enhance_url(rest) or rest
    return "standard", lookup_enhance_url(text) or text


class _EnhanceSignals(QObject):
    finished = Signal(object, str)


class _EnhanceJob(QRunnable):
    def __init__(self, url: str, requested_size: QSize, profile: str, signals: _EnhanceSignals):
        super().__init__()
        self._url = url
        self._requested_size = requested_size
        self._profile = profile
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
                    image = image.scaled(
                        size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
            enhanced = enhance_image(image, denoise=True, profile=self._profile)
            self._signals.finished.emit(enhanced, "")
        except Exception as exc:
            try:
                self._signals.finished.emit(None, str(exc) or "Enhance failed")
            except RuntimeError:
                pass


class EnhanceImageResponse(QQuickImageResponse):
    def __init__(self, url: str, requested_size: QSize, profile: str = "standard"):
        super().__init__()
        self._image = QImage()
        self._error = ""
        self._signals = _EnhanceSignals(self)
        self._signals.finished.connect(self._on_finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(_EnhanceJob(url, requested_size, profile, self._signals))

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
    """`image://enhance/std--<sha1>` or `image://enhance/deep--<sha1>`."""

    def requestImageResponse(self, identity: str, requested_size: QSize) -> QQuickImageResponse:
        profile, url = parse_enhance_id(identity)
        return EnhanceImageResponse(url, requested_size, profile)


class CacheEnhanceSignals(QObject):
    finished = Signal(str)


class CacheEnhanceJob(QRunnable):
    """Write an enhanced JPEG to dest, then notify with the cache key."""

    def __init__(self, key: str, url: str, profile: str, dest: Path, signals: CacheEnhanceSignals):
        super().__init__()
        self._key = key
        self._url = url
        self._profile = profile
        self._dest = Path(dest)
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            image = load_image(self._url)
            if image.isNull():
                raise RuntimeError(f"Could not load {self._url}")
            out = enhance_image(image, denoise=True, profile=self._profile)
            self._dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._dest.with_suffix(".part.jpg")
            if not out.save(str(tmp), "JPG", 90):
                raise RuntimeError("Could not write enhanced JPEG")
            tmp.replace(self._dest)
        except Exception:
            _log.exception("Enhance cache failed for %s", self._key)
            try:
                self._dest.with_suffix(".part.jpg").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._signals.finished.emit(self._key)
        except RuntimeError:
            pass


class PreviewEnhanceSignals(QObject):
    finished = Signal(int, str, object)


class PreviewEnhanceJob(QRunnable):
    def __init__(self, token: int, camera: str, image: QImage, profile: str, signals: PreviewEnhanceSignals):
        super().__init__()
        self._token = token
        self._camera = camera
        self._image = image
        self._profile = profile
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            out = enhance_image(self._image, denoise=True, profile=self._profile)
        except Exception:
            out = self._image
        try:
            self._signals.finished.emit(self._token, self._camera, out)
        except RuntimeError:
            pass
