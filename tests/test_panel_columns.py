"""Control-page panel drops open a real column and a lone panel fills it."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
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
    return QGuiApplication(["astro-dwarf-panel-columns"])


PROBE = r"""
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "."
import "components"

Window {
    id: host
    objectName: "panelColumnHost"
    width: 1200
    height: 640
    visible: true
    property string report: ""
    property int probeToken: 0
    property string probeAction: ""
    property string probeArg: ""
    property int probeSeam: 0

    Component {
        id: extraColumnShell
        HudSplitView {
            orientation: Qt.Vertical
            autoRestore: false
            SplitView.minimumWidth: Theme.px(196)
            SplitView.preferredWidth: Theme.px(280)
        }
    }

    Component.onCompleted: {
        PanelSwap.host = columns
        PanelSwap.columnFactory = extraColumnShell
        PanelSwap.registerSplit(columns)
        PanelSwap.registerSplit(leftCol)
        PanelSwap.registerSplit(centerCol)
        PanelSwap.registerSplit(rightCol)
        Qt.callLater(function() { PanelSwap.captureDefaults() })
    }

    function panelById(id) {
        const list = [panelA, panelB, panelC, panelD]
        for (let i = 0; i < list.length; i++) {
            if (list[i].panelId === id)
                return list[i]
        }
        return null
    }

    function visibleSplits() {
        const out = []
        for (let i = 0; i < columns.count; i++) {
            const item = columns.itemAt(i)
            if (item && item.visible && item.width > 1)
                out.push(item)
        }
        return out
    }

    function seamPoint(seam) {
        const vis = visibleSplits()
        if (!vis.length)
            return Qt.point(0, columns.height / 2)
        let x = vis[0].x
        if (seam <= 0)
            x = vis[0].x + 4
        else if (seam >= vis.length)
            x = vis[vis.length - 1].x + vis[vis.length - 1].width - 4
        else {
            const left = vis[seam - 1]
            const right = vis[seam]
            x = (left.x + left.width + right.x) / 2
        }
        const local = columns.mapToItem(columns, x, columns.height / 2)
        return local
    }

    function dropSeam(id, seam) {
        const panel = panelById(id)
        const pt = seamPoint(seam)
        PanelSwap.begin(panel, pt)
        PanelSwap.finish(pt)
    }

    function dropOn(id, targetId, where) {
        const panel = panelById(id)
        const target = panelById(targetId)
        const local = Qt.point(target.width / 2, target.height / 2)
        if (where === "before")
            local.y = 4
        else if (where === "after")
            local.y = Math.max(0, target.height - 4)
        const pt = target.mapToItem(columns, local.x, local.y)
        PanelSwap.begin(panel, pt)
        PanelSwap.finish(pt)
    }

    function describe() {
        const vis = visibleSplits()
        const keys = []
        for (let i = 0; i < vis.length; i++)
            keys.push(vis[i].settingsKey)
        const homes = []
        const ids = ["a", "b", "c", "d"]
        for (let i = 0; i < ids.length; i++) {
            const panel = panelById(ids[i])
            let key = ""
            for (let n = panel; n; n = n.parent) {
                if (n.settingsKey && n !== columns) {
                    key = n.settingsKey
                    break
                }
            }
            homes.push(ids[i] + ":" + key + (panel.SplitView && panel.SplitView.fillHeight ? ":fill" : ":fit"))
        }
        const all = []
        for (let i = 0; i < columns.count; i++) {
            const item = columns.itemAt(i)
            if (item)
                all.push(item.settingsKey + ":" + Math.round(item.width) + (item.visible ? "" : ":hidden"))
        }
        host.report = keys.join(",") + "|" + homes.join(",") + "|all=" + all.join(",")
    }

    onProbeTokenChanged: {
        host.report = "tick " + probeAction
        try {
            if (probeAction === "seam")
                dropSeam(probeArg, probeSeam)
            else if (probeAction === "on")
                dropOn(probeArg, probeSeamText, probeWhere)
            else if (probeAction === "reset")
                PanelSwap.resetToDefault()
            Qt.callLater(describe)
        } catch (err) {
            host.report = "err " + err
        }
    }
    property string probeSeamText: ""
    property string probeWhere: "swap"

    HudSplitView {
        id: columns
        settingsKey: "controlColumns"
        autoRestore: false
        anchors.fill: parent
        orientation: Qt.Horizontal
        HudSplitView {
            id: leftCol
            settingsKey: "controlLeft"
            autoRestore: false
            orientation: Qt.Vertical
            SplitView.preferredWidth: 320
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
        HudSplitView {
            id: rightCol
            settingsKey: "controlRight"
            autoRestore: false
            orientation: Qt.Vertical
            SplitView.preferredWidth: 320
            SplitView.minimumWidth: 196
            HudPanel { id: panelD; panelId: "d"; title: "DELTA"; SplitView.preferredHeight: 180; SplitView.minimumHeight: 80 }
        }
    }
}
"""


def _width(report: str, key: str) -> int:
    chunk = report.split("all=")[-1]
    for bit in chunk.split(","):
        if bit.startswith(key + ":"):
            return int(bit.split(":")[1])
    return -1


def _run(window: QQuickWindow, action: str, arg: str = "", seam: int = 0, where: str = "swap", target: str = "") -> str:
    window.setProperty("probeAction", action)
    window.setProperty("probeArg", arg)
    window.setProperty("probeSeam", seam)
    window.setProperty("probeWhere", where)
    window.setProperty("probeSeamText", target)
    window.setProperty("probeToken", int(window.property("probeToken")) + 1)
    QTest.qWait(80)
    QGuiApplication.processEvents()
    QTest.qWait(80)
    window.metaObject().invokeMethod(window, "describe")
    QGuiApplication.processEvents()
    return str(window.property("report"))


def test_gutter_drop_opens_column_and_stretches(tmp_path: Path | None = None) -> None:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp(prefix="panel-columns-"))
    app = _app()
    previous_org = app.organizationName()
    previous_name = app.applicationName()
    previous_format = QSettings.defaultFormat()
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app.setOrganizationName("AstroPanelColumnOrg")
    app.setApplicationName("AstroPanelColumnApp")
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))
    try:
        component = QQmlComponent(engine)
        component.setData(PROBE.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "panel_column_probe.qml")))
        window = component.create()
        errors = [err.toString() for err in component.errors()]
        _assert(component.status() == QQmlComponent.Status.Ready and window is not None,
                "panel column probe failed: " + "; ".join(errors + warnings))
        QQmlEngine.setObjectOwnership(window, QQmlEngine.ObjectOwnership.CppOwnership)
        QTest.qWait(120)
        opened = _run(window, "seam", "b", 2)
        _assert(_width(opened, "controlExtra1") >= 196, opened)
        _assert("b:controlExtra1:fill" in opened, opened)
        _assert("a:controlLeft" in opened, opened)
        shared = _run(window, "on", "a", where="before", target="b")
        _assert("a:controlExtra1:fit" in shared, shared)
        _assert("b:controlExtra1:fit" in shared, shared)
        _assert("controlLeft" not in shared.split("|")[0].split(","), shared)
        reset = _run(window, "reset")
        keys = reset.split("|")[0].split(",")
        _assert(keys == ["controlLeft", "controlCenter", "controlRight"], reset)
        _assert("a:controlLeft" in reset and "b:controlLeft" in reset, reset)
        _assert(_width(reset, "controlExtra1") < 0, reset)
    finally:
        app.setOrganizationName(previous_org)
        app.setApplicationName(previous_name)
        QSettings.setDefaultFormat(previous_format)


if __name__ == "__main__":
    test_gutter_drop_opens_column_and_stretches()
    print("ok")
