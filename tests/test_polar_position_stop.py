"""POLAR POS can be stopped between motor steps, and the stop halts both axes."""

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


def _run_polar(invoke, *, model: str = "Dwarf 3"):
    api = type("Api", (), {"motor_action": lambda *args, **kwargs: True})()
    with (
        patch.object(worker, "_api", api),
        patch.object(worker, "_invoke_sdk", invoke),
        patch.object(worker, "_device", {"model": model}),
    ):
        return worker.polar_position()


def test_polar_position_stops_before_the_next_motor_step() -> None:
    calls: list[int] = []

    def invoke(operation, function, action, label=None):
        calls.append(action)
        worker._stop.set()
        return True

    worker._stop.clear()
    worker._session_active.clear()
    try:
        _run_polar(invoke)
        raised = None
    except InterruptedError as exc:
        raised = str(exc)
    finally:
        worker._stop.clear()
        worker._session_active.clear()
    _assert(raised == "Polar positioning stopped", raised or "did not stop")
    _assert(calls == [5], calls)


def test_polar_position_does_not_start_when_already_stopped() -> None:
    calls: list[int] = []

    def invoke(operation, function, action, label=None):
        calls.append(action)
        return True

    worker._session_active.clear()
    worker._stop.set()
    try:
        _run_polar(invoke)
        raised = None
    except InterruptedError as exc:
        raised = str(exc)
    finally:
        worker._stop.clear()
    _assert(raised == "Polar positioning stopped", raised or "did not stop")
    _assert(calls == [], calls)


def test_session_stop_uses_the_session_message() -> None:
    worker._session_active.set()
    worker._stop.set()
    try:
        _run_polar(lambda *args, **kwargs: True)
        raised = None
    except InterruptedError as exc:
        raised = str(exc)
    finally:
        worker._session_active.clear()
        worker._stop.clear()
    _assert(raised == "Session stopped", raised or "did not stop")


def test_motor_failure_is_not_a_stop() -> None:
    calls: list[int] = []

    def invoke(operation, function, action, label=None):
        calls.append(action)
        return False

    worker._stop.clear()
    worker._session_active.clear()
    try:
        ok = _run_polar(invoke)
    finally:
        worker._stop.clear()
    _assert(ok is False, ok)
    _assert(calls == [5], calls)


def test_stop_polar_position_stops_both_axes() -> None:
    sent: list[tuple[int, int, int]] = []

    def send(message, command, module_id, timeout=None):
        sent.append((int(command), int(module_id), int(message.id)))
        return True

    worker._stop.set()
    worker._session_active.clear()
    previous = worker._motors_unhomed
    try:
        with patch.object(worker, "send_without_response", send):
            ok = worker.stop_polar_position()
        _assert(ok is True, ok)
        _assert(sent == [(14002, 6, 1), (14002, 6, 2)], sent)
        _assert(worker._motors_unhomed is True, "aborted home must be remembered")
        _assert(not worker._stop.is_set(), "manual stop must not latch the session flag")
    finally:
        worker._stop.clear()
        worker._session_active.clear()
        worker._motors_unhomed = previous


if __name__ == "__main__":
    test_polar_position_stops_before_the_next_motor_step()
    test_polar_position_does_not_start_when_already_stopped()
    test_session_stop_uses_the_session_message()
    test_motor_failure_is_not_a_stop()
    test_stop_polar_position_stops_both_axes()
    print("ok")
