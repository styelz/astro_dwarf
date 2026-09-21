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


if __name__ == "__main__":
    test_preview_samples_select_their_colours()
    print("ok")
