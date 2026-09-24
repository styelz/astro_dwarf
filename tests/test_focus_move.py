"""A typed focus target slews, then trims the coast with single steps."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf import device_worker


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += float(seconds)


class _Motor:
    """Matches the logged telephoto motor: ~24 steps per packet, ~80 of coast."""

    def __init__(self, start: int) -> None:
        self.pos = start
        self.running: int | None = None
        self.moved_at = 0.0
        self.commands: list[int] = []

    def send(self, message, command: int, module: int, timeout: float | None = None, *, wait: bool = True) -> bool:
        del module, timeout
        self.commands.append(int(command))
        if command == 15002:
            self.running = int(message.direction)
            self.moved_at = device_worker.time.monotonic()
        elif command == 15003:
            if self.running == device_worker._FOCUS_NEAR:
                self.pos -= device_worker._FOCUS_COAST
            elif self.running == device_worker._FOCUS_FAR:
                self.pos += device_worker._FOCUS_COAST
            self.running = None
        elif command == 15001:
            self.pos += -1 if int(message.direction) == device_worker._FOCUS_NEAR else 1
        return True

    def read(self) -> int:
        now = device_worker.time.monotonic()
        if self.running is not None and now - self.moved_at >= 0.2:
            self.pos += -24 if self.running == device_worker._FOCUS_NEAR else 24
            self.moved_at = now
        return self.pos


def _run(motor: _Motor, target: int) -> bool:
    clock = _Clock()
    device_worker._stop.clear()
    original = (
        device_worker.time.monotonic,
        device_worker.time.sleep,
        device_worker._focus_position,
        device_worker.send_without_response,
    )
    device_worker.time.monotonic = clock.monotonic
    device_worker.time.sleep = clock.sleep
    device_worker._focus_position = motor.read
    device_worker.send_without_response = motor.send
    try:
        return device_worker._set_focus_position(target)
    finally:
        (
            device_worker.time.monotonic,
            device_worker.time.sleep,
            device_worker._focus_position,
            device_worker.send_without_response,
        ) = original


def test_hundred_steps_slews_then_trims_onto_the_target() -> None:
    motor = _Motor(500)
    _assert(_run(motor, 600), "move should finish")
    _assert(motor.pos == 600, motor.pos)
    _assert(motor.commands.count(15002) == 1, motor.commands)
    _assert(motor.commands.count(15003) == 1, motor.commands)


def test_long_move_stops_before_the_coast() -> None:
    motor = _Motor(400)
    _assert(_run(motor, 600), "move should finish")
    _assert(motor.pos == 600, motor.pos)
    _assert(motor.commands.count(15002) == 1, motor.commands)


def test_downward_move_lands_on_the_typed_step() -> None:
    motor = _Motor(800)
    _assert(_run(motor, 600), "move should finish")
    _assert(motor.pos == 600, motor.pos)


def test_short_move_single_steps_without_a_slew() -> None:
    motor = _Motor(590)
    _assert(_run(motor, 600), "move should finish")
    _assert(motor.pos == 600, motor.pos)
    _assert(15002 not in motor.commands, motor.commands)


if __name__ == "__main__":
    test_hundred_steps_slews_then_trims_onto_the_target()
    test_long_move_stops_before_the_coast()
    test_downward_move_lands_on_the_typed_step()
    test_short_move_single_steps_without_a_slew()
    print("ok")
