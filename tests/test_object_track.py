"""Manual TRACK locks the tele center instead of slewing to computed coordinates."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import base_pb2, notify_pb2, task_center_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_NORMAL_TRACK_STATE,
    CMD_NOTIFY_STATE_ASTRO_TRACKING,
    CMD_TRACK_START_TRACK,
    CODE_TRACK_TRACKER_INITING,
    TYPE_NOTIFICATION,
    TelemetryTap,
    box_track_reply_failed,
    track_box_norm,
)
from astro_dwarf.device_worker import (
    CMD_TRACK_STOP_TRACK,
    box_track_blocked,
    box_track_rect,
    object_track_box,
)
from astro_dwarf.qt_backend import _object_track_label


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def test_box_covers_the_center_of_the_frame() -> None:
    x, y, w, h, cam = object_track_box(1920, 1080)
    _assert(cam == 0, cam)
    _assert(x + w // 2 == 960 and y + h // 2 == 540, (x, y, w, h))
    _assert(CMD_TRACK_START_TRACK == 14800, CMD_TRACK_START_TRACK)
    _assert(CMD_TRACK_STOP_TRACK == 14801, CMD_TRACK_STOP_TRACK)


def test_normal_track_notify_marks_object_tracking() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    message = notify_pb2.NormalTrackState()
    message.state = 1
    tap.on_packet(CMD_NOTIFY_NORMAL_TRACK_STATE, TYPE_NOTIFICATION, message.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("tracking_state") == "running", snap)
    _assert(snap.get("tracking_kind") == "object", snap)
    _assert(snap.get("tracking_target") == "Live view", snap)

    message.state = 0
    tap.on_packet(CMD_NOTIFY_NORMAL_TRACK_STATE, TYPE_NOTIFICATION, message.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("tracking_state") == "running", snap)
    _assert(snap.get("tracking_kind") == "object", "idle object-track packet must not drop the stop latch")

    astro = notify_pb2.AstroTrackingState()
    astro.state = 0
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_TRACKING, TYPE_NOTIFICATION, astro.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("tracking_state") == "running", snap)
    _assert(snap.get("tracking_kind") == "object", snap)


def test_box_stays_on_the_live_frame() -> None:
    rect = box_track_rect(1920, 1080, 0.8, 0.6, 0.15, 0.2)
    _assert(rect["frame_w"] == 1920 and rect["frame_h"] == 1080, rect)
    _assert(rect["x"] + rect["w"] <= 1920, rect)
    _assert(rect["y"] + rect["h"] <= 1080, rect)
    norm = track_box_norm(rect["x"] * 2, rect["y"] * 2, rect["w"] * 2, rect["h"] * 2, 1920, 1080)
    _assert(norm is not None, norm)
    _assert(abs(norm["track_box_nx"] - rect["nx"]) < 1e-6, norm)
    _assert(abs(norm["track_box_ny"] - rect["ny"]) < 1e-6, norm)


def test_unlabeled_running_track_blocks_a_box() -> None:
    _assert(box_track_blocked({"tracking_state": "running"}) != "", "unlabeled")
    _assert(
        box_track_blocked({"tracking_state": "running", "tracking_kind": "sidereal"}) != "",
        "sidereal",
    )
    _assert(box_track_blocked({"tracking_state": "running", "tracking_kind": "object"}) == "", "center")
    _assert(
        box_track_blocked({"tracking_state": "running", "tracking_kind": "object", "track_box": True}) == "",
        "redraw",
    )


def test_sidereal_running_keeps_a_box_lock() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    tap.update(
        {
            "tracking_kind": "object",
            "tracking_state": "running",
            "tracking_target": "Box lock",
            "track_box": True,
            "track_box_nx": 0.4,
        },
        force=True,
    )
    astro = notify_pb2.AstroTrackingState()
    astro.state = 1
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_TRACKING, TYPE_NOTIFICATION, astro.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("track_box") is True, snap)
    _assert(snap.get("tracking_kind") == "object", snap)
    _assert(snap.get("track_box_nx") == 0.4, snap)
    _assert(snap.get("goto_state") == "idle", snap)

    message = task_center_pb2.ResGetDeviceStateInfo()
    message.code = 0
    message.motion_motor_state_info.exclusive_state.astro_tracking_state.state = 1
    changes = tap.decode_device_state(message)
    _assert(changes.get("tracking_kind") != "sidereal", changes)
    _assert("track_box" not in changes, changes)


def test_sidereal_running_without_a_box_is_sidereal() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    astro = notify_pb2.AstroTrackingState()
    astro.state = 1
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_TRACKING, TYPE_NOTIFICATION, astro.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("tracking_kind") == "sidereal", snap)
    _assert(snap.get("track_box") is False, snap)


def test_tracker_reject_is_recorded() -> None:
    _assert(box_track_reply_failed(-14901), "failed")
    _assert(not box_track_reply_failed(0), "ok")
    _assert(not box_track_reply_failed(None), "no reply")
    _assert(not box_track_reply_failed(CODE_TRACK_TRACKER_INITING), "init")
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    reply = base_pb2.ComResponse()
    reply.code = -14901
    since = time.monotonic()
    tap.on_packet(CMD_TRACK_START_TRACK, 1, reply.SerializeToString())
    _assert(tap.response_after(CMD_TRACK_START_TRACK, since) == -14901, "reply")


def test_object_track_labels_skip_the_catalog() -> None:
    _assert(_object_track_label("Live tap"), "old placeholder")
    _assert(_object_track_label("Live view"), "current placeholder")
    _assert(not _object_track_label("M42"), "a named target still resolves")


def main() -> None:
    test_box_covers_the_center_of_the_frame()
    test_normal_track_notify_marks_object_tracking()
    test_box_stays_on_the_live_frame()
    test_unlabeled_running_track_blocks_a_box()
    test_sidereal_running_keeps_a_box_lock()
    test_sidereal_running_without_a_box_is_sidereal()
    test_tracker_reject_is_recorded()
    test_object_track_labels_skip_the_catalog()
    print("test_object_track: ok")


if __name__ == "__main__":
    main()
