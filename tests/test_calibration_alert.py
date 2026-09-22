"""A failed calibration must not toast as complete."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import base_pb2, notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_ASTRO_START_CALIBRATION,
    CMD_NOTIFY_STATE_ASTRO_CALIBRATION,
    CODE_ASTRO_CALIBRATION_FAILED,
    CODE_ASTRO_PLATE_SOLVING_FAILED,
    TYPE_NOTIFICATION,
    TelemetryTap,
    calibration_reply_failed,
)
from astro_dwarf.telemetry_view import AlertEngine

_RESPONSE = 1


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _messages(alerts: list[dict[str, str]]) -> list[str]:
    return [item["message"] for item in alerts]


def test_reply_codes() -> None:
    _assert(calibration_reply_failed(CODE_ASTRO_CALIBRATION_FAILED), "calibration failed is terminal")
    _assert(not calibration_reply_failed(0), "code 0 is not a failure")
    _assert(not calibration_reply_failed(CODE_ASTRO_PLATE_SOLVING_FAILED), "plate-solve retry continues")


def test_success_still_toasts_complete() -> None:
    alerts = AlertEngine().evaluate(
        {"calibration_state": "solving", "calibration_phase": 1},
        {"calibration_state": "idle", "calibration_phase": 1},
    )
    _assert(_messages(alerts) == ["Calibration complete"], alerts)
    _assert(alerts[0]["detail"] == "1 plate solve", alerts)
    _assert(alerts[0]["level"] == "success", alerts)


def test_failure_reply_then_idle_is_not_complete() -> None:
    engine = AlertEngine()
    failed = engine.evaluate(
        {"calibration_state": "solving", "calibration_phase": 1},
        {"calibration_state": "solving", "calibration_phase": 1, "calibration_error": "failed"},
    )
    _assert(_messages(failed) == ["Calibration failed"], failed)
    _assert(failed[0]["level"] == "error", failed)
    done = engine.evaluate(
        {"calibration_state": "solving", "calibration_phase": 1, "calibration_error": "failed"},
        {"calibration_state": "idle", "calibration_phase": 1, "calibration_error": "failed"},
    )
    _assert(done == [], done)


def test_idle_with_error_in_the_same_sample_is_not_complete() -> None:
    alerts = AlertEngine().evaluate(
        {"calibration_state": "solving", "calibration_phase": 1},
        {"calibration_state": "idle", "calibration_phase": 1, "calibration_error": "failed"},
    )
    _assert(_messages(alerts) == ["Calibration failed"], alerts)
    _assert(not any(item["message"] == "Calibration complete" for item in alerts), alerts)


def test_tap_publishes_calibration_failure_and_keeps_it_through_solving() -> None:
    events: list[dict] = []
    tap = TelemetryTap(lambda message: events.append(message), flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    tap.update({"calibration_state": "solving", "calibration_phase": 1}, force=True)

    reply = base_pb2.ComResponse()
    reply.code = CODE_ASTRO_CALIBRATION_FAILED
    tap.on_packet(CMD_ASTRO_START_CALIBRATION, _RESPONSE, reply.SerializeToString())
    _assert(tap.snapshot().get("calibration_error") == "failed", tap.snapshot())

    solving = notify_pb2.AstroCalibrationState()
    solving.state = 4
    solving.plate_solving_times = 1
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_CALIBRATION, TYPE_NOTIFICATION, solving.SerializeToString())
    _assert(tap.snapshot().get("calibration_error") == "failed", "a later plate-solve cleared the failure")

    idle = notify_pb2.AstroCalibrationState()
    idle.state = 0
    idle.plate_solving_times = 1
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_CALIBRATION, TYPE_NOTIFICATION, idle.SerializeToString())
    _assert(tap.snapshot().get("calibration_state") == "idle", tap.snapshot())
    _assert(tap.snapshot().get("calibration_error") == "failed", tap.snapshot())

    retry = base_pb2.ComResponse()
    retry.code = CODE_ASTRO_PLATE_SOLVING_FAILED
    before = len(events)
    tap.on_packet(CMD_ASTRO_START_CALIBRATION, _RESPONSE, retry.SerializeToString())
    _assert(len(events) == before, "a plate-solve retry must not publish a new failure")


def test_new_calibration_clears_the_previous_failure() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    tap._base = base_pb2
    tap._notify = notify_pb2
    tap.update({"calibration_state": "idle", "calibration_error": "failed"}, force=True)
    running = notify_pb2.AstroCalibrationState()
    running.state = 1
    running.plate_solving_times = 0
    tap.on_packet(CMD_NOTIFY_STATE_ASTRO_CALIBRATION, TYPE_NOTIFICATION, running.SerializeToString())
    snap = tap.snapshot()
    _assert(snap.get("calibration_state") == "running", snap)
    _assert(snap.get("calibration_error") == "", snap)


def main() -> None:
    test_reply_codes()
    test_success_still_toasts_complete()
    test_failure_reply_then_idle_is_not_complete()
    test_idle_with_error_in_the_same_sample_is_not_complete()
    test_tap_publishes_calibration_failure_and_keeps_it_through_solving()
    test_new_calibration_clears_the_previous_failure()
    print("test_calibration_alert: ok")


if __name__ == "__main__":
    main()
