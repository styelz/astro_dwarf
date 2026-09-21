from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Target
from astro_dwarf.services import (
    MOSAIC_IMAGE_QUAD_ORDER,
    SKY_WEB_FOV_JS,
    mosaic_chart_tilt,
    mosaic_image_quad_xy,
    mosaic_overlay_hud_tilt,
    mosaic_pane_footprints,
    overlay_view_roll_deg,
    parallactic_angle_deg,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _target() -> Target:
    return Target(name="Centre", ra_hours=5.0, dec_degrees=20.0)


def test_hud_tilt_matches_chart_tilt_not_full_pa() -> None:
    cases = (
        (False, 0.0, 0.0),
        (False, 180.0, 180.0),
        (True, 180.0, 0.0),
        (True, 0.0, 180.0),
    )
    for south_up, pa, expected in cases:
        tilt = mosaic_overlay_hud_tilt(south_up, pa)
        _assert(tilt == expected, (south_up, pa, tilt, expected))
        _assert(tilt == mosaic_chart_tilt(south_up, pa), (south_up, pa))
        _assert(tilt != 180.0 or pa != 0.0 or south_up, "N-up PA 0 must not HUD-flip")


def test_overlay_view_roll_is_minus_parallactic() -> None:
    when = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    lat, lon = -37.81, 144.96
    ra, dec = 5.36, -69.67
    q = parallactic_angle_deg(ra, dec, lat, lon, when)
    _assert(q is not None, "parallactic")
    _assert(abs(q) > 5.0, "LMC at this site is off the meridian so the HUD must roll")
    roll = overlay_view_roll_deg(ra, dec, lat, lon, when)
    expected = (-float(q)) % 360.0
    _assert(abs(roll - expected) < 1e-6, (roll, expected, q))


def test_jpeg_top_is_camera_up_on_north_up_chart() -> None:
    _assert(MOSAIC_IMAGE_QUAD_ORDER == (3, 0, 1, 2), MOSAIC_IMAGE_QUAD_ORDER)
    pane = mosaic_pane_footprints(_target(), 1, 1, 2.95, 1.66, 0.0, position_angle=0)[0]
    quad = mosaic_image_quad_xy(pane["corners"], 5.0, 20.0)
    top_y = (quad[0][1] + quad[1][1]) / 2.0
    bottom_y = (quad[3][1] + quad[2][1]) / 2.0
    _assert(top_y < bottom_y, (top_y, bottom_y, "PA 0 JPEG top must sit toward north / -y"))
    south = mosaic_pane_footprints(_target(), 1, 1, 2.95, 1.66, 0.0, position_angle=180)[0]
    south_quad = mosaic_image_quad_xy(south["corners"], 5.0, 20.0)
    south_top = (south_quad[0][1] + south_quad[1][1]) / 2.0
    south_bottom = (south_quad[3][1] + south_quad[2][1]) / 2.0
    _assert(
        south_top > south_bottom,
        (south_top, south_bottom, "PA 180 JPEG top must sit toward south / +y"),
    )


def test_one_by_one_and_mosaic_centre_share_camera_up() -> None:
    one = mosaic_pane_footprints(_target(), 1, 1, 2.95, 1.66, 0.2, position_angle=0)[0]
    two = mosaic_pane_footprints(_target(), 2, 2, 2.95, 1.66, 0.2, position_angle=0)
    one_quad = mosaic_image_quad_xy(one["corners"], 5.0, 20.0)
    # Live mosaic video is the 1×1 tele footprint at the mosaic centre, not pane 1.
    centre = mosaic_pane_footprints(_target(), 1, 1, 2.95, 1.66, 0.0, position_angle=0)[0]
    centre_quad = mosaic_image_quad_xy(centre["corners"], 5.0, 20.0)
    for left, right in zip(one_quad, centre_quad):
        _assert(abs(left[0] - right[0]) < 1e-6, (left, right))
        _assert(abs(left[1] - right[1]) < 1e-6, (left, right))
    _assert(len(two) == 4, len(two))
    pane1 = mosaic_image_quad_xy(two[0]["corners"], 5.0, 20.0)
    _assert(abs(pane1[0][0] - one_quad[0][0]) > 0.1, "pane 1 is offset; live video must not use it")


def test_stellarium_js_unifies_one_by_one_and_mosaic_live() -> None:
    _assert("function livePointingQuad" in SKY_WEB_FOV_JS, "1×1 and mosaic share one live quad")
    _assert("return [3, 0, 1, 2];" in SKY_WEB_FOV_JS, "JPEG TL is camera left-up")
    _assert("rotateChartGroup(box, p, stel," in SKY_WEB_FOV_JS, "1×1 HUD uses chart tilt")
    _assert("function rotateGroup" not in SKY_WEB_FOV_JS, "full-PA HUD rotation flipped S-UP mosaics")
    resolve = SKY_WEB_FOV_JS.split("function resolvePanes")[1].split("function viewKey")[0]
    _assert('=== "center"' not in resolve, "1×1 must still project ICRS panes")
    _assert("payloadPointing(p) || viewCenter(stel)" in SKY_WEB_FOV_JS, "empty payload still builds a 1×1")
    _assert("livePointingQuad(p, stel, box)" in SKY_WEB_FOV_JS, "mosaic live uses the centre footprint")
    _assert("function unitDir" in SKY_WEB_FOV_JS, "VIEW convertFrame needs a unit vector")
    _assert("function viewRollDeg" in SKY_WEB_FOV_JS, "screen HUD must pick up zenith-up field rotation")
    _assert("function hudTilt" in SKY_WEB_FOV_JS, "screen HUD tilt is view roll plus chart tilt")
    _assert("isFinite(q) ? -q : 0" in SKY_WEB_FOV_JS, "view roll is -parallactic like Aladin zenithRotation")
    _assert("var mosaic = Math.max(1, Number(p.columns) || 1) > 1" in SKY_WEB_FOV_JS, "1×1 stays on the screen HUD")
    _assert("if (mosaic && panes.length)" in SKY_WEB_FOV_JS, "only mosaics use ICRS pane projection")


if __name__ == "__main__":
    test_hud_tilt_matches_chart_tilt_not_full_pa()
    test_overlay_view_roll_is_minus_parallactic()
    test_jpeg_top_is_camera_up_on_north_up_chart()
    test_one_by_one_and_mosaic_centre_share_camera_up()
    test_stellarium_js_unifies_one_by_one_and_mosaic_live()
    print("ok")
