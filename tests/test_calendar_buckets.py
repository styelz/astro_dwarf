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
    property int hiddenDone: -1
    property int keptPlanned: -1
    property int scopedCount: -1
    property int allScopeCount: -1
    property int noHistoryCount: -1
    property int monthCount: -1
    property int plannedCount: -1
    property string multiOrder: ""
    property int bulkDayCount: -1
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
        root.hiddenDone = day.some(function(item) { return item.id === "h-done" }) ? 1 : 0
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
                observing_date: "2026-09-20", start_epoch_ms: i
            })
        }
        const bulk = Util.calendarDayBuckets(bulkSessions, bulkHistory, true, false, "scope")
        root.bulkDayCount = (bulk["2026-09-20"] || []).length
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
    _assert(int(host.property("dayCount")) == 3, "session rows plus a still-planned history row")
    _assert(str(host.property("dayOrder") or "") == "plan-run,h-plan,done-run", host.property("dayOrder"))
    _assert(int(host.property("hiddenDone")) == 0, "finished session hides its history row")
    _assert(int(host.property("keptPlanned")) == 1, "planned session keeps a separate history row")
    _assert(int(host.property("scopedCount")) == 4, "other telescope stays out of this scope")
    _assert(int(host.property("allScopeCount")) == 2, "all telescopes include the other night")
    _assert(int(host.property("noHistoryCount")) == 4, "history toggle leaves the session rows")
    _assert(int(host.property("monthCount")) == 3, "month count stays on September")
    _assert(int(host.property("plannedCount")) == 2, "planned count ignores history and finished runs")
    _assert(
        str(host.property("multiOrder") or "").startswith("plan-run,"),
        host.property("multiOrder"),
    )
    _assert(int(host.property("bulkDayCount")) == 2000, "finished runs do not add a second history row")
