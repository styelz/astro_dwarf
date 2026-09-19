from __future__ import annotations

import hashlib
import logging
import math
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from PySide6.QtCore import QObject, QRunnable, QUrl, Signal
from PySide6.QtGui import QImage, QImageReader

from .domain import ALBUM_FITS_SUFFIXES, album_is_fits_name
from .image_enhance import _DISPLAY_EDGE, _rgb_to_qimage, canonical_image_url

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)

DEFAULT_BLACK_PCT = 1.0
DEFAULT_WHITE_PCT = 99.8
DEFAULT_MID = 0.32
_FITS_BLOCK = 2880
_HIGH_BIT_FORMATS = {
    QImage.Format.Format_Grayscale16,
    QImage.Format.Format_RGBX64,
    QImage.Format.Format_RGBA64,
    QImage.Format.Format_RGBA64_Premultiplied,
}


def stretch_available() -> bool:
    return np is not None


def url_suffix(url: str) -> str:
    text = canonical_image_url(url) or str(url or "").strip()
    if not text:
        return ""
    parsed = QUrl(text)
    path = parsed.toLocalFile() or parsed.path() or text
    return Path(unquote(str(path))).suffix.lower()


def is_fits_url(url: str) -> bool:
    return url_suffix(url) in ALBUM_FITS_SUFFIXES or album_is_fits_name("", url)


def stretch_cache_key(url: str, black: float, white: float, mid: float) -> str:
    return hashlib.sha1(
        f"v2:{black:.3f}:{white:.3f}:{mid:.3f}:{canonical_image_url(url) or url}".encode("utf-8", "replace")
    ).hexdigest()


def is_preview_cache_valid(path: Path | str) -> bool:
    dest = Path(path)
    try:
        if not dest.is_file() or dest.stat().st_size < 400:
            return False
    except OSError:
        return False
    reader = QImageReader(str(dest))
    size = reader.size()
    return bool(size.isValid() and size.width() > 0 and size.height() > 0)


def local_preview_path(url: str) -> Path | None:
    text = canonical_image_url(url) or str(url or "").strip()
    if not text:
        return None
    parsed = QUrl(text)
    if parsed.isLocalFile() or text.startswith("file:"):
        path = parsed.toLocalFile() or unquote(text.split("file:", 1)[-1].lstrip("/"))
        local = Path(path)
        if local.is_file():
            return local
        trimmed = str(path or "").lstrip("/")
        if len(trimmed) >= 2 and trimmed[1] == ":":
            local = Path(trimmed)
            if local.is_file():
                return local
        return None
    as_path = Path(text)
    return as_path if as_path.is_file() else None


def needs_stretch(url: str) -> bool:
    if is_fits_url(url):
        return True
    local = local_preview_path(url)
    if local is None:
        return False
    if local.suffix.lower() not in {".png", ".tif", ".tiff"}:
        return False
    reader = QImageReader(str(local))
    if not reader.canRead():
        return False
    return reader.imageFormat() in _HIGH_BIT_FORMATS


