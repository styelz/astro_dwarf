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
from astro_dwarf.domain import (
    panorama_canvas_stamp_norm,
    panorama_frame_counts,
    panorama_fov_grid,
    panorama_leave_index,
    panorama_rect_matches,
    panorama_snap_rect,
    panorama_shot_cell,
    panorama_shot_cell_norm,
    panorama_shot_cell_px,
    panorama_shot_grid,
    panorama_stamp_live_ready,
    panorama_tele_overlay,
)
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
    _assert(changes.get("panorama_total") == 0, changes)


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

            rect = notify_pb2.PanoFramingRectUpdateNotify()
            rect.norm_x_tl = 0.0
            rect.norm_y_tl = 0.25
            rect.norm_x_br = 0.4
            rect.norm_y_br = 0.8
            rect.norm_limit_x_left = 0.0
            rect.norm_limit_y_top = 0.0
            rect.norm_limit_x_right = 1.0
            rect.norm_limit_y_bottom = 1.0
            rect.rect_hor_fov = 12.0
            rect.rect_ver_fov = 7.0
            tap.update(tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, rect.SerializeToString()), force=True)

            tap.persist_panorama_scan()
            cache_path = Path(tmp) / "panorama-cache" / "dev-1.webp"
            rect_path = Path(tmp) / "panorama-cache" / "dev-1.json"
            _assert(cache_path.is_file(), "persist_panorama_scan did not write the cache file")
            _assert(cache_path.read_bytes() == b"RIFF-first", cache_path.read_bytes())
            _assert(rect_path.is_file(), "the framing rect was not saved for the next launch")

            # A reconnect (or app restart) creates a brand-new tap with no in-memory state.
            reconnected = _tap(device_id="dev-1")
            reconnected.load_cached_panorama_scan()
            snapshot = reconnected.snapshot()
            _assert(snapshot.get("panorama_scan_path") == str(cache_path), snapshot)
            _assert(snapshot.get("panorama_scan_rev") == 1, snapshot)
            _assert(snapshot.get("panorama_has_rect") is True, snapshot)
            _assert(snapshot.get("panorama_x1") == 0.0, snapshot)
            _assert(snapshot.get("panorama_y2") == 0.8, snapshot)

            # Loading twice on the same connection must not re-trigger.
            reconnected.update({"panorama_scan_rev": 5}, force=True)
            reconnected.load_cached_panorama_scan()
            _assert(reconnected.snapshot().get("panorama_scan_rev") == 5, reconnected.snapshot())

            reconnected.clear_panorama_scan_cache()
            _assert(not cache_path.is_file(), "clear_panorama_scan_cache left the file behind")
            _assert(not rect_path.is_file(), "clear_panorama_scan_cache left the framing rect behind")
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


def test_panorama_stamp_live_skips_whole_canvas() -> None:
    _assert(not panorama_stamp_live_ready(1, 1), "1×1 is the scan, not a tele cell")
    _assert(not panorama_stamp_live_ready(1, 1, 0), "SHOOT before panorama_total is still 1×1")
    _assert(panorama_stamp_live_ready(4, 2, 8), "a real grid may show live tele")
    _assert(panorama_stamp_live_ready(60, 30, 1800), "a wide pano grid may show live tele")


def test_panorama_leave_index_is_the_cell_being_left() -> None:
    _assert(panorama_leave_index(None, 0) is None, panorama_leave_index(None, 0))
    _assert(panorama_leave_index(0, 0) is None, panorama_leave_index(0, 0))
    _assert(panorama_leave_index(0, 1) == 0, panorama_leave_index(0, 1))
    _assert(panorama_leave_index(11, 0) == 11, "progress reset still freezes the last cell")


def test_panorama_tracker_stays_on_a_half_cell_frame() -> None:
    # The opening frame snaps to row 11.5. Rounding that to row 12 parks
    # the reticle half a tele field below the shot.
    opening = panorama_snap_rect(0.467, 0.383, 0.533, 0.617)
    cols, rows = panorama_fov_grid(opening[2] - opening[0], opening[3] - opening[1], 1 / 60, 1 / 30)
    cell = panorama_shot_cell_norm(0, cols, rows, *opening)
    _assert(cell is not None, cell)
    _assert(abs((cell["ny"] - cell["nh"] / 2) - opening[1]) < 1e-9, cell)
    _assert(abs((cell["nx"] - cell["nw"] / 2) - opening[0]) < 1e-9, cell)
    rounded_top = round((opening[1] - 0.0) / (1 / 30)) * (1 / 30)
    _assert(abs(rounded_top - opening[1]) > 0.01, (rounded_top, opening[1]))


