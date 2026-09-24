from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.services import parse_sky_web_target
from astro_dwarf.sky_atlas import ATLAS_FOV_JS, clean_sky_target_name, parse_atlas_harvest

QML = ROOT / "astro_dwarf" / "qml"
SIMBAD_HELP = "Want to know what is a specific object ?Use the Simbad pointer tool!"


def test_clean_name_rejects_simbad_toolbar_text() -> None:
    assert clean_sky_target_name(SIMBAD_HELP) == ""
    assert clean_sky_target_name(SIMBAD_HELP, "fallback") == "fallback"
    assert clean_sky_target_name("  M 31\nGalaxy  ") == "M 31"
    assert clean_sky_target_name("NGC  7000") == "NGC 7000"


def test_atlas_harvest_drops_tooltip_name() -> None:
    raw = json.dumps({"name": SIMBAD_HELP, "ra_hours": 5.5, "dec_degrees": -5.4})
    parsed = parse_atlas_harvest(raw)
    assert parsed is not None
    assert parsed["name"] == ""


def test_sky_web_target_falls_back_on_tooltip_name() -> None:
    raw = json.dumps({"name": SIMBAD_HELP, "ra_hours": 5.5, "dec_degrees": -5.4})
    assert parse_sky_web_target(raw).name == "Stellarium target"
    raw = json.dumps({"name": "Orion Nebula", "ra_hours": 5.5, "dec_degrees": -5.4})
    assert parse_sky_web_target(raw).name == "Orion Nebula"


def test_atlas_tooltip_name_ignores_toolbar_tooltips() -> None:
    start = ATLAS_FOV_JS.index("function simbadTooltipName()")
    body = ATLAS_FOV_JS[start:ATLAS_FOV_JS.index("function pickedObject", start)]
    assert "querySelectorAll" not in body
    assert "aladin-tooltip-mouse" in body


def test_linux_webengine_suppresses_native_context_menu() -> None:
    for name in ("SkyWebEngineItem.qml", "SkyAtlasEngineItem.qml"):
        text = (QML / "pages" / name).read_text(encoding="utf-8")
        assert "onContextMenuRequested" in text, name
        assert "request.accepted = true" in text, name
        assert "signal hostTitle" in text, name
        assert "onTitleChanged" in text, name
    for name in ("SkyWebNativeItem.qml", "SkyAtlasNativeItem.qml"):
        text = (QML / "pages" / name).read_text(encoding="utf-8")
        assert "signal hostTitle" in text, name
        assert "onTitleChanged" in text, name
    for name in ("SkyWebView.qml", "SkyAtlasView.qml"):
        text = (QML / "pages" / name).read_text(encoding="utf-8")
        assert "astro-dwarf-host:" in text, name
        assert "onHostTitle" in text, name
    menu = (QML / "components" / "SkyContextMenu.qml").read_text(encoding="utf-8")
    assert 'Qt.platform.os === "linux" ? Popup.Item : Popup.Window' in menu
