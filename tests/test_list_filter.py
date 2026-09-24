from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl
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


def _probe():
    app = _app()
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    source = r"""
import QtQuick
Item {
    id: root
    property string ids: ""
    property string lenses: ""
    property string hay: ""
    Component.onCompleted: {
        const sessions = [
            {id: "m42", target_name: "Orion Nebula", device_name: "DWARF 3", status: "planned", notes: "Ha"},
            {id: "m31", target_name: "Andromeda", device_name: "DWARF II", status: "running", summary: "40 x 30s"},
            {id: "sun", target_name: "Sun", device_name: "DWARF 3", status: "done"}
        ]
        const planned = Util.filterByQueryAndStatus(sessions, "", "planned")
        const dwarf = Util.filterByQueryAndStatus(sessions, "dwarf 3", "")
        const ha = Util.filterByQueryAndStatus(sessions, "ha", "planned")
        const none = Util.filterByQueryAndStatus(sessions, "jupiter", "")
        root.ids = [planned, dwarf, ha, none].map(function(list) {
            return list.map(function(item) { return item.id }).join("+")
        }).join("|")
        const templates = [
            {id: "tele", name: "M42 tele", camera_text: "TELE · 4K · ASTRO", target_name: "Orion"},
            {id: "wide", name: "Milky Way", camera_text: "WIDE · 2K", target_name: "Milky Way"}
        ]
        const tele = Util.filterTemplates(templates, "", "tele")
        const named = Util.filterTemplates(templates, "milky", "wide")
        const missed = Util.filterTemplates(templates, "orion", "wide")
        root.lenses = [tele, named, missed].map(function(list) {
            return list.map(function(item) { return item.id }).join("+")
        }).join("|")
        root.hay = Util.itemMatchesQuery(sessions[1], "40 x 30s") ? "yes" : "no"
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "list_filter_probe.qml")))
    item = component.create()
    if item is None:
        raise RuntimeError(component.errorString())
    app.processEvents()
    return engine, component, item


def test_list_filter_matches_query_and_status() -> None:
    _engine, _component, host = _probe()
    _assert(str(host.property("ids") or "") == "m42|m42+sun|m42|", host.property("ids"))
    _assert(str(host.property("lenses") or "") == "tele|wide|", host.property("lenses"))
    _assert(str(host.property("hay") or "") == "yes", host.property("hay"))
