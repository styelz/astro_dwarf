from __future__ import annotations

import sys
import time
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf import device_worker as worker


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _OpenLoop:
    def is_closed(self) -> bool:
        return False


class _SocketFn:
    __globals__ = {"send_socket": lambda *args: None, "client_instance": object()}

    def __call__(self) -> None:
        return None


class _Api:
    connect_socket = _SocketFn()


def test_send_without_response_times_out() -> None:
    hung = Future()

    def fake_wait_for(coro, timeout=None):
        if hasattr(coro, "close"):
            coro.close()
        return None

    started = time.monotonic()
    with (
        patch.object(worker, "_api", _Api()),
        patch.object(worker, "_sdk_socket", return_value=(object(), _OpenLoop())),
        patch.object(worker, "_interrupt_sdk_wait", return_value=True) as interrupt,
        patch.object(worker, "log"),
        patch("astro_dwarf.device_worker.asyncio.wait_for", fake_wait_for),
        patch("astro_dwarf.device_worker.asyncio.run_coroutine_threadsafe", return_value=hung),
    ):
        ok = worker.send_without_response(object(), 14008, 6, timeout=0.2)
    elapsed = time.monotonic() - started
    _assert(ok is False, "timeout returns False")
    _assert(elapsed < 1.5, f"send_without_response blocked {elapsed:.2f}s")
    _assert(hung.cancelled(), "abandoned send is cancelled")
    _assert(interrupt.called, "timeout pokes the SDK wait")


def test_sdk_call_bounded_interrupts_without_matching_inflight() -> None:
    interrupted: list[str] = []

    def interrupt(reason: str) -> bool:
        interrupted.append(reason)
        return True

    def sdk(operation: str, *args: object) -> bool:
        time.sleep(0.35)
        return True

    previous = worker._in_flight
    try:
        worker._in_flight = None
        with (
            patch.object(worker, "_interrupt_sdk_wait", interrupt),
            patch.object(worker, "sdk_call", sdk),
        ):
            worker._sdk_call_bounded("stop_motors", 0.1)
    finally:
        worker._in_flight = previous
    _assert(interrupted, "timeout must poke the SDK wait even when _in_flight was unset")


def test_stop_all_finishes_when_motor_stop_hangs() -> None:
    def hanging_sdk(operation: str, *args: object) -> bool:
        time.sleep(0.35)
        return True

    class Tap:
        def snapshot(self) -> dict[str, str]:
            return {"tracking_state": "running", "goto_state": "running"}

    started = time.monotonic()
    worker._connected.set()
    worker._tap = Tap()
    try:
        with (
            patch.object(worker, "_STOP_ALL_BUDGET_S", 0.4),
            patch.object(worker, "_STOP_COMMAND_TIMEOUT", 0.2),
            patch.object(worker, "sdk_call", hanging_sdk),
            patch.object(worker, "log"),
            patch.object(worker, "report_status"),
            patch.object(worker, "request_state_refresh"),
            patch.object(worker, "_interrupt_sdk_wait", return_value=True),
        ):
            ok = worker.stop_all()
    finally:
        worker._connected.clear()
        worker._tap = None
        worker._stop.clear()
        worker._stop_phase = None
        worker._session_phase = None
    elapsed = time.monotonic() - started
    _assert(ok is True, "stop_all always returns")
    _assert(elapsed < 1.5, f"stop_all blocked {elapsed:.2f}s")


def main() -> int:
    test_send_without_response_times_out()
    test_sdk_call_bounded_interrupts_without_matching_inflight()
    test_stop_all_finishes_when_motor_stop_hangs()
    print("stop timeout tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