def test_panorama_shot_cell_matches_tracker_box() -> None:
    cell = panorama_shot_cell_norm(0, 4, 2, 0.0, 0.0, 1.0, 1.0)
    _assert(cell is not None, cell)
    _assert(abs(cell["nw"] - 0.25) < 1e-6, cell)
    _assert(abs(cell["nh"] - 0.5) < 1e-6, cell)
    _assert(abs(cell["nx"] - 0.125) < 1e-6, cell)
    _assert(abs(cell["ny"] - 0.25) < 1e-6, cell)
    # Odd row snakes: index 4 is col 3 of row 1.
    reverse = panorama_shot_cell_norm(4, 4, 2, 0.0, 0.0, 1.0, 1.0)
    _assert(reverse is not None, reverse)
    _assert(abs(reverse["col"] - 3) < 1e-6, reverse)
    _assert(abs(reverse["row"] - 1) < 1e-6, reverse)
    rect = panorama_shot_cell_px(
        0, 4, 2,
        x1=0.0, y1=0.0, x2=1.0, y2=1.0,
        limit_left=0.0, limit_top=0.0, span_x=1.0, span_y=1.0,
        fit_x=0.0, fit_y=0.0, fit_w=320.0, fit_h=90.0,
    )
    _assert(rect is not None, rect)
    _assert(abs(rect[0] - 0.0) < 1e-6, rect)
    _assert(abs(rect[1] - 0.0) < 1e-6, rect)
    _assert(abs(rect[2] - 80.0) < 1e-6, rect)
    _assert(abs(rect[3] - 45.0) < 1e-6, rect)


def test_panorama_tele_overlay_from_motor_span() -> None:
    box = panorama_tele_overlay(20, 30, 0, 80, 10, 50, 2.95, 1.66)
    _assert(box is not None, box)
    _assert(abs(box["nx"] - 20 / 80) < 1e-6, box)
    _assert(abs(box["ny"] - (50 - 30) / 40) < 1e-6, box)
    _assert(abs(box["nw"] - 2.95 / 80) < 1e-6, box)
    _assert(abs(box["nh"] - 1.66 / 40) < 1e-6, box)
    _assert(panorama_tele_overlay(0, 0, 0, 1, 0, 1, 2.95, 1.66) is None, "span smaller than tele FOV")


def test_panorama_stamp_size_is_full_canvas_cell() -> None:
    stamp = panorama_canvas_stamp_norm(1.0, 1.0, 32 / 9, 2.95, 1.66)
    _assert(stamp is not None, stamp)
    _assert(abs(stamp["nw"] - 1 / 60) < 1e-9, stamp)
    _assert(abs(stamp["nh"] - 1 / 30) < 1e-9, stamp)
    crop_cols, crop_row_count = panorama_fov_grid(0.25, 0.5, stamp["nw"], stamp["nh"])
    full_cols, full_row_count = panorama_fov_grid(1.0, 1.0, stamp["nw"], stamp["nh"])
    _assert((crop_cols, crop_row_count) == (15, 15), (crop_cols, crop_row_count))
    _assert((full_cols, full_row_count) == (60, 30), (full_cols, full_row_count))
    _assert(abs(crop_cols * stamp["nw"] - 0.25) < 1e-9, stamp)
    _assert(abs(full_cols * stamp["nw"] - 1.0) < 1e-9, stamp)


def test_panorama_rect_keeps_a_zero_corner() -> None:
    box = (0.2, 0.3, 0.5, 0.7)
    _assert(panorama_rect_matches(box, (0.20, 0.30, 0.50, 0.70)), box)
    _assert(panorama_rect_matches((0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)), "zero origin is a real corner")
    _assert(not panorama_rect_matches((0.467, 0.383, 0.533, 0.617), (0.386, 0.383, 0.533, 0.665)), "a resize is a different frame")


def _framing_rect(x1: float, y1: float, x2: float, y2: float) -> bytes:
    message = notify_pb2.PanoFramingRectUpdateNotify()
    message.norm_x_tl = x1
    message.norm_y_tl = y1
    message.norm_x_br = x2
    message.norm_y_br = y2
    message.norm_limit_x_right = 1
    message.norm_limit_y_bottom = 1
    message.rect_hor_fov = 45.06
    message.rect_ver_fov = 25.94
    return message.SerializeToString()


