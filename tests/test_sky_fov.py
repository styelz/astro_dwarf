from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    Camera,
    DeviceModel,
    apply_camera_fov_defaults,
    camera_fov,
    camera_fov_plausible,
    mosaic_stack_camera,
    sky_map_camera,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_overlay_follows_selected_camera() -> None:
    _assert(sky_map_camera("wide") is Camera.WIDE, "wide overlay")
    _assert(sky_map_camera("tele") is Camera.TELE, "tele overlay")
    _assert(sky_map_camera(Camera.WIDE) is Camera.WIDE, "wide enum")


def test_mosaic_plan_follows_selected_camera() -> None:
    _assert(sky_map_camera("wide") is Camera.WIDE, "1×1 live FOV still follows Wide")
    _assert(sky_map_camera("wide", mosaic_grid=True) is Camera.WIDE, "wide mosaic grid")
    _assert(sky_map_camera("tele", mosaic_grid=True) is Camera.TELE, "tele mosaic grid")
    _assert(sky_map_camera("wide", stacking=True) is Camera.TELE, "stacking")
    _assert(sky_map_camera("wide", mosaic_grid=True, stacking=True) is Camera.TELE, "stacking wins")


def test_mosaic_stack_camera_ignores_selected_wide() -> None:
    _assert(mosaic_stack_camera("wide") is Camera.TELE, "wide combo")
    _assert(mosaic_stack_camera(Camera.WIDE) is Camera.TELE, "wide enum")
    _assert(mosaic_stack_camera("tele") is Camera.TELE, "tele combo")
    _assert(mosaic_stack_camera() is Camera.TELE, "default")


def test_dwarf3_wide_fov_is_much_larger_than_tele() -> None:
    tele_h, tele_v = camera_fov(DeviceModel.DWARF_3, Camera.TELE)
    wide_h, wide_v = camera_fov(DeviceModel.DWARF_3, Camera.WIDE)
    _assert(tele_h == 2.95 and tele_v == 1.66, (tele_h, tele_v))
    _assert(wide_h == 45.06 and wide_v == 25.93, (wide_h, wide_v))
    _assert(wide_h > tele_h * 10, wide_h)


def test_implausible_firmware_fov_is_replaced() -> None:
    _assert(not camera_fov_plausible(2.95, 1.66, Camera.WIDE), "tele-sized wide")
    _assert(not camera_fov_plausible(0.79, 0.45, Camera.WIDE), "radians-as-degrees")
    _assert(camera_fov_plausible(45.06, 25.93, Camera.WIDE), "published wide")
    _assert(not camera_fov_plausible(1.66, 2.95, Camera.TELE), "swapped tele")
    _assert(camera_fov_plausible(2.95, 1.66, Camera.TELE), "published tele")
    telemetry = apply_camera_fov_defaults(
        {"wide_fov_h": 2.95, "wide_fov_v": 1.66, "tele_fov_h": 0.05, "tele_fov_v": 0.03},
        DeviceModel.DWARF_3,
    )
    _assert(telemetry["wide_fov_h"] == 45.06, telemetry["wide_fov_h"])
    _assert(telemetry["tele_fov_h"] == 2.95, telemetry["tele_fov_h"])


def test_wide_selected_does_not_space_stack_panes_on_wide_fov() -> None:
    from astro_dwarf.domain import Target
    from astro_dwarf.services import mosaic_pane_footprints

    tele_h, tele_v = camera_fov(DeviceModel.DWARF_3, mosaic_stack_camera("wide"))
    wide_h, _wide_v = camera_fov(DeviceModel.DWARF_3, Camera.WIDE)
    panes = {
        pane["index"]: pane
        for pane in mosaic_pane_footprints(
            Target(name="Centre", ra_hours=6.0, dec_degrees=0.0),
            2,
            2,
            tele_h,
            tele_v,
            0.2,
            position_angle=0,
        )
    }
    step_x = tele_h * (1.0 - 0.2)
    east_hours = (panes[2]["ra_hours"] - panes[1]["ra_hours"]) * 15.0
    _assert(abs(east_hours - step_x) < 0.05, "STACK 2×2 panes use the tele FOV with overlap")
    _assert(east_hours < wide_h * 0.5, "must not inherit the ~45° Wide grid")


def test_stellarium_overlay_listens_once() -> None:
    from astro_dwarf.services import SKY_WEB_FOV_JS

    _assert("ctl.changeBound" in SKY_WEB_FOV_JS, "overlay must bind stel.change once")
    _assert("live.draw(false)" in SKY_WEB_FOV_JS, "frame listener must use the cached redraw")
    _assert("ctl.paused" in SKY_WEB_FOV_JS, "parked map must be able to stop the overlay loop")
    _assert(SKY_WEB_FOV_JS.count("stel.change(function") == 1, "one listener")
    start = SKY_WEB_FOV_JS.find("function viewKey")
    end = SKY_WEB_FOV_JS.find("function writePosLabels")
    body = SKY_WEB_FOV_JS[start:end]
    _assert("viewCenter" in body, "cached redraw must notice the ICRS centre moving")
    _assert("viewRollDeg" in body, "cached redraw must notice parallactic tilt")


if __name__ == "__main__":
    test_overlay_follows_selected_camera()
    test_mosaic_plan_follows_selected_camera()
    test_mosaic_stack_camera_ignores_selected_wide()
    test_dwarf3_wide_fov_is_much_larger_than_tele()
    test_implausible_firmware_fov_is_replaced()
    test_wide_selected_does_not_space_stack_panes_on_wide_fov()
    test_stellarium_overlay_listens_once()
    print("ok")
