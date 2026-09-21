from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.services import (
    SKY_WEB_SITE_JS,
    SKY_WEB_TIME_NOW_JS,
    SKY_WEB_VIEW_APPLY_JS,
    sky_web_view_script,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_restore_script_drops_time_dependent_pose() -> None:
    script = sky_web_view_script({
        "ra_hours": 5.138,
        "dec_degrees": -68.991,
        "fov": 12.5,
        "yaw": 1.23,
        "pitch": 0.45,
        "roll": 0.1,
    })
    _assert("5.138" in script, script)
    _assert("-68.991" in script, script)
    _assert("12.5" in script, script)
    _assert('"yaw"' not in script, script)
    _assert('"pitch"' not in script, script)
    _assert('"roll"' not in script, script)


def test_restore_script_looks_at_icrs_at_current_time() -> None:
    _assert("keepSkyTimeNow" in SKY_WEB_VIEW_APPLY_JS, "restore must jump Stellarium to now")
    _assert(".utc = mjd" in SKY_WEB_VIEW_APPLY_JS, "restore must set engine UTC")
    _assert("40587.0" in SKY_WEB_VIEW_APPLY_JS, "UTC is MJD")
    _assert("lookAtIcrf" in SKY_WEB_VIEW_APPLY_JS, "restore points at saved RA/Dec")
    _assert("p.yaw" not in SKY_WEB_VIEW_APPLY_JS, "must not replay saved alt-az")
    _assert("p.pitch" not in SKY_WEB_VIEW_APPLY_JS, "must not replay saved alt-az")


def test_site_script_resets_clock_to_now() -> None:
    _assert("keepSkyTimeNow" in SKY_WEB_SITE_JS, "site apply must jump Stellarium to now")
    _assert(".utc = mjd" in SKY_WEB_SITE_JS, "site apply must set engine UTC")
    _assert("40587.0" in SKY_WEB_SITE_JS, "UTC is MJD")
    _assert("time_speed = 1" in SKY_WEB_SITE_JS, "site apply must resume realtime")
    _assert("startTimeIsSet" in SKY_WEB_SITE_JS, "must block Stellarium night-time jump")
    _assert("setTimeAfterSunSet" in SKY_WEB_SITE_JS, "must no-op the sunset startup clock")


def test_time_now_helper_blocks_stellarium_night_jump() -> None:
    _assert("startTimeIsSet" in SKY_WEB_TIME_NOW_JS, "helper must mark startup time as set")
    _assert("setTimeAfterSunSet" in SKY_WEB_TIME_NOW_JS, "helper must disable sunset jump")
    _assert("date2MJD" in SKY_WEB_TIME_NOW_JS, "helper uses engine MJD conversion")
    _assert("mdi-history" in SKY_WEB_TIME_NOW_JS, "helper clicks Stellarium reset-to-now")
    _assert("clickStellariumNow" in SKY_WEB_TIME_NOW_JS, "helper uses Stellarium now control")
    _assert("[0, 50, 250, 800, 1600]" in SKY_WEB_TIME_NOW_JS, "helper reapplies after Vue nextTick")


if __name__ == "__main__":
    test_restore_script_drops_time_dependent_pose()
    test_restore_script_looks_at_icrs_at_current_time()
    test_site_script_resets_clock_to_now()
    test_time_now_helper_blocks_stellarium_night_jump()
    print("ok")
