from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import DeviceModel, Target
from astro_dwarf.sky_atlas import ATLAS_ASTRO_JS
from astro_dwarf.services import (
    MOSAIC_IMAGE_QUAD_ORDER,
    MOSAIC_PA_PARALLACTIC,
    MOSAIC_PA_STORED,
    SKY_WEB_FOV_JS,
    altaz_camera_pa,
    horizon_altitude_deg,
    mosaic_chart_tilt,
    mosaic_image_quad_xy,
    mosaic_overlay_hud_tilt,
    mosaic_pane_footprints,
    overlay_view_roll_deg,
    parallactic_angle_deg,
    resolve_device_mosaic_pa,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _target() -> Target:
    return Target(name="Centre", ra_hours=5.0, dec_degrees=20.0)


def test_hud_tilt_is_full_camera_pa_not_south_up_chart() -> None:
    cases = (
        (False, 0.0, 0.0),
        (False, 180.0, 180.0),
        (True, 180.0, 180.0),
        (True, 0.0, 0.0),
        (True, 295.0, 295.0),
    )
    for south_up, pa, expected in cases:
        tilt = mosaic_overlay_hud_tilt(south_up, pa)
        _assert(tilt == expected, (south_up, pa, tilt, expected))
    _assert(mosaic_chart_tilt(True, 180.0) == 0.0, "mosaic screen-grid still uses PA − 180° in the south")
    _assert(mosaic_chart_tilt(True, 295.0) == 115.0, mosaic_chart_tilt(True, 295.0))
    _assert(mosaic_overlay_hud_tilt(True, 180.0) != mosaic_chart_tilt(True, 180.0), "1×1 is not chart tilt")


def test_southern_altaz_one_by_one_upright_at_parallactic() -> None:
    """1×1 live JPEG on a zenith-up view is upright when PA equals q.

    The old HUD used southern chart tilt (PA − 180°) plus view roll (−q).
    That sat upright only when the operator stored PA = q+180° (Atria ~295°),
    which then rotated mosaic ICRS 180°.
    """
    when = datetime(2026, 9, 21, 13, 50, 27, tzinfo=timezone.utc)
    lat, lon = -37.81, 144.96
    ra, dec = 16.811, -69.027
    q = parallactic_angle_deg(ra, dec, lat, lon, when)
    _assert(q is not None, "parallactic of Atria")
    roll = overlay_view_roll_deg(ra, dec, lat, lon, when)
    one = (roll + mosaic_overlay_hud_tilt(True, q)) % 360.0
    _assert(one < 1e-6 or abs(one - 360.0) < 1e-6, (one, q, roll))
    old = (roll + mosaic_chart_tilt(True, q)) % 360.0
    _assert(abs(old - 180.0) < 1e-6, (old, q, "chart-tilt HUD is upside-down"))
    workaround = (float(q) + 180.0) % 360.0
    old_fix = (roll + mosaic_chart_tilt(True, workaround)) % 360.0
    _assert(old_fix < 1e-6 or abs(old_fix - 360.0) < 1e-6, (old_fix, workaround))
    _assert(abs(workaround - 295.0) < 2.0, (workaround, "Atria at 23:50 needed stored PA ~295"))
    later = datetime(2026, 9, 21, 14, 12, 29, tzinfo=timezone.utc)
    later_q = parallactic_angle_deg(ra, dec, lat, lon, later)
    _assert(later_q is not None, "parallactic at 00:12")
    _assert(abs(float(later_q) - 120.0) < 1.0, (later_q, "Atria at 00:12 is PA ~120, not a new HUD offset"))


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


def test_altaz_stays_upright_on_both_sides_of_the_south_pole() -> None:
    """Alt-az does not roll the frame when the chart crosses the pole.

    DWARF II, DWARF 3, and DWARF Mini only pan and nod. Both of these fields
    sit well below the zenith at a southern site, so camera-up stays toward
    the zenith. A stored south-up angle points at the pole and turns over
    on the far side.
    """
    when = datetime(2026, 9, 21, 20, 32, tzinfo=timezone.utc)
    lat, lon = -37.81, 144.96
    near = (19.278, -82.955)
    far = (5.187, -86.292)
    fixed = []
    near_pa = None
    for ra, dec in (near, far):
        alt = horizon_altitude_deg(ra, dec, lat, lon, when)
        _assert(alt is not None and alt < 80.0, (ra, dec, alt, "not looking past zenith"))
        pa = resolve_device_mosaic_pa(
            lat, 192.0, longitude=lon, ra_hours=ra, dec_degrees=dec, mount_mode="", when=when
        )
        _assert(pa.source == MOSAIC_PA_PARALLACTIC, pa)
        if (ra, dec) == near:
            near_pa = pa
        roll = overlay_view_roll_deg(ra, dec, lat, lon, when)
        upright = (roll + pa.degrees) % 360.0
        _assert(upright < 1e-6 or abs(upright - 360.0) < 1e-6, (ra, dec, upright, pa.degrees))
        fixed.append((roll + 192.0) % 360.0)
    gap = min(abs(fixed[0] - fixed[1]), 360.0 - abs(fixed[0] - fixed[1]))
    _assert(gap > 90.0, (fixed, "stored PA 192° flips across the pole"))
    eq = resolve_device_mosaic_pa(
        lat, 192.0, longitude=lon, ra_hours=near[0], dec_degrees=near[1], mount_mode="EQ", when=when
    )
    _assert(eq.source == MOSAIC_PA_STORED and abs(eq.degrees - 192.0) < 1e-6, eq)
    over = altaz_camera_pa(near[0], near[1], lat, lon, when, mechanical_altitude=120.0)
    level = altaz_camera_pa(near[0], near[1], lat, lon, when, mechanical_altitude=45.0)
    _assert(over is not None and level is not None, (over, level))
    _assert(abs(((over - level) % 360.0) - 180.0) < 1e-6, (over, level, "past 90° looks behind the body"))
    _assert(
        set(DeviceModel) == {DeviceModel.DWARF_II, DeviceModel.DWARF_3, DeviceModel.DWARF_MINI},
        "II, 3, and Mini share one alt-az camera rule",
    )
    again = resolve_device_mosaic_pa(
        lat, 192.0, longitude=lon, ra_hours=near[0], dec_degrees=near[1], mount_mode="AZ", when=when
    )
    _assert(near_pa is not None, "near-side alt-az angle")
    _assert(again.source == near_pa.source and abs(again.degrees - near_pa.degrees) < 1e-6, (again, near_pa))


def _unspin_zenith(points: list[tuple[float, float]], residual: float) -> list[tuple[float, float]]:
    """Same screen unspin as Aladin ``levelZenithPanes``.

    ``residual`` is the clockwise angle of camera-right away from screen +x.
    """
    import math

    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    cos_r = math.cos(residual)
    sin_r = math.sin(residual)
    out = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * cos_r + dy * sin_r, cy - dx * sin_r + dy * cos_r))
    return out


