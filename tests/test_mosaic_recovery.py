from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_worker import (
    _engine_busy_error,
    _firmware_mosaic,
    _focus_soft_fail,
    _goto_fail_reason,
    _goto_keep_waiting_for_solve,
    _goto_needs_camera_reopen,
    _goto_solve_stalled,
    _goto_stalled_error,
    _goto_never_started_error,
    _goto_solve_timeout_error,
    _goto_started,
    _goto_terminal_fail,
    _goto_wait_complete,
    _firmware_mosaic_grid_finished,
    _mosaic_busy,
    _mosaic_idle_timeout_s,
    _session_needs_infinity_after_autofocus,
    _stop_targets,
    CODE_ASTRO_GOTO_FAILED,
    CODE_FOCUS_ASTRO_AUTO_FOCUS_FAST_ERROR,
    CODE_FOCUS_ASTRO_AUTO_FOCUS_SLOW_ERROR,
    CODE_FOCUS_EXP_TOO_LONG,
    mosaic_pane_goto_fail_message,
    _CAPTURE_BUSY_RETRY_S,
    _GOTO_BUSY_TIMEOUT_S,
    _GOTO_SOLVE_STALL_S,
    _GOTO_SOLVE_TIMEOUT_S,
    _MOSAIC_LAST_PANE_IDLE_S,
    _MOSAIC_PANE_GAP_S,
)
from astro_dwarf.domain import Target, TargetKind
from astro_dwarf.services import (
    is_mosaic_pane_name,
    live_mosaic_keep_sheet,
    live_mosaic_resume_plan,
    live_mosaic_scheduler_action,
    mosaic_group_title,
    mosaic_pane_footprints,
    mosaic_pane_index,
    sky_names_related,
)
from astro_dwarf.storage import SessionStore


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_firmware_mosaic_detection() -> None:
    _assert(_firmware_mosaic({"mosaic": {"rows": 2, "columns": 2}}), "2x2 firmware mosaic")
    _assert(not _firmware_mosaic({"mosaic": {"rows": 1, "columns": 1}}), "1x1 is a single stack")
    _assert(
        not _firmware_mosaic({"mosaic": {"rows": 2, "columns": 2, "grid_rows": 2, "grid_columns": 2}}),
        "imported plan is per-pane stacks",
    )
    _assert(not _firmware_mosaic({}), "missing mosaic")


def test_mosaic_busy_and_idle_timeout() -> None:
    _assert(_mosaic_busy({"capture_active": True}), "capturing")
    _assert(_mosaic_busy({"mosaic_active": True}), "firmware mosaic flag")
    _assert(_mosaic_busy({"goto_state": "running"}), "slew between panes")
    _assert(not _mosaic_busy({"capture_state": "idle"}), "idle stack")
    _assert(_mosaic_idle_timeout_s({"mosaic_index": 4}, 4) == _MOSAIC_LAST_PANE_IDLE_S, "last pane")
    _assert(_mosaic_idle_timeout_s({"mosaic_index": 2}, 4) == _MOSAIC_PANE_GAP_S, "more panes remain")
    _assert(_mosaic_idle_timeout_s({}, 4) == _MOSAIC_PANE_GAP_S, "unknown pane after reconnect")


def test_live_mosaic_resume_plan() -> None:
    _assert(live_mosaic_resume_plan("stacking", 2, 4, True) == (2, True), "join current pane")
    _assert(live_mosaic_resume_plan("stacking", 2, 4, False) == (2, False), "interrupted stack is retried")
    _assert(live_mosaic_resume_plan("complete", 4, 4, False) is None, "last pane already done")
    _assert(live_mosaic_resume_plan("complete", 2, 4, False) == (3, False), "completed pane advances")
    _assert(live_mosaic_resume_plan("goto", 3, 4, False) == (3, False), "resume the slew")
    _assert(live_mosaic_resume_plan("changing", 2, 4, True) == (2, False), "do not join leftover capture while changing panes")
    _assert(live_mosaic_resume_plan("recovered", 1, 4, False) == (1, False), "unknown phase starts current")
    _assert(live_mosaic_resume_plan("stacking", 4, 4, True) == (4, True), "join last pane")


