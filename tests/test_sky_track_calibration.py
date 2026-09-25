"""An uncalibrated sky-map slew warns instead of toasting GOTO failed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import base_pb2

from astro_dwarf.device_telemetry import (
    CMD_ASTRO_START_GOTO_DSO,
    CODE_ASTRO_GOTO_FAILED,
    CODE_ASTRO_NEED_CALIBRATION,
    TelemetryTap,
)
from astro_dwarf.device_worker import _goto_accept_error
from astro_dwarf.telemetry_view import (
    TRACKING_NEEDS_CALIBRATION_TOAST,
    AlertEngine,
    tracking_needs_calibration,
)

_RESPONSE = 1


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def test_uncalibrated_goto_failed_is_the_calibration_warning() -> None:
    raw = f"GOTO to start tracking failed: CODE_ASTRO_GOTO_FAILED ({CODE_ASTRO_GOTO_FAILED})"
    _assert(tracking_needs_calibration(raw), raw)
    _assert(tracking_needs_calibration(f"CODE_ASTRO_NEED_CALIBRATION ({CODE_ASTRO_NEED_CALIBRATION})"), "named reject")
    message = _goto_accept_error(CODE_ASTRO_GOTO_FAILED)
    _assert(message is not None and tracking_needs_calibration(message), message)
    _assert("calibrat" in str(message).lower(), message)


def test_reply_sets_need_calibration_and_does_not_error_toast() -> None:
    events: list[dict] = []
    tap = TelemetryTap(lambda message: events.append(message), flush_interval=0)
    tap._base = base_pb2
    reply = base_pb2.ComResponse()
    reply.code = CODE_ASTRO_GOTO_FAILED
    tap.on_packet(CMD_ASTRO_START_GOTO_DSO, _RESPONSE, reply.SerializeToString())
    _assert(tap.snapshot().get("goto_error") == "need_calibration", tap.snapshot())

    alerts = AlertEngine().evaluate({}, {"goto_error": "need_calibration"})
    _assert(len(alerts) == 1, alerts)
    _assert(alerts[0]["level"] == "warning", alerts)
    _assert(alerts[0]["message"] == TRACKING_NEEDS_CALIBRATION_TOAST, alerts)
    _assert(alerts[0]["toast"] == "", "the command result owns the visible warning")


def test_other_goto_rejects_stay_errors() -> None:
    alerts = AlertEngine().evaluate({}, {"goto_error": "failed"})
    _assert(alerts[0]["level"] == "error", alerts)
    _assert(alerts[0]["message"] == "GOTO failed", alerts)
    _assert(alerts[0]["toast"] == "1", alerts)


def main() -> None:
    test_uncalibrated_goto_failed_is_the_calibration_warning()
    test_reply_sets_need_calibration_and_does_not_error_toast()
    test_other_goto_rejects_stay_errors()
    print("test_sky_track_calibration: ok")


if __name__ == "__main__":
    main()
