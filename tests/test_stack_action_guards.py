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
    control_restore_should_apply_mode,
    control_restore_should_defer,
    preview_should_preserve_shooting_mode,
    preview_should_skip_go_live,
    stacking_blocks_action,
    tracking_blocks_action,
)
from astro_dwarf.telemetry_view import (
    reconnect_holds_device,
    reconnect_infers_panorama_framing,
    reconnect_join_label,
    recovery_should_drop,
    telemetry_operation_live,
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
        not capture_should_skip_dark_hold(
            needs_continue=False,
            continued=False,
            frames=0,
            elapsed_s=70.0,
            exposure_s=15.0,
            taken=1,
        ),
        "a captured subframe counts even while stacked is still 0",
    )
    _assert(
        not capture_should_skip_dark_hold(
            needs_continue=True, continued=False, frames=0, elapsed_s=0.0, exposure_s=15.0, taken=1
        ),
        "continue-shooting must not interrupt a stack that has already taken a frame",
    )
    _assert(
        is_chatter("START_CAPTURE : CODE_ASTRO_DARK_NOT_FOUND message receive (non-blocking, capture continues)"),
        "the missing-darks warning must not surface as a HUD prompt",
    )
    _assert(
        is_chatter("START_CAPTURE : CODE_ASTRO_DARK_TEMP_MISMATCH message receive (non-blocking, capture continues)"),
        "a dark temperature mismatch must not surface as a HUD prompt",
    )


def test_reconnect_joins_live_mode_and_drops_a_restart() -> None:
    framing = {"shooting_mode": 7}
    _assert(reconnect_infers_panorama_framing(framing), "mode 7 with homed steppers is framing")
    _assert(reconnect_holds_device(framing), "open panorama must not be overwritten")
    _assert(
        not control_restore_should_apply_mode(2, 7, preview_active=False, tracking=False, telemetry=framing),
        "saved DSO must not replace panorama framing",
    )
    _assert(preview_should_preserve_shooting_mode(framing, 2), "preview must leave panorama mode alone")
    _assert(preview_should_skip_go_live(framing, 2), "GoLive must not close panorama framing")
    _assert(reconnect_join_label(framing) == "panorama framing", reconnect_join_label(framing))

    restarted = {"shooting_mode": 7, "motors_unhomed": True}
    _assert(not reconnect_infers_panorama_framing(restarted), "a power cycle is not an open frame")
    _assert(not reconnect_holds_device(restarted), "a restarted head accepts the saved setup")
    _assert(
        control_restore_should_apply_mode(1, 7, preview_active=False, tracking=False, telemetry=restarted),
        "saved PHOTO applies after a restart",
    )
    _assert(recovery_should_drop(restarted, same_night=True), "same-night power cycle drops the parked run")

    stacking = {"capture_state": "running", "capture_active": True, "shooting_mode": 2}
    _assert(telemetry_operation_live(stacking), "a stack is a live job")
    _assert(not recovery_should_drop(stacking, same_night=False), "a live stack is joined even next night")
    _assert("stack" in reconnect_join_label(stacking), reconnect_join_label(stacking))
    _assert(
        control_restore_should_defer(
            session_active=False,
            stopping=False,
            worker_busy=False,
            mosaic_running=False,
            capturing=False,
            device_live=True,
        ),
        "recording and panorama defer exposure restore",
    )

    recording = {"record_state": "running", "shooting_mode": 1}
    _assert(telemetry_operation_live(recording), "recording is a live job")
    _assert(preview_should_skip_go_live(recording, 1), "GoLive must not stop a recording")

    idle_next_night = {"shooting_mode": 1}
    _assert(recovery_should_drop(idle_next_night, same_night=False), "an idle telescope next night is a fresh start")
    _assert(not recovery_should_drop(idle_next_night, same_night=True), "the same night may continue an idle plan")
    _assert(reconnect_join_label(idle_next_night) == "", "idle photo has nothing to join")


def test_photo_mode_auto_enters_dso_for_tracking() -> None:
    _assert(command_required_shooting_mode("sky_track") == 2, "sky track needs DSO")
    _assert(command_required_shooting_mode("track") == 2, "track needs DSO")
    _assert(command_required_shooting_mode("photo") == 1, "photo stays PHOTO")
    _assert(command_required_shooting_mode("panorama_shoot") is None, "panorama shoot is not photo-only")
    _assert(command_required_shooting_mode("panorama_frame_start") is None, "panorama framing is not photo-only")
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
    test_reconnect_joins_live_mode_and_drops_a_restart()
    test_photo_mode_auto_enters_dso_for_tracking()
    print("ok")