def test_recovered_firmware_mosaic_restarts_unless_the_grid_finished() -> None:
    idle = {"capture_active": False, "capture_state": "idle", "goto_state": "idle", "mosaic_index": 2}
    _assert(not _firmware_mosaic_grid_finished(idle, 4), "stopped on pane 2 of 4")
    _assert(not _firmware_mosaic_grid_finished({**idle, "mosaic_index": 0}, 4), "no pane reported")
    finished = {**idle, "mosaic_index": 4}
    _assert(_firmware_mosaic_grid_finished(finished, 4), "every pane already shot")
    running = {**finished, "capture_active": True, "capture_state": "running"}
    _assert(not _firmware_mosaic_grid_finished(running, 4), "still exposing the last pane")
    _assert(_mosaic_idle_timeout_s(finished, 4) == _MOSAIC_LAST_PANE_IDLE_S, "finished grid uses the short idle")
    _assert(_mosaic_idle_timeout_s(idle, 4) == _MOSAIC_PANE_GAP_S, "mid-grid idle still waits out a pane gap")


def test_failed_live_mosaic_does_not_block_scheduler() -> None:
    _assert(live_mosaic_scheduler_action("goto", True, False, True) == "wait", "running worker holds the queue")
    _assert(live_mosaic_scheduler_action("stacking", False, True, True) == "resume", "join the live stack")
    _assert(
        live_mosaic_scheduler_action("goto", False, False, True) == "yield",
        "failed leftover must not block a due session",
    )
    _assert(
        live_mosaic_scheduler_action("stacking", False, False, False) == "idle",
        "keep recovery until reconnect or a session is due",
    )
    _assert(live_mosaic_scheduler_action("", False, False, True) == "idle", "no mosaic")


def test_goto_reopens_camera_when_slew_never_starts() -> None:
    _assert(_goto_never_started_error(RuntimeError("GOTO pane 2 did not start")), "exact no-start")
    _assert(_goto_needs_camera_reopen(RuntimeError("GOTO pane 2 did not start")), "no-start after stack")
    _assert(_goto_needs_camera_reopen(RuntimeError("GOTO pane 2 failed: CAMERA_TELE_CLOSED (-10501)")), "closed")
    _assert(not _goto_needs_camera_reopen(RuntimeError("GOTO pane 2 failed: FUNCTION_BUSY (-11501)")), "busy")
    tracking_timeout = RuntimeError(
        "GOTO pane 3 finished but tracking did not start. "
        "Set the telescope to your observing site, then retry."
    )
    _assert(not _goto_never_started_error(tracking_timeout), "tracking timeout is not no-start")
    _assert(not _goto_needs_camera_reopen(tracking_timeout), "tracking timeout is not a closed camera")
    solve_timeout = RuntimeError("GOTO pane 3 timed out after 90 s while plate-solving")
    _assert(_goto_solve_timeout_error(solve_timeout), "solve timeout token")
    _assert(not _goto_needs_camera_reopen(solve_timeout), "long plate-solve is not a closed camera")
    stalled = RuntimeError("GOTO target plate-solve stalled after 90 s")
    _assert(_goto_stalled_error(stalled), "first hang is retried")
    _assert(not _goto_solve_timeout_error(stalled), "a retry is not the terminal timeout")
    _assert(not _goto_needs_camera_reopen(stalled), "a stalled solve is not a closed camera")
    _assert(not _goto_terminal_fail(stalled), "the first stall must be sent again")


