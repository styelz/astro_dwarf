"""Stitch a DWARF panorama session into one JPEG.

The session folder holds the full-size tiles, named ``row_col.jpg``. Folders
``1`` through ``5`` repeat that grid at smaller sizes. The phone's quick view
uses a small folder. A sharp view uses the full-size tiles, scaled to fit a
desktop image.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QRunnable, Signal

from .domain import album_http_path, album_http_url, album_listing_entries, album_session_dir

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

DEFAULT_OVERLAP = 0.20
PREVIEW_MAX_EDGE = 2048
SHARP_MAX_EDGE = 4096
PREVIEW_LEVELS = (5, 4, 3, 2, 1, 0)
SHARP_LEVELS = (0, 1, 2, 3, 4, 5)
_LEVEL_DIRS = {"1", "2", "3", "4", "5"}
_TILE_NAME = re.compile(r"^(\d+)_(\d+)\.(?:jpg|jpeg)$", re.IGNORECASE)
_SCENE = re.compile(
    r"_pv_create_scene\(\s*[^,]+,\s*"
    r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*"
    r"[^,]+,\s*[^,]+,\s*[^,]+,\s*[^,]+,\s*"
    r"([\d.]+)\s*,\s*([\d.]+)\s*,\s*"
    r"[^,]+,\s*[^,]+,\s*"
    r"([\d.]+)\s*\)"
)


class _Cancelled(RuntimeError):
    pass


@dataclass(slots=True)
class PanoramaBuild:
    path: str
    detail: str
    rows: int
    cols: int
    level: int
    tile_width: int
    tile_height: int
    overlap: float


class PanoramaSignals(QObject):
    progress = Signal(int, int, int)
    finished = Signal(int, str, str, str)


def panorama_available() -> bool:
    return np is not None and cv2 is not None


def panorama_geometry(entry: dict[str, Any] | None) -> dict[str, Any]:
    """Rows, columns, and tile size from an album mediaInfos row."""
    source = entry if isinstance(entry, dict) else {}
    param = source.get("panoParam") if isinstance(source.get("panoParam"), dict) else {}

    def number(key: str) -> int:
        try:
            value = int(param.get(key) or 0)
        except (TypeError, ValueError):
            return 0
        return value if value > 0 else 0

    return {
        "pano_rows": number("panoRows"),
        "pano_cols": number("panoCols"),
        "pano_tile_width": number("imageWidth"),
        "pano_tile_height": number("imageHeight"),
        "pano_preview_path": str(source.get("panoPreviewUrl") or "").strip(),
    }


def panorama_progress_update(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
    remembered: tuple[int, int] | None,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Remember tile progress while a shoot is running.

    The second value is ``(done, total)`` when this delta is the shoot
    finishing with every tile taken. A stop before the last tile returns
    no finish, and the memory is cleared.
    """
    prior = previous if isinstance(previous, dict) else {}
    delta = current if isinstance(current, dict) else {}
    prev_state = str(prior.get("panorama_state") or "")
    if delta.get("panorama_state") not in (None, ""):
        state = str(delta.get("panorama_state"))
    else:
        state = prev_state
    if state == "running":
        done = _progress_count(delta, prior, "panorama_completed", remembered, 0)
        total = _progress_count(delta, prior, "panorama_total", remembered, 1)
        if total > 0:
            return (max(0, done), total), None
        return remembered, None
    if prev_state == "running" and state != "running":
        if remembered is not None:
            done, total = remembered
        else:
            done = int(prior.get("panorama_completed") or 0)
            total = int(prior.get("panorama_total") or 0)
        if total > 0 and done >= total:
            return None, (done, total)
        return None, None
    return remembered, None


