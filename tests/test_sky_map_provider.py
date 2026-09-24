from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    DEFAULT_SKY_MAP_PROVIDER,
    SKY_MAP_PROVIDER_ALADIN,
    SKY_MAP_PROVIDER_STELLARIUM_WEB,
    app_settings_from_dict,
    normalized_sky_map_provider,
    to_dict,
)
from astro_dwarf.services import SKY_WEB_DISMISS_POLL_JS, sky_web_fov_script
from astro_dwarf.sky_atlas import (
    SKY_MAP_FOV_DEG,
    atlas_set_fov_from_view,
    atlas_view_payload,
    parse_atlas_harvest,
    sky_atlas_boot_script,
    sky_atlas_dismiss_poll_script,
    sky_atlas_fov_script,
    sky_atlas_home_script,
    sky_atlas_live_script,
    sky_atlas_lock_target_script,
    sky_atlas_open_menu_script,
    sky_atlas_pin_target_script,
    sky_atlas_site_script,
    sky_atlas_view_poll_script,
    sky_atlas_view_pos_script,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_provider_defaults_to_stellarium_web() -> None:
    settings = app_settings_from_dict({})
    _assert(settings.sky_map_provider == DEFAULT_SKY_MAP_PROVIDER, settings.sky_map_provider)
    _assert(settings.sky_map_provider == SKY_MAP_PROVIDER_STELLARIUM_WEB, settings.sky_map_provider)


def test_provider_aliases_and_unknown() -> None:
    _assert(normalized_sky_map_provider("Stellarium Web") == SKY_MAP_PROVIDER_STELLARIUM_WEB, "alias")
    _assert(normalized_sky_map_provider("aladin-lite") == SKY_MAP_PROVIDER_ALADIN, "aladin alias")
    _assert(normalized_sky_map_provider("nope") == SKY_MAP_PROVIDER_STELLARIUM_WEB, "unknown")
    _assert(normalized_sky_map_provider(None) == SKY_MAP_PROVIDER_STELLARIUM_WEB, "empty")


def test_provider_round_trip() -> None:
    settings = app_settings_from_dict({"sky_map_provider": "aladin"})
    dumped = to_dict(settings)
    _assert(dumped["sky_map_provider"] == SKY_MAP_PROVIDER_ALADIN, dumped)
    again = app_settings_from_dict(dumped)
    _assert(again.sky_map_provider == SKY_MAP_PROVIDER_ALADIN, again.sky_map_provider)
    web = app_settings_from_dict({"sky_map_provider": "stellarium_web"})
    _assert(web.sky_map_provider == SKY_MAP_PROVIDER_STELLARIUM_WEB, web.sky_map_provider)


def test_atlas_harvest_json() -> None:
    hit = parse_atlas_harvest('{"name":"M31","ra_hours":0.712,"dec_degrees":41.27}')
    _assert(hit is not None and hit["name"] == "M31", hit)
    _assert(hit["ra_hours"] == 0.712, hit)
    rich = parse_atlas_harvest(
        '{"name":"M42","ra_hours":5.588,"dec_degrees":-5.391,'
        '"type":"HII","magnitude":4.0}'
    )
    _assert(rich is not None and rich.get("type") == "HII", rich)
    _assert(rich is not None and rich.get("magnitude") == 4.0, rich)
    _assert(parse_atlas_harvest("{}") is None, "empty")
    _assert(parse_atlas_harvest('{"error":"no"}') is None, "error")


def test_atlas_set_fov_from_view() -> None:
    _assert(atlas_set_fov_from_view(100, 56) == 56, "inscribed")
    _assert(atlas_set_fov_from_view(40, 70) == 40, "portrait")
    _assert(atlas_set_fov_from_view(12, None) == 12, "x only")
    _assert(atlas_set_fov_from_view("nope", 8) == 8, "y only")
    _assert(atlas_set_fov_from_view("x", "y") is None, "bad")


def test_atlas_view_and_lock_helpers() -> None:
    view = atlas_view_payload(10.684, 41.269, 2.5)
    _assert(abs(view["ra_hours"] - 10.684 / 15) < 1e-6, view)
    _assert(view["fov"] == 2.5, view)
    script = sky_atlas_lock_target_script({"name": "M31", "ra_hours": 0.712, "dec_degrees": 41.27})
    _assert("0.712" in script and "41.27" in script, script)
    fov = sky_atlas_fov_script({"mode": "panes", "panes": []})
    _assert('"mode": "panes"' in fov or '"mode":"panes"' in fov, fov)
    _assert("syntheticPanes" in fov and "drawHorizon" in fov, "fov overlay")
    _assert("altKey" not in fov, "ctrl wheel lives on the horizon canvas")
    boot = sky_atlas_boot_script()
    _assert("STG" in boot and "contextmenu" in boot, "boot")
    _assert("lookPan" in boot and "drawHorizon" in boot and "zenithRotation" in boot, "planetarium")
    _assert("gotoCenter" in boot and "box.dragging" in boot and "requestSync" in boot, "stable pan")
    _assert("zenithRotation(eq[0], eq[1]" in boot, "pan keeps zenith up while dragging")
    _assert("function nearestAngle" in boot, "parallactic branch cut must not spin the view")
    _assert(SKY_MAP_FOV_DEG == 70.0, SKY_MAP_FOV_DEG)
    _assert("applyFov(aladin, 70)" in boot, "shared home field")
    _assert("markMoved" in boot and "applyFov" in boot and "inscribedFov" in boot, "fov persist")
    _assert("objectClicked" in boot and "selectSky" in boot, "simbad harvest")
    _assert("paintFov" in boot and "drawHeadingLabels" in boot, "screen fov")
    _assert("hudInsets" in boot and "aladin-status-bar" in boot, "hud chrome")
    _assert("labelOnFov" in boot and "drawScreenMosaic" in boot and "drawPaneMedia" in boot, "fov on frame")
    _assert("paintIndex" in boot and "strokeTargetQuad" in boot, "target corners and numbered cells")
    _assert("payload.columns" in boot and "col1OnRight" in boot, "mosaic grid")
    _assert("ctrlKey" in boot and "bindLiveOpacityWheel" in boot, "ctrl wheel opacity")
    _assert("drawPaneMedia" in boot and "rememberImage" in boot, "live preview on fov")
    live = sky_atlas_live_script("data:image/jpeg;base64,xx", True, 0.4, 0)
    _assert("drawHorizon" in live and "wheelOpacity" in live, live)
    _assert("liveEnabled" in live and "0.4" in live, live)
    _assert("hor.az - 180" in boot, "heading compass")
    site = sky_atlas_site_script(-37.81, 144.96)
    _assert('"has_site": true' in site and "-37.81" in site, site)
    _assert("astro.home" in sky_atlas_home_script(), "home")
    _assert("no-site" in sky_atlas_boot_script(), "home status")
    _assert("hideAtlasMenu" in boot and "menuLast" in boot, "atlas menu intercept")
    opened = sky_atlas_open_menu_script(120.5, 80)
    _assert("120.5" in opened and "80" in opened, opened)
    _assert("astro-dwarf-atlas-menu" in opened and "contextMenu._show" in opened, opened)
    _assert("document.body.appendChild" in opened and "z-index" in opened, "menu above fov")
    _assert("data-theme" in opened and "--bg-color" in opened, "menu theme")
    poll = sky_atlas_view_poll_script()
    _assert("user_moved" in poll and "inscribedFov" in poll, "poll fov")
    _assert("setFovValue" in poll, "poll last setFov")
    pos = sky_atlas_view_pos_script(5.588, -5.391)
    _assert("applyLook" in pos and "setFov" not in pos, "centre only")
    pin = sky_atlas_pin_target_script({"name": "FOV centre", "ra_hours": 1.2, "dec_degrees": -37.8})
    _assert("FOV centre" in pin and "1.2" in pin, pin)
    fov = sky_atlas_fov_script({"mode": "panes", "panes": []})
    _assert("preventDefault" in fov and "pix2world" in fov, "dblclick centre")
    _assert("clickBound" in fov and "simbadTooltipName" in fov, "named click")


def test_atlas_target_tooltip_stays_above_location_box() -> None:
    html = (ROOT / "astro_dwarf" / "qml" / "sky_atlas" / "index.html").read_text(encoding="utf-8")
    boot = sky_atlas_boot_script()
    _assert("aladin-simbadPointer-control" in html, "simbad target")
    _assert("maximum-scale=1" in html, "ctrl wheel should not page-zoom")
    _assert("aladin-tooltip" in html and "z-index: 90" in html, "tooltip above chrome")
    _assert("transform: none" in html, "tooltip not over location box")
    _assert("astro-dwarf-atlas-tooltip" in boot and "aladin-simbadPointer-control" in boot, "boot tooltip")
    _assert("transform:none" in boot.replace(" ", ""), "boot pins tooltip right")


def test_map_left_click_dismisses_context_menu() -> None:
    web = sky_web_fov_script({})
    _assert("ctl.dismissAt = Date.now()" in web, "stellarium left click")
    _assert("astro-dwarf-host:menu" in web, "stellarium pushes the right-click")
    _assert("ctl.timer = setTimeout" in web, "stellarium redraws without animation frames")
    _assert("ev.button !== 0" in web, "stellarium ignores the opening right-click")
    _assert("ctl.dismissAt = 0" in web, "stellarium right-click clears a stale dismiss")
    _assert('return "dismiss"' in SKY_WEB_DISMISS_POLL_JS and "ctl.dismissAt = 0" in SKY_WEB_DISMISS_POLL_JS, "stellarium poll")
    atlas = sky_atlas_boot_script()
    _assert("box.dismissAt = Date.now()" in atlas, "aladin left click")
    _assert("astro-dwarf-host:menu" in atlas, "aladin pushes the right-click")
    _assert("ev.button !== 0" in atlas, "aladin ignores the opening right-click")
    _assert("box.dismissAt = 0" in atlas, "aladin right-click clears a stale dismiss")
    poll = sky_atlas_dismiss_poll_script()
    _assert('return "dismiss"' in poll and "box.dismissAt = 0" in poll, "aladin poll")


if __name__ == "__main__":
    test_provider_defaults_to_stellarium_web()
    test_provider_aliases_and_unknown()
    test_provider_round_trip()
    test_atlas_harvest_json()
    test_atlas_set_fov_from_view()
    test_atlas_view_and_lock_helpers()
    test_atlas_target_tooltip_stays_above_location_box()
    test_map_left_click_dismisses_context_menu()
    print("ok")
