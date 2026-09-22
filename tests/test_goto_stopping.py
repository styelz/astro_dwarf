from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from unittest.mock import patch

from astro_dwarf import device_worker
from astro_dwarf.device_telemetry import GOTO_STOP_UNWIND_S, TelemetryTap, settle_goto_changes
from astro_dwarf.device_worker import CODE_ASTRO_FUNCTION_BUSY
from astro_dwarf.telemetry_view import AlertEngine, derive_activity


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_leftover_stopping_is_dropped() -> None:
    changes, owned, since = settle_goto_changes(
        {"goto_state": "stopping", "goto_target": "Nu Octantis pane 3"},
        previous_state="",
        owned=False,
        stopping_since=0.0,
        now=100.0,
    )
    _assert("goto_state" not in changes, "a stopping sample with no slew in this link must not publish")
    _assert("goto_target" not in changes, "the leftover slew name must not become the HUD target")
    _assert(owned is False and since == 0.0, "leftover stopping must not arm an unwind")


def test_watched_stop_stays_briefly() -> None:
    changes, owned, since = settle_goto_changes(
        {"goto_state": "stopping"},
        previous_state="solving",
        owned=True,
        stopping_since=0.0,
        now=50.0,
    )
    _assert(changes.get("goto_state") == "stopping", "a stop we just watched stays visible")
    _assert(owned is True and since == 50.0, "unwind clock starts at the stopping sample")
    aged, owned_after, _since_after = settle_goto_changes(
        {"goto_state": "stopping"},
        previous_state="stopping",
        owned=True,
        stopping_since=50.0,
        now=50.0 + GOTO_STOP_UNWIND_S,
    )
    _assert(aged.get("goto_state") == "idle", "a stop that never finishes must release")
    _assert(aged.get("goto_released") is True, "synthetic idle is marked so it is not a GOTO complete")
    _assert(owned_after is False, "released stop is no longer owned")


def test_tap_does_not_latch_leftover_stopping() -> None:
    events: list[dict] = []
    tap = TelemetryTap(lambda message: events.append(message), flush_interval=0)
    try:
        tap.update({"goto_state": "stopping", "goto_target": "Nu Octantis pane 3"}, force=True)
        snap = tap.snapshot()
        _assert(snap.get("goto_state") != "stopping", f"snapshot latched {snap.get('goto_state')}")
        _assert(derive_activity(snap)[0] != "goto", "leftover stopping must not look like a slew")
        published = [item["data"].get("goto_state") for item in events if "goto_state" in item.get("data", {})]
        _assert("stopping" not in published, f"published stopping: {published}")
    finally:
        tap.reset()


def test_tap_keeps_then_releases_a_watched_stop() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    try:
        tap.update({"goto_state": "running"}, force=True)
        tap.update({"goto_state": "stopping"}, force=True)
        _assert(tap.snapshot().get("goto_state") == "stopping", "watched stop stays stopping")
        _assert(derive_activity(tap.snapshot())[0] == "goto", "a live stop still occupies the pad")
        tap._release_stuck_goto_stop()
        _assert(tap.snapshot().get("goto_state") == "stopping", "unwind must wait out the grace")
        tap._goto_stopping_since = time.monotonic() - GOTO_STOP_UNWIND_S
        tap._release_stuck_goto_stop()
        _assert(tap.snapshot().get("goto_state") == "idle", "stuck stop releases after the grace")
        _assert(derive_activity(tap.snapshot())[0] != "goto", "released stop must leave tracking mode")
    finally:
        tap.reset()


def test_stale_release_does_not_clear_a_new_slew() -> None:
    changes, owned, since = settle_goto_changes(
        {"goto_state": "idle", "goto_released": True},
        previous_state="running",
        owned=True,
        stopping_since=0.0,
        now=80.0,
    )
    _assert("goto_state" not in changes, "a late unwind must not publish idle over a new slew")
    _assert("goto_released" not in changes, "the synthetic flag must not stick on the new slew")
    _assert(owned is True and since == 0.0, "the new slew stays owned")
    real, released, _since = settle_goto_changes(
        {"goto_state": "idle"},
        previous_state="solving",
        owned=True,
        stopping_since=0.0,
        now=80.0,
    )
    _assert(real.get("goto_state") == "idle" and released is False, "a real idle still ends the slew")


