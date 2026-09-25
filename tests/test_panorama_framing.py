from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_PANO_FRAMING_RECT,
    CMD_NOTIFY_PANO_FRAMING_STATE,
    CMD_NOTIFY_PANO_FRAMING_THUMBNAIL,
    CMD_NOTIFY_PANORAMA_PROGRESS,
    CMD_NOTIFY_PANORAMA_STATE,
    TYPE_NOTIFICATION,
    TelemetryTap,
)
from astro_dwarf.domain import panorama_shot_cell, panorama_shot_grid, panorama_tele_overlay
from astro_dwarf.telemetry_view import derive_activity


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _tap(device_id: str = "") -> TelemetryTap:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0, device_id=device_id)
    tap._notify = notify_pb2
    tap._base = object()
    return tap


def test_panorama_progress_and_state() -> None:
    tap = _tap()
    progress = notify_pb2.PanoramaProgress()
    progress.total_count = 12
    progress.completed_count = 3
    changes = tap._decode(CMD_NOTIFY_PANORAMA_PROGRESS, TYPE_NOTIFICATION, progress.SerializeToString())
    _assert(changes.get("panorama_state") == "running", changes)
    _assert(changes.get("panorama_completed") == 3, changes)
    _assert(changes.get("panorama_total") == 12, changes)
    _assert(derive_activity(changes) == ("panorama", "3/12"), derive_activity(changes))

    idle = notify_pb2.PanoramaState()
    idle.state = 0
    changes = tap._decode(CMD_NOTIFY_PANORAMA_STATE, TYPE_NOTIFICATION, idle.SerializeToString())
    _assert(changes.get("panorama_state") == "idle", changes)
    _assert(changes.get("panorama_completed") == 0, changes)


def test_framing_rect_and_webp() -> None:
    tap = _tap()
    state = notify_pb2.PanoFramingStateNotify()
    state.state = 1
    changes = tap._decode(CMD_NOTIFY_PANO_FRAMING_STATE, TYPE_NOTIFICATION, state.SerializeToString())
    _assert(changes.get("panorama_framing_state") == "running", changes)
    _assert(derive_activity(changes) == ("panorama_frame", "FRAMING"), derive_activity(changes))

    rect = notify_pb2.PanoFramingRectUpdateNotify()
    rect.norm_x_tl = 0.2
    rect.norm_y_tl = 0.3
    rect.norm_x_br = 0.5
    rect.norm_y_br = 0.7
    rect.norm_limit_x_left = 0.0
    rect.norm_limit_y_top = 0.0
    rect.norm_limit_x_right = 1.0
    rect.norm_limit_y_bottom = 1.0
    rect.rect_hor_fov = 45.0
    rect.rect_ver_fov = 26.0
    changes = tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, rect.SerializeToString())
    _assert(changes.get("panorama_has_rect") is True, changes)
    _assert(changes.get("panorama_x1") == 0.2, changes)
    _assert(changes.get("panorama_y2") == 0.7, changes)
    _assert(changes.get("panorama_rect_fov_h") == 45.0, changes)

    thumb = notify_pb2.PanoFramingThumbnailUpdateNotify()
    thumb.webp_data = b"RIFF"
    changes = tap._decode(CMD_NOTIFY_PANO_FRAMING_THUMBNAIL, TYPE_NOTIFICATION, thumb.SerializeToString())
    _assert(changes.get("panorama_scan_rev") == 1, changes)
    path = Path(str(changes.get("panorama_scan_path")))
    _assert(path.is_file() and path.read_bytes() == b"RIFF", changes)
    path.unlink(missing_ok=True)
    path.parent.rmdir()


def test_running_grid_wins_over_framing() -> None:
    activity = derive_activity({
        "panorama_state": "running",
        "panorama_completed": 1,
        "panorama_total": 4,
        "panorama_framing_state": "running",
    })
    _assert(activity == ("panorama", "1/4"), activity)


