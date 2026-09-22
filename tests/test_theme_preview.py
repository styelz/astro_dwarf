from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML_DIR = ROOT / "astro_dwarf" / "qml"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _app() -> QGuiApplication:
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    return QGuiApplication([])


def _create_preview():
    app = _app()
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    source = """
import QtQuick
import ".."
Item {
    id: root
    property string picked: ""
    property bool successFixed: Theme.roleFixed("success")
    property bool accentFixed: Theme.roleFixed("accent")
    property string okHex: Theme.colorToHex(Theme.colorFor("success"))
    property string okName: Theme.roleName("success")
    property string fovName: Theme.roleName("fov")
    property string fovParent: Theme.parentOf("fov")
    property bool fovFixed: Theme.roleFixed("fov")
    property string fovHex: Theme.colorToHex(Theme.fov)
    property string fovPickerHex: Theme.colorToHex(Qt.hsla(Theme.effectiveHue("fov"), Theme.effectiveSat("fov"), Theme.effectiveLight("fov"), 1))
    readonly property var linkedLook: ({
        hue: 0.08,
        brightness: 0,
        palette: ({ accent: ({ hue: 0.2, brightness: -0.2, sat: 0.2 }) })
    })
    readonly property var ownLook: ({
        hue: 0.08,
        brightness: 0,
        palette: ({
            accent: ({ hue: 0.2, brightness: -0.2, sat: 0.2 }),
            fov: ({ hue: 0.01, brightness: 0, sat: 1 })
        })
    })
    property string linkedFovHex: Theme.colorToHex(Theme.previewColor(linkedLook, "fov"))
    property string linkedAccentHex: Theme.colorToHex(Theme.previewColor(linkedLook, "accent"))
    property string ownFovHex: Theme.colorToHex(Theme.previewColor(ownLook, "fov"))
    property string ownAccentHex: Theme.colorToHex(Theme.previewColor(ownLook, "accent"))
    property real glowAlpha: Theme.previewColor(linkedLook, "glowAccent").a
    width: 980
    height: 90
    ThemePreview {
        objectName: "themePreview"
        anchors.fill: parent
        highlightRole: root.picked
        onRolePicked: function (key) { root.picked = key }
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "components" / "theme_preview_probe.qml")))
    item = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(component.status() == QQmlComponent.Status.Ready and item is not None,
            "ThemePreview failed: " + "; ".join(errors))
    app.processEvents()
    return engine, component, item


def _find(root: QObject, name: str) -> QObject:
    child = root.findChild(QObject, name)
    _assert(child is not None, "missing " + name)
    return child


def _click(obj: QObject) -> None:
    click = getattr(obj, "click", None)
    if callable(click):
        click()
        return
    clicked = getattr(obj, "clicked", None)
    emit = getattr(clicked, "emit", None) if clicked is not None else None
    if callable(emit):
        emit()
        return
    raise AssertionError("cannot click " + obj.objectName())


def test_preview_samples_select_their_colours() -> None:
    engine, _component, host = _create_preview()

    cases = [
        ("previewAction", "surfaceHigh"),
        ("previewLive", "fillActive"),
        ("previewChip", "accent"),
        ("previewField", "inputBg"),
        ("previewOk", "success"),
        ("previewWarn", "warning"),
        ("previewErr", "danger"),
        ("previewFov", "fov"),
    ]
    for name, role in cases:
        _click(_find(host, name))
        picked = str(host.property("picked") or "")
        _assert(picked == role, name + " picked " + repr(picked))

    success_fixed = host.property("successFixed")
    accent_fixed = host.property("accentFixed")
    ok_hex = str(host.property("okHex") or "")
    _assert(success_fixed is True, "success is fixed, got " + repr(success_fixed))
    _assert(accent_fixed is False, "accent is editable, got " + repr(accent_fixed))
    _assert(ok_hex == "#3DFFB0", "OK colour " + ok_hex)
    _assert(str(host.property("okName") or "") == "OK", "OK name " + repr(host.property("okName")))
    _assert(str(host.property("fovName") or "") == "FOV", "FOV name " + repr(host.property("fovName")))
    _assert(str(host.property("fovParent") or "") == "", "FOV parent " + repr(host.property("fovParent")))
    _assert(host.property("fovFixed") is False, "FOV is editable, got " + repr(host.property("fovFixed")))
    _assert(str(host.property("fovHex") or "") == "#02900A", "default FOV " + repr(host.property("fovHex")))
    _assert(str(host.property("fovPickerHex") or "") == str(host.property("fovHex") or ""),
            "picker " + repr(host.property("fovPickerHex")) + " swatch " + repr(host.property("fovHex")))
    linked_fov = str(host.property("linkedFovHex") or "")
    linked_accent = str(host.property("linkedAccentHex") or "")
    _assert(linked_fov == "#02900A", "themed FOV " + linked_fov)
    _assert(linked_accent != linked_fov and linked_accent != "", "accent still tints, " + linked_accent)
    own_fov = str(host.property("ownFovHex") or "")
    own_accent = str(host.property("ownAccentHex") or "")
    _assert(own_fov != "#02900A" and own_fov != "", "custom FOV " + own_fov)
    _assert(own_accent != own_fov and own_accent != "", "custom accent " + own_accent)
    glow_alpha = float(host.property("glowAlpha") or 0)
    _assert(glow_alpha < 0.5, "glow stays translucent, alpha " + repr(glow_alpha))
    for rel in (
        ROOT / "astro_dwarf" / "qml" / "pages" / "SkyWebView.qml",
        ROOT / "astro_dwarf" / "qml" / "pages" / "SkyAtlasView.qml",
        ROOT / "astro_dwarf" / "qml" / "components" / "LiveViewPane.qml",
        ROOT / "astro_dwarf" / "qml" / "components" / "MosaicViewPane.qml",
        ROOT / "astro_dwarf" / "qml" / "pages" / "ControlPage.qml",
    ):
        text = rel.read_text(encoding="utf-8")
        _assert("Theme.fov" in text, rel.name + " does not use the FOV colour")


def _create_theme_update_probe():
    app = _app()
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    source = """
import QtQuick
import ".."
import "../components"
Item {
    id: root
    property bool updateOk: false
    property bool editedBefore: false
    property bool editedAfter: false
    property int iceCount: 0
    property real hueAfter: -1
    property bool revertOk: false
    property bool customRevertOk: true
    property real hueDefault: -1
    property bool iceSaved: true
    property string cyanName: ""
    property real chipWidth: 0
    property real chipTarget: Theme.px(88)
    property string savedSnapshot: ""
    property string namesSnapshot: ""
    property string paletteSnapshot: ""
    property real hueSnapshot: 0
    property real brightSnapshot: 0
    property string activeSnapshot: ""

    function capture() {
        root.savedSnapshot = Theme.savedThemesJson
        root.namesSnapshot = Theme.themeNamesJson
        root.paletteSnapshot = Theme.paletteJson
        root.hueSnapshot = Theme.hue
        root.brightSnapshot = Theme.brightness
        root.activeSnapshot = Theme.activeThemeId
        root.chipWidth = chip.implicitWidth
    }

    function run() {
        Theme.applyTheme("ice")
        Theme.hue = 0.12
        root.editedBefore = Theme.themeEdited
        root.updateOk = Theme.updateTheme("ice")
        root.editedAfter = Theme.themeEdited
        const list = Theme.listedThemes
        let n = 0
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === "ice")
                n++
        }
        root.iceCount = n
        Theme.hue = 0.9
        Theme.applyTheme("ice")
        root.hueAfter = Theme.hue
        root.revertOk = Theme.revertBuiltinTheme("ice")
        root.hueDefault = Theme.hue
        root.iceSaved = Theme.hasSavedCopy("ice")
        root.customRevertOk = Theme.revertBuiltinTheme("custom1")
        const cyan = Theme.themeById("stock")
        root.cyanName = cyan && cyan.name ? String(cyan.name) : ""
    }

    function restore() {
        Theme.savedThemesJson = root.savedSnapshot
        Theme.themeNamesJson = root.namesSnapshot
        Theme.paletteJson = root.paletteSnapshot
        Theme.hue = root.hueSnapshot
        Theme.brightness = root.brightSnapshot
        Theme.activeThemeId = root.activeSnapshot
    }

    ThemePresetChip {
        id: chip
        themeEntry: ({ id: "ice", name: "Ice", hue: 0.55, brightness: 0, palette: ({}) })
    }

    Component.onCompleted: root.capture()
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "components" / "theme_update_probe.qml")))
    item = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(component.status() == QQmlComponent.Status.Ready and item is not None,
            "theme update probe failed: " + "; ".join(errors))
    app.processEvents()
    return engine, component, item