def test_aladin_zenith_pane_sits_level_like_stellarium() -> None:
    """A few degrees of Aladin map roll must not turn the pane over.

    Stellarium's alt-az grid is level, pane 1 at the top-right, JPEG top
    toward camera-up. Aladin used the raw corner ring as the JPEG, which
    plants the top-left pixel on camera right-up, and it kept that ring's roll.
    """
    import math

    _assert("function imageQuadFromRing" in ATLAS_ASTRO_JS, "Aladin JPEG order helper")
    _assert("return [ring[3], ring[0], ring[1], ring[2]];" in ATLAS_ASTRO_JS, ATLAS_ASTRO_JS[ATLAS_ASTRO_JS.find("function imageQuadFromRing"):ATLAS_ASTRO_JS.find("function imageQuadFromRing") + 240])
    _assert(MOSAIC_IMAGE_QUAD_ORDER == (3, 0, 1, 2), MOSAIC_IMAGE_QUAD_ORDER)
    _assert("function levelZenithPanes" in ATLAS_ASTRO_JS, "zenith panes snap level")
    _assert("var extra = zenithCamera ? 0 :" in ATLAS_ASTRO_JS, "zenith overlay does not add map roll")
    _assert("dx * cos + dy * sin" in ATLAS_ASTRO_JS, "unspin x")
    _assert("- dx * sin + dy * cos" in ATLAS_ASTRO_JS, "unspin y")
    roll = math.radians(4.0)
    # Pane 1 is up-right. Roll those centres so camera-right leaves screen +x,
    # which is the inverse of the Aladin unspin.
    level = [(20.0, -10.0), (-20.0, -10.0), (20.0, 10.0), (-20.0, 10.0)]
    cos_r, sin_r = math.cos(roll), math.sin(roll)
    rolled = [(x * cos_r - y * sin_r, x * sin_r + y * cos_r) for x, y in level]
    snapped = _unspin_zenith(rolled, roll)
    for got, want in zip(snapped, level):
        _assert(abs(got[0] - want[0]) < 1e-6 and abs(got[1] - want[1]) < 1e-6, (got, want))
    pane1 = snapped[0]
    _assert(pane1[0] > 0 and pane1[1] < 0, (pane1, "pane 1 stays up and right"))