def test_goto_keeps_waiting_while_plate_solving() -> None:
    _assert(_GOTO_SOLVE_TIMEOUT_S >= 600.0, "a slew that is still moving can exceed 5 min")
    _assert(_GOTO_SOLVE_STALL_S <= 90.0, "a hung plate-solve must not sit for minutes")
    _assert(_goto_solve_stalled("solving", _GOTO_SOLVE_STALL_S), "solving at the stall is retried")
    _assert(not _goto_solve_stalled("solving", _GOTO_SOLVE_STALL_S - 1), "a normal solve is still inside the window")
    _assert(not _goto_solve_stalled("running", 120.0), "slewing is not a stalled solve")
    _assert(not _goto_keep_waiting_for_solve("solving", 301.0, 300.0), "a stuck plate-solve is not a long slew")
    _assert(_goto_keep_waiting_for_solve("running", 301.0, 300.0), "still slewing past 5m")
    _assert(not _goto_keep_waiting_for_solve("idle", 301.0, 300.0), "idle uses tracking timeout")
    _assert(not _goto_keep_waiting_for_solve("solving", 200.0, 300.0), "before base timeout")
    _assert(not _goto_keep_waiting_for_solve("running", _GOTO_SOLVE_TIMEOUT_S, 300.0), "hard cap")


def test_engine_busy_error_matches_firmware_reply() -> None:
    _assert(_engine_busy_error(RuntimeError("GOTO pane 2 failed: CODE_ASTRO_FUNCTION_BUSY (-11501)")), "busy name")
    _assert(_engine_busy_error(RuntimeError("GOTO pane 2 failed: FUNCTION_BUSY (-11501)")), "short name")
    _assert(_engine_busy_error(RuntimeError("GOTO pane 2 failed: CODE_ASTRO_GOTO_RUNNING (-11508)")), "goto running")
    _assert(not _engine_busy_error(RuntimeError("GOTO pane 2 failed: CAMERA_TELE_CLOSED (-10501)")), "closed")
    _assert(
        not _engine_busy_error(RuntimeError(f"GOTO pane 3 failed: CODE_ASTRO_GOTO_FAILED ({CODE_ASTRO_GOTO_FAILED})")),
        "plate-solve fail is not busy",
    )
    _assert(_GOTO_BUSY_TIMEOUT_S >= 90.0, "waiting 45s after stop_goto was still FUNCTION_BUSY")
    _assert(_CAPTURE_BUSY_RETRY_S >= 5.0, "short 3s waits were still busy after a pane stack")


def test_mosaic_goto_fail_does_not_start_stack() -> None:
    failed = RuntimeError(f"GOTO pane 3 failed: CODE_ASTRO_GOTO_FAILED ({CODE_ASTRO_GOTO_FAILED})")
    _assert(_goto_terminal_fail(failed), "GOTO_FAILED stops the pane")
    _assert(_goto_fail_reason(failed) == "not calibrated or this scene will not plate-solve", _goto_fail_reason(failed))
    _assert(
        _goto_terminal_fail(RuntimeError("GOTO pane 3 failed: CODE_ASTRO_NEED_CALIBRATION (-11511)")),
        "need calibration stops the pane",
    )
    _assert(
        not _goto_terminal_fail(RuntimeError("GOTO pane 2 failed: FUNCTION_BUSY (-11501)")),
        "busy is retried",
    )
    message = mosaic_pane_goto_fail_message(
        pane=3,
        total=4,
        ra=5.36,
        dec=-69.7,
        name="LMC pane 3",
        error=failed,
    )
    _assert("RA 5.3600h" in message, message)
    _assert("Dec -69.700°" in message, message)
    _assert("Not stacking this pane" in message, message)
    _assert("LMC pane 3" in message, message)


def test_goto_started_ignores_leftover_stop() -> None:
    _assert(_goto_started("running"), "slew running")
    _assert(_goto_started("solving"), "plate solving")
    _assert(not _goto_started("stopping"), "stop_goto unwind is not a new slew")
    _assert(not _goto_started("idle"), "idle")
    _assert(not _goto_started(""), "empty")


