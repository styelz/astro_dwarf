from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_worker import _capture_running
from astro_dwarf.qt_backend import control_restore_should_defer, stacking_blocks_action


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


if __name__ == "__main__":
    test_stack_start_blocked_while_capturing()
    test_tracking_blocked_while_stacking()
    test_idle_scope_allows_stack_and_track()
    test_capture_running_helper()
    test_control_restore_defers_while_firmware_still_stacking()
    print("ok")
