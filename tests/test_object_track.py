"""Manual TRACK locks the tele center instead of slewing to computed coordinates."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import base_pb2, notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_NORMAL_TRACK_STATE,
    CMD_NOTIFY_STATE_ASTRO_TRACKING,
    TYPE_NOTIFICATION,
    TelemetryTap,
)
from astro_dwarf.device_worker import CMD_TRACK_START_TRACK, CMD_TRACK_STOP_TRACK, object_track_box
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


def test_object_track_labels_skip_the_catalog() -> None:
    _assert(_object_track_label("Live tap"), "old placeholder")
    _assert(_object_track_label("Live view"), "current placeholder")
    _assert(not _object_track_label("M42"), "a named target still resolves")


def main() -> None:
    test_box_covers_the_center_of_the_frame()
    test_normal_track_notify_marks_object_tracking()
    test_object_track_labels_skip_the_catalog()
    print("test_object_track: ok")


if __name__ == "__main__":
    main()