def test_leftover_stop_skips_joystick_motors() -> None:
    operations = _stop_targets(include_motors=False)
    _assert("stop_motors" not in operations, operations)
    with_motors = _stop_targets(include_motors=True)
    _assert("stop_motors" in with_motors, with_motors)


def test_goto_wait_ignores_leftover_tracking() -> None:
    _assert(
        not _goto_wait_complete(
            seen_goto_busy=False,
            tracking=True,
            tracking_at_start=True,
            elapsed_s=8.0,
        ),
        "leftover tracking is not a finished slew",
    )
    _assert(
        not _goto_wait_complete(
            seen_goto_busy=True,
            tracking=True,
            tracking_at_start=True,
            elapsed_s=2.0,
        ),
        "leftover tracking plus a new slew starting is not a handoff",
    )
    _assert(
        _goto_wait_complete(
            seen_goto_busy=True,
            tracking=True,
            tracking_at_start=True,
            elapsed_s=2.0,
            seen_tracking_drop=True,
        ),
        "tracking dropped during the slew, then came back",
    )
    _assert(
        _goto_wait_complete(
            seen_goto_busy=False,
            tracking=True,
            tracking_at_start=False,
            elapsed_s=6.0,
        ),
        "fast handoff after tracking was off",
    )
    _assert(
        not _goto_wait_complete(
            seen_goto_busy=False,
            tracking=False,
            tracking_at_start=False,
            elapsed_s=6.0,
        ),
        "still slewing",
    )


def test_mosaic_pane_footprints_are_distinct() -> None:
    target = Target(name="M31", kind=TargetKind.EQUATORIAL, ra_hours=0.712, dec_degrees=41.269)
    panes = mosaic_pane_footprints(target, 2, 2, 2.95, 1.66, 0.2, south_up=False, position_angle=0.0)
    _assert(len(panes) == 4, panes)
    points = {(pane["ra_hours"], pane["dec_degrees"]) for pane in panes}
    _assert(len(points) == 4, points)
    _assert(all(abs(pane["ra_hours"] - 0.712) > 0.01 or abs(pane["dec_degrees"] - 41.269) > 0.2 for pane in panes), panes)


def test_mosaic_pane_matches_sky_chart() -> None:
    target = Target(name="eq", kind=TargetKind.EQUATORIAL, ra_hours=6.0, dec_degrees=20.0)
    north_up = mosaic_pane_footprints(target, 2, 2, 2.0, 2.0, 0.0, south_up=False, position_angle=0.0)
    pane1 = next(item for item in north_up if item["index"] == 1)
    # N-up chart: pane 1 is camera-right / top → west and north (right side of the view).
    _assert(pane1["ra_hours"] < 6.0, pane1)
    _assert(pane1["dec_degrees"] > 20.0, pane1)
    south_up = mosaic_pane_footprints(target, 2, 2, 2.0, 2.0, 0.0, south_up=True, position_angle=180.0)
    south1 = next(item for item in south_up if item["index"] == 1)
    # S-up chart: camera-right is east, camera-up is south.
    _assert(south1["ra_hours"] > 6.0, south1)
    _assert(south1["dec_degrees"] < 20.0, south1)


def test_mosaic_pane_names_are_not_catalog_objects() -> None:
    _assert(is_mosaic_pane_name("I 212 pane 1"), "pane suffix is detected")
    _assert(is_mosaic_pane_name("M31 pane 2 of 4"), "pane-of suffix is detected")
    _assert(not is_mosaic_pane_name("I 212"), "object name is not a pane")
    _assert(mosaic_group_title("I 212 pane 1") == "I 212", mosaic_group_title("I 212 pane 1"))
    _assert(mosaic_pane_index("I 212 pane 1") == 1, mosaic_pane_index("I 212 pane 1"))
    _assert(sky_names_related("I 212 pane 1", "I 212"), "pane relates to parent")
    _assert(sky_names_related("I 212", "I 212 pane 1"), "parent relates to pane")
    _assert(not sky_names_related("I 212", "M31 pane 1"), "different objects")
    _assert(not sky_names_related("I 212", "I 212"), "same object is not a pane pair")


