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

try:
    import onnxruntime as ort
except ImportError:  # pragma: no cover
    ort = None

_log = logging.getLogger(__name__)

_MODEL_DIR: Path | None = None
_URLS: dict[str, str] = {}
_URL_LOCK = threading.Lock()
_ONNX_LOCK = threading.Lock()
_ONNX_SESSION = None
_ONNX_INPUT = ""
_ONNX_FAILED = False

# Single-file general denoiser (~30 MB). Cached under the app data dir on first Deep Clean.
_ONNX_NAME = "1xDeNoise_realplksr_otf.onnx"
_ONNX_URL = (
    "https://huggingface.co/hugglyberry/upscale-and-refine-models/resolve/main/"
    "1xDeNoise_realplksr_otf.onnx"
)


def set_model_dir(path: Path | str | None) -> None:
    global _MODEL_DIR
    _MODEL_DIR = Path(path) if path else None


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


def enhance_image(image: QImage, *, denoise: bool = True, profile: str = "standard") -> QImage:
    """Display-only asinh stretch and denoise. profile is 'standard' or 'deep'."""
    if image is None or image.isNull() or np is None:
        return image
    rgb = _qimage_to_rgb(image)
    if rgb.size == 0:
        return image
    work = rgb.astype(np.float32) * (1.0 / 255.0)
    deep = str(profile or "standard").strip().lower() == "deep"
    stretched = _asinh_display(work, punch=22.0 if deep else 16.0)
    if denoise:
        stretched = _denoise_starsafe(stretched, deep=deep)
        if deep:
            stretched = _onnx_denoise(stretched)
    out = np.clip(stretched * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    return _rgb_to_qimage(out)


def _asinh_display(rgb, punch: float):
    lum = _luminance(rgb)
    step = max(1, min(lum.shape) // 320)
    sample = lum[::step, ::step]
    if sample.size < 16:
        return rgb
    sky = float(np.median(sample))
    mad = float(np.median(np.abs(sample - sky))) * 1.4826
    # Clip through the sky floor so already-stretched Dwarf JPEGs still lose fog.
    black = max(0.0, min(float(np.percentile(sample, 8.0)), sky + 0.15 * max(mad, 1e-4)))
    white = max(float(np.percentile(sample, 99.6)), black + 0.10)
    scale = max(white - black, 1e-4)
    x = np.clip((rgb - black) / scale, 0.0, None)
    stretched = np.arcsinh(x * punch) / np.arcsinh(punch)
    return np.clip(stretched, 0.0, 1.0)


def _luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def _star_weight(lum):
    """0 = sky (safe to denoise), 1 = star core (keep sharp)."""
    if cv2 is not None:
        blur = cv2.GaussianBlur(lum, (9, 9), 0)
        excess = lum - blur
        thresh = max(0.028, float(np.percentile(excess, 93)))
        mask = (excess > thresh).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.dilate(mask, kernel)
        return cv2.GaussianBlur(mask.astype(np.float32), (7, 7), 0)
    padded = np.pad(lum, 2, mode="edge")
    acc = np.zeros_like(lum)
    for dy in range(5):
        for dx in range(5):
            acc += padded[dy : dy + lum.shape[0], dx : dx + lum.shape[1]]
    blur = acc / 25.0
    excess = lum - blur
    thresh = max(0.028, float(np.percentile(excess, 93)))
    return np.clip((excess - thresh) / 0.08, 0.0, 1.0)


def _denoise_starsafe(rgb, *, deep: bool):
    stars = _star_weight(_luminance(rgb))[..., None]
    cleaned = _nlmeans(rgb, h=11.0 if deep else 7.0, search=21 if deep else 15)
    if deep and cv2 is not None:
        u8 = np.clip(cleaned * 255.0, 0, 255).astype(np.uint8)
        cleaned = cv2.bilateralFilter(u8, 7, 28, 28).astype(np.float32) * (1.0 / 255.0)
    return np.clip(cleaned * (1.0 - stars) + rgb * stars, 0.0, 1.0)


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


def _onnx_denoise(rgb):
    session, input_name = _onnx_session()
    if session is None or not input_name:
        return rgb
    try:
        return _onnx_run(session, input_name, rgb)
    except Exception:
        _log.exception("ONNX denoise failed; using classical result")
        return rgb


def _onnx_session():
    global _ONNX_SESSION, _ONNX_INPUT, _ONNX_FAILED
    if ort is None or _ONNX_FAILED:
        return None, ""
    with _ONNX_LOCK:
        if _ONNX_SESSION is not None:
            return _ONNX_SESSION, _ONNX_INPUT
        path = _ensure_onnx_model()
        if path is None:
            _ONNX_FAILED = True
            return None, ""
        try:
            session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            _ONNX_SESSION = session
            _ONNX_INPUT = session.get_inputs()[0].name
            return session, _ONNX_INPUT
        except Exception:
            _log.exception("Could not load ONNX denoise model")
            _ONNX_FAILED = True
            return None, ""


def _ensure_onnx_model() -> Path | None:
    folder = _MODEL_DIR or (Path.home() / ".astro-dwarf" / "models")
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / _ONNX_NAME
    if dest.is_file() and dest.stat().st_size > 1_000_000:
        return dest
    tmp = dest.with_suffix(".part")
    try:
        request = urllib.request.Request(_ONNX_URL, headers={"User-Agent": "AstroDwarf"})
        with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        if tmp.stat().st_size < 1_000_000:
            tmp.unlink(missing_ok=True)
            return None
        tmp.replace(dest)
        return dest
    except Exception:
        _log.exception("Could not download ONNX denoise model")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _onnx_run(session, input_name: str, rgb):
    height, width = rgb.shape[:2]
    tile = 512
    overlap = 24
    if height * width <= tile * tile:
        return _onnx_infer(session, input_name, rgb)
    out = np.zeros_like(rgb)
    weight = np.zeros((height, width, 1), dtype=np.float32)
    ramp = np.linspace(0.15, 1.0, overlap, dtype=np.float32)
    for y0 in range(0, height, tile - overlap):
        for x0 in range(0, width, tile - overlap):
            y1 = min(height, y0 + tile)
            x1 = min(width, x0 + tile)
            patch = rgb[y0:y1, x0:x1]
            cleaned = _onnx_infer(session, input_name, patch)
            mask = np.ones((y1 - y0, x1 - x0, 1), dtype=np.float32)
            if y0 > 0:
                mask[:overlap, :, 0] *= ramp
            if x0 > 0:
                mask[:, :overlap, 0] *= ramp
            if y1 < height:
                mask[-overlap:, :, 0] *= ramp[::-1]
            if x1 < width:
                mask[:, -overlap:, 0] *= ramp[::-1]
            out[y0:y1, x0:x1] += cleaned * mask
            weight[y0:y1, x0:x1] += mask
    return np.clip(out / np.clip(weight, 1e-6, None), 0.0, 1.0)


def _onnx_infer(session, input_name: str, rgb):
    src_h, src_w = rgb.shape[:2]
    padded, src_h, src_w = _pad_hw(rgb, 16)
    nchw = np.transpose(padded, (2, 0, 1))[None, ...].astype(np.float32)
    raw = session.run(None, {input_name: nchw})[0]
    out = np.squeeze(raw)
    if out.ndim == 3 and out.shape[0] in (1, 3, 4):
        out = np.transpose(out, (1, 2, 0))
    if out.ndim == 2:
        out = np.repeat(out[..., None], 3, axis=2)
    out = out[:src_h, :src_w, :3].astype(np.float32)
    # Residual models stay near zero; reconstruction models stay in 0-1.
    if float(np.mean(np.abs(out))) < 0.18 or float(out.min()) < -0.02:
        out = padded[:src_h, :src_w] - out
    return np.clip(out, 0.0, 1.0)


def _pad_hw(rgb, multiple: int):
    height, width = rgb.shape[:2]
    pad_h = (multiple - height % multiple) % multiple
    pad_w = (multiple - width % multiple) % multiple
    if pad_h or pad_w:
        rgb = np.pad(rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
    return rgb, height, width


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
