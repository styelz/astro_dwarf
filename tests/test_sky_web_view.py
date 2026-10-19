from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.services import (
    SKY_WEB_BOOT_JS,
    SKY_WEB_HOST_LINK_JS,
    SKY_WEB_SITE_JS,
    SKY_WEB_TIME_NOW_JS,
    SKY_WEB_VIEW_APPLY_JS,
    SKY_WEB_VIEW_POLL_JS,
    external_link_filename,
    external_link_url,
    parse_sky_host_title,
    save_external_bytes,
    sky_web_view_script,
)
from astro_dwarf.sky_atlas import SKY_MAP_FOV_DEG, sky_atlas_boot_script, sky_atlas_view_script


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


def test_shared_fov_is_degrees_on_both_maps() -> None:
    _assert(SKY_MAP_FOV_DEG == 70.0, SKY_MAP_FOV_DEG)
    _assert("applyFov(aladin, 70)" in sky_atlas_boot_script(), "Aladin home field")
    atlas = sky_atlas_view_script({"ra_hours": 5.0, "dec_degrees": -69.0, "fov": 0})
    _assert("fov = 70" in atlas, atlas)
    _assert("skyFovDegrees(stel.core.fov)" in SKY_WEB_VIEW_POLL_JS, "poll degrees")
    _assert("fov: Number(stel.core.fov)" not in SKY_WEB_VIEW_POLL_JS, "poll must not store radians")
    _assert("skyFovRadians" in SKY_WEB_VIEW_APPLY_JS, "apply converts degrees")
    _assert("stel.core.fov = fov" in SKY_WEB_VIEW_APPLY_JS, "engine field is radians")
    home = sky_web_view_script({"ra_hours": 5.0, "dec_degrees": -69.0})
    _assert("70.0" in home or '"fov": 70' in home, home)
    wide = sky_web_view_script({"ra_hours": 5.0, "dec_degrees": -69.0, "fov": 12.5})
    _assert("12.5" in wide, wide)


