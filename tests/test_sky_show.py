from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Target, TargetKind
from astro_dwarf.services import mosaic_pane_footprints, sky_show_plan


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _close(actual: float, expected: float, places: int = 3) -> None:
    _assert(abs(actual - expected) < 10 ** (-places), f"{actual} != {expected}")


def _target(name: str, ra: float, dec: float, mosaic: dict | None = None) -> dict:
    return {
        "target_name": name,
        "target": {"name": name, "ra_hours": ra, "dec_degrees": dec},
        "mosaic": mosaic
        or {
            "rows": 1,
            "columns": 1,
            "rotation_degrees": 0,
            "horizontal_scale": 150,
            "vertical_scale": 150,
            "grid_rows": 0,
            "grid_columns": 0,
            "row": 0,
            "column": 0,
        },
    }


def test_single_target_is_one_frame_at_its_coordinates() -> None:
    item = _target("M42", 5.588, -5.391)
    plan = sky_show_plan(item, fov_h=2.95, fov_v=1.66)
    _assert(plan["ok"] is True, plan)
    _assert(plan["mosaic"] is False, plan)
    _assert(plan["columns"] == 1 and plan["rows"] == 1, plan)
    _assert(plan["name"] == "M42", plan)
    _close(float(plan["ra_hours"]), 5.588, 6)
    _close(float(plan["dec_degrees"]), -5.391, 6)


def test_missing_coordinates_are_not_a_sky_target() -> None:
    plan = sky_show_plan({"target_name": "Sun", "target": {"name": "Sun", "kind": "solar"}})
    _assert(plan["ok"] is False, plan)
    _assert(plan["ra_hours"] is None, plan)


def test_firmware_mosaic_keeps_its_centre_and_scale() -> None:
    item = _target(
        "NGC 1",
        1.0,
        10.0,
        {
            "rows": 2,
            "columns": 3,
            "rotation_degrees": 15,
            "horizontal_scale": 80,
            "vertical_scale": 80,
            "grid_rows": 0,
            "grid_columns": 0,
            "row": 0,
            "column": 0,
        },
    )
    plan = sky_show_plan(item, fov_h=3.0, fov_v=2.0)
    _assert(plan["mosaic"] is True, plan)
    _assert(plan["columns"] == 3 and plan["rows"] == 2, plan)
    _close(float(plan["overlap"]), 0.2, 6)
    _close(float(plan["ra_hours"]), 1.0, 6)
    _close(float(plan["dec_degrees"]), 10.0, 6)
    _close(float(plan["position_angle"]), 15.0, 6)
    gapped = _target(
        "NGC 1",
        1.0,
        10.0,
        {
            "rows": 2,
            "columns": 2,
            "rotation_degrees": 0,
            "horizontal_scale": 150,
            "vertical_scale": 150,
            "grid_rows": 0,
            "grid_columns": 0,
            "row": 0,
            "column": 0,
        },
    )
    gapped_plan = sky_show_plan(gapped, fov_h=3.0, fov_v=2.0)
    _close(float(gapped_plan["overlap"]), 0.0, 6)


def test_pane_group_uses_grid_centre_and_overlap() -> None:
    center = Target(name="Eq", kind=TargetKind.EQUATORIAL, ra_hours=5.0, dec_degrees=0.0)
    panes = mosaic_pane_footprints(center, 2, 2, 2.95, 1.66, 0.2, position_angle=0)
    members = []
    for pane in panes:
        members.append(
            _target(
                "Eq",
                float(pane["ra_hours"]),
                float(pane["dec_degrees"]),
                {
                    "rows": 1,
                    "columns": 1,
                    "rotation_degrees": 12,
                    "horizontal_scale": 150,
                    "vertical_scale": 150,
                    "grid_rows": 2,
                    "grid_columns": 2,
                    "row": pane["row"],
                    "column": pane["column"],
                    "group_id": "eq-grid",
                },
            )
        )
    members[0]["is_grouped"] = True
    members[0]["group_title"] = "Eq"
    plan = sky_show_plan(members[0], members, fov_h=2.95, fov_v=1.66)
    _assert(plan["ok"] is True and plan["mosaic"] is True, plan)
    _assert(plan["columns"] == 2 and plan["rows"] == 2, plan)
    _assert(plan["name"] == "Eq", plan)
    _close(float(plan["ra_hours"]), 5.0, 2)
    _close(float(plan["dec_degrees"]), 0.0, 2)
    _close(float(plan["overlap"]), 0.2, 2)
    _close(float(plan["position_angle"]), 12.0, 6)


if __name__ == "__main__":
    test_single_target_is_one_frame_at_its_coordinates()
    test_missing_coordinates_are_not_a_sky_target()
    test_firmware_mosaic_keeps_its_centre_and_scale()
    test_pane_group_uses_grid_centre_and_overlap()
    print("ok")
