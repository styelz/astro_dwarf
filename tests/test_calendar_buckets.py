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
    property int dayCount: -1
    property string dayOrder: ""
    property int showsActual: -1
    property int hidesPlannedSlot: -1
    property int keptPlanned: -1
    property int scopedCount: -1
    property int allScopeCount: -1
    property int noHistoryCount: -1
    property int monthCount: -1
    property int plannedCount: -1
    property string multiOrder: ""
    property int bulkDayCount: -1
    property string slipId: ""
    property string slipEpoch: ""
    property int slipHidden: -1
    property string labTimeline: ""
    property string labQueue: ""
    property string labHistory: ""
    Component.onCompleted: {
        const sessions = [
            {id: "done-run", device_id: "scope", observing_date: "2026-09-20", status: "done", start_epoch_ms: 3000},
            {id: "plan-run", device_id: "scope", observing_date: "2026-09-20", status: "planned", start_epoch_ms: 1000},
            {id: "other", device_id: "other", observing_date: "2026-09-21", status: "planned", start_epoch_ms: 1000},
            {id: "later", device_id: "scope", observing_date: "2026-10-01", status: "planned", start_epoch_ms: 1000}
        ]
        const history = [
            {id: "h-done", session_id: "done-run", device_id: "scope", from_history: true, observing_date: "2026-09-20", start_epoch_ms: 3000},
            {id: "h-plan", session_id: "plan-run", device_id: "scope", from_history: true, observing_date: "2026-09-20", start_epoch_ms: 2000},
            {id: "h-blank", session_id: "", device_id: "scope", from_history: true, observing_date: "2026-09-20", start_epoch_ms: 0},
            {id: "h-other", session_id: "missing", device_id: "other", from_history: true, observing_date: "2026-09-21", start_epoch_ms: 1500}
        ]
        const buckets = Util.calendarDayBuckets(sessions, history, true, false, "scope")
        const day = buckets["2026-09-20"] || []
        root.dayCount = day.length
        root.dayOrder = day.map(function(item) { return item.id }).join(",")
        root.showsActual = day.some(function(item) { return item.id === "h-done" }) ? 1 : 0
        root.hidesPlannedSlot = day.some(function(item) { return item.id === "done-run" }) ? 0 : 1
        root.keptPlanned = day.some(function(item) { return item.id === "h-plan" }) ? 1 : 0
        root.scopedCount = Util.calendarBucketCount(buckets, "")
        const all = Util.calendarDayBuckets(sessions, history, true, true, "scope")
        root.allScopeCount = (all["2026-09-21"] || []).length
        const quiet = Util.calendarDayBuckets(sessions, history, false, true, "scope")
        root.noHistoryCount = Util.calendarBucketCount(quiet, "")
        root.monthCount = Util.calendarBucketCount(buckets, "2026-09")
        root.plannedCount = Util.calendarPlannedCount(buckets)
        const span = Util.calendarEntriesForKeys(all, ["2026-09-21", "2026-09-20"])
        root.multiOrder = span.map(function(item) { return item.id }).join(",")
        const bulkSessions = []
        const bulkHistory = []
        for (let i = 0; i < 2000; i++) {
            bulkSessions.push({
                id: "s" + i, device_id: "scope", observing_date: "2026-09-20",
                status: "done", start_epoch_ms: i
            })
            bulkHistory.push({
                id: "h" + i, session_id: "s" + i, device_id: "scope", from_history: true,
                observing_date: "2026-09-20", start_epoch_ms: i + 1
            })
        }
        const bulk = Util.calendarDayBuckets(bulkSessions, bulkHistory, true, false, "scope")
        root.bulkDayCount = (bulk["2026-09-20"] || []).length
        const blocks = [
            {id: "plan-block", device_id: "lab", observing_date: "2026-10-06", status: "planned", start_epoch_ms: 1000},
            {id: "run-block", device_id: "lab", observing_date: "2026-10-06", status: "running", start_epoch_ms: 2000},
            {id: "fin-block", device_id: "lab", observing_date: "2026-10-06", status: "done", start_epoch_ms: 3000},
            {id: "err-block", device_id: "lab", observing_date: "2026-10-06", status: "error", start_epoch_ms: 4000},
            {id: "skip-block", device_id: "lab", observing_date: "2026-10-06", status: "skipped", start_epoch_ms: 5000},
            {id: "slip-session", device_id: "scope", observing_date: "2026-09-22", status: "done", start_epoch_ms: 1000}
        ]
        const blockHistory = [
            {id: "fin-history", session_id: "fin-block", device_id: "lab", from_history: true, observing_date: "2026-10-06", status: "done", start_epoch_ms: 8000, end_epoch_ms: 9500},
            {id: "slip-history", session_id: "slip-session", device_id: "scope", from_history: true, observing_date: "2026-09-22", start_epoch_ms: 9000, end_epoch_ms: 12000}
        ]
        const slipShown = Util.calendarDayBuckets(blocks, blockHistory, true, false, "scope")
        const slipDay = slipShown["2026-09-22"] || []
        root.slipId = slipDay.map(function(item) { return item.id }).join(",")
        root.slipEpoch = slipDay.length ? String(slipDay[0].start_epoch_ms) : ""
        const slipQuiet = Util.calendarDayBuckets(blocks, blockHistory, false, false, "scope")
        root.slipHidden = (slipQuiet["2026-09-22"] || []).length
        const labPlan = Util.calendarDayBuckets(blocks, blockHistory, false, false, "lab")
        root.labTimeline = (labPlan["2026-10-06"] || []).map(function(item) { return item.id }).join(",")
        const labRows = blocks.filter(function(item) { return item.device_id === "lab" })
        root.labQueue = Util.filterSessionQueue(labRows, "", false).map(function(item) { return item.id }).join(",")
        root.labHistory = blockHistory.filter(function(item) { return item.device_id === "lab" }).map(function(item) { return item.session_id }).join(",")
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "calendar_buckets_probe.qml")))
    item = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(
        component.status() == QQmlComponent.Status.Ready and item is not None,
        "calendar bucket probe failed: " + "; ".join(errors),
    )
    app.processEvents()
    return engine, component, item


