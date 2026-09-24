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
    source = """
import QtQuick
Item {
    id: root
    property int collapsedCount: -1
    property int expandedCount: -1
    property bool collapsedIsGroup: false
    property string collapsedId: ""
    property string collapsedSummary: ""
    property string groupStatus: ""
    property string groupDuration: ""
    property string expandedFirst: ""
    property string expandedSecond: ""
    property string moveBeforeId: ""
    property bool moveSkip: true
    property string snapBeforeId: ""
    property bool selfSkip: false
    property int groupKeyCount: -1
    property bool expandMapHasGroup: false
    property int expandedKeyN: -1
    property int historyCollapsedCount: -1
    property int historyExpandedCount: -1
    property bool historyCollapsedIsGroup: false
    property string historyOutcome: ""
    property string historySummary: ""
    property string historyFrames: ""
    property string collapsedDeleteIds: ""
    property string expandedDeleteId: ""
    property bool collapsedDeleteEnabled: false
    Component.onCompleted: {
        const items = [
            {
                id: "pane-2", group_key: "lmc|scope", group_id: "lmc", is_grouped: true,
                pane_index: 2, pane_name: "LMC pane 2", status: "planned",
                start_epoch_ms: 2000, end_epoch_ms: 3000, planned_duration_seconds: 100,
                start_date: "2026-09-21", start_time: "20:10", pane_count: 2, grid_text: "2×1"
            },
            {
                id: "pane-1", group_key: "lmc|scope", group_id: "lmc", is_grouped: true,
                pane_index: 1, pane_name: "LMC pane 1", status: "running",
                start_epoch_ms: 1000, end_epoch_ms: 2000, planned_duration_seconds: 100,
                start_date: "2026-09-21", start_time: "20:00", pane_count: 2, grid_text: "2×1"
            },
            {
                id: "solo", group_key: "session:solo", is_grouped: false,
                pane_index: 0, pane_name: "Orion", status: "planned"
            }
        ]
        const collapsed = Util.visibleClusteredSessions(items, {})
        const expanded = Util.visibleClusteredSessions(items, {"lmc|scope": true})
        root.collapsedCount = collapsed.length
        root.expandedCount = expanded.length
        root.collapsedIsGroup = !!(collapsed[0] && collapsed[0].group_collapsed)
        root.collapsedId = String((collapsed[0] && collapsed[0].id) || "")
        root.collapsedSummary = String((collapsed[0] && collapsed[0].group_summary) || "")
        root.groupStatus = String((collapsed[0] && collapsed[0].group_status) || "")
        root.groupDuration = String((collapsed[0] && collapsed[0].group_duration_text) || "")
        root.expandedFirst = String((expanded[0] && expanded[0].pane_name) || "")
        root.expandedSecond = String((expanded[1] && expanded[1].pane_name) || "")
        const planned = [
            {
                id: "pane-1", group_key: "lmc|scope", group_id: "lmc", is_grouped: true,
                pane_index: 1, pane_name: "LMC pane 1", status: "planned", device_id: "scope",
                observing_date: "2026-09-21"
            },
            {
                id: "pane-2", group_key: "lmc|scope", group_id: "lmc", is_grouped: true,
                pane_index: 2, pane_name: "LMC pane 2", status: "planned", device_id: "scope",
                observing_date: "2026-09-21"
            },
            {
                id: "solo", group_key: "session:solo", is_grouped: false,
                pane_name: "Orion", status: "planned", device_id: "scope",
                observing_date: "2026-09-21"
            }
        ]
        const collapsedRows = Util.visibleClusteredSessions(planned, {})
        const moved = Util.reorderBeforeId(collapsedRows, collapsedRows.length, collapsedRows[0])
        root.moveBeforeId = String(moved.beforeId || "")
        root.moveSkip = !!moved.skip
        const expandedRows = Util.visibleClusteredSessions(planned, {"lmc|scope": true})
        const mid = Util.reorderBeforeId(expandedRows, 1, expandedRows[2])
        root.snapBeforeId = String(mid.beforeId || "")
        root.selfSkip = !!Util.reorderBeforeId(expandedRows, 1, expandedRows[0]).skip
        const keys = Util.mosaicGroupKeys(items)
        root.groupKeyCount = keys.length
        root.expandMapHasGroup = !!(Util.mosaicGroupKeyMap(items)["lmc|scope"])
        root.expandedKeyN = Util.expandedKeyCount({"lmc|scope": true}, keys)
        const historyItems = [
            {
                id: "h-2", group_key: "lmc|scope|2026-09-20", group_id: "lmc", is_grouped: true,
                pane_index: 2, target_name: "LMC pane 2", ok: false, outcome: "Failed",
                captured_frames: 4, planned_frames: 10, planned_duration_seconds: 100,
                actual_duration_seconds: 40, date: "2026-09-20", device_id: "scope",
                grid_text: "2×1", group_title: "LMC"
            },
            {
                id: "h-1", group_key: "lmc|scope|2026-09-20", group_id: "lmc", is_grouped: true,
                pane_index: 1, target_name: "LMC pane 1", ok: true, outcome: "Completed",
                captured_frames: 10, planned_frames: 10, planned_duration_seconds: 100,
                actual_duration_seconds: 110, date: "2026-09-20", device_id: "scope",
                grid_text: "2×1", group_title: "LMC"
            },
            {
                id: "h-solo", group_key: "session:h-solo", is_grouped: false,
                target_name: "Orion", ok: true, outcome: "Completed"
            }
        ]
        const histCollapsed = Util.visibleClusteredHistory(historyItems, {})
        const histExpanded = Util.visibleClusteredHistory(historyItems, {"lmc|scope|2026-09-20": true})
        root.historyCollapsedCount = histCollapsed.length
        root.historyExpandedCount = histExpanded.length
        root.historyCollapsedIsGroup = !!(histCollapsed[0] && histCollapsed[0].group_collapsed)
        root.historyOutcome = String((histCollapsed[0] && histCollapsed[0].outcome) || "")
        root.historySummary = String((histCollapsed[0] && histCollapsed[0].group_summary) || "")
        root.historyFrames = String((histCollapsed[0] && histCollapsed[0].frame_text) || "")
        root.collapsedDeleteIds = Util.sessionDeleteIds(collapsed[0]).join(",")
        root.expandedDeleteId = Util.sessionDeleteIds(expanded[0]).join(",")
        root.collapsedDeleteEnabled = Util.sessionDeleteEnabled(collapsed[0])
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "session_groups_probe.qml")))
    item = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(
        component.status() == QQmlComponent.Status.Ready and item is not None,
        "session group probe failed: " + "; ".join(errors),
    )
    app.processEvents()
    return engine, component, item


def test_mosaic_sessions_collapse_by_default() -> None:
    _engine, _component, host = _probe()
    _assert(int(host.property("collapsedCount")) == 2, "collapsed mosaic plus solo")
    _assert(bool(host.property("collapsedIsGroup")), "first visible row is the mosaic")
    _assert(str(host.property("collapsedId") or "") == "pane-1", "pane 1 represents the group")
    _assert(str(host.property("collapsedSummary") or "") == "2 panes · 2×1", host.property("collapsedSummary"))
    _assert(str(host.property("groupStatus") or "") == "running", host.property("groupStatus"))
    _assert(str(host.property("groupDuration") or "") == "0:00:02", host.property("groupDuration"))
    _assert(int(host.property("expandedCount")) == 3, "expanded mosaic shows both panes")
    _assert(str(host.property("expandedFirst") or "") == "LMC pane 1", host.property("expandedFirst"))
    _assert(str(host.property("expandedSecond") or "") == "LMC pane 2", host.property("expandedSecond"))
    _assert(not bool(host.property("moveSkip")), "collapsed mosaic can move to the end")
    _assert(str(host.property("moveBeforeId") or "") == "", host.property("moveBeforeId"))
    _assert(str(host.property("snapBeforeId") or "") == "pane-1", host.property("snapBeforeId"))
    _assert(bool(host.property("selfSkip")), "drop inside own mosaic is a no-op")
    _assert(int(host.property("groupKeyCount")) == 1, "one mosaic group key")
    _assert(bool(host.property("expandMapHasGroup")), "expand-all map includes the mosaic")
    _assert(int(host.property("expandedKeyN")) == 1, "expanded key count")
    _assert(int(host.property("historyCollapsedCount")) == 2, "collapsed mosaic history plus solo")
    _assert(bool(host.property("historyCollapsedIsGroup")), "history mosaic collapses to one row")
    _assert(str(host.property("historyOutcome") or "") == "1/2 completed", host.property("historyOutcome"))
    _assert(str(host.property("historySummary") or "") == "2 panes · 2×1", host.property("historySummary"))
    _assert(str(host.property("historyFrames") or "") == "14/20", host.property("historyFrames"))
    _assert(int(host.property("historyExpandedCount")) == 3, "expanded history shows both panes")
    _assert(str(host.property("collapsedDeleteIds") or "") == "pane-1,pane-2", host.property("collapsedDeleteIds"))
    _assert(str(host.property("expandedDeleteId") or "") == "pane-1", host.property("expandedDeleteId"))
    _assert(bool(host.property("collapsedDeleteEnabled")), "collapsed mosaic can delete the planned pane")


if __name__ == "__main__":
    test_mosaic_sessions_collapse_by_default()
    print("ok")