def test_linux_webengine_stays_in_sky_slot() -> None:
    qml = (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyPage.qml").read_text(encoding="utf-8")
    _assert("nativeMapOverlay" in qml, "native HWND/WKWebView park must stay gated")
    _assert(
        "parent: mapLoader.nativeMapOverlay ? root.contentItem : mapSlot" in qml,
        "Linux WebEngine must stay in the sky slot",
    )
    _assert("if (!mapLoader.nativeMapOverlay)" in qml, "Linux must skip the -4096 park")
    _assert("skyPage.mapLive || skyPage.mapKeepAlive" in qml, "map stays loaded after the first visit")
    _assert("LifecycleState.Active" in (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyWebEngineItem.qml").read_text(encoding="utf-8"), "hidden sky page must not discard Stellarium")


def test_time_now_helper_blocks_stellarium_night_jump() -> None:
    _assert("startTimeIsSet" in SKY_WEB_TIME_NOW_JS, "helper must mark startup time as set")
    _assert("setTimeAfterSunSet" in SKY_WEB_TIME_NOW_JS, "helper must disable sunset jump")
    _assert("date2MJD" in SKY_WEB_TIME_NOW_JS, "helper uses engine MJD conversion")
    _assert("mdi-history" in SKY_WEB_TIME_NOW_JS, "helper clicks Stellarium reset-to-now")
    _assert("clickStellariumNow" in SKY_WEB_TIME_NOW_JS, "helper uses Stellarium now control")
    _assert("[0, 50, 250, 800, 1600]" in SKY_WEB_TIME_NOW_JS, "helper reapplies after Vue nextTick")
    _assert("__astroDwarfSkyTimeNow" in SKY_WEB_TIME_NOW_JS, "clock jumps to now only once per page")
    qml = (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyWebView.qml").read_text(encoding="utf-8")
    _assert(
        "appliedSiteKey !== backend.skyWebSiteScript" in qml.split("onSelectedDeviceChanged")[1],
        "device updates must not reapply the site clock",
    )


APP_PILL = (
    "https://www.stellarium-labs.com/stellarium-mobile-plus/"
    "?utm_source=stellariumweb&utm_medium=topbar"
)


def _host_link(href: str, target: str = "", origin: str = "https://stellarium-web.org", modified: bool = False) -> str:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine

    QCoreApplication.instance() or QCoreApplication([])
    engine = QJSEngine()
    defined = engine.evaluate(SKY_WEB_HOST_LINK_JS)
    _assert(not defined.isError(), defined.toString())
    call = (
        "astroDwarfHostLink("
        + repr(href)
        + ", "
        + repr(target)
        + ", "
        + repr(origin)
        + ", "
        + ("true" if modified else "false")
        + ")"
    )
    result = engine.evaluate(call)
    _assert(not result.isError(), result.toString())
    return str(result.toString())


def test_stellarium_app_link_opens_on_the_host() -> None:
    _assert(_host_link(APP_PILL, "_blank") == APP_PILL, "App pill leaves the embedded view")
    _assert(
        _host_link("https://en.wikipedia.org/wiki/Atria", "_blank") == "https://en.wikipedia.org/wiki/Atria",
        "other new-window links leave too",
    )
    _assert(
        _host_link("mailto:contact@stellarium-labs.com") == "mailto:contact@stellarium-labs.com",
        "mail links leave the embedded view",
    )
    _assert(_host_link("https://stellarium-web.org/skysource/Atria") == "", "same-origin pages stay in the map")
    _assert(
        _host_link("https://stellarium-web.org/skysource/Atria", modified=True)
        == "https://stellarium-web.org/skysource/Atria",
        "a modified click still opens on the host",
    )
    _assert(_host_link("javascript:alert(1)", "_blank") == "", "script links stay closed")
    opened = parse_sky_host_title(
        "astro-dwarf-host:open\thttps%3A%2F%2Fwww.stellarium-labs.com%2Fstellarium-mobile-plus%2F"
        "%3Futm_source%3Dstellariumweb%26utm_medium%3Dtopbar\t10"
    )
    _assert(opened.get("kind") == "open", opened)
    _assert(opened.get("url") == APP_PILL, opened)
    spaced = parse_sky_host_title("astro-dwarf-host:menu 12 34 99")
    _assert(spaced == {"kind": "menu", "x": 12.0, "y": 34.0}, spaced)
    linked = parse_sky_host_title("astro-dwarf-host:link 8 20 https%3A%2F%2Fexample.com%2Fa 5")
    _assert(linked.get("kind") == "link" and linked.get("url") == "https://example.com/a", linked)
    _assert(parse_sky_host_title("astro-dwarf-host:open javascript%3Aalert(1) 1") == {}, "script title")
    _assert(parse_sky_host_title("astro-dwarf-host:open file%3A%2F%2F%2Fsecret 1") == {}, "file title")
    _assert(external_link_url(APP_PILL) == APP_PILL, "labs url")
    _assert(external_link_url("file:///C:/secret") == "", "file url")
    _assert(external_link_filename(APP_PILL) == "stellarium-mobile-plus.html", external_link_filename(APP_PILL))
    _assert(external_link_filename("https://example.com/notes.pdf") == "notes.pdf", "pdf name")
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        target = folder / "saved.html"
        save_external_bytes(target, b"<html>old</html>")
        _assert(target.read_bytes() == b"<html>old</html>", "old payload")
        save_external_bytes(target, b"<html>new</html>")
        _assert(target.read_bytes() == b"<html>new</html>", "new payload")
        _assert(not (folder / "saved.html.part").exists(), "part file is replaced")
    from PySide6.QtQml import QJSEngine

    engine_boot = QJSEngine()
    boot = engine_boot.evaluate(SKY_WEB_BOOT_JS)
    _assert(not boot.isError(), boot.toString())
    _assert(boot.toString() == "error", repr(boot.toString()))
    _assert("installHostLinks" in SKY_WEB_BOOT_JS, "boot installs the host link bridge")
    _assert("astroDwarfHostLink" in SKY_WEB_BOOT_JS, "boot uses the same link rule")
    page = (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyPage.qml").read_text(encoding="utf-8")
    _assert("Open link in new window" in page, "link menu opens on the host")
    _assert("Save link as" in page, "link menu saves")
    _assert("Copy link" in page, "link menu copies")
    engine = (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyWebEngineItem.qml").read_text(encoding="utf-8")
    _assert("backend.openExternalUrl" in engine, "Linux new windows open on the host")
    _assert("popupSink" not in engine, "Linux must not swallow the new window")
    view = (ROOT / "astro_dwarf" / "qml" / "pages" / "SkyWebView.qml").read_text(encoding="utf-8")
    _assert("hostLinkRequested" in view, "Windows title channel opens the host browser")
    _assert("pollHostLink" in view, "a missed title still opens the host browser")


if __name__ == "__main__":
    test_restore_script_drops_time_dependent_pose()
    test_restore_script_looks_at_icrs_at_current_time()
    test_site_script_resets_clock_to_now()
    test_shared_fov_is_degrees_on_both_maps()
    test_linux_webengine_stays_in_sky_slot()
    test_time_now_helper_blocks_stellarium_night_jump()
    test_stellarium_app_link_opens_on_the_host()
    print("ok")