def load_preview_bytes(url: str) -> bytes:
    local = local_preview_path(url)
    if local is not None:
        return local.read_bytes()
    text = canonical_image_url(url) or str(url or "").strip()
    parsed = QUrl(text)
    if parsed.scheme() not in {"http", "https"} and not text.startswith(("http://", "https://")):
        raise FileNotFoundError(f"No local file for {url}")
    fetches = []
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
                headers={"User-Agent": "AstroDwarf", "Accept": "*/*"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read()
            if data:
                return data
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError(f"Could not load {url}")


def _fits_card_value(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return None
    if "/" in text:
        in_quote = False
        cut = len(text)
        for i, ch in enumerate(text):
            if ch == "'":
                in_quote = not in_quote
            elif ch == "/" and not in_quote:
                cut = i
                break
        text = text[:cut].strip()
    if text in {"T", "F"}:
        return text == "T"
    if text.startswith("'"):
        return text.strip("'").replace("''", "'").strip()
    try:
        if any(ch in text for ch in ".Ee"):
            return float(text)
        return int(text)
    except ValueError:
        return text


def parse_fits_header(data: bytes, offset: int = 0) -> tuple[dict[str, Any], int]:
    header: dict[str, Any] = {}
    while offset + 80 <= len(data):
        card = data[offset : offset + 80].decode("ascii", "replace")
        offset += 80
        key = card[:8].rstrip()
        if key == "END":
            pad = (_FITS_BLOCK - (offset % _FITS_BLOCK)) % _FITS_BLOCK
            return header, offset + pad
        if len(card) >= 10 and card[8:10] == "= ":
            header[key] = _fits_card_value(card[10:80])
        if offset % _FITS_BLOCK == 0 and "END" in header:
            return header, offset
    raise ValueError("FITS header is truncated")


def _fits_dtype(bitpix: int):
    mapping = {
        8: np.dtype("u1"),
        16: np.dtype(">i2"),
        32: np.dtype(">i4"),
        64: np.dtype(">i8"),
        -32: np.dtype(">f4"),
        -64: np.dtype(">f8"),
    }
    try:
        return mapping[int(bitpix)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported FITS BITPIX {bitpix}") from exc


def _fits_data_nbytes(header: dict[str, Any]) -> int:
    naxis = int(header.get("NAXIS") or 0)
    bitpix = abs(int(header.get("BITPIX") or 0))
    bytepix = bitpix // 8
    if bytepix <= 0:
        return 0
    pixels = 0
    if naxis > 0:
        pixels = 1
        for index in range(1, naxis + 1):
            pixels *= int(header.get(f"NAXIS{index}") or 0)
    pcount = max(int(header.get("PCOUNT") or 0), 0)
    gcount = max(int(header.get("GCOUNT") or 1), 1)
    return bytepix * gcount * (pcount + pixels)


def _fits_skip_data(offset: int, nbytes: int) -> int:
    if nbytes <= 0:
        return offset
    return offset + ((nbytes + _FITS_BLOCK - 1) // _FITS_BLOCK) * _FITS_BLOCK


def _fits_is_image_hdu(header: dict[str, Any]) -> bool:
    naxis = int(header.get("NAXIS") or 0)
    if naxis < 2:
        return False
    if header.get("ZIMAGE"):
        return False
    xtension = str(header.get("XTENSION") or "IMAGE").strip().upper()
    if xtension in {"BINTABLE", "TABLE", "A3DTABLE"}:
        return False
    dims = [int(header.get(f"NAXIS{i}") or 0) for i in range(1, naxis + 1)]
    return all(size > 0 for size in dims)


def _fits_display_array(arr):
    """Turn a FITS HDU into a 2D gray or H×W×3 RGB array for preview.

    Dwarf stacked-16 files store RGB as NAXIS3=3, so numpy sees (3, H, W).
    Using that as height×width paints a 3-pixel-tall strip.
    """
    work = np.squeeze(arr)
    while work.ndim > 3:
        work = np.squeeze(work[0])
    if work.ndim <= 2:
        return np.ascontiguousarray(work)

    def _image_pair(a: int, b: int) -> bool:
        return a > 4 and b > 4

    shape = work.shape
    if shape[0] in (3, 4) and _image_pair(shape[1], shape[2]):
        work = np.moveaxis(work, 0, -1)
        return np.ascontiguousarray(work[..., :3])
    if shape[2] in (3, 4) and _image_pair(shape[0], shape[1]):
        return np.ascontiguousarray(work[..., :3])
    if shape[1] in (3, 4) and _image_pair(shape[0], shape[2]):
        work = np.moveaxis(work, 1, -1)
        return np.ascontiguousarray(work[..., :3])
    return np.ascontiguousarray(np.take(work, 0, axis=int(np.argmin(shape))))


def decode_fits_image(data: bytes) -> "np.ndarray":
    if np is None:
        raise RuntimeError("numpy is required to preview FITS")
    if not data.startswith(b"SIMPLE"):
        raise ValueError("Not a FITS file")
    offset = 0
    while offset + _FITS_BLOCK <= len(data):
        header, offset = parse_fits_header(data, offset)
        nbytes = _fits_data_nbytes(header)
        if not _fits_is_image_hdu(header):
            offset = _fits_skip_data(offset, nbytes)
            continue
        naxis = int(header.get("NAXIS") or 0)
        dims = [int(header.get(f"NAXIS{i}") or 0) for i in range(1, naxis + 1)]
        dtype = _fits_dtype(int(header.get("BITPIX") or 0))
        raw = data[offset : offset + nbytes]
        if len(raw) < nbytes:
            raise ValueError("FITS image data is truncated")
        offset = _fits_skip_data(offset, nbytes)
        arr = np.frombuffer(raw, dtype=dtype, count=math.prod(dims)).reshape(tuple(reversed(dims))).astype(np.float32)
        bscale = float(header.get("BSCALE") or 1.0)
        bzero = float(header.get("BZERO") or 0.0)
        if bscale != 1.0 or bzero != 0.0:
            arr = arr * np.float32(bscale) + np.float32(bzero)
        return _fits_display_array(arr)
    raise ValueError("FITS file has no image HDU")


def _qimage_to_float(image: QImage):
    if image is None or image.isNull() or np is None:
        return np.empty((0, 0), dtype=np.float32)
    fmt = image.format()
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    ptr = image.constBits()
    if fmt == QImage.Format.Format_Grayscale16:
        buf = np.frombuffer(ptr, dtype=np.uint16, count=(stride // 2) * height).reshape(height, stride // 2)
        return buf[:, :width].astype(np.float32)
    if fmt in {
        QImage.Format.Format_RGBX64,
        QImage.Format.Format_RGBA64,
        QImage.Format.Format_RGBA64_Premultiplied,
    }:
        buf = np.frombuffer(ptr, dtype=np.uint16, count=(stride // 2) * height).reshape(height, stride // 2)
        rgba = buf[:, : width * 4].reshape(height, width, 4).astype(np.float32)
        return rgba[:, :, :3]
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    stride = converted.bytesPerLine()
    ptr = converted.constBits()
    buf = np.frombuffer(ptr, dtype=np.uint8, count=stride * height).reshape(height, stride)
    rgba = buf[:, : width * 4].reshape(height, width, 4).astype(np.float32)
    return rgba[:, :, :3]


def load_stretch_array(url: str):
    text = canonical_image_url(url) or str(url or "").strip()
    if is_fits_url(text):
        return decode_fits_image(load_preview_bytes(text))
    local = local_preview_path(text)
    if local is not None:
        image = QImage(str(local))
        if image.isNull():
            raise RuntimeError(f"Could not decode {local.name}")
        return _qimage_to_float(image)
    data = load_preview_bytes(text)
    if data.startswith(b"SIMPLE"):
        return decode_fits_image(data)
    image = QImage.fromData(data)
    if image.isNull():
        raise RuntimeError(f"Could not decode image from {url}")
    return _qimage_to_float(image)


def _downsample(arr, max_edge: int = _DISPLAY_EDGE):
    if arr.ndim == 1 or max(arr.shape[:2]) <= max_edge:
        return arr
    height, width = arr.shape[:2]
    step = max(1, math.ceil(max(height, width) / max_edge))
    return arr[::step, ::step] if arr.ndim == 2 else arr[::step, ::step, ...]


def apply_stretch(arr, black: float = DEFAULT_BLACK_PCT, white: float = DEFAULT_WHITE_PCT, mid: float = DEFAULT_MID):
    if np is None:
        raise RuntimeError("numpy is required to preview FITS")
    work = _downsample(np.ascontiguousarray(arr))
    finite = work[np.isfinite(work)]
    if finite.size == 0:
        raise RuntimeError("FITS image has no finite pixels")
    lo = float(np.percentile(finite, min(max(black, 0.0), 30.0)))
    hi = float(np.percentile(finite, min(max(white, 70.0), 100.0)))
    if not math.isfinite(lo) or not math.isfinite(hi) or hi <= lo:
        lo = float(np.min(finite))
        hi = float(np.max(finite))
    if hi <= lo:
        hi = lo + 1.0
    scaled = np.clip((work - lo) / (hi - lo), 0.0, 1.0)
    mid_v = min(max(float(mid), 0.05), 0.95)
    if abs(mid_v - 0.5) > 1e-4:
        gamma = math.log(0.5) / math.log(mid_v)
        scaled = np.power(scaled, gamma)
    rgb8 = np.clip(scaled * 255.0 + 0.5, 0.0, 255.0).astype(np.uint8)
    if rgb8.ndim == 2:
        rgb8 = np.repeat(rgb8[:, :, None], 3, axis=2)
    elif rgb8.ndim == 3 and rgb8.shape[2] == 1:
        rgb8 = np.repeat(rgb8, 3, axis=2)
    elif rgb8.ndim == 3 and rgb8.shape[2] > 3:
        rgb8 = rgb8[:, :, :3]
    return _rgb_to_qimage(rgb8)


def render_stretch_preview(
    url: str,
    black: float = DEFAULT_BLACK_PCT,
    white: float = DEFAULT_WHITE_PCT,
    mid: float = DEFAULT_MID,
) -> QImage:
    return apply_stretch(load_stretch_array(url), black, white, mid)


def write_stretch_preview(
    url: str,
    dest: Path,
    black: float = DEFAULT_BLACK_PCT,
    white: float = DEFAULT_WHITE_PCT,
    mid: float = DEFAULT_MID,
) -> Path:
    image = render_stretch_preview(url, black, white, mid)
    if image is None or image.isNull():
        raise RuntimeError("Stretch returned an empty image")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.jpg")
    if not QImage(image).save(str(tmp), "JPG", 90):
        raise RuntimeError("Could not write FITS preview")
    tmp.replace(dest)
    return dest


class MediaPreviewSignals(QObject):
    finished = Signal(str)


class CacheStretchJob(QRunnable):
    def __init__(
        self,
        key: str,
        url: str,
        dest: Path,
        black: float,
        white: float,
        mid: float,
        signals: MediaPreviewSignals,
    ):
        super().__init__()
        self._key = key
        self._url = url
        self._dest = Path(dest)
        self._black = black
        self._white = white
        self._mid = mid
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            if not stretch_available():
                raise RuntimeError("numpy is not installed; cannot preview FITS")
            write_stretch_preview(self._url, self._dest, self._black, self._white, self._mid)
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                _log.debug("Media stretch skipped for %s: HTTP %s", self._key, exc.code)
            else:
                _log.exception("Media stretch failed for %s", self._key)
            try:
                self._dest.with_suffix(".part.jpg").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._signals.finished.emit(self._key)
        except RuntimeError:
            pass
