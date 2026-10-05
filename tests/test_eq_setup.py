"""EQ setup copy matches the DWARF app: pose by hemisphere, then wedge moves."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.telemetry_view import (
    AlertEngine,
    device_mosaic_needs_eq,
    eq_move_instruction,
    eq_pose_steps,
    eq_within_limit,
    format_telemetry,
)


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def test_two_degrees_is_the_accept_limit() -> None:
    _assert(eq_within_limit(2.0, -2.0), "2° on both axes is aligned")
    _assert(not eq_within_limit(2.01, 0.0), "past 2° still needs a wedge move")
    _assert(not eq_within_limit(-151.17, -51.50), "the Zeta Apodis residual is not aligned")


def test_positive_azimuth_is_clockwise_and_positive_altitude_is_up() -> None:
    _assert(
        eq_move_instruction("azi", 3.5) == "Rotate the head clockwise 3.50°.",
        eq_move_instruction("azi", 3.5),
    )
    _assert(
        eq_move_instruction("azi", -151.17) == "Rotate the head counterclockwise 151.17°.",
        eq_move_instruction("azi", -151.17),
    )
    _assert(
        eq_move_instruction("alt", 1.2) == "Tilt the top of the telescope up 1.20°.",
        eq_move_instruction("alt", 1.2),
    )
    _assert(
        eq_move_instruction("alt", -51.5) == "Tilt the top of the telescope down 51.50°.",
        eq_move_instruction("alt", -51.5),
    )
    _assert(eq_move_instruction("azi", 0.0) == "Azimuth is on the pole.", eq_move_instruction("azi", 0.0))


def test_pose_follows_the_hemisphere() -> None:
    north = eq_pose_steps(45)
    _assert("back of the telescope north" in north["text"], north)
    _assert("logo faces south" in north["text"], north)
    _assert("Polaris" in north["text"], north)
    _assert("45.0°" in north["text"], north)
    _assert("faces south" in north["text"], north)
    south = eq_pose_steps(-37.81667)
    _assert(south["hemisphere"] == "south", south)
    _assert("back of the telescope south" in south["text"], south)
    _assert("logo faces north" in south["text"], south)
    _assert("south celestial pole" in south["text"], south)
    _assert("37.8°" in south["text"], south)
    _assert("faces north" in south["text"], south)
    _assert("tripod legs" in south["text"], south)


def test_large_residual_warns_instead_of_complete() -> None:
    alerts = AlertEngine().evaluate(
        {"eq_state": "running"},
        {"eq_state": "idle", "eq_azi_err": -151.17, "eq_alt_err": -51.50},
    )
    _assert(len(alerts) == 1, alerts)
    _assert(alerts[0]["level"] == "warning", alerts)
    _assert(alerts[0]["message"] == "Adjust the wedge", alerts)
    _assert("counterclockwise 151.17°" in alerts[0]["detail"], alerts)
    _assert("down 51.50°" in alerts[0]["detail"], alerts)


def test_device_mosaic_needs_eq_until_body_status_is_eq() -> None:
    _assert(device_mosaic_needs_eq("") is True, "a missing body status is still alt-az")
    _assert(device_mosaic_needs_eq(None) is True, "no mount mode is still alt-az")
    _assert(device_mosaic_needs_eq("AZ") is True, "alt-az")
    _assert(device_mosaic_needs_eq("2") is True, "a raw status is not EQ")
    _assert(device_mosaic_needs_eq("EQ") is False, "EQ")
    _assert(device_mosaic_needs_eq(" eq ") is False, "EQ")


def test_small_residual_is_aligned() -> None:
    alerts = AlertEngine().evaluate(
        {"eq_state": "running", "eq_azi_err": 8.0, "eq_alt_err": 4.0},
        {"eq_state": "idle", "eq_azi_err": 0.4, "eq_alt_err": -1.2},
    )
    _assert(alerts[0]["level"] == "success", alerts)
    _assert(alerts[0]["message"] == "EQ aligned", alerts)
    view = format_telemetry({"eq_azi_err": 0.4, "eq_alt_err": -1.2}, None)
    _assert(view["eq_ready"] is True, view)
    _assert(view["eq_azi_action"].startswith("Rotate the head clockwise"), view)


def main() -> None:
    test_two_degrees_is_the_accept_limit()
    test_positive_azimuth_is_clockwise_and_positive_altitude_is_up()
    test_pose_follows_the_hemisphere()
    test_large_residual_warns_instead_of_complete()
    test_device_mosaic_needs_eq_until_body_status_is_eq()
    test_small_residual_is_aligned()
    print("test_eq_setup: ok")


if __name__ == "__main__":
    main()