def test_stellarium_js_unifies_one_by_one_and_mosaic_live() -> None:
    _assert("function livePointingQuad" in SKY_WEB_FOV_JS, "1×1 and mosaic share one live quad")
    _assert("return [3, 0, 1, 2];" in SKY_WEB_FOV_JS, "JPEG TL is camera left-up")
    _assert("rotateChartGroup(box, p, stel," in SKY_WEB_FOV_JS or "function rotateChartGroup" in SKY_WEB_FOV_JS,
            "1×1 HUD helper remains")
    _assert("function rotateOverlay" in SKY_WEB_FOV_JS, "1×1 and mosaic grid pass distinct tilts")
    _assert("function cameraHudTilt" in SKY_WEB_FOV_JS, "1×1 HUD uses camera PA plus view roll")
    _assert("function mosaicGridTilt" in SKY_WEB_FOV_JS, "numbered mosaic fallback keeps chart tilt")
    _assert("function rotateGroup" not in SKY_WEB_FOV_JS, "full-PA HUD rotation flipped S-UP mosaics")
    resolve = SKY_WEB_FOV_JS.split("function resolvePanes")[1].split("function viewKey")[0]
    _assert('=== "center"' not in resolve, "1×1 must still project ICRS panes")
    _assert("payloadPointing(p) || viewCenter(stel)" in SKY_WEB_FOV_JS, "empty payload still builds a 1×1")
    _assert("livePointingQuad(p, stel, box)" in SKY_WEB_FOV_JS, "mosaic live uses the centre footprint")
    _assert("function unitDir" in SKY_WEB_FOV_JS, "VIEW convertFrame needs a unit vector")
    _assert("function viewRollDeg" in SKY_WEB_FOV_JS, "screen HUD must pick up zenith-up field rotation")
    _assert("function hudTilt" in SKY_WEB_FOV_JS, "screen HUD tilt helper exists")
    _assert("function cameraHudTilt" in SKY_WEB_FOV_JS, "1×1 HUD is view roll plus live camera PA")
    _assert("function liveCameraPa" in SKY_WEB_FOV_JS, "alt-az uses live parallactic, not stored PA")
    _assert("overlayMountMode(p) !== \"EQ\"" in SKY_WEB_FOV_JS, "mosaics on alt-az follow the zenith too")
    _assert("pastZenith(p) ? 180 : 0" in SKY_WEB_FOV_JS, "frame inverts only past mechanical zenith")
    _assert("liveCameraPa(p, stel)" in SKY_WEB_FOV_JS, "live JPEG corners follow live camera PA")
    _assert("isFinite(q) ? -q : 0" in SKY_WEB_FOV_JS, "view roll is -parallactic like Aladin zenithRotation")
    _assert("var projected = drawPanes(el, box, p, stel, panes);" in SKY_WEB_FOV_JS, "1×1 and mosaics share ICRS drawPanes")
    _assert("if (mosaic && panes.length)" not in SKY_WEB_FOV_JS, "1×1 must not skip ICRS projection")


