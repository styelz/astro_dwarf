"""A drop on the top or bottom of the control area opens a full-width row."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QML_DIR = ROOT / "astro_dwarf" / "qml"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _app() -> QGuiApplication:
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    return QGuiApplication(["astro-dwarf-panel-rows"])


PROBE = r"""
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "."
import "components"

Window {
    id: host
    objectName: "panelRowHost"
    width: 1200
    height: 640
    visible: true
    property string report: ""
    property int probeToken: 0
    property string probeAction: ""
    property string probeArg: ""

    Component {
        id: extraColumnShell
        HudSplitView {
            orientation: Qt.Vertical
            autoRestore: false
            SplitView.minimumWidth: 196
            SplitView.preferredWidth: 280
        }
    }

    Component {
        id: extraRowShell
        HudSplitView {
            orientation: Qt.Horizontal
            autoRestore: false
            SplitView.minimumHeight: 120
            SplitView.preferredHeight: 220
            SplitView.fillWidth: true
        }
    }

    Component.onCompleted: {
        PanelSwap.host = rows
        PanelSwap.columnFactory = extraColumnShell
        PanelSwap.rowFactory = extraRowShell
        PanelSwap.registerSplit(rows)
        PanelSwap.registerSplit(columns)
        PanelSwap.registerSplit(leftCol)
        PanelSwap.registerSplit(centerCol)
        Qt.callLater(function() { PanelSwap.captureDefaults() })
    }

    function panelById(id) {
        const list = [panelA, panelB, panelC]
        for (let i = 0; i < list.length; i++) {
            if (list[i].panelId === id)
                return list[i]
        }
        return null
    }

    function dropEdge(id, edge) {
        const panel = panelById(id)
        const y = edge === "bottom" ? rows.height - 4 : 4
        const pt = Qt.point(rows.width / 2, y)
        PanelSwap.begin(panel, pt)
        PanelSwap.finish(pt)
    }

    function dropSide(id, targetId) {
        const panel = panelById(id)
        const target = panelById(targetId)
        const pt = target.mapToItem(rows, 4, target.height / 2)
        PanelSwap.begin(panel, pt)
        PanelSwap.finish(pt)
    }

    function describe() {
        const bands = []
        for (let i = 0; i < rows.count; i++) {
            const item = rows.itemAt(i)
            if (!item)
                continue
            bands.push(item.settingsKey + ":" + Math.round(item.width) + "x" + Math.round(item.height) + (item.visible ? "" : ":hidden"))
        }
        const homes = []
        const ids = ["a", "b", "c"]
        for (let i = 0; i < ids.length; i++) {
            const panel = panelById(ids[i])
            let key = ""
            for (let n = panel; n; n = n.parent) {
                if (n.settingsKey && n !== rows && n !== columns) {
                    key = n.settingsKey
                    break
                }
            }
            const fill = panel.SplitView && panel.SplitView.fillHeight ? ":fill" : ":fit"
            homes.push(ids[i] + ":" + key + fill)
        }
        host.report = bands.join(",") + "|" + homes.join(",")
    }

    onProbeTokenChanged: {
        host.report = "tick " + probeAction
        try {
            if (probeAction === "edge")
                dropEdge(probeArg, probeEdge)
            else if (probeAction === "side")
                dropSide(probeArg, probeEdge)
            else if (probeAction === "reset")
                PanelSwap.resetToDefault()
            Qt.callLater(describe)
        } catch (err) {
            host.report = "err " + err
        }
    }
    property string probeEdge: "top"

    HudSplitView {
        id: rows
        settingsKey: "controlRows"
        autoRestore: false
        anchors.fill: parent
        orientation: Qt.Vertical
        HudSplitView {
            id: columns
            settingsKey: "controlColumns"
            autoRestore: false
            orientation: Qt.Horizontal
            SplitView.fillHeight: true
            SplitView.minimumHeight: 160
            HudSplitView {
                id: leftCol
                settingsKey: "controlLeft"
                autoRestore: false
                orientation: Qt.Vertical
                SplitView.preferredWidth: 400
                SplitView.minimumWidth: 196
                HudPanel { id: panelA; panelId: "a"; title: "ALPHA"; SplitView.preferredHeight: 180; SplitView.minimumHeight: 80 }
                HudPanel { id: panelB; panelId: "b"; title: "BRAVO"; SplitView.preferredHeight: 180; SplitView.minimumHeight: 80 }
            }
            HudSplitView {
                id: centerCol
                settingsKey: "controlCenter"
                autoRestore: false
                orientation: Qt.Vertical
                SplitView.fillWidth: true
                SplitView.minimumWidth: 196
                HudPanel { id: panelC; panelId: "c"; title: "CHARLIE"; SplitView.preferredHeight: 180; SplitView.minimumHeight: 80 }
            }
        }
    }
}
"""


def _run(window: QQuickWindow, action: str, arg: str = "", edge: str = "top") -> str:
    window.setProperty("probeAction", action)
    window.setProperty("probeArg", arg)
    window.setProperty("probeEdge", edge)
    window.setProperty("probeToken", int(window.property("probeToken")) + 1)
    QTest.qWait(80)
    QGuiApplication.processEvents()
    QTest.qWait(80)
    window.metaObject().invokeMethod(window, "describe")
    QGuiApplication.processEvents()
    return str(window.property("report"))


def _band(report: str, key: str) -> str:
    for bit in report.split("|")[0].split(","):
        if bit.startswith(key + ":"):
            return bit
    return ""


def test_edge_drop_opens_full_row(tmp_path: Path | None = None) -> None:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="panel-rows-"))
    app = _app()
    previous_org = app.organizationName()
    previous_name = app.applicationName()
    previous_format = QSettings.defaultFormat()
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app.setOrganizationName("AstroPanelRowOrg")
    app.setApplicationName("AstroPanelRowApp")
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))
    try:
        component = QQmlComponent(engine)
        component.setData(PROBE.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "panel_row_probe.qml")))
        window = component.create()
        errors = [err.toString() for err in component.errors()]
        _assert(component.status() == QQmlComponent.Status.Ready and window is not None,
                "panel row probe failed: " + "; ".join(errors + warnings))
        QQmlEngine.setObjectOwnership(window, QQmlEngine.ObjectOwnership.CppOwnership)
        QTest.qWait(120)
        opened = _run(window, "edge", "c", "top")
        row = _band(opened, "controlRow1")
        _assert(row.startswith("controlRow1:"), opened)
        width = int(row.split(":")[1].split("x")[0])
        _assert(width >= 1100, opened)
        _assert("c:controlRow1Col1:fill" in opened, opened)
        _assert(opened.split("|")[0].startswith("controlRow1:"), opened)
        _assert("a:controlLeft" in opened and "b:controlLeft" in opened, opened)
        shared = _run(window, "side", "b", "c")
        _assert("b:controlRow1Col2:fill" in shared or "b:controlRow1Col1:fill" in shared, shared)
        _assert("c:controlRow1Col1:fill" in shared or "c:controlRow1Col2:fill" in shared, shared)
        _assert("b:controlRow1Col" in shared and "c:controlRow1Col" in shared, shared)
        bKey = [bit for bit in shared.split("|")[1].split(",") if bit.startswith("b:")][0]
        cKey = [bit for bit in shared.split("|")[1].split(",") if bit.startswith("c:")][0]
        _assert(bKey.split(":")[1] != cKey.split(":")[1], shared)
        _assert(_band(shared, "controlRow1").split(":")[1].split("x")[0] >= "1100" or int(_band(shared, "controlRow1").split(":")[1].split("x")[0]) >= 1100, shared)
        bottom = _run(window, "edge", "a", "bottom")
        _assert(_band(bottom, "controlRow2"), bottom)
        _assert("a:controlRow2Col1:fill" in bottom, bottom)
        _assert(bottom.split("|")[0].rstrip(":hidden").endswith("controlRow2") or "controlRow2:" in bottom.split("|")[0].split(",")[-1], bottom)
        reset = _run(window, "reset")
        _assert("controlRow1" not in reset and "controlRow2" not in reset, reset)
        _assert("c:controlCenter" in reset and "b:controlLeft" in reset, reset)
        _assert(reset.split("|")[0].startswith("controlColumns:"), reset)
    finally:
        app.setOrganizationName(previous_org)
        app.setApplicationName(previous_name)
        QSettings.setDefaultFormat(previous_format)


if __name__ == "__main__":
    test_edge_drop_opens_full_row()
    print("ok")