def test_calendar_buckets_index_each_night_once() -> None:
    _engine, _component, host = _probe()
    _assert(int(host.property("dayCount")) == 3, "plan, kept history, and the actual finished run")
    _assert(str(host.property("dayOrder") or "") == "plan-run,h-plan,h-done", host.property("dayOrder"))
    _assert(int(host.property("showsActual")) == 1, "finished run is drawn from history")
    _assert(int(host.property("hidesPlannedSlot")) == 1, "finished session leaves the planned slot")
    _assert(int(host.property("keptPlanned")) == 1, "planned session keeps a separate history row")
    _assert(int(host.property("scopedCount")) == 4, "other telescope stays out of this scope")
    _assert(int(host.property("allScopeCount")) == 2, "all telescopes include the other night")
    _assert(int(host.property("noHistoryCount")) == 3, "finished sessions leave when history is hidden")
    _assert(int(host.property("monthCount")) == 3, "month count stays on September")
    _assert(int(host.property("plannedCount")) == 2, "planned count ignores history and finished runs")
    _assert(
        str(host.property("multiOrder") or "").startswith("plan-run,"),
        host.property("multiOrder"),
    )
    _assert(int(host.property("bulkDayCount")) == 2000, "finished runs do not add a second history row")
    _assert(str(host.property("slipId") or "") == "slip-history", host.property("slipId"))
    _assert(str(host.property("slipEpoch") or "") == "9000", host.property("slipEpoch"))
    _assert(int(host.property("slipHidden")) == 0, "a finished run stays off the plan")
    _assert(str(host.property("labTimeline") or "") == "plan-block,run-block", host.property("labTimeline"))
    _assert(str(host.property("labQueue") or "") == "plan-block,run-block", host.property("labQueue"))
    _assert(str(host.property("labHistory") or "") == "fin-block", host.property("labHistory"))