def test_altaz_mosaic_is_one_camera_angle() -> None:
    """Alt-az panes share the centre angle. A per-pane angle fans the boxes.

    Beta Hydri's panes differ by about nine degrees of parallactic angle.
    The photos and the contact sheet are one zenith-up frame, so the
    rectangles stay parallel. Equatorial mounts keep the one stored angle.
    """
    from types import SimpleNamespace

    from astro_dwarf.services import mosaic_session_footprints, stitch_capture_position_angle

    when = datetime(2026, 10, 18, 18, 4, tzinfo=timezone.utc)
    lat, lon = -37.81667, 144.96667
    target = Target(name="Beta Hydri", ra_hours=0.438, dec_degrees=-77.25)
    centre = parallactic_angle_deg(0.438, -77.25, lat, lon, when)
    _assert(centre is not None and abs(float(centre) - 90.0) < 20.0, centre)
    panes = mosaic_pane_footprints(
        target, 2, 2, 2.95, 1.66, 0.15,
        latitude=lat, longitude=lon, mount_mode="AZ", when=when,
        position_angle=centre,
    )
    angles = {pane["position_angle"] for pane in panes}
    _assert(angles == {round(float(centre), 3)}, angles)
    equatorial = mosaic_pane_footprints(
        target, 2, 2, 2.95, 1.66, 0.15,
        latitude=lat, longitude=lon, mount_mode="EQ", when=when,
        position_angle=180,
    )
    _assert({pane["position_angle"] for pane in equatorial} == {180.0}, equatorial)
    saved = [85.4, 83.8, 94.3, 94.0]
    coords = [(0.609, -75.947), (0.694, -78.439), (0.221, -76.021), (0.224, -78.528)]
    sessions = []
    for index, (angle, (ra, dec)) in enumerate(zip(saved, coords), start=1):
        sessions.append(SimpleNamespace(
            name=f"pane {index}",
            target=SimpleNamespace(ra_hours=ra, dec_degrees=dec),
            mosaic=SimpleNamespace(
                row=(index - 1) // 2 + 1,
                column=(index - 1) % 2 + 1,
                rows=2,
                columns=2,
                rotation_degrees=angle,
                grid_rows=2,
                grid_columns=2,
            ),
        ))
    drawn = mosaic_session_footprints(sessions, 2.95, 1.66, float(centre))
    drawn_angles = {pane["position_angle"] for pane in drawn}
    _assert(len(drawn_angles) == 1, drawn_angles)
    shared = next(iter(drawn_angles))
    _assert(83.0 < shared < 95.0, shared)
    _assert(shared not in saved, (shared, "must not keep one pane's angle and fan the rest"))
    fresh = stitch_capture_position_angle(
        0.224, -78.528, 0.0,
        latitude=lat, longitude=lon, mount_mode="AZ",
        captured_at=datetime(2026, 10, 18, 18, 24, tzinfo=timezone.utc),
    )
    _assert(fresh == 0.0, fresh)
    kept = stitch_capture_position_angle(
        0.224, -78.528, 180.0, mount_mode="EQ",
        captured_at="2026-10-18T18:24:00+00:00",
    )
    _assert(abs(kept - 180.0) < 1e-6, kept)
    _assert("function zenithPaneRoll" not in SKY_WEB_FOV_JS, "Stellarium must not roll each pane")
    _assert("function zenithCellRolls" not in ATLAS_ASTRO_JS, "Aladin must not roll each pane")


def test_both_charts_share_the_vertical_field_and_the_level_grid() -> None:
    """Aladin and Stellarium size the camera from the vertical field.

    The old Aladin box divided width by getFov()[0] and height by getFov()[1].
    On a landscape map that is a different rectangle from Stellarium, which
    scales both axes from the vertical field. Projected alt-az panes on
    Stellarium also drop the shared map roll, the same unspin Aladin uses.
    """
    import math

    _assert("function cameraPanePixels" in ATLAS_ASTRO_JS, "Aladin pane size")
    _assert("function verticalFieldDeg" in ATLAS_ASTRO_JS, "vertical field, not getFov()[0]")
    _assert("var panePx = cameraPanePixels(width, height, fovH, fovV, aladin);" in ATLAS_ASTRO_JS, "paintFov uses the shared scale")
    _assert("(fovH / fovX) * width" not in ATLAS_ASTRO_JS, "per-axis getFov scale is gone")
    _assert("function levelZenithDrawn" in SKY_WEB_FOV_JS, "Stellarium levels projected panes")
    _assert("levelZenithDrawn(drawn)" in SKY_WEB_FOV_JS, "drawPanes applies the unspin")
    half_v = 2 * math.tan(math.radians(70.0) / 4)
    height = 1080
    h = (2 * math.tan(math.radians(1.66) / 4) / half_v) * height
    w = (2 * math.tan(math.radians(2.95) / 4) / half_v) * height
    _assert(abs(w / h - 2.95 / 1.66) < 0.02, (w, h, "box keeps the tele aspect"))
    wide = (2.95 / 70.0) * 1920
    _assert(w < wide * 0.7, (w, wide, "landscape width is not the vertical field stretched across the window"))


if __name__ == "__main__":
    test_hud_tilt_is_full_camera_pa_not_south_up_chart()
    test_southern_altaz_one_by_one_upright_at_parallactic()
    test_overlay_view_roll_is_minus_parallactic()
    test_jpeg_top_is_camera_up_on_north_up_chart()
    test_one_by_one_and_mosaic_centre_share_camera_up()
    test_altaz_stays_upright_on_both_sides_of_the_south_pole()
    test_aladin_zenith_pane_sits_level_like_stellarium()
    test_stellarium_js_unifies_one_by_one_and_mosaic_live()
    test_altaz_mosaic_is_one_camera_angle()
    test_both_charts_share_the_vertical_field_and_the_level_grid()
    print("ok")
