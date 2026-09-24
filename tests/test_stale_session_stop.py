"""A failed session's leftover stop must not reject the next manual command."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf import device_worker as worker


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _quiet_stop():
    return (
        patch.object(worker, "log"),
        patch.object(worker, "report_status"),
        patch.object(worker, "request_state_refresh"),
    )


def test_leftover_stop_clears_the_latch() -> None:
    worker._session_active.clear()
    worker._connected.clear()
    worker._stop.set()
    try:
        quiet_log, quiet_status, quiet_refresh = _quiet_stop()
        with quiet_log, quiet_status, quiet_refresh:
            ok = worker.stop_all(include_motors=False)
        _assert(ok is True, ok)
        _assert(not worker._stop.is_set(), "leftover stop must not latch the next command")
    finally:
        worker._stop.clear()
        worker._session_active.clear()
        worker._connected.clear()
        worker._stop_phase = None


def test_in_session_stop_stays_latched() -> None:
    worker._session_active.set()
    worker._connected.clear()
    worker._stop.clear()
    try:
        quiet_log, quiet_status, quiet_refresh = _quiet_stop()
        with quiet_log, quiet_status, quiet_refresh:
            worker.stop_all(include_motors=False)
        _assert(worker._stop.is_set(), "a stop during a live session must stay latched")
    finally:
        worker._session_active.clear()
        worker._stop.clear()
        worker._connected.clear()
        worker._stop_phase = None


def test_stale_stop_does_not_abort_the_next_dark_check() -> None:
    """Calibrate and polar both enter through this check."""
    worker._session_active.clear()
    worker._stop.set()
    previous_choice = worker._dark_run_choice
    worker._dark_run_choice = None
    seen: list[bool] = []

    def query(wide: bool):
        seen.append(worker._stop.is_set())
        if worker._stop.is_set():
            raise InterruptedError("Session stopped")
        return []

    settings = {"gain_ok": True, "exposure_ok": True, "exp_index": 0, "gain": 60, "bin_index": 0, "temperature": "10"}
    try:
        with (
            patch.object(worker, "_dark_capture_settings", return_value=settings),
            patch.object(worker, "_query_dark_library", query),
            patch.object(worker, "dark_library_status", return_value="match"),
            patch.object(worker, "log"),
        ):
            worker._offer_darks_before_manual_alignment("Stack")
    except InterruptedError as exc:
        raise AssertionError(f"stale stop aborted the dark check: {exc}") from exc
    finally:
        worker._stop.clear()
        worker._session_active.clear()
        worker._dark_run_choice = previous_choice
    _assert(seen == [False], seen)


def test_polar_position_runs_after_leftover_stop() -> None:
    calls: list[int] = []

    def invoke(operation, function, action, label=None):
        calls.append(action)
        return True

    worker._session_active.clear()
    worker._connected.clear()
    worker._stop.set()
    previous_choice = worker._dark_run_choice
    worker._dark_run_choice = "continue"
    api = type("Api", (), {"motor_action": lambda *args, **kwargs: True})()
    try:
        quiet_log, quiet_status, quiet_refresh = _quiet_stop()
        with quiet_log, quiet_status, quiet_refresh:
            worker.stop_all(include_motors=False)
        with (
            patch.object(worker, "_api", api),
            patch.object(worker, "_invoke_sdk", invoke),
            patch.object(worker, "_device", {"model": "Dwarf 3", "camera": "tele"}),
        ):
            worker._offer_darks_before_manual_alignment("Stack")
            ok = worker.polar_position()
    except InterruptedError as exc:
        raise AssertionError(f"polar pos rejected after leftover stop: {exc}") from exc
    finally:
        worker._stop.clear()
        worker._session_active.clear()
        worker._connected.clear()
        worker._dark_run_choice = previous_choice
        worker._stop_phase = None
    _assert(ok is True, ok)
    _assert(calls == [5, 6, 9, 7], calls)


if __name__ == "__main__":
    test_leftover_stop_clears_the_latch()
    test_in_session_stop_stays_latched()
    test_stale_stop_does_not_abort_the_next_dark_check()
    test_polar_position_runs_after_leftover_stop()
    print("ok")