def test_panorama_scan_cache_survives_reconnect() -> None:
    previous_override = os.environ.get("ASTRO_DWARF_DATA")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASTRO_DWARF_DATA"] = tmp
        try:
            tap = _tap(device_id="dev-1")
            thumb = notify_pb2.PanoFramingThumbnailUpdateNotify()
            thumb.webp_data = b"RIFF-first"
            tap.update(tap._decode(CMD_NOTIFY_PANO_FRAMING_THUMBNAIL, TYPE_NOTIFICATION, thumb.SerializeToString()), force=True)

            tap.persist_panorama_scan()
            cache_path = Path(tmp) / "panorama-cache" / "dev-1.webp"
            _assert(cache_path.is_file(), "persist_panorama_scan did not write the cache file")
            _assert(cache_path.read_bytes() == b"RIFF-first", cache_path.read_bytes())

            # A reconnect (or app restart) creates a brand-new tap with no in-memory state.
            reconnected = _tap(device_id="dev-1")
            reconnected.load_cached_panorama_scan()
            snapshot = reconnected.snapshot()
            _assert(snapshot.get("panorama_scan_path") == str(cache_path), snapshot)
            _assert(snapshot.get("panorama_scan_rev") == 1, snapshot)

            # Loading twice on the same connection must not re-trigger.
            reconnected.update({"panorama_scan_rev": 5}, force=True)
            reconnected.load_cached_panorama_scan()
            _assert(reconnected.snapshot().get("panorama_scan_rev") == 5, reconnected.snapshot())

            reconnected.clear_panorama_scan_cache()
            _assert(not cache_path.is_file(), "clear_panorama_scan_cache left the file behind")
        finally:
            if previous_override is None:
                os.environ.pop("ASTRO_DWARF_DATA", None)
            else:
                os.environ["ASTRO_DWARF_DATA"] = previous_override


def test_panorama_shot_grid_uses_painted_canvas_aspect() -> None:
    # 1800-shot full pano on the ~32:9 scan, DWARF 3 tele 2.95°×1.66°.
    cols, rows = panorama_shot_grid(1800, 32 / 9, 2.95, 1.66)
    _assert((cols, rows) == (60, 30), (cols, rows))
    # A 1:1 canvas would use fewer columns; that is the too-wide overlay.
    square_cols, square_rows = panorama_shot_grid(1800, 1.0, 2.95, 1.66)
    _assert((square_cols, square_rows) == (30, 60), (square_cols, square_rows))
    _assert(cols > square_cols, "tele FOV cells must be narrower on a wide canvas")
    _assert(panorama_shot_grid(1, 32 / 9) == (1, 1), panorama_shot_grid(1, 32 / 9))


def test_panorama_shot_cell_snakes() -> None:
    # 4×2: row 0 LTR, row 1 RTL so the next shot drops and reverses.
    _assert(panorama_shot_cell(0, 4) == (0, 0), panorama_shot_cell(0, 4))
    _assert(panorama_shot_cell(3, 4) == (3, 0), panorama_shot_cell(3, 4))
    _assert(panorama_shot_cell(4, 4) == (3, 1), panorama_shot_cell(4, 4))
    _assert(panorama_shot_cell(7, 4) == (0, 1), panorama_shot_cell(7, 4))
    _assert(panorama_shot_cell(8, 4) == (0, 2), panorama_shot_cell(8, 4))


def test_panorama_tele_overlay_from_motor_span() -> None:
    box = panorama_tele_overlay(20, 30, 0, 80, 10, 50, 2.95, 1.66)
    _assert(box is not None, box)
    _assert(abs(box["nx"] - 20 / 80) < 1e-6, box)
    _assert(abs(box["ny"] - (50 - 30) / 40) < 1e-6, box)
    _assert(abs(box["nw"] - 2.95 / 80) < 1e-6, box)
    _assert(abs(box["nh"] - 1.66 / 40) < 1e-6, box)
    _assert(panorama_tele_overlay(0, 0, 0, 1, 0, 1, 2.95, 1.66) is None, "span smaller than tele FOV")


def test_panorama_pointing_tracks_motor_and_unwraps_az() -> None:
    tap = _tap()
    tap.update({"panorama_state": "running", "motor_pos_1": 350.0, "motor_pos_2": 40.0}, force=True)
    tap.update({"motor_pos_1": 10.0, "motor_pos_2": 20.0}, force=True)
    snap = tap.snapshot()
    _assert(snap.get("panorama_has_pointing") is True, snap)
    _assert(abs(float(snap["panorama_az"]) - 370.0) < 1e-6, snap)
    _assert(abs(float(snap["panorama_az_min"]) - 350.0) < 1e-6, snap)
    _assert(abs(float(snap["panorama_az_max"]) - 370.0) < 1e-6, snap)
    _assert(abs(float(snap["panorama_alt_max"]) - 40.0) < 1e-6, snap)
    _assert(abs(float(snap["panorama_alt_min"]) - 20.0) < 1e-6, snap)


if __name__ == "__main__":
    test_panorama_progress_and_state()
    test_framing_rect_and_webp()
    test_running_grid_wins_over_framing()
    test_panorama_scan_cache_survives_reconnect()
    test_panorama_shot_grid_uses_painted_canvas_aspect()
    test_panorama_shot_cell_snakes()
    test_panorama_tele_overlay_from_motor_span()
    test_panorama_pointing_tracks_motor_and_unwraps_az()
    print("ok")
