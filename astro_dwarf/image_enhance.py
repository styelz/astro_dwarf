from __future__ import annotations

import hashlib
import logging
import threading
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QEventLoop, QObject, QSize, Qt, QThreadPool, QTimer, QUrl, QRunnable, Signal
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
_NUMPY_WARNED = False


def enhance_available() -> bool:
    return np is not None


def _warn_numpy_missing() -> None:
    global _NUMPY_WARNED
    if _NUMPY_WARNED:
        return
    _NUMPY_WARNED = True
    _log.warning("numpy is not installed; showing original images instead of enhanced ones")


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


def canonical_image_url(url: str) -> str:
    """One encoding for cache keys and loaders: local files are FullyEncoded file:// URLs."""
    text = str(url or "").strip()
    if not text:
        return ""
    as_path = Path(text)
    if as_path.is_file():
        return QUrl.fromLocalFile(str(as_path.resolve())).toString(QUrl.ComponentFormattingOption.FullyEncoded)
    parsed = QUrl(text)
    if parsed.isLocalFile() or text.startswith("file:"):
        path = parsed.toLocalFile() or unquote(text.split("file:", 1)[-1].lstrip("/"))
        local = Path(path)
        if not local.is_file() and path:
            trimmed = path.lstrip("/")
            if len(trimmed) >= 2 and trimmed[1] == ":":
                local = Path(trimmed)
        if local.is_file():
            return QUrl.fromLocalFile(str(local.resolve())).toString(QUrl.ComponentFormattingOption.FullyEncoded)
        if path:
            return QUrl.fromLocalFile(str(Path(path))).toString(QUrl.ComponentFormattingOption.FullyEncoded)
    if parsed.scheme() in {"http", "https"} or text.startswith(("http://", "https://")):
        return text
    return text


def enhance_cache_key(url: str, profile: str) -> str:
    kind = "deep" if str(profile or "").strip().lower() == "deep" else "std"
    return hashlib.sha1(f"v8:{kind}:{canonical_image_url(url) or url}".encode("utf-8", "replace")).hexdigest()


def is_enhance_cache_valid(path: Path | str) -> bool:
    """Reject leftover full-size originals that used to be stored as 'enhanced'."""
    dest = Path(path)
    try:
        if not dest.is_file() or dest.stat().st_size < 1000:
            return False
    except OSError:
        return False
    image = QImage(str(dest))
    if image.isNull():
        return False
    return max(image.width(), image.height()) <= _DISPLAY_EDGE + 2


def enhance_image(image: QImage, *, denoise: bool = True, profile: str = "standard") -> QImage:
    """Display-only: smooth grain, clip the sky to black, keep nebula/stars."""
    if image is None or image.isNull():
        return image
    if np is None:
        _warn_numpy_missing()
        return _fit_display(image)
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
    cleaned = _nlmeans(rgb, h=14.0 if deep else 9.0, search=21)
    if cv2 is not None:
        u8 = np.clip(cleaned * 255.0, 0, 255).astype(np.uint8)
        blur = cv2.bilateralFilter(u8, 9 if deep else 7, 36 if deep else 24, 36 if deep else 24)
        blur = blur.astype(np.float32) * (1.0 / 255.0)
        lum = _luminance(cleaned)
        sky = np.clip(1.0 - lum * 3.2, 0.0, 1.0)[..., None]
        cleaned = blur * sky + cleaned * (1.0 - sky)
    return np.clip(cleaned, 0.0, 1.0)


def _crush_sky(rgb, *, deep: bool):
    """Pull the grainy sky down a bit without burying the object."""
    lum = _luminance(rgb)
    step = max(1, min(lum.shape) // 280)
    sample = lum[::step, ::step]
    if sample.size < 16:
        return rgb
    sky = float(np.median(sample))
    floor = float(np.percentile(sample, 10 if deep else 8))
    mad = float(np.median(np.abs(sample - np.median(sample)))) * 1.4826
    extra = 0.35 if deep else 0.18
    cap = 0.10 if deep else 0.07
    black = min(floor + extra * max(mad, 1e-4), cap, sky * (0.55 if deep else 0.40))
    crushed = np.clip(rgb - black, 0.0, 1.0)
    return crushed


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
    as_path = Path(text)
    if as_path.is_file():
        image = QImage(str(as_path))
        if not image.isNull():
            return image
    parsed = QUrl(text)
    if parsed.isLocalFile() or text.startswith("file:"):
        path = parsed.toLocalFile() or unquote(text.split("file:", 1)[-1].lstrip("/"))
        for candidate in (path, path.lstrip("/")):
            if not candidate:
                continue
            image = QImage(candidate)
            if not image.isNull():
                return image
        return QImage()
    if parsed.scheme() in {"http", "https"} or text.startswith(("http://", "https://")):
        return _load_http_image(text, parsed)
    image = QImage(text)
    if not image.isNull():
        return image
    return QImage()


def _load_http_image(text: str, parsed: QUrl) -> QImage:
    fetches: list[str] = []
    for fetch in (
        text,
        parsed.toString(QUrl.ComponentFormattingOption.FullyEncoded),
        parsed.toString(),
    ):
        if fetch and fetch not in fetches:
            fetches.append(fetch)
    last_error: Exception | None = None
    for fetch in fetches:
        try:
            request = urllib.request.Request(
                fetch,
                headers={"User-Agent": "AstroDwarf", "Accept": "image/jpeg,image/*,*/*"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            image = QImage.fromData(data)
            if not image.isNull():
                return image
            last_error = RuntimeError(f"Could not decode image from {fetch}")
        except Exception as exc:
            last_error = exc
    image = _load_http_qt(parsed)
    if not image.isNull():
        return image
    if last_error:
        raise last_error
    raise RuntimeError(f"Could not load image from {text}")


def _load_http_qt(parsed: QUrl) -> QImage:
    try:
        from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
    except ImportError:
        return QImage()
    manager = QNetworkAccessManager()
    request = QNetworkRequest(parsed)
    request.setRawHeader(b"User-Agent", b"AstroDwarf")
    request.setRawHeader(b"Accept", b"image/jpeg,image/*,*/*")
    reply = manager.get(request)
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    reply.finished.connect(loop.quit)
    timer.start(90_000)
    loop.exec()
    try:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            _log.warning("Qt HTTP enhance fetch failed: %s", reply.errorString())
            return QImage()
        image = QImage.fromData(bytes(reply.readAll()))
        return image
    finally:
        reply.deleteLater()
        manager.deleteLater()


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
            image = load_image(canonical_image_url(self._url) or self._url)
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
            if not enhance_available():
                _warn_numpy_missing()
            else:
                image = load_image(canonical_image_url(self._url) or self._url)
                if image.isNull():
                    raise RuntimeError(f"Could not load {self._url}")
                out = enhance_image(image, denoise=True, profile=self._profile)
                if out is None or out.isNull():
                    raise RuntimeError("Enhance returned an empty image")
                if max(out.width(), out.height()) > _DISPLAY_EDGE + 2:
                    raise RuntimeError(
                        f"Enhance left a full-size frame {out.width()}x{out.height()}; refusing to cache it"
                    )
                saved = QImage(out)
                self._dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._dest.with_suffix(".part.jpg")
                if not saved.save(str(tmp), "JPG", 90):
                    raise RuntimeError("Could not write enhanced JPEG")
                tmp.replace(self._dest)
                _log.info(
                    "Enhance cache %s %s %sx%s -> %sx%s",
                    self._profile,
                    self._key[:8],
                    image.width(),
                    image.height(),
                    saved.width(),
                    saved.height(),
                )
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
