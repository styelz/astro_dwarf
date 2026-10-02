"""Stitch a DWARF panorama session into one image.

The session folder holds the full-size tiles, named ``row_col.jpg``. Folders
``1`` through ``5`` repeat that grid at smaller sizes. The phone's quick view
uses a small folder and the single overlap written into ``pano_preview.html``.
A sharp view uses the full-size tiles, scaled to fit a desktop image.

The viewer keeps a JPEG. Downloading that panorama saves the constructed
image as a TIFF, not the tile folder.

That overlap is one fraction for both axes. On a nearby wall the nod does not
land on it, and each frame keeps its own exposure. The stitch measures each
join and evens the exposure. A join with no texture keeps the firmware step.
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
_ALIGN_SLACK = 0.10
_ALIGN_SCORE = 0.50
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
    exported = Signal(int, bool, str, str)


def panorama_available() -> bool:
    return np is not None and cv2 is not None


def panorama_result_caption(
    cols: int,
    rows: int,
    *,
    quality: str,
    overlap: float,
    saved: int,
    tele_fov_h: float = 0.0,
    tele_fov_v: float = 0.0,
) -> str:
    """One line under a finished panorama: grid, field, overlap, and stitch."""
    cols_n = max(1, int(cols or 1))
    rows_n = max(1, int(rows or 1))
    shots = cols_n * rows_n
    label = "sharp" if str(quality) == "sharp" else "preview"
    parts = [f"{cols_n}×{rows_n}"]
    try:
        fov_h = float(tele_fov_h)
        fov_v = float(tele_fov_v)
        overlap_n = float(overlap)
    except (TypeError, ValueError):
        fov_h = fov_v = overlap_n = 0.0
    if fov_h > 0.5 and fov_v > 0.3:
        step = (1.0 - overlap_n) if 0.0 < overlap_n < 1.0 else 1.0
        span_h = fov_h * (1.0 + max(0, cols_n - 1) * step)
        span_v = fov_v * (1.0 + max(0, rows_n - 1) * step)
        parts.append(f"{span_h:.1f}°×{span_v:.1f}°")
    if 0.02 <= overlap_n <= 0.8:
        parts.append(f"{round(overlap_n * 100)}% overlap")
    kept = max(0, int(saved or 0))
    if kept != shots:
        parts.append(f"{kept}/{shots} shots")
    parts.append(label)
    return " · ".join(parts)


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


def panorama_album_tiff_name(session: str) -> str:
    """Local album file for one constructed panorama."""
    folder = panorama_session_folder(session) or album_http_path(session).rstrip("/")
    label = PurePosixPath(folder).name if folder else ""
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in label).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        cleaned = "panorama"
    return f"{cleaned}.tif"


def panorama_download_action(
    *,
    kind: str,
    is_dir: bool,
    protected: bool,
    session: str,
    item_id: str,
    built_folder: str,
    built_item_id: str,
    built_quality: str,
    status: str,
    has_image: bool,
) -> str:
    """How a media download should treat this row.

    ``tiff`` copies the constructed image, ``wait`` finishes the stitch already
    on screen, ``stitch`` builds the sharp image, and ``folder`` keeps a
    normal download. Preview and sharp are both the constructed image.
    """
    if str(kind or "") != "panorama" or not is_dir or protected or not session:
        return "folder"
    if str(built_quality or "") not in {"", "preview", "sharp"}:
        return "stitch"
    same = (
        built_folder == session
        and str(built_item_id or "") == str(item_id or "")
        and bool(item_id)
    )
    if same and status == "done" and has_image:
        return "tiff"
    if same and status == "working":
        return "wait"
    return "stitch"


def write_panorama_tiff(image_bgr: Any, dest: Path) -> None:
    """Write the constructed panorama. ``image_bgr`` is an 8-bit OpenCV image."""
    if cv2 is None:
        raise RuntimeError("opencv is required to save the panorama")
    ok, encoded = cv2.imencode(".tif", image_bgr)
    if not ok:
        raise RuntimeError("Could not encode the panorama TIFF")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.tif")
    tmp.write_bytes(encoded.tobytes())
    tmp.replace(dest)


def export_panorama_tiff(source: Path, dest: Path) -> Path:
    """Copy the constructed panorama into the album as a TIFF."""
    source = Path(source)
    dest = Path(dest)
    if dest.suffix.lower() not in {".tif", ".tiff"}:
        dest = dest.with_suffix(".tif")
    sibling = source.with_suffix(".tif")
    origin = sibling if sibling.is_file() and sibling.stat().st_size > 0 else source
    if not origin.is_file() or origin.stat().st_size <= 0:
        raise RuntimeError("The constructed panorama is not ready")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.tif")
    try:
        if origin.suffix.lower() in {".tif", ".tiff"}:
            tmp.write_bytes(origin.read_bytes())
        else:
            if cv2 is None or np is None:
                raise RuntimeError("opencv is required to save the panorama")
            encoded_src = np.frombuffer(origin.read_bytes(), dtype=np.uint8).copy()
            image = cv2.imdecode(encoded_src, cv2.IMREAD_COLOR)
            if image is None or getattr(image, "size", 0) == 0:
                raise RuntimeError("Could not read the constructed panorama")
            ok, encoded = cv2.imencode(".tif", image)
            if not ok:
                raise RuntimeError("Could not encode the panorama TIFF")
            tmp.write_bytes(encoded.tobytes())
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if not dest.is_file() or dest.stat().st_size <= 0:
        raise RuntimeError("Could not save the panorama TIFF")
    return dest


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
    align: bool = False,
) -> Any:
    """Feather-blend a row/column grid. Missing cells stay black.

    ``align`` measures each join and matches exposure. Joins that are flat
    stay on the firmware overlap.
    """
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
    placement = _aligned_placement(prepared, step_x, step_y) if align else None
    if placement is None:
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
    else:
        positions, gains = placement
        origin_x = min(point[0] for point in positions.values())
        origin_y = min(point[1] for point in positions.values())
        positions = {coord: (point[0] - origin_x, point[1] - origin_y) for coord, point in positions.items()}
        canvas_w = max(point[0] for point in positions.values()) + tile_w
        canvas_h = max(point[1] for point in positions.values()) + tile_h
        acc = np.zeros((canvas_h, canvas_w, 3), np.float32)
        weight = np.zeros((canvas_h, canvas_w), np.float32)
        for (row, col), frame in prepared.items():
            x, y = positions[(row, col)]
            mask = _feather_mask(
                tile_h,
                tile_w,
                0,
                0,
                fade_left=(row, col - 1) in positions,
                fade_right=(row, col + 1) in positions,
                fade_top=(row - 1, col) in positions,
                fade_bottom=(row + 1, col) in positions,
                left=_pair_overlap(positions, (row, col), (row, col - 1), 0, tile_w),
                right=_pair_overlap(positions, (row, col), (row, col + 1), 0, tile_w),
                top=_pair_overlap(positions, (row, col), (row - 1, col), 1, tile_h),
                bottom=_pair_overlap(positions, (row, col), (row + 1, col), 1, tile_h),
            )
            painted_frame = frame.astype(np.float32) * gains[(row, col)][None, None, :]
            acc[y:y + tile_h, x:x + tile_w] += painted_frame * mask[:, :, None]
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
    tele_fov_h: float = 0.0,
    tele_fov_v: float = 0.0,
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
    canvas = composite_grid(tiles, overlap=overlap, max_edge=0, align=True)
    bgr = cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Could not encode the panorama")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.jpg")
    tmp.write_bytes(encoded.tobytes())
    tmp.replace(dest)
    try:
        write_panorama_tiff(bgr, dest.with_suffix(".tif"))
    except (OSError, RuntimeError):
        pass
    detail = panorama_result_caption(
        cols,
        rows,
        quality=quality,
        overlap=overlap,
        saved=len(saved),
        tele_fov_h=tele_fov_h,
        tele_fov_v=tele_fov_v,
    )
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
        tele_fov_h: float = 0.0,
        tele_fov_v: float = 0.0,
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
        self._tele_fov_h = float(tele_fov_h or 0)
        self._tele_fov_v = float(tele_fov_v or 0)
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
                tele_fov_h=self._tele_fov_h,
                tele_fov_v=self._tele_fov_v,
            )
            status, detail, path = "done", result.detail, result.path
        except _Cancelled:
            return
        except Exception as exc:
            status, detail, path = "failed", str(exc) or "Panorama stitch failed", ""
            try:
                if self._dest.suffix:
                    self._dest.with_suffix(".part.jpg").unlink(missing_ok=True)
                    self._dest.with_suffix(".part.tif").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._signals.finished.emit(self._token, status, detail, path)
        except RuntimeError:
            pass


class PanoramaTiffExport(QRunnable):
    """Copy a constructed panorama into the album as a TIFF."""

    def __init__(
        self,
        token: int,
        source: Path,
        dest: Path,
        signals: PanoramaSignals,
        cancelled: Callable[[], bool],
    ):
        super().__init__()
        self._token = int(token)
        self._source = Path(source)
        self._dest = Path(dest)
        self._signals = signals
        self._cancelled = cancelled
        self.setAutoDelete(True)

    def run(self) -> None:
        if self._cancelled():
            return
        try:
            path = export_panorama_tiff(self._source, self._dest)
            if self._cancelled():
                return
            self._signals.exported.emit(self._token, True, str(path), "")
        except Exception as exc:
            if self._cancelled():
                return
            try:
                self._signals.exported.emit(self._token, False, "", str(exc) or "Could not save the panorama")
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
    left: int | None = None,
    right: int | None = None,
    top: int | None = None,
    bottom: int | None = None,
) -> Any:
    mask = np.ones((height, width), np.float32)
    left_n = overlap_x if left is None else left
    right_n = overlap_x if right is None else right
    top_n = overlap_y if top is None else top
    bottom_n = overlap_y if bottom is None else bottom
    left_n = min(max(0, int(left_n)), max(0, width // 3))
    right_n = min(max(0, int(right_n)), max(0, width // 3))
    top_n = min(max(0, int(top_n)), max(0, height // 3))
    bottom_n = min(max(0, int(bottom_n)), max(0, height // 3))
    if fade_left and left_n > 1:
        mask[:, :left_n] *= np.linspace(0.0, 1.0, left_n, dtype=np.float32)[None, :]
    if fade_right and right_n > 1:
        mask[:, width - right_n:] *= np.linspace(1.0, 0.0, right_n, dtype=np.float32)[None, :]
    if fade_top and top_n > 1:
        mask[:top_n, :] *= np.linspace(0.0, 1.0, top_n, dtype=np.float32)[:, None]
    if fade_bottom and bottom_n > 1:
        mask[height - bottom_n:, :] *= np.linspace(1.0, 0.0, bottom_n, dtype=np.float32)[:, None]
    return mask


def _pair_overlap(
    positions: dict[tuple[int, int], tuple[int, int]],
    coord: tuple[int, int],
    neighbor: tuple[int, int],
    axis: int,
    size: int,
) -> int:
    if coord not in positions or neighbor not in positions:
        return 0
    start = positions[coord][axis]
    other = positions[neighbor][axis]
    return max(0, min(start + size, other + size) - max(start, other))


def _aligned_placement(
    tiles: dict[tuple[int, int], Any],
    step_x: int,
    step_y: int,
) -> tuple[dict[tuple[int, int], tuple[int, int]], dict[tuple[int, int], Any]] | None:
    """Tile origins and per-channel gains. None keeps the firmware grid."""
    sample = next(iter(tiles.values()))
    height, width = int(sample.shape[0]), int(sample.shape[1])
    if width < 24 or height < 24 or step_x < 4 or step_y < 4:
        return None
    measured: dict[tuple[tuple[int, int], tuple[int, int]], tuple[int, int]] = {}
    for (row, col), frame in tiles.items():
        right = (row, col + 1)
        if right in tiles:
            shift = _measured_shift(frame, tiles[right], 1, step_x)
            if shift is not None:
                measured[((row, col), right)] = shift
        below = (row + 1, col)
        if below in tiles:
            shift = _measured_shift(frame, tiles[below], 0, step_y)
            if shift is not None:
                measured[((row, col), below)] = shift
    positions = _solve_positions(set(tiles), measured, step_x, step_y)
    gains = _solve_gains(tiles, positions)
    return positions, gains


def _measured_shift(src: Any, dst: Any, axis: int, nominal: int) -> tuple[int, int] | None:
    """Translation of ``dst`` relative to ``src``.

    ``axis`` 1 is the neighbor to the right, 0 the neighbor below. The search
    stays near the firmware step so a flat wall cannot lock onto a far peak.
    """
    gray_src = cv2.cvtColor(src, cv2.COLOR_RGB2GRAY)
    gray_dst = cv2.cvtColor(dst, cv2.COLOR_RGB2GRAY)
    along = int(gray_src.shape[1] if axis == 1 else gray_src.shape[0])
    cross = int(gray_src.shape[0] if axis == 1 else gray_src.shape[1])
    slack = max(2, int(round(along * _ALIGN_SLACK)))
    box = max(6, int(round(along * 0.08)))
    end = along - max(2, int(round(along * 0.02)))
    start = end - box
    if start < along // 2:
        return None
    margin = max(2, int(round(cross * 0.08)))
    if axis == 1:
        template = gray_src[margin:cross - margin, start:end]
    else:
        template = gray_src[start:end, margin:cross - margin]
    if template.size == 0 or float(template.std()) < 1.5:
        return None
    expect = start - int(nominal)
    search_0 = max(0, expect - slack)
    search_1 = min(along, expect + box + slack)
    if axis == 1:
        search = gray_dst[:, search_0:search_1]
    else:
        search = gray_dst[search_0:search_1, :]
    if search.shape[0] <= template.shape[0] or search.shape[1] <= template.shape[1]:
        return None
    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _score, score, _where, loc = cv2.minMaxLoc(result)
    if not np.isfinite(score) or float(score) < _ALIGN_SCORE:
        return None
    along_loc = int(loc[0] if axis == 1 else loc[1])
    along_limit = int(result.shape[1] if axis == 1 else result.shape[0])
    if along_loc <= 1 or along_loc >= along_limit - 2:
        return None
    if axis == 1:
        found = search_0 + int(loc[0])
        dx = int(start - found)
        dy = int(margin - int(loc[1]))
    else:
        found = search_0 + int(loc[1])
        dy = int(start - found)
        dx = int(margin - int(loc[0]))
    if abs(dx if axis == 0 else dy) > slack:
        return None
    return dx, dy


def _solve_positions(
    coords: set[tuple[int, int]],
    measured: dict[tuple[tuple[int, int], tuple[int, int]], tuple[int, int]],
    step_x: int,
    step_y: int,
) -> dict[tuple[int, int], tuple[int, int]]:
    """One step per row boundary and per column boundary.

    The head makes one move for a whole row, so the tiles in that row share a
    step. The median ignores a single join that locked onto the wrong peak.
    A boundary with no texture keeps the firmware step.
    """
    rows = max(row for row, _col in coords) + 1
    cols = max(col for _row, col in coords) + 1
    x_groups: dict[int, list[int]] = {}
    y_groups: dict[int, list[int]] = {}
    for (src, dst), (dx, dy) in measured.items():
        if dst == (src[0], src[1] + 1):
            x_groups.setdefault(src[1], []).append(dx)
        elif dst == (src[0] + 1, src[1]):
            y_groups.setdefault(src[0], []).append(dy)
    x_steps = [_boundary_step(x_groups.get(col), step_x) for col in range(cols - 1)]
    y_steps = [_boundary_step(y_groups.get(row), step_y) for row in range(rows - 1)]
    xs = [0]
    ys = [0]
    for step in x_steps:
        xs.append(xs[-1] + step)
    for step in y_steps:
        ys.append(ys[-1] + step)
    return {(row, col): (xs[col], ys[row]) for row, col in coords}


def _boundary_step(values: list[int] | None, nominal: int) -> int:
    if not values:
        return int(nominal)
    return int(round(float(np.median(values))))


def _solve_gains(
    tiles: dict[tuple[int, int], Any],
    positions: dict[tuple[int, int], tuple[int, int]],
) -> dict[tuple[int, int], Any]:
    ordered = sorted(tiles)
    index = {coord: i for i, coord in enumerate(ordered)}
    count = len(ordered)
    equations: list[tuple[int, int, Any]] = []
    for row, col in ordered:
        for neighbor in ((row, col + 1), (row + 1, col)):
            if neighbor not in tiles:
                continue
            left, right = _overlap_patches(tiles[(row, col)], tiles[neighbor], positions[(row, col)], positions[neighbor])
            if left is None or _gray_corr(left, right) < 0.35:
                continue
            mean_left = left.reshape(-1, left.shape[-1]).mean(axis=0)
            mean_right = right.reshape(-1, right.shape[-1]).mean(axis=0)
            if np.any(mean_left < 3) or np.any(mean_right < 3):
                continue
            ratio = mean_left / np.maximum(mean_right, 1e-3)
            if np.any(ratio < 0.25) or np.any(ratio > 4):
                continue
            equations.append((index[(row, col)], index[neighbor], np.log(ratio)))
    gains = {coord: np.ones(3, np.float32) for coord in ordered}
    if not equations:
        return gains
    for channel in range(3):
        matrix = []
        target = []
        for src, dst, log_ratio in equations:
            row = np.zeros(count, np.float64)
            row[dst] = 1.0
            row[src] = -1.0
            matrix.append(row)
            target.append(float(log_ratio[channel]))
        solved, *_rest = np.linalg.lstsq(np.stack(matrix), np.array(target, np.float64), rcond=None)
        solved = solved - solved[index[ordered[0]]]
        for coord, slot in index.items():
            gains[coord][channel] = float(np.exp(np.clip(solved[slot], np.log(0.4), np.log(2.5))))
    return gains


def _overlap_patches(src: Any, dst: Any, src_at: tuple[int, int], dst_at: tuple[int, int]) -> tuple[Any, Any]:
    src_x, src_y = src_at
    dst_x, dst_y = dst_at
    src_h, src_w = int(src.shape[0]), int(src.shape[1])
    dst_h, dst_w = int(dst.shape[0]), int(dst.shape[1])
    x0 = max(src_x, dst_x)
    y0 = max(src_y, dst_y)
    x1 = min(src_x + src_w, dst_x + dst_w)
    y1 = min(src_y + src_h, dst_y + dst_h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None, None
    left = src[y0 - src_y:y1 - src_y, x0 - src_x:x1 - src_x]
    right = dst[y0 - dst_y:y1 - dst_y, x0 - dst_x:x1 - dst_x]
    if left.shape != right.shape or left.size == 0:
        return None, None
    return left, right


def _gray_corr(src: Any, dst: Any) -> float:
    left = src.astype(np.float32).mean(axis=2)
    right = dst.astype(np.float32).mean(axis=2)
    left = left - float(left.mean())
    right = right - float(right.mean())
    denom = float(np.sqrt((left * left).sum() * (right * right).sum()))
    if denom < 1e-3:
        return 0.0
    return float((left * right).sum() / denom)


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