def test_live_mosaic_persist_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as folder:
        store = SessionStore(Path(folder))
        payload = {
            "group": "live-mosaic-demo",
            "columns": 2,
            "rows": 2,
            "total": 4,
            "current_index": 2,
            "phase": "stacking",
            "camera": "tele",
            "panes": [
                {"index": 1, "ra_hours": 1.0, "dec_degrees": 10.0, "name": "M31 pane 1"},
                {"index": 2, "ra_hours": 1.1, "dec_degrees": 10.0, "name": "M31 pane 2"},
            ],
        }
        store.save_live_mosaic("device-1", payload)
        loaded = store.load_live_mosaics()
        _assert("device-1" in loaded, "persisted mosaic is loaded")
        _assert(loaded["device-1"]["current_index"] == 2, loaded["device-1"])
        _assert(len(loaded["device-1"]["panes"]) == 2, "panes stored")
        store.clear_live_mosaic("device-1")
        _assert(store.load_live_mosaics() == {}, "cleared mosaic is gone")


def test_session_continues_after_astro_autofocus_soft_fail() -> None:
    slow = RuntimeError(
        f"Auto focus failed: CODE_FOCUS_ASTRO_AUTO_FOCUS_SLOW_ERROR ({CODE_FOCUS_ASTRO_AUTO_FOCUS_SLOW_ERROR})"
    )
    fast = RuntimeError(
        f"Auto focus failed: CODE_FOCUS_ASTRO_AUTO_FOCUS_FAST_ERROR ({CODE_FOCUS_ASTRO_AUTO_FOCUS_FAST_ERROR})"
    )
    exposure = RuntimeError(f"Auto focus failed: CODE_FOCUS_EXP_TOO_LONG ({CODE_FOCUS_EXP_TOO_LONG})")
    _assert(_focus_soft_fail(slow), "slow AF lock failure is continuable")
    _assert(_focus_soft_fail(fast), "fast AF lock failure is continuable")
    _assert(_focus_soft_fail(exposure), "AF exposure-too-long is continuable")
    _assert(not _focus_soft_fail(RuntimeError("Auto focus failed: TELE_CLOSED (-10501)")), "closed camera stays fatal")
    _assert(
        _session_needs_infinity_after_autofocus({"autofocus": True}, True),
        "AF-only workflow falls back to infinity",
    )
    _assert(
        not _session_needs_infinity_after_autofocus({"infinite_focus": True}, True),
        "explicit infinity already runs next",
    )
    _assert(
        not _session_needs_infinity_after_autofocus({"polar_align": True}, True),
        "polar alignment already sends infinity",
    )
    _assert(
        not _session_needs_infinity_after_autofocus({"autofocus": True}, False),
        "successful AF does not add infinity",
    )


def _astro_session(**workflow: bool) -> dict:
    flags = {
        "calibrate": False,
        "autofocus": False,
        "infinite_focus": False,
        "polar_align": False,
        "goto": True,
        "wait_before_seconds": 0,
        "wait_after_seconds": 0,
    }
    flags.update(workflow)
    return {
        "id": "session-focus",
        "name": "M42",
        "action": "astro",
        "target": {"kind": "equatorial", "name": "M42", "ra_hours": 5.5, "dec_degrees": -5.4},
        "camera": {
            "camera": "tele",
            "exposure_seconds": 15,
            "gain": 60,
            "frame_count": 10,
            "binning": 1,
            "ir_filter": "VIS",
        },
        "workflow": flags,
        "mosaic": {},
    }