def test_latest_device_rect_is_kept() -> None:
    tap = _tap()
    wide = _framing_rect(0.341, 0.175, 0.659, 0.825)
    opening = _framing_rect(0.467, 0.383, 0.533, 0.617)
    tap.on_packet(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, opening)
    tap.on_packet(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, wide)
    tap.on_packet(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, opening)
    snap = tap.snapshot()
    _assert(abs(float(snap["panorama_x1"]) - 0.467) < 1e-6, snap)
    _assert(abs(float(snap["panorama_y1"]) - 0.383) < 1e-6, snap)
    _assert(abs(float(snap["panorama_x2"]) - 0.533) < 1e-6, snap)
    _assert(abs(float(snap["panorama_y2"]) - 0.617) < 1e-6, snap)


def test_panorama_frame_snaps_to_whole_cells() -> None:
    opening = panorama_snap_rect(0.467, 0.383, 0.533, 0.617)
    cols, rows = panorama_fov_grid(opening[2] - opening[0], opening[3] - opening[1], 1 / 60, 1 / 30)
    _assert((cols, rows) == (4, 7), (cols, rows, opening))
    messy = panorama_snap_rect(0.420, 0.370, 0.590, 0.640)
    cols, rows = panorama_fov_grid(messy[2] - messy[0], messy[3] - messy[1], 1 / 60, 1 / 30)
    _assert((cols, rows) == (10, 8), (cols, rows, messy))
    full = panorama_snap_rect(0.250, 0.000, 0.750, 1.000)
    cols, rows = panorama_fov_grid(full[2] - full[0], full[3] - full[1], 1 / 60, 1 / 30)
    _assert((cols, rows) == (30, 30), (cols, rows, full))


def test_framed_area_uses_the_full_grid_cell() -> None:
    # A full panorama is 1800 tele fields, 60×30 on the 32:9 scan.
    # The opening frame is about 4×7 of those cells (28 shots). The cell
    # stays 1/60 × 1/30, which paints as the tele rectangle, not a square.
    stamp = panorama_canvas_stamp_norm(1.0, 1.0, 32 / 9, 2.95, 1.66)
    _assert(stamp is not None, stamp)
    opening_cols, opening_rows = panorama_fov_grid(0.066, 0.234, stamp["nw"], stamp["nh"])
    _assert((opening_cols, opening_rows) == (4, 7), (opening_cols, opening_rows))
    _assert(opening_cols * opening_rows == 28, (opening_cols, opening_rows))
    painted = (stamp["nw"] / stamp["nh"]) * (32 / 9)
    _assert(abs(painted - (2.95 / 1.66)) < 0.02, painted)
    wide_cols, wide_rows = panorama_fov_grid(0.318, 0.650, stamp["nw"], stamp["nh"])
    _assert(abs(stamp["nw"] - 1 / 60) < 1e-9, stamp)
    _assert(wide_cols * wide_rows != 28, (wide_cols, wide_rows))


def test_panorama_frame_counts_match_the_tele_grid() -> None:
    one = panorama_frame_counts(0, 0, 2 / 60, 1 / 30, view_aspect=32 / 9, tele_fov_h=2.95, tele_fov_v=1.66)
    _assert(one == (2, 1), one)
    full = panorama_frame_counts(0, 0, 1, 1, view_aspect=32 / 9, tele_fov_h=2.95, tele_fov_v=1.66)
    _assert(full == (60, 30), full)


