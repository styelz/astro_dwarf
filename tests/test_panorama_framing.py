from __future__ import annotations

import sys
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
from astro_dwarf.telemetry_view import derive_activity


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _tap() -> TelemetryTap:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
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
