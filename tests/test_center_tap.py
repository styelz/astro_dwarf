from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_worker import (
    _joystick_hold_seconds,
    _wide_linkage_pixels,
    _wide_view_slew_degrees,
)
from astro_dwarf.domain import camera_fov_plausible


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_wide_view_slew_puts_tap_on_crosshair() -> None:
    yaw, pitch = _wide_view_slew_degrees(0.5, 0.5, 45.06, 25.93)
    _assert(abs(yaw) < 1e-9 and abs(pitch) < 1e-9, (yaw, pitch))
    yaw, pitch = _wide_view_slew_degrees(1.0, 0.0, 40.0, 20.0)
    _assert(abs(yaw - 20.0) < 1e-9, yaw)
    _assert(abs(pitch - 10.0) < 1e-9, pitch)
    yaw, pitch = _wide_view_slew_degrees(0.0, 1.0, 40.0, 20.0)
    _assert(abs(yaw + 20.0) < 1e-9, yaw)
    _assert(abs(pitch + 10.0) < 1e-9, pitch)


def test_linkage_pixels_stay_in_live_1920_space() -> None:
    x, y = _wide_linkage_pixels(0.0, 0.0)
    _assert((x, y) == (0, 0), (x, y))
    x, y = _wide_linkage_pixels(1.0, 1.0)
    _assert((x, y) == (1919, 1079), (x, y))
    x, y = _wide_linkage_pixels(0.66, 0.76)
    _assert(x == round(0.66 * 1919), x)
    _assert(y == round(0.76 * 1079), y)


def test_stub_wide_fov_is_not_used_for_slew() -> None:
    _assert(not camera_fov_plausible(2.95, 1.66, "wide"), "tele-sized wide")
    _assert(camera_fov_plausible(45.06, 25.93, "wide"), "published wide")


def test_unhomed_joystick_hold_scales_with_degrees() -> None:
    _assert(abs(_joystick_hold_seconds(20.0, 20.0) - 1.0) < 1e-9, _joystick_hold_seconds(20.0, 20.0))
    _assert(abs(_joystick_hold_seconds(10.0, 20.0) - 0.5) < 1e-9, _joystick_hold_seconds(10.0, 20.0))
    _assert(_joystick_hold_seconds(200.0, 20.0) == 8.0, _joystick_hold_seconds(200.0, 20.0))


if __name__ == "__main__":
    test_wide_view_slew_puts_tap_on_crosshair()
    test_linkage_pixels_stay_in_live_1920_space()
    test_stub_wide_fov_is_not_used_for_slew()
    test_unhomed_joystick_hold_scales_with_degrees()
    print("ok")
