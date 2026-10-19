"""Star-align a finished custom mosaic onto one canvas.

The planned pane centres are only the seed. Stars in each shared edge
correct shift, rotation, and scale. A missing pane stays a hole. An edge
with too few stars keeps that seed placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

_MIN_MATCHES = 4
_LOW_OVERLAP = 0.15
_MAX_CANVAS = 8192
# Full-frame stills are ~1920px on the sheet and ~3856px on disk. A fixed
# 18px window then misses a degree of alt-az field rotation and a few
# percent of plate scale. Match a short side first, then refine.
_COARSE_LONG_SIDE = 420
_COARSE_STARS = 80


@dataclass(slots=True)
class StitchPane:
    index: int
    row: int
    column: int
    image: Any
    ra_hours: float | None = None
    dec_degrees: float | None = None
    position_angle: float = 0.0
    fov_h: float = 0.0
    fov_v: float = 0.0
    path: str = ""
    flip: bool = False


@dataclass(slots=True)
class StitchResult:
    jpeg: bytes
    residual_px: float | None
    unmatched: list[tuple[int, int]] = field(default_factory=list)
    warning: str = ""
    width: int = 0
    height: int = 0


def stitch_available() -> bool:
    return np is not None and cv2 is not None


def overlap_warning(overlap: float) -> str:
    try:
        value = float(overlap)
    except (TypeError, ValueError):
        return ""
    if value != value or value >= _LOW_OVERLAP:
        return ""
    return f"Overlap is {value * 100:.0f}%. Star matching needs about 15% or more."


def stitch_panes(
    panes: list[StitchPane],
    *,
    overlap: float = 0.2,
    overlap_h: float | None = None,
    overlap_v: float | None = None,
) -> StitchResult:
    if not stitch_available():
        raise RuntimeError("numpy and opencv are required to stitch a mosaic")
    usable = [pane for pane in panes if pane is not None and _image_ok(pane.image)]
    if len(usable) < 2:
        raise ValueError("A stitch needs at least two panes")
    warning = overlap_warning(overlap)
    prepared = [_prepare(pane) for pane in usable]
    oh = _axis(overlap_h, overlap)
    ov = _axis(overlap_v, overlap)
    seeds = _seed_placements(prepared, oh, ov)
    stars = {item["index"]: _stars(item["rgb"]) for item in prepared}
    coarse = _coarse_catalog(prepared, seeds)
    edges = _neighbor_edges(prepared)
    inliers: list[tuple[int, int, Any, Any]] = []
    unmatched: list[tuple[int, int]] = []
    for left, right in edges:
        pairs = _edge_pairs(left, right, seeds, stars, coarse)
        if pairs is None:
            unmatched.append((left, right))
            continue
        src, dst = pairs
        inliers.append((left, right, src, dst))
    solved, connected = _solve_similarities(prepared, seeds, inliers)
    if coarse is not None and inliers:
        refined: list[tuple[int, int, Any, Any]] = []
        changed = False
        for left, right, src, dst in inliers:
            pairs = _edge_inliers(left, right, solved, stars)
            if pairs is None:
                refined.append((left, right, src, dst))
                continue
            refined.append((left, right, pairs[0], pairs[1]))
            changed = True
        if changed:
            inliers = refined
            solved, connected = _solve_similarities(prepared, solved, inliers)
    for left, right in edges:
        if left not in connected or right not in connected:
            pair = (left, right)
            if pair not in unmatched:
                unmatched.append(pair)
    residual = _median_residual(solved, inliers)
    canvas, width, height = _blend(prepared, solved)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise RuntimeError("Could not encode the stitched JPEG")
    return StitchResult(
        jpeg=encoded.tobytes(),
        residual_px=residual,
        unmatched=unmatched,
        warning=warning,
        width=width,
        height=height,
    )


class StitchSignals(QObject):
    finished = Signal(int, str, str, str, str)


class StitchJob(QRunnable):
    """Encode a stitch off the GUI thread. Panes are already numpy arrays."""

    def __init__(
        self,
        token: int,
        panes: list[StitchPane],
        overlap: float,
        dest: Path,
        signals: StitchSignals,
    ):
        super().__init__()
        self._token = int(token)
        self._panes = panes
        self._overlap = float(overlap)
        self._dest = Path(dest)
        self._signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        status = "failed"
        detail = "Stitch failed"
        warning = ""
        path = ""
        try:
            loaded: list[StitchPane] = []
            for pane in self._panes:
                if pane.path and (pane.image is None or not _image_ok(pane.image)):
                    loaded.append(replace(pane, image=load_stack_array(pane.path)))
                else:
                    loaded.append(pane)
            result = stitch_panes(loaded, overlap=self._overlap)
            self._dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._dest.with_suffix(".part.jpg")
            tmp.write_bytes(result.jpeg)
            tmp.replace(self._dest)
            status = "done"
            if result.residual_px is None:
                detail = "Placed from the planned grid. No star match on the joins."
            else:
                detail = f"Star residual {result.residual_px:.2f} px"
            if result.unmatched:
                names = ", ".join(f"{left}–{right}" for left, right in result.unmatched)
                detail += f". Unmatched edges {names}"
            warning = result.warning
            path = str(self._dest)
        except Exception as exc:
            detail = str(exc) or "Stitch failed"
            try:
                self._dest.with_suffix(".part.jpg").unlink(missing_ok=True)
            except OSError:
                pass
        try:
            self._signals.finished.emit(self._token, status, detail, warning, path)
        except RuntimeError:
            pass


def qimage_rgb(image: Any) -> Any:
    """Copy a QImage into a contiguous RGB uint8 array for the stitch job."""
    if np is None or image is None or image.isNull():
        return None
    from PySide6.QtGui import QImage

    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    if width < 8 or height < 8:
        return None
    stride = converted.bytesPerLine()
    ptr = converted.constBits()
    buf = np.frombuffer(ptr, dtype=np.uint8, count=stride * height).reshape(height, stride)
    rgba = buf[:, : width * 4].reshape(height, width, 4)
    return np.ascontiguousarray(rgba[:, :, :3])


def load_stack_array(path: Path | str) -> Any:
    """Decode a local stacked JPEG, PNG, or FITS into a float RGB array."""
    if not stitch_available():
        raise RuntimeError("numpy and opencv are required to stitch a mosaic")
    file = Path(path)
    suffix = file.suffix.lower()
    if suffix in {".fits", ".fit", ".fts"}:
        from .media_preview import decode_fits_image

        array = decode_fits_image(file.read_bytes())
        return _as_rgb_float(array)
    flags = cv2.IMREAD_UNCHANGED
    raw = cv2.imread(str(file), flags)
    if raw is None:
        raise ValueError(f"Could not read {file.name}")
    if raw.ndim == 3 and raw.shape[2] >= 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
    return _as_rgb_float(raw)


def _axis(explicit: float | None, fallback: float) -> float:
    if explicit is None:
        value = fallback
    else:
        try:
            value = float(explicit)
        except (TypeError, ValueError):
            value = fallback
    if value != value:
        value = fallback
    return min(0.95, max(0.0, value))


def _image_ok(image: Any) -> bool:
    if image is None or np is None:
        return False
    array = np.asarray(image)
    return array.ndim >= 2 and array.shape[0] >= 8 and array.shape[1] >= 8


def _prepare(pane: StitchPane) -> dict[str, Any]:
    rgb = _as_rgb_float(pane.image)
    if pane.flip:
        rgb = np.ascontiguousarray(np.flip(rgb, axis=(0, 1)))
    return {
        "index": int(pane.index),
        "row": int(pane.row),
        "column": int(pane.column),
        "rgb": rgb,
        "height": int(rgb.shape[0]),
        "width": int(rgb.shape[1]),
        "position_angle": float(pane.position_angle or 0.0),
    }


def _as_rgb_float(image: Any) -> Any:
    """Map a pane into 0–1 RGB without changing a display JPEG's sky.

    Contact-sheet stills are already stretched. A second 1%–99.5% stretch
    lands in the sky noise when stars are sparse, so the mosaic goes gray
    and the darker pane edges show up as a cross. Linear FITS stay linear
    until a sky-based stretch below.
    """
    source = np.asarray(image)
    integer = np.issubdtype(source.dtype, np.integer)
    if source.ndim == 2:
        rgb = np.repeat(source[..., None], 3, axis=2)
    elif source.ndim == 3 and source.shape[2] == 1:
        rgb = np.repeat(source, 3, axis=2)
    elif source.ndim == 3 and source.shape[2] >= 3:
        rgb = source[..., :3]
    else:
        raise ValueError("Pane image must be gray or RGB")
    work = rgb.astype(np.float32, copy=False)
    if work.size == 0:
        raise ValueError("Pane image is empty")
    peak = float(np.nanmax(work)) if work.size else 0.0
    if not np.isfinite(peak) or peak <= 0:
        return np.zeros(work.shape, dtype=np.float32)
    if peak <= 1.5:
        return np.clip(work, 0.0, 1.0).astype(np.float32)
    if integer and peak <= 255.0:
        return np.clip(work / 255.0, 0.0, 1.0).astype(np.float32)
    return _linear_display(work)


def _linear_display(work: Any) -> Any:
    """Show a linear stack with the sky dark and star cores near white."""
    out = np.empty(work.shape, dtype=np.float32)
    for channel in range(work.shape[2]):
        out[..., channel] = _stretch_linear_channel(work[..., channel])
    return out


def _stretch_linear_channel(channel: Any) -> Any:
    step_y = max(1, int(channel.shape[0]) // 180)
    step_x = max(1, int(channel.shape[1]) // 180)
    sample = channel[::step_y, ::step_x]
    finite = sample[np.isfinite(sample)]
    if finite.size < 16:
        peak = float(np.nanmax(channel)) if channel.size else 0.0
        if not np.isfinite(peak) or peak <= 0:
            return np.zeros(channel.shape, dtype=np.float32)
        return np.clip(channel / peak, 0.0, 1.0).astype(np.float32)
    med = float(np.median(finite))
    mad = max(float(np.median(np.abs(finite - med))) * 1.4826, 1e-6)
    black = med - 2.0 * mad
    keep = max(8, int(finite.size * 0.002))
    white = float(np.median(np.partition(finite, -keep)[-keep:]))
    white = max(white, med + 12.0 * mad)
    if white <= black:
        white = black + 1.0
    scaled = np.clip((channel - np.float32(black)) / np.float32(white - black), 0.0, 1.0)
    strength = 6.0
    curved = np.arcsinh(scaled * strength) / np.arcsinh(strength)
    return curved.astype(np.float32)


def _seed_placements(prepared: list[dict[str, Any]], overlap_h: float, overlap_v: float) -> dict[int, Any]:
    """Lay panes on the contact sheet without spinning them.

    The sheet and the camera JPEGs are both zenith-up. A pane position angle
    is east of north, so seeding a rotation from it turns the bottom row
    several degrees the wrong way. The star match then accepts that pose:
    Beta Hydri's bottom panes were 9° apart in parallactic angle and only
    about 3° apart on the sensor, and the spun seed reported a sub-pixel
    residual on the wrong stars. The real field rotation is a few degrees
    and the edge match takes it from this level seed.
    """
    width = max(item["width"] for item in prepared)
    height = max(item["height"] for item in prepared)
    step_x = width * (1.0 - overlap_h)
    step_y = height * (1.0 - overlap_v)
    seeds: dict[int, Any] = {}
    for item in prepared:
        origin_x = (int(item["column"]) - 1) * step_x
        origin_y = (int(item["row"]) - 1) * step_y
        seeds[item["index"]] = np.array([1.0, 0.0, origin_x, origin_y], dtype=np.float64)
    return seeds


def _stars(rgb: Any, limit: int = 400) -> Any:
    gray = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]).astype(np.float32)
    small = cv2.GaussianBlur(gray, (0, 0), 1.1)
    radius = max(15, int(min(gray.shape) * 0.06) | 1)
    large = cv2.GaussianBlur(gray, (radius, radius), 0)
    high = small - large
    kernel = np.ones((5, 5), np.uint8)
    peaks = (high == cv2.dilate(high, kernel)) & (high > max(0.02, float(np.percentile(high, 99.2)) * 0.45))
    ys, xs = np.nonzero(peaks)
    cap = max(_MIN_MATCHES, int(limit))
    if len(xs) > cap:
        score = high[ys, xs]
        keep = np.argpartition(score, -cap)[-cap:]
        xs = xs[keep]
        ys = ys[keep]
    points = []
    height, width = high.shape
    for x, y in zip(xs.tolist(), ys.tolist()):
        x0, x1 = max(0, x - 2), min(width, x + 3)
        y0, y1 = max(0, y - 2), min(height, y + 3)
        patch = high[y0:y1, x0:x1]
        if patch.size == 0 or float(patch.sum()) <= 0:
            continue
        grid_y, grid_x = np.mgrid[y0:y1, x0:x1]
        weight = np.clip(patch, 0, None)
        total = float(weight.sum())
        if total <= 0:
            continue
        points.append((float((grid_x * weight).sum() / total), float((grid_y * weight).sum() / total)))
    if not points:
        return np.zeros((0, 2), dtype=np.float64)
    return np.asarray(points, dtype=np.float64)


def _coarse_catalog(
    prepared: list[dict[str, Any]],
    seeds: dict[int, Any],
) -> tuple[dict[int, Any], dict[int, Any], float] | None:
    """Downscaled stars and seeds for joins the 18px window cannot see."""
    longest = max(max(int(item["width"]), int(item["height"])) for item in prepared)
    if longest <= _COARSE_LONG_SIDE:
        return None
    lift = float(longest) / float(_COARSE_LONG_SIDE)
    stars: dict[int, Any] = {}
    for item in prepared:
        width = int(item["width"])
        height = int(item["height"])
        tw = max(8, int(round(width / lift)))
        th = max(8, int(round(height / lift)))
        small = cv2.resize(item["rgb"], (tw, th), interpolation=cv2.INTER_AREA)
        stars[int(item["index"])] = _stars(small, _COARSE_STARS)
    scaled: dict[int, Any] = {}
    for index, params in seeds.items():
        shrunk = np.array(params, dtype=np.float64)
        shrunk[2] /= lift
        shrunk[3] /= lift
        scaled[index] = shrunk
    return stars, scaled, lift


def _edge_pairs(
    left: int,
    right: int,
    seeds: dict[int, Any],
    stars: dict[int, Any],
    coarse: tuple[dict[int, Any], dict[int, Any], float] | None,
) -> tuple[Any, Any] | None:
    pairs = _edge_inliers(left, right, seeds, stars)
    if pairs is not None or coarse is None:
        return pairs
    coarse_stars, coarse_seeds, lift = coarse
    pairs = _edge_inliers(left, right, coarse_seeds, coarse_stars)
    if pairs is None:
        return None
    src, dst = pairs
    return src * lift, dst * lift


def _neighbor_edges(prepared: list[dict[str, Any]]) -> list[tuple[int, int]]:
    by_cell = {(int(item["row"]), int(item["column"])): int(item["index"]) for item in prepared}
    edges: list[tuple[int, int]] = []
    for (row, column), index in by_cell.items():
        for other in (by_cell.get((row, column + 1)), by_cell.get((row + 1, column))):
            if other is None:
                continue
            edges.append((index, other))
    return edges


def _apply(params: Any, points: Any) -> Any:
    a, b, tx, ty = [float(value) for value in params]
    x = points[:, 0]
    y = points[:, 1]
    return np.column_stack((a * x - b * y + tx, b * x + a * y + ty))


def _edge_inliers(left: int, right: int, seeds: dict[int, Any], stars: dict[int, Any]) -> tuple[Any, Any] | None:
    """Return matched pixels (right pane, left pane) after a similarity RANSAC."""
    right_stars = stars.get(right)
    left_stars = stars.get(left)
    if right_stars is None or left_stars is None or len(right_stars) < _MIN_MATCHES or len(left_stars) < _MIN_MATCHES:
        return None
    right_canvas = _apply(seeds[right], right_stars)
    left_canvas = _apply(seeds[left], left_stars)
    radius = 18.0
    right_px = []
    left_px = []
    for index, point in enumerate(right_canvas):
        delta = left_canvas - point
        dist = np.hypot(delta[:, 0], delta[:, 1])
        nearest = int(np.argmin(dist))
        if float(dist[nearest]) > radius:
            continue
        back = right_canvas - left_canvas[nearest]
        back_dist = np.hypot(back[:, 0], back[:, 1])
        if int(np.argmin(back_dist)) != index or float(back_dist[index]) > radius:
            continue
        right_px.append(right_stars[index])
        left_px.append(left_stars[nearest])
    if len(right_px) < _MIN_MATCHES:
        return None
    src = np.asarray(right_px, dtype=np.float32)
    dst = np.asarray(left_px, dtype=np.float32)
    _matrix, inlier_mask = cv2.estimateAffinePartial2D(
        src,
        dst,
        method=cv2.RANSAC,
        ransacReprojThreshold=2.5,
        maxIters=400,
        confidence=0.99,
        refineIters=8,
    )
    if inlier_mask is None:
        return None
    keep = inlier_mask.ravel().astype(bool)
    if int(keep.sum()) < _MIN_MATCHES:
        return None
    return src[keep].astype(np.float64), dst[keep].astype(np.float64)


def _solve_similarities(
    prepared: list[dict[str, Any]],
    seeds: dict[int, Any],
    inliers: list[tuple[int, int, Any, Any]],
) -> tuple[dict[int, Any], set[int]]:
    """One similarity per pane. The first pane stays on its seed."""
    indexes = [int(item["index"]) for item in prepared]
    ref = indexes[0]
    connected = {ref}
    changed = True
    while changed:
        changed = False
        for left, right, _src, _dst in inliers:
            if left in connected and right not in connected:
                connected.add(right)
                changed = True
            elif right in connected and left not in connected:
                connected.add(left)
                changed = True
    free = [index for index in indexes if index in connected and index != ref]
    solved = {index: np.array(seeds[index], dtype=np.float64) for index in indexes}
    if not free:
        return solved, connected
    columns = {index: offset * 4 for offset, index in enumerate(free)}
    rows: list[Any] = []
    targets: list[float] = []

    def _known(index: int, x: float, y: float) -> tuple[float, float]:
        a, b, tx, ty = [float(value) for value in seeds[index]]
        return a * x - b * y + tx, b * x + a * y + ty

    def _add_unknown(row_x: Any, row_y: Any, index: int, x: float, y: float, sign: float) -> None:
        base = columns[index]
        row_x[base + 0] += sign * x
        row_x[base + 1] += sign * (-y)
        row_x[base + 2] += sign
        row_y[base + 0] += sign * y
        row_y[base + 1] += sign * x
        row_y[base + 3] += sign

    for left, right, src, dst in inliers:
        if left not in connected or right not in connected:
            continue
        for (qx, qy), (px, py) in zip(src, dst):
            row_x = np.zeros(len(free) * 4, dtype=np.float64)
            row_y = np.zeros(len(free) * 4, dtype=np.float64)
            bx = 0.0
            by = 0.0
            # S(right) - S(left) = 0
            if right in columns:
                _add_unknown(row_x, row_y, right, float(qx), float(qy), 1.0)
            else:
                kx, ky = _known(right, float(qx), float(qy))
                bx -= kx
                by -= ky
            if left in columns:
                _add_unknown(row_x, row_y, left, float(px), float(py), -1.0)
            else:
                kx, ky = _known(left, float(px), float(py))
                bx += kx
                by += ky
            rows.append(row_x)
            rows.append(row_y)
            targets.append(bx)
            targets.append(by)
    if not rows:
        return solved, connected
    matrix = np.vstack(rows)
    answer, *_rest = np.linalg.lstsq(matrix, np.asarray(targets, dtype=np.float64), rcond=None)
    for index, offset in columns.items():
        solved[index] = answer[offset : offset + 4]
    return solved, connected


def _median_residual(solved: dict[int, Any], inliers: list[tuple[int, int, Any, Any]]) -> float | None:
    gaps: list[float] = []
    for left, right, src, dst in inliers:
        if right not in solved or left not in solved:
            continue
        moved = _apply(solved[right], src)
        target = _apply(solved[left], dst)
        gaps.extend(np.hypot(moved[:, 0] - target[:, 0], moved[:, 1] - target[:, 1]).tolist())
    if not gaps:
        return None
    return float(np.median(np.asarray(gaps, dtype=np.float64)))


def _corners(width: int, height: int) -> Any:
    return np.array(
        [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]],
        dtype=np.float64,
    )


def _blend(prepared: list[dict[str, Any]], solved: dict[int, Any]) -> tuple[Any, int, int]:
    placed: list[tuple[dict[str, Any], Any]] = []
    points = []
    for item in prepared:
        params = solved[item["index"]]
        corners = _apply(params, _corners(item["width"], item["height"]))
        placed.append((item, params))
        points.append(corners)
    all_points = np.vstack(points)
    min_x = float(np.min(all_points[:, 0]))
    min_y = float(np.min(all_points[:, 1]))
    max_x = float(np.max(all_points[:, 0]))
    max_y = float(np.max(all_points[:, 1]))
    pad = 2.0
    width = int(np.ceil(max_x - min_x + 1.0 + pad * 2))
    height = int(np.ceil(max_y - min_y + 1.0 + pad * 2))
    width = max(1, min(_MAX_CANVAS, width))
    height = max(1, min(_MAX_CANVAS, height))
    canvas = np.zeros((height, width, 3), dtype=np.float32)
    weight = np.zeros((height, width), dtype=np.float32)
    for item, params in placed:
        shifted = np.array(params, dtype=np.float64)
        shifted[2] += pad - min_x
        shifted[3] += pad - min_y
        matrix = np.array(
            [[shifted[0], -shifted[1], shifted[2]], [shifted[1], shifted[0], shifted[3]]],
            dtype=np.float32,
        )
        warped = cv2.warpAffine(
            item["rgb"],
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        mask = np.full((item["height"], item["width"]), 255, np.uint8)
        warped_mask = cv2.warpAffine(mask, matrix, (width, height), flags=cv2.INTER_NEAREST)
        cover = warped_mask > 0
        if not np.any(cover):
            continue
        dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
        feather = max(8.0, 0.08 * min(item["width"], item["height"]))
        soft = np.clip(dist / feather, 0.0, 1.0).astype(np.float32)
        warped_soft = cv2.warpAffine(soft, matrix, (width, height), flags=cv2.INTER_LINEAR)
        pane_weight = warped_soft * cover.astype(np.float32)
        overlap = (weight > 0.02) & (pane_weight > 0.02)
        adjusted = warped
        if np.count_nonzero(overlap) >= 32:
            existing = canvas[overlap] / np.maximum(weight[overlap, None], 1e-6)
            delta = np.median(existing - warped[overlap], axis=0)
            adjusted = np.clip(warped + delta.astype(np.float32), 0.0, 1.0)
        canvas += adjusted * pane_weight[..., None]
        weight += pane_weight
    painted = weight > 1e-4
    if np.any(painted):
        canvas[painted] /= weight[painted, None]
    image = np.clip(canvas * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return image, width, height