def test_tap_keeps_a_slew_that_starts_during_unwind() -> None:
    tap = TelemetryTap(lambda _message: None, flush_interval=0)
    try:
        tap.update({"goto_state": "running"}, force=True)
        tap.update({"goto_state": "stopping"}, force=True)
        tap._goto_stopping_since = time.monotonic() - GOTO_STOP_UNWIND_S
        tap.update({"goto_state": "running", "goto_target": "Pane 2"}, force=True)
        tap.update({"goto_state": "idle", "goto_released": True}, force=True)
        snap = tap.snapshot()
        _assert(snap.get("goto_state") == "running", f"new slew cleared: {snap.get('goto_state')}")
        _assert(snap.get("goto_target") == "Pane 2", "new target cleared")
        _assert(not snap.get("goto_released"), "synthetic release stuck on the live slew")
        _assert(derive_activity(snap)[0] == "goto", "HUD left the live slew")
    finally:
        tap.reset()


def test_synthetic_release_is_not_a_completed_goto() -> None:
    alerts = AlertEngine().evaluate(
        {"goto_state": "stopping", "goto_target": "Nu Octantis pane 3"},
        {"goto_state": "idle", "goto_target": "Nu Octantis pane 3", "goto_released": True},
    )
    _assert(
        not any(item["message"].startswith("GOTO complete") for item in alerts),
        "clearing a stuck stop must not toast GOTO complete",
    )
    done = AlertEngine().evaluate(
        {"goto_state": "solving", "goto_target": "Nu Octantis pane 3"},
        {"goto_state": "idle", "goto_target": "Nu Octantis pane 3"},
    )
    _assert(
        any(item["message"].startswith("GOTO complete") for item in done),
        "a real slew that reaches idle is still a completed GOTO",
    )


class _BusyThenAcceptedTap:
    def __init__(self) -> None:
        self.gotos = 0

    def snapshot(self) -> dict:
        return {"goto_state": "idle", "tracking_state": "idle"}

    def response_after(self, cmd: int, since: float) -> int:
        if cmd != 11002:
            return 0
        if self.gotos < 2:
            return CODE_ASTRO_FUNCTION_BUSY
        return 0


def test_live_track_retries_after_latched_stop() -> None:
    """STOP ALL leaves _stop set. The FUNCTION_BUSY retry must still send GOTO."""
    tap = _BusyThenAcceptedTap()
    calls: list[str] = []

    def fake_sdk(operation: str, *args: object) -> bool:
        calls.append(operation)
        if operation == "goto":
            tap.gotos += 1
        return True

    def fake_wait(seconds: float, message: str | None = None, progress: object = None) -> None:
        _assert(not device_worker._stop.is_set(), "latched stop must be clear before the retry wait")
        _assert(seconds == 2.0, "retry still waits for the engine to release")

    device_worker._stop.set()
    device_worker._session_active.clear()
    previous_tap = device_worker._tap
    device_worker._tap = tap
    try:
        with (
            patch.object(device_worker, "sdk_call", fake_sdk),
            patch.object(device_worker, "_wait_seconds", fake_wait),
        ):
            device_worker._start_goto_for_tracking(1.25, -30.0, "Retry target")
    finally:
        device_worker._tap = previous_tap
        device_worker._stop.clear()
        device_worker._session_active.clear()
    _assert(calls.count("goto") == 2, f"retry did not send the second GOTO: {calls}")
    _assert("stop_goto" in calls, f"retry did not clear the stuck stop: {calls}")


def test_session_stop_still_aborts_track_retry() -> None:
    tap = _BusyThenAcceptedTap()
    calls: list[str] = []

    def fake_sdk(operation: str, *args: object) -> bool:
        calls.append(operation)
        if operation == "goto":
            tap.gotos += 1
        return True

    device_worker._stop.set()
    device_worker._session_active.set()
    previous_tap = device_worker._tap
    device_worker._tap = tap
    try:
        with patch.object(device_worker, "sdk_call", fake_sdk):
            try:
                device_worker._start_goto_for_tracking(1.25, -30.0, "Retry target")
            except InterruptedError as exc:
                _assert(str(exc) == "Tracking stopped", str(exc))
            else:
                raise AssertionError("an active session stop must abort the retry")
    finally:
        device_worker._tap = previous_tap
        device_worker._stop.clear()
        device_worker._session_active.clear()
    _assert(calls.count("goto") == 1, f"session stop still sent another GOTO: {calls}")


def main() -> None:
    test_leftover_stopping_is_dropped()
    test_watched_stop_stays_briefly()
    test_tap_does_not_latch_leftover_stopping()
    test_tap_keeps_then_releases_a_watched_stop()
    test_stale_release_does_not_clear_a_new_slew()
    test_tap_keeps_a_slew_that_starts_during_unwind()
    test_synthetic_release_is_not_a_completed_goto()
    test_live_track_retries_after_latched_stop()
    test_session_stop_still_aborts_track_retry()
    print("test_goto_stopping: ok")


if __name__ == "__main__":
    main()
