from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_telemetry import is_chatter
from astro_dwarf.device_worker import _capture_running, capture_should_skip_dark_hold
from astro_dwarf.qt_backend import (
    command_required_shooting_mode,
    command_should_auto_enter_dso,
    control_restore_should_defer,
    stacking_blocks_action,
    tracking_blocks_action,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_stack_start_blocked_while_capturing() -> None:
    _assert(
        stacking_blocks_action("stack", capturing=True, mosaic_running=False) != "",
        "a second stack start must be refused while capture is running",
    )
    _assert(
        stacking_blocks_action("stack", capturing=False, mosaic_running=True) != "",
        "a second stack start must be refused while a mosaic is running",
    )
    _assert(
        stacking_blocks_action("stop_astro", capturing=True, mosaic_running=False) == "",
        "stop_astro must still abort a running stack",
    )


def test_tracking_blocked_while_stacking() -> None:
    for operation in ("track", "sky_track", "stop_goto"):
        _assert(
            stacking_blocks_action(operation, capturing=True, mosaic_running=False) != "",
            f"{operation} must not drop tracking under a running stack",
        )
        _assert(
            stacking_blocks_action(operation, capturing=False, mosaic_running=True) != "",
            f"{operation} must not interrupt a mosaic",
        )
    _assert(
        stacking_blocks_action("stop_goto", capturing=False, mosaic_running=False) == "",
        "stop_goto stays available when nothing is stacking",
    )


def test_calibrate_blocked_while_tracking() -> None:
    _assert(
        tracking_blocks_action("calibrate", tracking=True) == "Stop tracking before calibrating",
        "calibrate must be refused while sidereal tracking owns the mount",
    )
    _assert(tracking_blocks_action("calibrate", tracking=False) == "", "idle calibrate stays available")
    for operation in ("track", "stop_goto", "polar", "polar_position", "stack"):
        _assert(
            tracking_blocks_action(operation, tracking=True) == "",
            f"{operation} is not the calibrate conflict",
        )


def test_idle_scope_allows_stack_and_track() -> None:
    for operation in ("stack", "track", "sky_track", "stop_goto", "calibrate"):
        _assert(
            stacking_blocks_action(operation, capturing=False, mosaic_running=False) == "",
            f"{operation} must not be blocked when idle",
        )


def test_capture_running_helper() -> None:
    _assert(_capture_running({"capture_active": True}), "active flag is capturing")
    _assert(_capture_running({"capture_state": "running"}), "running state is capturing")
    _assert(not _capture_running({"capture_active": False, "capture_state": "idle"}), "idle is not capturing")


def test_control_restore_defers_while_firmware_still_stacking() -> None:
    idle = dict(
        session_active=False,
        stopping=False,
        worker_busy=False,
        mosaic_running=False,
        capturing=False,
    )
    _assert(not control_restore_should_defer(**idle), "idle reconnect may restore CONTROL")
    _assert(
        control_restore_should_defer(**{**idle, "capturing": True}),
        "stop_astro is not a stop_all pending, so capturing must defer restore",
    )
    _assert(
        control_restore_should_defer(**{**idle, "mosaic_running": True}),
        "a running mosaic must not receive restored exposure or count",
    )
    _assert(
        control_restore_should_defer(**{**idle, "worker_busy": True}),
        "a busy worker still owns the telescope",
    )


def test_missing_darks_hold_is_skipped() -> None:
    held = dict(needs_continue=True, continued=False, frames=0, elapsed_s=0.0, exposure_s=15.0)
    _assert(capture_should_skip_dark_hold(**held), "a missing-darks flag must continue immediately")
    _assert(
        not capture_should_skip_dark_hold(**{**held, "continued": True}),
        "continue-shooting is sent once",
    )
    _assert(
        not capture_should_skip_dark_hold(
            needs_continue=False, continued=False, frames=0, elapsed_s=20.0, exposure_s=15.0
        ),
        "a real first exposure is allowed to finish",
    )
    _assert(
        capture_should_skip_dark_hold(
            needs_continue=False, continued=False, frames=0, elapsed_s=70.0, exposure_s=15.0
        ),
        "running at 0 frames past one exposure is the darks hold",
    )
    _assert(
        not capture_should_skip_dark_hold(
            needs_continue=False, continued=False, frames=1, elapsed_s=70.0, exposure_s=15.0
        ),
        "frames already stacking are left alone",
    )
    _assert(
        is_chatter("START_CAPTURE : CODE_ASTRO_DARK_NOT_FOUND message receive (non-blocking, capture continues)"),
        "the missing-darks warning must not surface as a HUD prompt",
    )
    _assert(
        is_chatter("START_CAPTURE : CODE_ASTRO_DARK_TEMP_MISMATCH message receive (non-blocking, capture continues)"),
        "a dark temperature mismatch must not surface as a HUD prompt",
    )


def test_photo_mode_auto_enters_dso_for_tracking() -> None:
    _assert(command_required_shooting_mode("sky_track") == 2, "sky track needs DSO")
    _assert(command_required_shooting_mode("track") == 2, "track needs DSO")
    _assert(command_required_shooting_mode("photo") == 1, "photo stays PHOTO")
    _assert(command_should_auto_enter_dso("sky_track", 1), "PHOTO sky track switches to DSO")
    _assert(command_should_auto_enter_dso("track", 1), "PHOTO track switches to DSO")
    _assert(not command_should_auto_enter_dso("sky_track", 2), "already DSO does not switch again")
    _assert(not command_should_auto_enter_dso("sky_track", 8), "Sun mode stays gated")
    _assert(not command_should_auto_enter_dso("stack", 1), "stack still asks for DSO")
    _assert(not command_should_auto_enter_dso("calibrate", 1), "calibrate still asks for DSO")
    _assert(not command_should_auto_enter_dso("photo", 2), "photo does not auto-switch from DSO")


if __name__ == "__main__":
    test_stack_start_blocked_while_capturing()
    test_tracking_blocked_while_stacking()
    test_calibrate_blocked_while_tracking()
    test_idle_scope_allows_stack_and_track()
    test_capture_running_helper()
    test_control_restore_defers_while_firmware_still_stacking()
    test_missing_darks_hold_is_skipped()
    test_photo_mode_auto_enters_dso_for_tracking()
    print("ok")