def test_panorama_shoot_writes_grid_after_panorama_mode() -> None:
    import astro_dwarf.device_worker as worker
    from astro_dwarf.device_telemetry import (
        CMD_PANORAMA_STOP_FRAMING,
        CMD_PANORAMA_STOP_FRAMING_AND_START_GRID,
        CMD_PANORAMA_UPDATE_FRAMING_RECT,
    )

    sent: list[tuple[int, int, object]] = []

    def fake_send(message, command, module_id, timeout=None):
        sent.append((int(command), int(module_id), message))
        return True

    class Tap:
        def __init__(self) -> None:
            self.state = {"shooting_mode": 2, "shooting_tech": 2}

        def snapshot(self) -> dict:
            return dict(self.state)

        def update(self, changes, force=False) -> None:
            self.state.update(changes)

        def persist_panorama_scan(self) -> None:
            return None

    previous = (worker.send_without_response, worker._forget_pending_command, worker._tap, worker._device)
    worker.send_without_response = fake_send
    worker._forget_pending_command = lambda _command: None
    worker._tap = Tap()
    worker._device = {"model": "Dwarf 3"}
    try:
        ok = worker._panorama_command("panorama_shoot", (0.1, 0.2, 0.4, 0.5, 3, 4))
        _assert(ok is True, ok)
        commands = [item[0] for item in sent]
        _assert(commands[:2] == [16402, 16403], commands)
        _assert(int(sent[0][2].mode) == 7, sent[0][2])
        _assert(int(sent[1][2].tech) == 6, sent[1][2])
        _assert(commands[2] == CMD_PANORAMA_UPDATE_FRAMING_RECT, commands)
        _assert(commands[3] == 16703 and int(sent[3][2].value) == 4, sent[3])
        _assert(int(sent[3][2].param_id) == 0x0702F0000000001C, hex(int(sent[3][2].param_id)))
        _assert(commands[4] == 16703 and int(sent[4][2].value) == 3, sent[4])
        _assert(int(sent[4][2].param_id) == 0x0702F0000000001D, hex(int(sent[4][2].param_id)))
        _assert(commands[5] == CMD_PANORAMA_STOP_FRAMING_AND_START_GRID, commands)
        _assert(commands[6] == CMD_PANORAMA_STOP_FRAMING, commands)
        _assert(worker._tap.snapshot().get("shooting_mode") == 7, worker._tap.snapshot())
        _assert(worker._tap.snapshot().get("shooting_tech") == 6, worker._tap.snapshot())
        _assert(worker._panorama_return_mode == (2, 2), worker._panorama_return_mode)
        _assert(len(commands) == 7, commands)
    finally:
        worker._panorama_return_mode = None
        worker._panorama_seen_active = False
        worker._panorama_shot_seen = False
        (
            worker.send_without_response,
            worker._forget_pending_command,
            worker._tap,
            worker._device,
        ) = previous


def test_panorama_cancel_restores_photo_mode() -> None:
    import astro_dwarf.device_worker as worker
    from astro_dwarf.device_telemetry import CMD_PANORAMA_START_FRAMING, CMD_PANORAMA_STOP_FRAMING

    sent: list[tuple[int, object]] = []

    def fake_send(message, command, module_id, timeout=None):
        sent.append((int(command), message))
        return True

    class Tap:
        def __init__(self) -> None:
            self.state = {"shooting_mode": 1, "shooting_tech": 1}

        def snapshot(self) -> dict:
            return dict(self.state)

        def update(self, changes, force=False) -> None:
            self.state.update(changes)

    previous = (worker.send_without_response, worker._forget_pending_command, worker._tap, worker._device)
    worker.send_without_response = fake_send
    worker._forget_pending_command = lambda _command: None
    worker._tap = Tap()
    worker._device = {"model": "Dwarf 3"}
    worker._panorama_return_mode = None
    worker._panorama_seen_active = False
    try:
        started = worker._panorama_command("panorama_frame_start", ())
        _assert(started is True, started)
        _assert(worker._panorama_return_mode == (1, 1), worker._panorama_return_mode)
        stopped = worker._panorama_command("panorama_frame_stop", ())
        _assert(stopped is True, stopped)
        _assert(sent[-2][0] == 16402 and int(sent[-2][1].mode) == 1, sent[-2])
        _assert(sent[-1][0] == 16403 and int(sent[-1][1].tech) == 1, sent[-1])
        _assert(CMD_PANORAMA_START_FRAMING in [item[0] for item in sent], sent)
        _assert(CMD_PANORAMA_STOP_FRAMING in [item[0] for item in sent], sent)
        _assert(worker._tap.snapshot().get("shooting_mode") == 1, worker._tap.snapshot())
        _assert(worker._panorama_return_mode is None, worker._panorama_return_mode)
    finally:
        worker._panorama_return_mode = None
        worker._panorama_seen_active = False
        worker._panorama_shot_seen = False
        (
            worker.send_without_response,
            worker._forget_pending_command,
            worker._tap,
            worker._device,
        ) = previous