def _run_setup_names(workflow: dict[str, bool], focus: str) -> list[str]:
    import astro_dwarf.device_worker as worker
    from unittest.mock import patch

    names: list[str] = []
    attempts = {"af": 0}

    def step(name: str, operation: str | None = None, *args: object, **_kwargs: object) -> None:
        names.append(name)
        if operation == "autofocus" and args and args[0] is False:
            attempts["af"] += 1
            if focus == "fatal":
                raise RuntimeError("Auto focus failed: motor stalled")
            if focus == "soft" and attempts["af"] == 1:
                raise RuntimeError("Auto focus failed: ASTRO_AUTO_FOCUS_SLOW_ERROR (-15100)")

    saved = (
        worker._device,
        worker._tap,
        worker._prompt_darks,
        worker._stack_exposure_name,
        worker._stack_gain,
        worker._stack_bin_index,
    )
    worker._stop.clear()
    try:
        with (
            patch.object(worker, "connect", lambda: True),
            patch.object(worker, "_wait_seconds", lambda *_a, **_k: None),
            patch.object(worker, "sdk_call", lambda *_a, **_k: True),
            patch.object(
                worker,
                "_device",
                {"model": "Dwarf 3", "latitude": -33.0, "longitude": 151.0, "camera": "tele"},
            ),
        ):
            worker._tap = None
            worker._prompt_darks = False
            try:
                worker._run_session_steps(_astro_session(**workflow), step)
            except RuntimeError as exc:
                exc.step_names = names  # type: ignore[attr-defined]
                raise
    finally:
        (
            worker._device,
            worker._tap,
            worker._prompt_darks,
            worker._stack_exposure_name,
            worker._stack_gain,
            worker._stack_bin_index,
        ) = saved
        worker._stop.clear()
    return names


def test_session_focuses_before_calibration_and_retries_after_a_soft_fail() -> None:
    locked = _run_setup_names({"calibrate": True, "autofocus": True}, "lock")
    _assert(locked.index("Auto focus") < locked.index("Polar positioning"), locked)
    _assert(locked.index("Polar positioning") < locked.index("Calibration"), locked)
    _assert(locked.index("Calibration") < locked.index("GOTO target"), locked)
    _assert("Auto focus after calibration" not in locked, locked)
    _assert("Infinity focus after autofocus failed" not in locked, locked)

    missed = _run_setup_names({"calibrate": True, "autofocus": True}, "soft")
    _assert(missed.index("Auto focus") < missed.index("Infinity focus after autofocus failed"), missed)
    _assert(missed.index("Infinity focus after autofocus failed") < missed.index("Polar positioning"), missed)
    _assert(missed.index("Polar positioning") < missed.index("Calibration"), missed)
    _assert(missed.index("Calibration") < missed.index("Auto focus after calibration"), missed)
    _assert(missed.index("Auto focus after calibration") < missed.index("GOTO target"), missed)
    _assert(missed.count("Auto focus") == 1, missed)

    polar_only = _run_setup_names({"polar_align": True, "autofocus": True}, "lock")
    _assert("Polar positioning" not in polar_only, polar_only)
    _assert("Calibration" not in polar_only, polar_only)
    _assert("Auto focus after calibration" not in polar_only, polar_only)
    _assert(polar_only.index("Auto focus") < polar_only.index("Polar alignment"), polar_only)

    calibrate_only = _run_setup_names({"calibrate": True}, "lock")
    _assert("Auto focus" not in calibrate_only, calibrate_only)
    _assert(calibrate_only.index("Polar positioning") < calibrate_only.index("Calibration"), calibrate_only)
    _assert(calibrate_only.index("Calibration") < calibrate_only.index("GOTO target"), calibrate_only)

    both = _run_setup_names({"calibrate": True, "autofocus": True, "polar_align": True}, "soft")
    _assert("Infinity focus after autofocus failed" not in both, both)
    _assert(both.index("Auto focus") < both.index("Polar positioning"), both)
    _assert(both.index("Polar positioning") < both.index("Infinity focus before polar alignment"), both)
    _assert(both.index("Polar alignment") < both.index("Calibration"), both)
    _assert(both.index("Calibration") < both.index("Auto focus after calibration"), both)