def resolve_completed_panorama(
    ip: str,
    *,
    expect_count: int = 0,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Newest panorama session, after a short wait so the new folder can appear."""
    del expect_count
    best = _newest_panorama(ip)
    for _pause in range(2):
        _check(cancelled)
        time.sleep(0.8)
        _check(cancelled)
        nxt = _newest_panorama(ip)
        if nxt is None:
            continue
        changed = best is None or _panorama_mtime(nxt) > _panorama_mtime(best) or _panorama_key(nxt) != _panorama_key(best)
        best = nxt
        if changed and _pause > 0:
            break
    if not best or not panorama_session_folder(str(best.get("filePath") or "")):
        raise RuntimeError("No panorama was found on the telescope")
    return best


def panorama_session_folder(path: str) -> str:
    """Session directory for a panorama file, thumbnail, or numbered subfolder."""
    session = album_session_dir(path)
    posix = PurePosixPath(session)
    if posix.name in _LEVEL_DIRS:
        parent = str(posix.parent)
        return "" if parent in {".", "/"} else parent
    return session


def panorama_output_path(cache_dir: Path, session: str, quality: str) -> Path:
    digest = hashlib.sha256(album_http_path(session).encode("utf-8")).hexdigest()[:16]
    label = "sharp" if str(quality) == "sharp" else "preview"
    return Path(cache_dir) / digest / f"{label}.jpg"


def tile_coord(name: str) -> tuple[int, int] | None:
    match = _TILE_NAME.fullmatch(PurePosixPath(str(name or "").replace("\\", "/")).name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def choose_panorama_level(available: set[int], quality: str) -> int | None:
    order = SHARP_LEVELS if str(quality) == "sharp" else PREVIEW_LEVELS
    for level in order:
        if level in available:
            return level
    return None


def parse_panorama_preview(html_text: str) -> dict[str, float]:
    """Overlap and grid size from ``pano_preview.html``."""
    match = _SCENE.search(str(html_text or ""))
    if not match:
        return {}
    levels, cols, rows, tile_w, tile_h, overlap = (float(group) for group in match.groups())
    found: dict[str, float] = {}
    if levels > 0:
        found["levels"] = levels
    if cols > 0:
        found["cols"] = cols
    if rows > 0:
        found["rows"] = rows
    if tile_w > 0:
        found["tile_width"] = tile_w
    if tile_h > 0:
        found["tile_height"] = tile_h
    if 0.02 <= overlap <= 0.8:
        found["overlap"] = overlap
    return found


def grid_steps(tile_w: int, tile_h: int, cols: int, rows: int, overlap: float) -> tuple[int, int, int, int]:
    width = max(1, int(tile_w))
    height = max(1, int(tile_h))
    step_x = max(1, int(round(width * (1.0 - overlap))))
    step_y = max(1, int(round(height * (1.0 - overlap))))
    if overlap > 0 and width > 1:
        step_x = min(step_x, width - 1)
    if overlap > 0 and height > 1:
        step_y = min(step_y, height - 1)
    canvas_w = width + max(0, int(cols) - 1) * step_x
    canvas_h = height + max(0, int(rows) - 1) * step_y
    return canvas_w, canvas_h, step_x, step_y


def fit_tile_size(
    tile_w: int,
    tile_h: int,
    cols: int,
    rows: int,
    overlap: float,
    max_edge: int,
) -> tuple[int, int]:
    canvas_w, canvas_h, _step_x, _step_y = grid_steps(tile_w, tile_h, cols, rows, overlap)
    long_edge = max(canvas_w, canvas_h)
    if max_edge <= 0 or long_edge <= max_edge:
        return max(1, int(tile_w)), max(1, int(tile_h))
    scale = max_edge / float(long_edge)
    return max(1, int(round(tile_w * scale))), max(1, int(round(tile_h * scale)))


def composite_grid(
    tiles: dict[tuple[int, int], Any],
    *,
    overlap: float = DEFAULT_OVERLAP,
    max_edge: int = 0,
) -> Any:
    """Feather-blend a row/column grid. Missing cells stay black."""
    if not panorama_available():
        raise RuntimeError("numpy and opencv are required to stitch a panorama")
    usable = {coord: image for coord, image in tiles.items() if _image_ok(image)}
    if len(usable) < 2:
        raise ValueError("A panorama stitch needs at least two tiles")
    rows = max(row for row, _col in usable) + 1
    cols = max(col for _row, col in usable) + 1
    sample = next(iter(usable.values()))
    source_h, source_w = int(sample.shape[0]), int(sample.shape[1])
    tile_w, tile_h = fit_tile_size(source_w, source_h, cols, rows, overlap, max_edge)
    prepared: dict[tuple[int, int], Any] = {}
    for coord, image in usable.items():
        frame = image
        if int(frame.shape[1]) != tile_w or int(frame.shape[0]) != tile_h:
            frame = cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        prepared[coord] = frame
    _canvas_w, _canvas_h, step_x, step_y = grid_steps(tile_w, tile_h, cols, rows, overlap)
    canvas_w = tile_w + (cols - 1) * step_x
    canvas_h = tile_h + (rows - 1) * step_y
    overlap_x = max(0, tile_w - step_x)
    overlap_y = max(0, tile_h - step_y)
    acc = np.zeros((canvas_h, canvas_w, 3), np.float32)
    weight = np.zeros((canvas_h, canvas_w), np.float32)
    for (row, col), frame in prepared.items():
        mask = _feather_mask(
            tile_h,
            tile_w,
            overlap_x,
            overlap_y,
            fade_left=col > 0,
            fade_right=col < cols - 1,
            fade_top=row > 0,
            fade_bottom=row < rows - 1,
        )
        x = col * step_x
        y = row * step_y
        acc[y:y + tile_h, x:x + tile_w] += frame.astype(np.float32) * mask[:, :, None]
        weight[y:y + tile_h, x:x + tile_w] += mask
    painted = weight > 0
    acc[painted] /= weight[painted, None]
    return np.clip(acc, 0, 255).astype(np.uint8)


def build_panorama(
    ip: str,
    session: str,
    dest: Path,
    *,
    quality: str = "preview",
    rows: int = 0,
    cols: int = 0,
    preview_path: str = "",
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PanoramaBuild:
    """Download one resolution of a session and write a stitched JPEG."""
    if not panorama_available():
        raise RuntimeError("numpy and opencv are required to stitch a panorama")
    host = str(ip or "").strip()
    folder = panorama_session_folder(session)
    if not host or not folder:
        raise RuntimeError("This panorama has no telescope address")
    _check(cancelled)
    overlap = DEFAULT_OVERLAP
    parsed = _preview_settings(host, folder, preview_path)
    if parsed.get("overlap"):
        overlap = float(parsed["overlap"])
    if rows <= 0:
        rows = int(parsed.get("rows") or 0)
    if cols <= 0:
        cols = int(parsed.get("cols") or 0)
    available, listed = _discover_levels(host, folder, rows, cols)
    level = choose_panorama_level(available, quality)
    if level is None:
        raise RuntimeError("No panorama tiles were found in this session")
    _check(cancelled)
    names = _tile_names(host, folder, level, rows, cols, listed)
    coords = [(tile_coord(name), name) for name in names]
    coords = [(coord, name) for coord, name in coords if coord is not None]
    if len(coords) < 2:
        raise RuntimeError("No panorama tiles were found in this session")
    if rows <= 0:
        rows = max(coord[0] for coord, _name in coords) + 1
    if cols <= 0:
        cols = max(coord[1] for coord, _name in coords) + 1
    tile_dir = Path(dest).parent / f"level-{level}"
    tile_dir.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[tuple[int, int], Path]] = []
    total = len(coords)
    for index, (coord, name) in enumerate(coords, start=1):
        _check(cancelled)
        local = tile_dir / Path(name).name
        if not local.is_file() or local.stat().st_size < 100:
            url = _tile_url(host, folder, level, name)
            try:
                local.write_bytes(_read_url(url, timeout=20))
            except (OSError, HTTPError, URLError, TimeoutError, RuntimeError):
                if progress:
                    progress(index, total)
                continue
        if local.is_file() and local.stat().st_size >= 100:
            saved.append((coord, local))
        if progress:
            progress(index, total)
    if len(saved) < 2:
        raise RuntimeError("Could not download the panorama tiles")
    _check(cancelled)
    max_edge = SHARP_MAX_EDGE if str(quality) == "sharp" else PREVIEW_MAX_EDGE
    tiles: dict[tuple[int, int], Any] = {}
    tile_w = 0
    tile_h = 0
    fitted_w = 0
    fitted_h = 0
    for coord, path in saved:
        _check(cancelled)
        frame = _load_jpeg(path)
        if tile_w <= 0:
            tile_h, tile_w = int(frame.shape[0]), int(frame.shape[1])
            fitted_w, fitted_h = fit_tile_size(tile_w, tile_h, cols, rows, overlap, max_edge)
        if int(frame.shape[1]) != fitted_w or int(frame.shape[0]) != fitted_h:
            frame = cv2.resize(frame, (fitted_w, fitted_h), interpolation=cv2.INTER_AREA)
        tiles[coord] = frame
    canvas = composite_grid(tiles, overlap=overlap, max_edge=0)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Could not encode the panorama")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.jpg")
    tmp.write_bytes(encoded.tobytes())
    tmp.replace(dest)
    label = "sharp" if str(quality) == "sharp" else "preview"
    detail = f"{rows}×{cols} {label} · {tile_w}×{tile_h} tiles"
    if fitted_w != tile_w or fitted_h != tile_h:
        detail += f" · fit {int(canvas.shape[1])}×{int(canvas.shape[0])}"
    if len(saved) != rows * cols:
        detail += f" · {len(saved)}/{rows * cols} tiles"
    return PanoramaBuild(
        path=str(dest),
        detail=detail,
        rows=rows,
        cols=cols,
        level=int(level),
        tile_width=tile_w,
        tile_height=tile_h,
        overlap=overlap,
    )


class PanoramaJob(QRunnable):
    """Download and stitch off the GUI thread."""

    def __init__(
        self,
        token: int,
        ip: str,
        session: str,
        quality: str,
        rows: int,
        cols: int,
        preview_path: str,
        dest: Path,
        signals: PanoramaSignals,
        cancelled: Callable[[], bool],
        discover: bool = False,
        expect_count: int = 0,
    ):
        super().__init__()
        self._token = int(token)
        self._ip = ip
        self._session = session
        self._quality = quality
        self._rows = int(rows or 0)
        self._cols = int(cols or 0)
        self._preview_path = preview_path
        self._dest = Path(dest)
        self._signals = signals
        self._cancelled = cancelled
        self._discover = bool(discover)
        self._expect_count = int(expect_count or 0)
        self.setAutoDelete(True)

    def run(self) -> None:
        if self._cancelled():
            return
        try:
            if self._discover:
                row = resolve_completed_panorama(
                    self._ip,
                    expect_count=self._expect_count,
                    cancelled=self._cancelled,
                )
                geometry = panorama_geometry(row)
                self._session = panorama_session_folder(str(row.get("filePath") or ""))
                self._rows = self._rows or int(geometry["pano_rows"] or 0)
                self._cols = self._cols or int(geometry["pano_cols"] or 0)
                self._preview_path = self._preview_path or str(geometry["pano_preview_path"] or "")
                self._dest = panorama_output_path(self._dest, self._session, self._quality)
            result = build_panorama(
                self._ip,
                self._session,
                self._dest,
                quality=self._quality,
                rows=self._rows,
                cols=self._cols,
                preview_path=self._preview_path,
                progress=lambda done, total: self._signals.progress.emit(self._token, done, total),
                cancelled=self._cancelled,
            )
            status, detail, path = "done", result.detail, result.path
        except _Cancelled:
            return
        except Exception as exc:
            status, detail, path = "failed", str(exc) or "Panorama stitch failed", ""
            try:
                if self._dest.suffix:
                    self._dest.with_suffix(".part.jpg").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._signals.finished.emit(self._token, status, detail, path)
        except RuntimeError:
            pass


def _image_ok(image: Any) -> bool:
    return image is not None and getattr(image, "size", 0) and getattr(image, "ndim", 0) >= 2


def _feather_mask(
    height: int,
    width: int,
    overlap_x: int,
    overlap_y: int,
    *,
    fade_left: bool,
    fade_right: bool,
    fade_top: bool,
    fade_bottom: bool,
) -> Any:
    mask = np.ones((height, width), np.float32)
    if fade_left and overlap_x > 1:
        mask[:, :overlap_x] *= np.linspace(0.0, 1.0, overlap_x, dtype=np.float32)[None, :]
    if fade_right and overlap_x > 1:
        mask[:, width - overlap_x:] *= np.linspace(1.0, 0.0, overlap_x, dtype=np.float32)[None, :]
    if fade_top and overlap_y > 1:
        mask[:overlap_y, :] *= np.linspace(0.0, 1.0, overlap_y, dtype=np.float32)[:, None]
    if fade_bottom and overlap_y > 1:
        mask[height - overlap_y:, :] *= np.linspace(1.0, 0.0, overlap_y, dtype=np.float32)[:, None]
    return mask


def _progress_count(
    delta: dict[str, Any],
    prior: dict[str, Any],
    key: str,
    remembered: tuple[int, int] | None,
    index: int,
) -> int:
    if key in delta and delta.get(key) not in (None, ""):
        try:
            return int(delta.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    if remembered is not None:
        return int(remembered[index])
    try:
        return int(prior.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _panorama_mtime(entry: dict[str, Any]) -> int:
    try:
        return int(entry.get("modificationTime") or 0)
    except (TypeError, ValueError):
        return 0


def _panorama_key(entry: dict[str, Any]) -> str:
    return str(entry.get("filePath") or entry.get("fileName") or "")


def _album_panoramas(ip: str) -> list[dict[str, Any]]:
    host = str(ip or "").strip()
    if not host:
        return []
    request = Request(
        f"http://{host}:8082/album/list/mediaInfos",
        data=json.dumps({"mediaType": 5, "pageIndex": 0, "pageSize": 0}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except (OSError, HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _newest_panorama(ip: str) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for row in _album_panoramas(ip):
        if best is None or _panorama_mtime(row) >= _panorama_mtime(best):
            best = row
    return best


def _check(cancelled: Callable[[], bool] | None) -> None:
    if cancelled and cancelled():
        raise _Cancelled()


def _read_url(url: str, timeout: float = 20) -> bytes:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the telescope: {exc.reason}") from exc


def _head_ok(url: str) -> bool:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=6) as response:
            return 200 <= int(response.status) < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False


def _join(folder: str, name: str) -> str:
    directory = album_http_path(folder).rstrip("/")
    leaf = str(name or "").replace("\\", "/").lstrip("/")
    if not directory:
        return album_http_path(leaf)
    if not leaf:
        return directory
    return f"{directory}/{leaf}"


def _tile_url(ip: str, session: str, level: int, name: str) -> str:
    prefix = "" if int(level) == 0 else f"{int(level)}/"
    return album_http_url(ip, _join(session, prefix + Path(name).name))


def _preview_settings(ip: str, session: str, preview_path: str) -> dict[str, float]:
    remote = album_http_path(preview_path) or _join(session, "pano_preview.html")
    url = album_http_url(ip, remote)
    if not url:
        return {}
    try:
        text = _read_url(url, timeout=8).decode("utf-8", "replace")
    except (OSError, HTTPError, URLError, TimeoutError, RuntimeError):
        return {}
    return parse_panorama_preview(text)


def _list_dir(ip: str, folder: str) -> list[dict[str, Any]] | None:
    url = album_http_url(ip, album_http_path(folder).rstrip("/") + "/")
    if not url:
        return None
    try:
        body = _read_url(url, timeout=8)
    except (OSError, HTTPError, URLError, TimeoutError, RuntimeError):
        return None
    text = body.decode("utf-8", "replace")
    if not text.lstrip().lower().startswith("<!doctype html") and "<a " not in text.lower():
        return None
    return album_listing_entries(text)


def _discover_levels(
    ip: str,
    session: str,
    rows: int,
    cols: int,
) -> tuple[set[int], dict[int, list[str]]]:
    available: set[int] = set()
    listed: dict[int, list[str]] = {}
    root = _list_dir(ip, session)
    if root:
        root_tiles: list[str] = []
        for entry in root:
            name = str(entry.get("name") or "")
            if entry.get("is_dir") and name in _LEVEL_DIRS:
                available.add(int(name))
                continue
            if tile_coord(name):
                root_tiles.append(name)
        if root_tiles:
            available.add(0)
            listed[0] = root_tiles
        for level in sorted(level for level in available if level > 0):
            sub = _list_dir(ip, _join(session, str(level)))
            if not sub:
                continue
            names = [str(item.get("name") or "") for item in sub if tile_coord(str(item.get("name") or ""))]
            if names:
                listed[level] = names
        if available:
            return available, listed
    probe = "00_00.jpg"
    if rows > 0 and cols > 0:
        probe = "00_00.jpg"
    for level in (0, 1, 2, 3, 4, 5):
        if _head_ok(_tile_url(ip, session, level, probe)):
            available.add(level)
    return available, listed


def _tile_names(
    ip: str,
    session: str,
    level: int,
    rows: int,
    cols: int,
    listed: dict[int, list[str]],
) -> list[str]:
    names = list(listed.get(int(level)) or [])
    if names:
        return names
    if int(level) > 0:
        sub = _list_dir(ip, _join(session, str(level)))
        if sub:
            names = [str(item.get("name") or "") for item in sub if tile_coord(str(item.get("name") or ""))]
            if names:
                return names
    if rows > 0 and cols > 0:
        return [f"{row:02d}_{col:02d}.jpg" for row in range(rows) for col in range(cols)]
    return []


def _load_jpeg(path: Path) -> Any:
    data = np.fromfile(path, dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        raise RuntimeError(f"Could not read {path.name}")
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