def test_finished_panorama_returns_to_photo() -> None:
    import heapq

    import astro_dwarf.device_worker as worker

    sent: list[tuple[int, object]] = []

    def fake_send(message, command, module_id, timeout=None):
        sent.append((int(command), message))
        return True

    class Tap:
        def __init__(self) -> None:
            self.state = {
                "shooting_mode": 7,
                "shooting_tech": 6,
                "panorama_state": "running",
                "panorama_framing_state": "running",
            }

        def snapshot(self) -> dict:
            return dict(self.state)

        def update(self, changes, force=False) -> None:
            self.state.update(changes)

    previous = (worker.send_without_response, worker._forget_pending_command, worker._tap)
    worker.send_without_response = fake_send
    worker._forget_pending_command = lambda _command: None
    worker._tap = Tap()
    worker._panorama_return_mode = (2, 2)
    worker._panorama_seen_active = False
    worker._panorama_shot_seen = False
    try:
        worker._maybe_restore_after_panorama(worker._tap.snapshot())
        _assert(worker._panorama_shot_seen is True, "a running shoot must be remembered")
        _assert(not worker._queued_internal("leave_panorama_mode"), "still shooting")
        worker._tap.state["panorama_state"] = "idle"
        worker._maybe_restore_after_panorama(worker._tap.snapshot())
        _assert(worker._panorama_return_mode == (1, 1), worker._panorama_return_mode)
        _assert(worker._tap.snapshot().get("panorama_framing_state") == "idle", worker._tap.snapshot())
        _assert(worker._queued_internal("leave_panorama_mode"), "photo restore was not queued")
        _assert(worker._leave_panorama_mode() is True, "leave failed")
        _assert(sent[-2][0] == 16402 and int(sent[-2][1].mode) == 1, sent)
        _assert(sent[-1][0] == 16403 and int(sent[-1][1].tech) == 1, sent)
        _assert(worker._tap.snapshot().get("shooting_mode") == 1, worker._tap.snapshot())
    finally:
        worker._panorama_return_mode = None
        worker._panorama_seen_active = False
        worker._panorama_shot_seen = False
        with worker._commands.mutex:
            retained = [item for item in worker._commands.queue if item[2].get("command") != "leave_panorama_mode"]
            worker._commands.queue.clear()
            worker._commands.queue.extend(retained)
            heapq.heapify(worker._commands.queue)
        (
            worker.send_without_response,
            worker._forget_pending_command,
            worker._tap,
        ) = previous


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


def test_repeated_framing_rect_is_saved_once() -> None:
    previous_override = os.environ.get("ASTRO_DWARF_DATA")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["ASTRO_DWARF_DATA"] = tmp
        try:
            tap = _tap(device_id="dev-2")
            rect = notify_pb2.PanoFramingRectUpdateNotify()
            rect.norm_x_tl = 0.1
            rect.norm_y_tl = 0.2
            rect.norm_x_br = 0.6
            rect.norm_y_br = 0.7
            rect.norm_limit_x_right = 1.0
            rect.norm_limit_y_bottom = 1.0
            rect.rect_hor_fov = 20.0
            rect.rect_ver_fov = 11.0
            data = rect.SerializeToString()
            rect_path = Path(tmp) / "panorama-cache" / "dev-2.json"
            tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, data)
            _assert(rect_path.is_file(), "first rect is saved")
            rect_path.write_text("sentinel", encoding="utf-8")
            changes = tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, data)
            _assert(changes.get("panorama_x1") == rect.norm_x_tl, changes)
            _assert(rect_path.read_text(encoding="utf-8") == "sentinel", "an identical rect is not rewritten")
            rect.norm_x_br = 0.65
            tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, rect.SerializeToString())
            _assert('"panorama_x2": 0.65' in rect_path.read_text(encoding="utf-8"), "a moved rect is saved")
            tap.clear_panorama_scan_cache()
            tap._decode(CMD_NOTIFY_PANO_FRAMING_RECT, TYPE_NOTIFICATION, rect.SerializeToString())
            _assert(rect_path.is_file(), "the same rect is saved again after the cache is cleared")
        finally:
            if previous_override is None:
                os.environ.pop("ASTRO_DWARF_DATA", None)
            else:
                os.environ["ASTRO_DWARF_DATA"] = previous_override


if __name__ == "__main__":
    test_panorama_progress_and_state()
    test_framing_rect_and_webp()
    test_running_grid_wins_over_framing()
    test_panorama_scan_cache_survives_reconnect()
    test_panorama_shot_grid_uses_painted_canvas_aspect()
    test_panorama_shot_cell_snakes()
    test_panorama_stamp_live_skips_whole_canvas()
    test_panorama_leave_index_is_the_cell_being_left()
    test_panorama_tracker_stays_on_a_half_cell_frame()
    test_panorama_shot_cell_matches_tracker_box()
    test_panorama_tele_overlay_from_motor_span()
    test_panorama_stamp_size_is_full_canvas_cell()
    test_panorama_rect_keeps_a_zero_corner()
    test_latest_device_rect_is_kept()
    test_panorama_frame_snaps_to_whole_cells()
    test_framed_area_uses_the_full_grid_cell()
    test_panorama_frame_counts_match_the_tele_grid()
    test_panorama_shoot_writes_grid_after_panorama_mode()
    test_panorama_cancel_restores_photo_mode()
    test_finished_panorama_returns_to_photo()
    test_panorama_pointing_tracks_motor_and_unwraps_az()
    print("ok")