def test_hard_focus_failure_stops_before_polar_position() -> None:
    import astro_dwarf.device_worker as worker

    raised = ""
    names: list[str] = []
    try:
        _run_setup_names({"calibrate": True, "autofocus": True}, "fatal")
    except RuntimeError as exc:
        raised = str(exc)
        names = list(getattr(exc, "step_names", []))
    _assert("motor stalled" in raised, raised or "session continued")
    _assert("Polar positioning" not in names, names)
    _assert("Calibration" not in names, names)
    _assert(not worker._stop.is_set(), "a focus failure must not latch stop")


def test_stop_on_pane_2_keeps_sheet() -> None:
    _assert(live_mosaic_keep_sheet(False, True, 2, 2, {1: object()}), "keep pane 1 after stop")
    _assert(not live_mosaic_keep_sheet(False, True, 2, 2, {}), "empty sheet is not held")
    _assert(not live_mosaic_keep_sheet(False, False, 2, 2, {1: object()}), "failed mosaic clears")
    _assert(live_mosaic_keep_sheet(True, False, 2, 2, {1: object(), 2: object()}), "success keeps sheet")


def test_stalled_plate_solve_fails_fast_and_a_short_solve_still_completes() -> None:
    import astro_dwarf.device_worker as worker

    class Hung:
        def snapshot(self) -> dict[str, str]:
            return {"goto_state": "solving", "tracking_state": "idle"}

        def response_after(self, cmd: int, since: float) -> None:
            return None

    class Finished:
        def __init__(self) -> None:
            self.reads = 0

        def snapshot(self) -> dict[str, str]:
            self.reads += 1
            if self.reads < 4:
                return {"goto_state": "solving", "tracking_state": "idle"}
            return {"goto_state": "idle", "tracking_state": "running"}

        def response_after(self, cmd: int, since: float) -> None:
            return None

    class Slewing:
        def snapshot(self) -> dict[str, str]:
            return {"goto_state": "running", "tracking_state": "idle"}

        def response_after(self, cmd: int, since: float) -> None:
            return None

    clock = {"now": 0.0}
    previous = (worker._tap, worker.time.monotonic, worker.time.sleep, worker.log, worker._stop.is_set())

    def monotonic() -> float:
        return clock["now"]

    def sleep(seconds: float) -> None:
        clock["now"] += float(seconds)

    worker._stop.clear()
    worker.time.monotonic = monotonic
    worker.time.sleep = sleep
    worker.log = lambda *args, **kwargs: None
    try:
        worker._tap = Finished()
        worker._await_operation("GOTO target", "goto", 0.0)
        _assert(clock["now"] < _GOTO_SOLVE_STALL_S, "a solve that hands off to tracking must not hit the stall")

        clock["now"] = 0.0
        worker._tap = Hung()
        try:
            worker._await_operation("GOTO target", "goto", 0.0)
        except RuntimeError as exc:
            _assert("plate-solve stalled" in str(exc), str(exc))
            _assert(clock["now"] < 120.0, f"stall took {clock['now']}s")
        else:
            raise AssertionError("a hung plate-solve returned")

        clock["now"] = 0.0
        try:
            worker._await_operation("GOTO target", "goto", 0.0, stall_is_terminal=True)
        except RuntimeError as exc:
            _assert("while plate-solving" in str(exc), str(exc))
            _assert("plate-solve stalled" not in str(exc), str(exc))
        else:
            raise AssertionError("the second hang returned")

        clock["now"] = 0.0
        worker._tap = Slewing()
        raised = False
        try:
            worker._await_operation("GOTO target", "goto", 0.0)
        except RuntimeError as exc:
            raised = True
            _assert("plate-solve stalled" not in str(exc), str(exc))
            _assert(clock["now"] > 300.0, "a moving slew must keep the long budget")
        _assert(raised, "a slew that never finishes still has to time out")
    finally:
        worker._tap = previous[0]
        worker.time.monotonic = previous[1]
        worker.time.sleep = previous[2]
        worker.log = previous[3]
        if previous[4]:
            worker._stop.set()