def test_builtin_theme_update_keeps_one_chip() -> None:
    _engine, _component, host = _create_theme_update_probe()
    try:
        host.run()
        page = (QML_DIR / "pages" / "InterfaceSettings.qml").read_text(encoding="utf-8")
        _assert(host.property("editedBefore") is True, "ice edit was not dirty")
        _assert(host.property("updateOk") is True, "updateTheme rejected a built-in")
        _assert(host.property("editedAfter") is False, "updated ice still looks edited")
        _assert(int(host.property("iceCount") or 0) == 1, "ice listed " + str(host.property("iceCount")))
        hue_after = float(host.property("hueAfter") or -1)
        _assert(abs(hue_after - 0.12) < 0.002, "reapply hue " + str(hue_after))
        _assert(host.property("revertOk") is True, "default restore rejected ice")
        hue_default = float(host.property("hueDefault") or -1)
        _assert(abs(hue_default - 0.55) < 0.002, "shipped ice hue " + str(hue_default))
        _assert(host.property("iceSaved") is False, "ice override was kept")
        _assert(host.property("customRevertOk") is False, "custom theme accepted a default restore")
        _assert(str(host.property("cyanName") or "") == "Cyan", "cyan name " + repr(host.property("cyanName")))
        _assert('text: "STOCK"' not in page, "stock button still present")
        _assert('objectName: "themeDefaultButton"' in page, "default button missing")
        chip_width = float(host.property("chipWidth") or 0)
        chip_target = float(host.property("chipTarget") or 0)
        _assert(abs(chip_width - chip_target) < 0.5, "chip width " + str(chip_width) + " target " + str(chip_target))
        _assert('objectName: "themeUpdateButton"' in page, "update button missing")
        _assert("visible: Theme.themeEdited && !!Theme.activeTheme && !iface.naming" in page,
                "update stays hidden while a theme is edited")
    finally:
        host.restore()


if __name__ == "__main__":
    test_preview_samples_select_their_colours()
    test_builtin_theme_update_keeps_one_chip()
    print("ok")