def test_stop_preview_dismisses_a_stopped_mosaic_sheet() -> None:
    from astro_dwarf.qt_backend import mosaic_stop_preview_keeps_sheet

    _assert(
        not mosaic_stop_preview_keeps_sheet(
            session_running=False,
            worker_running=False,
            capturing=False,
            disconnecting=False,
            connected=True,
            shutting_down=False,
            has_sheet=True,
        ),
        "a stopped mosaic must leave the preview",
    )
    _assert(
        mosaic_stop_preview_keeps_sheet(
            session_running=True,
            worker_running=False,
            capturing=False,
            disconnecting=False,
            connected=True,
            shutting_down=False,
            has_sheet=True,
        ),
        "a running pane keeps the contact sheet",
    )
    _assert(
        mosaic_stop_preview_keeps_sheet(
            session_running=False,
            worker_running=False,
            capturing=True,
            disconnecting=False,
            connected=True,
            shutting_down=False,
            has_sheet=True,
        ),
        "an open shutter keeps the contact sheet",
    )
    _assert(
        mosaic_stop_preview_keeps_sheet(
            session_running=False,
            worker_running=False,
            capturing=False,
            disconnecting=True,
            connected=False,
            shutting_down=False,
            has_sheet=True,
        ),
        "disconnect keeps cached panes",
    )


def test_failed_mosaic_does_not_keep_live_hud() -> None:
    from astro_dwarf.qt_backend import mosaic_goto_failed_result, mosaic_preview_keep_live_sheet

    result = (
        "Mosaic pane 2/4 GOTO failed · RA 14.5518h Dec -61.964° (Toliman pane 2) · "
        "will not plate-solve. Not stacking this pane."
    )
    _assert(mosaic_goto_failed_result(result), "clouded-out pane GOTO is a mosaic fail")
    _assert(
        not mosaic_preview_keep_live_sheet(live_phase="failed", worker_running=False),
        "HUD must leave live mosaic after the worker returns a GOTO fail",
    )
    _assert(not live_mosaic_keep_sheet(False, False, 2, 2, {1: object()}), "failed mosaic drops the sheet")


def main() -> int:
    test_firmware_mosaic_detection()
    test_mosaic_busy_and_idle_timeout()
    test_live_mosaic_resume_plan()
    test_recovered_firmware_mosaic_restarts_unless_the_grid_finished()
    test_failed_live_mosaic_does_not_block_scheduler()
    test_goto_reopens_camera_when_slew_never_starts()
    test_engine_busy_error_matches_firmware_reply()
    test_mosaic_goto_fail_does_not_start_stack()
    test_goto_keeps_waiting_while_plate_solving()
    test_stalled_plate_solve_fails_fast_and_a_short_solve_still_completes()
    test_goto_started_ignores_leftover_stop()
    test_leftover_stop_skips_joystick_motors()
    test_goto_wait_ignores_leftover_tracking()
    test_mosaic_pane_footprints_are_distinct()
    test_mosaic_pane_matches_sky_chart()
    test_mosaic_pane_names_are_not_catalog_objects()
    test_live_mosaic_persist_roundtrip()
    test_session_continues_after_astro_autofocus_soft_fail()
    test_session_focuses_before_calibration_and_retries_after_a_soft_fail()
    test_hard_focus_failure_stops_before_polar_position()
    test_stop_on_pane_2_keeps_sheet()
    test_stop_preview_dismisses_a_stopped_mosaic_sheet()
    test_failed_mosaic_does_not_keep_live_hud()
    print("mosaic recovery tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
