import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import ".."
import "../components"

Item {
    id: calendarPage
    property date shownMonth: new Date()
    property date selectedDate: new Date()
    property var selectedDayKeys: ({})
    property string selectionAnchorKey: ""
    property int viewMode: 0
    property var selectedIds: ({})
    property string selectionAnchorId: ""
    property int nowLineScrollTries: 0
    Settings {
        id: calendarStore
        category: "calendar"
        property bool showAllDevices: true
    }
    property alias showAllDevices: calendarStore.showAllDevices
    readonly property int selectedCount: Util.idSetCount(selectedIds)
    function selectClick(id, shift, items) {
        const result = Util.clickSelect(selectedIds, items || backend.sessions, id, shift, selectionAnchorId)
        selectedIds = result.map
        selectionAnchorId = result.anchor
    }
    property var contextSession: ({})
    property var contextItems: []
    function openSessionMenu(session, items) {
        contextSession = session || ({})
        contextItems = items || []
        sessionMenu.popup()
    }
    function editItem(item) {
        sessionDialog.openExisting(item)
    }
    Connections {
        target: backend
        function onSessionsChanged() {
            calendarPage.selectedIds = Util.pruneIdSet(calendarPage.selectedIds, backend.sessions)
        }
    }
    function dateKey(value) {
        return value.getFullYear() + "-" + String(value.getMonth() + 1).padStart(2, "0") + "-" + String(value.getDate()).padStart(2, "0")
    }
    function dateFromKey(key) {
        const parts = String(key || "").split("-")
        if (parts.length < 3)
            return new Date()
        return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]), 12, 0, 0)
    }
    function observingNow() {
        return backend.localNow || {}
    }
    function firstCellDate() {
        const first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1)
        const mondayIndex = (first.getDay() + 6) % 7
        return new Date(first.getFullYear(), first.getMonth(), 1 - mondayIndex)
    }
    function shiftMonth(delta) {
        const step = Number(delta) || 0
        if (!step)
            return
        calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() + step, 1)
    }
    function matchesScope(item) {
        return calendarPage.showAllDevices || item.device_id === backend.selectedDeviceId
    }
    function sessionsForDay(key) {
        return backend.sessions.filter(item => item.observing_date === key && calendarPage.matchesScope(item))
    }
    readonly property int selectedDayCount: Util.idSetCount(selectedDayKeys)
    function isDaySelected(key) {
        return Util.idSetHas(calendarPage.selectedDayKeys, key)
    }
    function sortedDayKeys() {
        return Object.keys(calendarPage.selectedDayKeys || {}).sort()
    }
    function setSingleDay(value) {
        const key = typeof value === "string" ? value : calendarPage.dateKey(value)
        const date = calendarPage.dateFromKey(key)
        calendarPage.selectedDate = date
        const next = {}
        next[key] = true
        calendarPage.selectedDayKeys = next
        calendarPage.selectionAnchorKey = key
    }
    function clickDay(value, modifiers) {
        const key = typeof value === "string" ? value : calendarPage.dateKey(value)
        const date = calendarPage.dateFromKey(key)
        const shift = !!(modifiers & Qt.ShiftModifier)
        const ctrl = !!(modifiers & Qt.ControlModifier)
        if (shift) {
            const fromKey = calendarPage.selectionAnchorKey || calendarPage.dateKey(calendarPage.selectedDate)
            const from = calendarPage.dateFromKey(fromKey)
            const lo = from.getTime() <= date.getTime() ? from : date
            const hi = from.getTime() <= date.getTime() ? date : from
            const next = {}
            const cursor = new Date(lo.getFullYear(), lo.getMonth(), lo.getDate(), 12, 0, 0)
            const last = new Date(hi.getFullYear(), hi.getMonth(), hi.getDate(), 12, 0, 0)
            while (cursor.getTime() <= last.getTime()) {
                next[calendarPage.dateKey(cursor)] = true
                cursor.setDate(cursor.getDate() + 1)
            }
            calendarPage.selectedDayKeys = next
            calendarPage.selectedDate = date
            return
        }
        if (ctrl) {
            if (calendarPage.isDaySelected(key)) {
                if (calendarPage.selectedDayCount <= 1)
                    return
                const next = Object.assign({}, calendarPage.selectedDayKeys)
                delete next[key]
                calendarPage.selectedDayKeys = next
                if (calendarPage.dateKey(calendarPage.selectedDate) === key) {
                    const remain = Object.keys(next).sort()
                    calendarPage.selectedDate = calendarPage.dateFromKey(remain[remain.length - 1])
                }
                calendarPage.selectionAnchorKey = calendarPage.dateKey(calendarPage.selectedDate)
                return
            }
            const next = Object.assign({}, calendarPage.selectedDayKeys)
            next[key] = true
            calendarPage.selectedDayKeys = next
            calendarPage.selectedDate = date
            calendarPage.selectionAnchorKey = key
            return
        }
        calendarPage.setSingleDay(date)
    }
    function sessionsForKeys(keys) {
        const set = {}
        const list = keys || []
        for (let i = 0; i < list.length; i++)
            set[list[i]] = true
        const items = backend.sessions.filter(item => set[item.observing_date] && calendarPage.matchesScope(item))
        items.sort((a, b) => {
            const da = String(a.observing_date || "")
            const db = String(b.observing_date || "")
            if (da !== db)
                return da < db ? -1 : 1
            return Number(a.start_epoch_ms || 0) - Number(b.start_epoch_ms || 0)
        })
        return items
    }
    function selectedNightsTitle() {
        const keys = calendarPage.sortedDayKeys()
        if (keys.length <= 1) {
            const one = keys.length === 1 ? calendarPage.dateFromKey(keys[0]) : calendarPage.selectedDate
            return Qt.formatDate(one, "ddd d MMM").toUpperCase()
        }
        const a = calendarPage.dateFromKey(keys[0])
        const b = calendarPage.dateFromKey(keys[keys.length - 1])
        if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear())
            return (a.getDate() + "–" + Qt.formatDate(b, "d MMM")).toUpperCase()
        return (Qt.formatDate(a, "d MMM") + " – " + Qt.formatDate(b, "d MMM")).toUpperCase()
    }
    function sessionWhenText(item) {
        if (calendarPage.selectedDayCount <= 1)
            return item.start_time
        return Qt.formatDate(calendarPage.dateFromKey(item.observing_date), "d MMM") + "  " + item.start_time
    }
    readonly property var nightSessions: {
        const _sessions = backend.sessions
        const _all = calendarPage.showAllDevices
        const _device = backend.selectedDeviceId
        return calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
    }
    readonly property var sidebarSessions: {
        const _sessions = backend.sessions
        const _all = calendarPage.showAllDevices
        const _device = backend.selectedDeviceId
        const _keys = calendarPage.selectedDayKeys
        return calendarPage.sessionsForKeys(Object.keys(_keys || {}))
    }
    readonly property int shownMonthSessionCount: {
        const _sessions = backend.sessions
        const _all = calendarPage.showAllDevices
        const _device = backend.selectedDeviceId
        const prefix = calendarPage.shownMonth.getFullYear() + "-" + String(calendarPage.shownMonth.getMonth() + 1).padStart(2, "0")
        return backend.sessions.filter(item => calendarPage.matchesScope(item) && String(item.observing_date || "").indexOf(prefix) === 0).length
    }
    readonly property var nightLayout: calendarPage.layoutNight(calendarPage.nightSessions)
    function nightDeviceIds(items) {
        const present = {}
        for (let i = 0; i < items.length; i++)
            present[items[i].device_id] = true
        const ids = []
        const devices = backend.devices || []
        for (let i = 0; i < devices.length; i++) {
            const id = devices[i].id
            if (present[id])
                ids.push(id)
        }
        for (let i = 0; i < items.length; i++) {
            const id = items[i].device_id
            if (ids.indexOf(id) < 0)
                ids.push(id)
        }
        return ids
    }
    function sessionSpanSeconds(item) {
        return Math.max(0, Number(item.planned_duration_seconds || 0))
    }
    function sessionEndMs(item) {
        const marked = Number(item.end_epoch_ms || 0)
        if (marked > 0)
            return marked
        return Number(item.start_epoch_ms || 0) + calendarPage.sessionSpanSeconds(item) * 1000
    }
    // Two sessions share lanes only when they genuinely overlap in time; a 500 ms
    // slack keeps back-to-back sessions out of each other's lane.
    function sessionsOverlap(a, b) {
        return a.start < b.end - 500 && b.start < a.end - 500
    }
    // Lane assignment for one cluster of transitively overlapping sessions. Each
    // session then grows rightwards over any lane that stays free for its whole
    // run, so a lone session never renders as a sliver next to a busy stretch.
    function packCluster(cluster, column, columns, layout) {
        const laneEnds = []
        const placed = []
        for (let i = 0; i < cluster.length; i++) {
            const slot = { item: cluster[i], lane: 0, start: Number(cluster[i].start_epoch_ms), end: calendarPage.sessionEndMs(cluster[i]) }
            while (slot.lane < laneEnds.length && slot.start < laneEnds[slot.lane] - 500)
                slot.lane += 1
            if (slot.lane === laneEnds.length)
                laneEnds.push(slot.end)
            else
                laneEnds[slot.lane] = Math.max(laneEnds[slot.lane], slot.end)
            placed.push(slot)
        }
        const lanes = Math.max(1, laneEnds.length)
        for (let i = 0; i < placed.length; i++) {
            let span = 1
            while (placed[i].lane + span < lanes) {
                let free = true
                for (let j = 0; j < placed.length && free; j++) {
                    if (j !== i && placed[j].lane === placed[i].lane + span && calendarPage.sessionsOverlap(placed[i], placed[j]))
                        free = false
                }
                if (!free)
                    break
                span += 1
            }
            layout[placed[i].item.id] = { column: column, columns: columns, lane: placed[i].lane, lanes: lanes, span: span }
        }
    }
    function layoutNight(items) {
        const deviceIds = calendarPage.showAllDevices ? calendarPage.nightDeviceIds(items) : [backend.selectedDeviceId]
        const columns = Math.max(1, deviceIds.length)
        const byDevice = {}
        for (let i = 0; i < items.length; i++) {
            const id = items[i].device_id || backend.selectedDeviceId
            if (!byDevice[id])
                byDevice[id] = []
            byDevice[id].push(items[i])
        }
        const layout = {}
        for (let d = 0; d < deviceIds.length; d++) {
            const group = (byDevice[deviceIds[d]] || []).slice().sort(function(a, b) {
                return Number(a.start_epoch_ms) - Number(b.start_epoch_ms)
            })
            let cluster = []
            let clusterEnd = 0
            for (let i = 0; i < group.length; i++) {
                const start = Number(group[i].start_epoch_ms)
                if (cluster.length && start >= clusterEnd - 500) {
                    calendarPage.packCluster(cluster, d, columns, layout)
                    cluster = []
                    clusterEnd = 0
                }
                cluster.push(group[i])
                clusterEnd = Math.max(clusterEnd, calendarPage.sessionEndMs(group[i]))
            }
            if (cluster.length)
                calendarPage.packCluster(cluster, d, columns, layout)
        }
        return layout
    }
    function timelineSlot(item) {
        const layout = (calendarPage.nightLayout && item && calendarPage.nightLayout[item.id]) || { column: 0, columns: 1, lane: 0, lanes: 1, span: 1 }
        const lanes = Math.max(1, layout.lanes)
        const lane = Math.max(0, Math.min(lanes - 1, layout.lane))
        const span = Math.max(1, Math.min(lanes - lane, layout.span || 1))
        const laneGap = nightTimeline.laneGap
        const laneW = (nightTimeline.columnWidth - laneGap * (lanes - 1)) / lanes
        return {
            x: nightTimeline.columnX(layout.column) + lane * (laneW + laneGap),
            width: Math.max(Theme.px(28), laneW * span + laneGap * (span - 1))
        }
    }
    function deviceConnected(deviceId) {
        const devices = backend.devices || []
        for (let i = 0; i < devices.length; i++) {
            if (devices[i].id === deviceId)
                return !!devices[i].connected
        }
        return false
    }
    function sessionRunEnabled(item) {
        if (!item)
            return false
        if (item.status === "running")
            return !root.sessionStopping(item)
        return calendarPage.deviceConnected(item.device_id)
    }
    function sessionActualSeconds(item) {
        backend.clockText
        if (!item)
            return 0
        if (String(item.status || "") === "running" && item.actual_started_at) {
            const started = Date.parse(item.actual_started_at)
            const now = Number(calendarPage.observingNow().epoch_ms || 0)
            if (started && now)
                return Math.max(0, (now - started) / 1000)
        }
        return Number(item.actual_duration_seconds || 0)
    }
    function deviceName(deviceId) {
        const devices = backend.devices || []
        for (let i = 0; i < devices.length; i++) {
            if (devices[i].id === deviceId)
                return devices[i].name
        }
        return "Unknown"
    }
    function deviceColor(deviceId) {
        const devices = backend.devices || []
        for (let i = 0; i < devices.length; i++) {
            if (devices[i].id === deviceId)
                return devices[i].color
        }
        return Theme.accent
    }
    function chipText(item) {
        return item.start_time + "  " + (item.pane_index < 1000000 ? "pane " + item.pane_index : item.target_name)
    }
    function sessionLabel(item) {
        return item.pane_name || item.target_name || ""
    }
    function sessionDetail(item, extra) {
        const bits = []
        if (item.is_grouped && item.group_title)
            bits.push(item.group_title)
        if (extra)
            bits.push(extra)
        return bits.join("  ·  ")
    }
    readonly property int cutoffHour: backend.observingDayCutoffHour
    readonly property real nightOriginMs: {
        const _id = backend.selectedDeviceId
        const _cutoff = calendarPage.cutoffHour
        const _tz = backend.selectedDevice.timezone_name
        return Number(backend.nightStartEpochMs(calendarPage.nightKey()))
    }
    function nightKey() {
        return calendarPage.dateKey(calendarPage.selectedDate)
    }
    function nightStartMs(key, deviceId) {
        const day = key || calendarPage.nightKey()
        if (deviceId)
            return Number(backend.nightStartEpochMs(day, deviceId))
        if (!key || day === calendarPage.nightKey())
            return calendarPage.nightOriginMs
        return Number(backend.nightStartEpochMs(day))
    }
    function timelineMinutes(timeText) {
        const bits = String(timeText || "00:00").split(":")
        let minutes = Number(bits[0]) * 60 + Number(bits[1]) - cutoffHour * 60
        if (minutes < 0)
            minutes += 1440
        return minutes
    }
    function timelineMinutesFromEpoch(epochMs, key, deviceId) {
        const start = calendarPage.nightStartMs(key, deviceId)
        if (!start)
            return 0
        return (Number(epochMs) - start) / 60000
    }
    function timelineSnapStep() {
        if (calendarPage.viewMode !== 1 || !nightTimeline.visible)
            return 5
        // Once a minute is several pixels tall, 5-minute snap is a visible jump.
        if (nightTimeline.hourHeight / 60 >= 8)
            return 1
        return Math.max(1, Math.min(5, nightTimeline.tickMinutes))
    }
    function snapTimelineMinutes(minutes) {
        const step = calendarPage.timelineSnapStep()
        const maxStart = 1440 - step
        return Math.max(0, Math.min(maxStart, Math.round(Number(minutes) / step) * step))
    }
    function timelineClock(minutes) {
        const snapped = calendarPage.snapTimelineMinutes(minutes)
        const hour = (cutoffHour + Math.floor(snapped / 60)) % 24
        const minute = snapped % 60
        return String(hour).padStart(2, "0") + ":" + String(minute).padStart(2, "0")
    }
    function timelineMinutesFromPos(pos) {
        if (root.currentPage !== 1 || calendarPage.viewMode !== 1 || !nightTimeline.visible)
            return -1
        const local = timelineTrack.mapFromItem(DragCoordinator.contentItem, pos.x, pos.y)
        if (local.x < 0 || local.x > timelineTrack.width)
            return -1
        return calendarPage.snapTimelineMinutes((local.y - DragCoordinator.grabOffsetY - nightTimeline.itemOffset) / nightTimeline.hourHeight * 60)
    }
    function timelineDate(minutes, deviceId) {
        return backend.nightTimelineIso(calendarPage.nightKey(), calendarPage.snapTimelineMinutes(minutes), deviceId || "")
    }
    function applySessionDrop(sid, source, position) {
        if (!sid || !position || !DragCoordinator.contentItem)
            return false
        if (calendarPage.viewMode === 1) {
            const minutes = calendarPage.timelineMinutesFromPos(position)
            if (minutes < 0)
                return false
            backend.moveSessionStart(sid, calendarPage.timelineDate(minutes, source && source.device_id))
            return true
        }
        if (!monthDays)
            return false
        for (let i = 0; i < monthDays.count; i++) {
            const cell = monthDays.itemAt(i)
            if (!cell || cell.width <= 0 || cell.height <= 0)
                continue
            const local = cell.mapFromItem(DragCoordinator.contentItem, position.x, position.y)
            if (local.x < 0 || local.y < 0 || local.x > cell.width || local.y > cell.height)
                continue
            backend.moveSessionDate(sid, cell.key)
            calendarPage.setSingleDay(cell.cellDate)
            return true
        }
        return false
    }
    function currentObservingKey() {
        return String(calendarPage.observingNow().observing_date || calendarPage.dateKey(new Date()))
    }
    function openNight(value) {
        calendarPage.setSingleDay(value)
        viewMode = 1
        requestNowLineScroll()
    }
    function nightBarZ(item) {
        if (!item)
            return 1
        if (item.is_grouped) {
            const count = Math.max(1, Number(item.pane_count) || 1)
            const pane = Number(item.pane_index)
            const idx = (pane > 0 && pane < 1000000) ? pane : 1
            return Math.max(1, Math.min(18, 1 + (count - idx)))
        }
        const items = calendarPage.nightSessions
        let later = 0
        const start = Number(item.start_epoch_ms)
        const id = String(item.id || "")
        for (let i = 0; i < items.length; i++) {
            const other = items[i]
            const otherStart = Number(other.start_epoch_ms)
            if (otherStart > start || (otherStart === start && String(other.id || "") > id))
                later += 1
        }
        return Math.max(1, Math.min(18, 1 + later))
    }
    function nightSessionAtScene(scene) {
        if (!nightSessionRepeater || !scene)
            return null
        for (let i = 0; i < nightSessionRepeater.count; i++) {
            const bar = nightSessionRepeater.itemAt(i)
            if (!bar)
                continue
            const local = bar.mapFromItem(null, scene.x, scene.y)
            if (local.x >= 0 && local.y >= 0 && local.x < bar.width && local.y < bar.height)
                return bar.modelData
        }
        return null
    }
    function hoverMinutesFromY(y) {
        return calendarPage.snapTimelineMinutes(Number(y) / nightTimeline.hourHeight * 60)
    }
    function createSessionAtMinutes(minutes) {
        sessionDialog.openForDate(calendarPage.nightKey(), calendarPage.snapTimelineMinutes(minutes))
    }
    function fitNightZoom() {
        nightTimeline.zoomLocked = false
        nightTimeline.autoFit()
        calendarPage.requestNowLineScroll()
    }
    function requestNowLineScroll() {
        nowLineScrollTries = 0
        nowLineScrollTimer.restart()
    }
    function scrollNowLineIntoView() {
        if (calendarPage.viewMode !== 1 || !nightTimeline.visible)
            return
        const viewH = timelineFlick.height
        if (viewH <= 1) {
            if (nowLineScrollTries < 8) {
                nowLineScrollTries += 1
                nowLineScrollTimer.restart()
            }
            return
        }
        nowLineScrollTries = 0
        nightTimeline.autoFit()
        const maxY = Math.max(0, timelineFlick.contentHeight - viewH)
        // Centre on the now line tonight, otherwise park the first session near the top.
        let target = -1
        if (calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey())
            target = nowLine.y - viewH / 2 + nowLine.height / 2
        else if (calendarPage.nightSessions.length)
            target = nightTimeline.firstSessionMinutes() / 60 * nightTimeline.hourHeight - viewH * 0.2
        if (target < 0 && !calendarPage.nightSessions.length)
            return
        timelineFlick.contentY = Math.max(0, Math.min(maxY, target))
    }
    Timer {
        id: nowLineScrollTimer
        interval: 16
        repeat: false
        onTriggered: calendarPage.scrollNowLineIntoView()
    }
    // Refit and re-centre only when the night itself changes; a routine session
    // refresh must never yank the timeline out from under the user.
    onSelectedDateChanged: {
        nightTimeline.zoomLocked = false
        calendarPage.requestNowLineScroll()
    }
    Component.onCompleted: {
        const today = calendarPage.dateFromKey(calendarPage.currentObservingKey())
        calendarPage.setSingleDay(today)
        shownMonth = today
    }
    HudSplitView {
        id: calendarSplit
        settingsKey: "calendarSplit"
        anchors.fill: parent
        orientation: Qt.Horizontal
        ColumnLayout {
            SplitView.fillWidth: true
            SplitView.minimumWidth: Theme.px(420)
            spacing: Theme.px(10)
            PageHeader {
                id: calendarHeader
                readonly property bool tight: width < Theme.px(860)
                title: calendarPage.viewMode === 0
                    ? Qt.formatDate(calendarPage.shownMonth, "MMMM yyyy").toUpperCase()
                    : Qt.formatDate(calendarPage.selectedDate, "dddd d MMMM").toUpperCase()
                subtitle: {
                    const planned = backend.sessions.filter(item => item.status === "planned" && calendarPage.matchesScope(item)).length
                    const nightCount = calendarPage.viewMode === 0 ? calendarPage.sidebarSessions.length : calendarPage.nightSessions.length
                    const nightLabel = calendarPage.viewMode === 0 && calendarPage.selectedDayCount > 1 ? "on selected nights" : "on the selected night"
                    const scope = calendarPage.showAllDevices ? "all telescopes" : (backend.selectedDevice.name || "this telescope")
                    return planned + " planned session" + (planned === 1 ? "" : "s") + "  ·  " + nightCount + " " + nightLabel + "  ·  " + scope + "  ·  night rolls over at " + String(calendarPage.cutoffHour).padStart(2, "0") + ":00  ·  " + (backend.selectedDevice.timezone_name || "UTC")
                }
                HudButton { text: "MONTH"; buttonColor: calendarPage.viewMode === 0 ? Theme.fillActive : Theme.surfaceHigh; foregroundColor: calendarPage.viewMode === 0 ? Theme.accent : Theme.textSecondary; onClicked: calendarPage.viewMode = 0 }
                HudButton { text: "NIGHT"; buttonColor: calendarPage.viewMode === 1 ? Theme.fillActive : Theme.surfaceHigh; foregroundColor: calendarPage.viewMode === 1 ? Theme.accent : Theme.textSecondary; onClicked: calendarPage.openNight(calendarPage.selectedDate) }
                HudButton {
                    visible: (backend.devices || []).length > 1
                    text: calendarHeader.tight ? "ALL" : "ALL DEVICES"
                    Accessible.name: "All devices"
                    buttonColor: calendarPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                    foregroundColor: calendarPage.showAllDevices ? Theme.accent : Theme.textSecondary
                    onClicked: calendarPage.showAllDevices = true
                }
                HudButton {
                    visible: (backend.devices || []).length > 1
                    text: calendarHeader.tight ? "THIS" : "THIS DEVICE"
                    Accessible.name: "This device"
                    buttonColor: !calendarPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                    foregroundColor: !calendarPage.showAllDevices ? Theme.accent : Theme.textSecondary
                    onClicked: calendarPage.showAllDevices = false
                }
                HudButton {
                    text: "‹"; implicitWidth: Theme.px(40)
                    Accessible.name: calendarPage.viewMode === 0 ? "Previous month" : "Previous night"
                    onClicked: {
                        if (calendarPage.viewMode === 0)
                            calendarPage.shiftMonth(-1)
                        else {
                            const value = new Date(calendarPage.selectedDate)
                            value.setDate(value.getDate() - 1)
                            calendarPage.setSingleDay(value)
                        }
                    }
                }
                HudButton { text: "TODAY"; onClicked: {
                    const today = calendarPage.dateFromKey(calendarPage.currentObservingKey())
                    calendarPage.shownMonth = today
                    calendarPage.setSingleDay(today)
                    calendarPage.requestNowLineScroll()
                } }
                HudButton {
                    text: "›"; implicitWidth: Theme.px(40)
                    Accessible.name: calendarPage.viewMode === 0 ? "Next month" : "Next night"
                    onClicked: {
                        if (calendarPage.viewMode === 0)
                            calendarPage.shiftMonth(1)
                        else {
                            const value = new Date(calendarPage.selectedDate)
                            value.setDate(value.getDate() + 1)
                            calendarPage.setSingleDay(value)
                        }
                    }
                }
                HudButton {
                    text: calendarHeader.tight ? "+ NEW" : "+ NEW SESSION"
                    Accessible.name: "New session"
                    busyText: "OPENING…"
                    buttonColor: Theme.fillActive
                    foregroundColor: Theme.accent
                    onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate))
                }
            }
            SelectionBar {
                active: calendarPage.viewMode === 1
                selectedCount: calendarPage.nightSessions.filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).length
                totalCount: calendarPage.nightSessions.length
                noun: "session"
                allowMove: true
                sessionIds: calendarPage.nightSessions.filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).map(item => item.id)
                onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(calendarPage.nightSessions, true)
                onClearRequested: calendarPage.selectedIds = ({})
                onEditRequested: sessionDialog.openSelected(Util.itemsByIds(calendarPage.nightSessions, calendarPage.selectedIds))
                onDeleteRequested: {
                    const chosen = {}
                    const items = calendarPage.nightSessions
                    for (let i = 0; i < items.length; i++) {
                        const id = items[i] && items[i].id
                        if (id && Util.idSetHas(calendarPage.selectedIds, id))
                            chosen[id] = true
                    }
                    root.confirmBulkDelete("deleteSessions", chosen, "session")
                }
            }
            Text {
                readonly property bool monthEmpty: calendarPage.viewMode === 0 && calendarPage.shownMonthSessionCount === 0
                readonly property bool nightEmpty: calendarPage.viewMode === 1 && calendarPage.nightSessions.length === 0
                visible: monthEmpty || nightEmpty
                Layout.fillWidth: true
                color: Theme.muted
                font.pixelSize: Theme.fontSm
                font.letterSpacing: 0.4
                wrapMode: Text.NoWrap
                elide: Text.ElideRight
                text: {
                    if (monthEmpty)
                        return calendarPage.showAllDevices
                            ? "Nothing scheduled this month. Drop a session onto a night, or create a new one."
                            : "Nothing scheduled on this telescope this month."
                    return calendarPage.showAllDevices
                        ? "Nothing scheduled for this night. Drop a session onto the timeline, or create a new one."
                        : "Nothing scheduled on this telescope for this night."
                }
                Accessible.name: text
            }
            Item {
                id: monthPane
                visible: calendarPage.viewMode === 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                property real wheelAccum: 0
                function applyWheel(event) {
                    const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
                    if (!delta)
                        return
                    event.accepted = true
                    if (monthWheelCool.running)
                        return
                    monthPane.wheelAccum += delta
                    if (Math.abs(monthPane.wheelAccum) < 60)
                        return
                    calendarPage.shiftMonth(monthPane.wheelAccum > 0 ? -1 : 1)
                    monthPane.wheelAccum = 0
                    monthWheelCool.restart()
                }
                Timer {
                    id: monthWheelCool
                    interval: 90
                    repeat: false
                }
                WheelHandler {
                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                    acceptedModifiers: Qt.NoModifier
                    blocking: true
                    onWheel: event => monthPane.applyWheel(event)
                }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(10)
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater { model: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]; Text { required property string modelData; text: modelData; color: Theme.accent; font.pixelSize: Theme.fontSm; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } }
                    }
                    GridLayout {
                        id: monthGrid
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        columns: 7
                        rows: 6
                        rowSpacing: Theme.px(5)
                        columnSpacing: Theme.px(5)
                    Repeater {
                        id: monthDays
                        model: 42
                        delegate: Rectangle {
                            id: dayCell
                            objectName: "calendar-day-" + dayCell.key
                            required property int index
                            property date cellDate: {
                                calendarPage.shownMonth
                                const value = calendarPage.firstCellDate()
                                value.setDate(value.getDate() + index)
                                return value
                            }
                            property string key: calendarPage.dateKey(cellDate)
                            property var daySessions: {
                                const _sessions = backend.sessions
                                const _all = calendarPage.showAllDevices
                                const _device = backend.selectedDeviceId
                                return calendarPage.sessionsForDay(dayCell.key)
                            }
                            readonly property bool isToday: key === calendarPage.currentObservingKey()
                            readonly property bool isSelected: calendarPage.isDaySelected(key)
                            readonly property bool inMonth: cellDate.getMonth() === calendarPage.shownMonth.getMonth()
                            readonly property int chipLimit: {
                                const inner = Math.max(0, height - Theme.s3)
                                const dateH = Theme.fontSm + Theme.px(6)
                                const moreH = Theme.fontXs + Theme.px(4)
                                const chipH = Theme.px(22) + Theme.px(3)
                                let room = inner - dateH
                                if (dayCell.daySessions.length <= 0)
                                    return 0
                                let n = Math.floor(room / chipH)
                                if (dayCell.daySessions.length > n)
                                    n = Math.floor((room - moreH) / chipH)
                                return Math.max(0, n)
                            }
                            readonly property color otherMonthFill: Qt.hsla(Theme.panelFill.hslHue, Theme.panelFill.hslSaturation * 0.35, Theme.panelFill.hslLightness, Theme.panelFill.a)
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            radius: Theme.radius
                            clip: true
                            color: isSelected ? Theme.fillChecked : cellHover.hovered ? Theme.surfaceHigh : inMonth ? Theme.panelFill : otherMonthFill
                            border.color: dayCell.activeFocus || dropArea.containsDrag ? Theme.accent : isSelected ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) : Theme.outline
                            border.width: dayCell.activeFocus ? Theme.px(2) : Theme.px(1)
                            Behavior on color { ColorAnimation { duration: Theme.quick } }
                            HoverHandler { id: cellHover }
                            WheelHandler {
                                acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                acceptedModifiers: Qt.NoModifier
                                blocking: true
                                onWheel: event => monthPane.applyWheel(event)
                            }
                            activeFocusOnTab: true
                            Accessible.role: Accessible.Button
                            Accessible.name: {
                                const n = dayCell.daySessions.length
                                const label = Qt.formatDate(dayCell.cellDate, "dddd d MMMM")
                                const extra = dayCell.isToday ? ", tonight" : ""
                                if (!n)
                                    return label + extra + ", no sessions"
                                return label + extra + ", " + n + (n === 1 ? " session" : " sessions")
                            }
                            Keys.onReturnPressed: calendarPage.openNight(dayCell.cellDate)
                            Keys.onSpacePressed: calendarPage.clickDay(dayCell.cellDate, Qt.NoModifier)
                            Keys.onLeftPressed: if (index % 7 > 0) { const n = monthDays.itemAt(index - 1); if (n) n.forceActiveFocus() }
                            Keys.onRightPressed: if (index % 7 < 6) { const n = monthDays.itemAt(index + 1); if (n) n.forceActiveFocus() }
                            Keys.onUpPressed: if (index >= 7) { const n = monthDays.itemAt(index - 7); if (n) n.forceActiveFocus() }
                            Keys.onDownPressed: if (index < 35) { const n = monthDays.itemAt(index + 7); if (n) n.forceActiveFocus() }
                            Rectangle {
                                // animated accent ring on tonight's cell
                                anchors.fill: parent
                                anchors.margins: Theme.px(2)
                                radius: Theme.radius
                                color: "transparent"
                                border.color: Theme.accent
                                border.width: 1
                                visible: dayCell.isToday
                                opacity: 0.6
                                SequentialAnimation on opacity {
                                    running: dayCell.isToday && calendarPage.visible && calendarPage.viewMode === 0
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.15; duration: Theme.slow * 5; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 0.8; duration: Theme.slow * 5; easing.type: Easing.InOutSine }
                                }
                            }
                            Text {
                                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(5)
                                visible: dayCell.isToday
                                text: "TONIGHT"
                                color: Theme.accent
                                font.pixelSize: Theme.fontXs; font.bold: true; font.letterSpacing: 1
                            }
                            DropArea {
                                id: dropArea
                                anchors.fill: parent
                                keys: ["session"]
                                onDropped: drop => {
                                    const sid = DragCoordinator.dragSessionId(drop)
                                    if (!sid)
                                        return
                                    backend.moveSessionDate(sid, dayCell.key)
                                    calendarPage.setSingleDay(dayCell.cellDate)
                                }
                            }
                            Column {
                                anchors.fill: parent
                                anchors.margins: Theme.px(6)
                                spacing: Theme.px(3)
                                Text { text: dayCell.cellDate.getDate(); color: dayCell.isToday ? Theme.accent : dayCell.inMonth ? Theme.textPrimary : Theme.muted; font.pixelSize: Theme.fontSm; font.bold: dayCell.isToday; font.family: Theme.fontMono }
                                Repeater {
                                    id: chipRepeater
                                    model: dayCell.daySessions.slice(0, dayCell.chipLimit)
                                    delegate: Rectangle {
                                        id: sessionChip
                                        objectName: "calendar-session-" + modelData.id
                                        required property var modelData
                                        property string sessionId: modelData.id
                                        readonly property color deviceTone: Util.sessionTone(modelData)
                                        width: parent.width
                                        height: Theme.px(22)
                                        radius: Theme.px(2)
                                        color: Util.statusFill(modelData.status)
                                        border.color: Qt.rgba(Util.statusColor(modelData.status).r, Util.statusColor(modelData.status).g, Util.statusColor(modelData.status).b, 0.55)
                                        opacity: DragCoordinator.active && Util.sameSessionGroup(DragCoordinator.data, modelData) ? 0.35 : 1
                                        Accessible.name: calendarPage.chipText(modelData)
                                        Rectangle { x: Theme.px(1); y: Theme.px(1); width: Theme.px(3); height: parent.height - Theme.px(2); radius: Theme.px(1); color: sessionChip.deviceTone }
                                        Rectangle {
                                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(3)
                                            width: Theme.px(5); height: Theme.px(5); radius: 2.5
                                            color: Util.statusColor(modelData.status)
                                            visible: String(modelData.status) !== "planned"
                                        }
                                        Text { anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: Theme.px(10); anchors.topMargin: Theme.s1; anchors.bottomMargin: Theme.s1; text: calendarPage.chipText(modelData); color: Theme.textPrimary; font.pixelSize: Theme.fontXs; elide: Text.ElideRight }
                                        SessionDragArea {
                                            dragItem: sessionChip.modelData
                                            editOnDoubleTap: false
                                            pressedAction: function() { calendarPage.setSingleDay(dayCell.cellDate) }
                                        }
                                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: calendarPage.openSessionMenu(sessionChip.modelData, dayCell.daySessions) }
                                    }
                                }
                                Text {
                                    visible: dayCell.daySessions.length > dayCell.chipLimit
                                    text: dayCell.chipLimit > 0
                                          ? "+" + (dayCell.daySessions.length - dayCell.chipLimit) + " more"
                                          : dayCell.daySessions.length + (dayCell.daySessions.length === 1 ? " session" : " sessions")
                                    color: Theme.accent
                                    font.pixelSize: Theme.fontXs
                                    elide: Text.ElideRight
                                    width: parent.width
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: (mouse) => calendarPage.clickDay(dayCell.cellDate, mouse.modifiers)
                                        onDoubleClicked: calendarPage.openNight(dayCell.cellDate)
                                    }
                                }
                            }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.NoModifier
                                onTapped: calendarPage.clickDay(dayCell.cellDate, Qt.NoModifier)
                                onDoubleTapped: calendarPage.openNight(dayCell.cellDate)
                            }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ShiftModifier
                                onTapped: calendarPage.clickDay(dayCell.cellDate, Qt.ShiftModifier)
                            }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ControlModifier
                                onTapped: calendarPage.clickDay(dayCell.cellDate, Qt.ControlModifier)
                            }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.MetaModifier
                                onTapped: calendarPage.clickDay(dayCell.cellDate, Qt.ControlModifier)
                            }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ShiftModifier | Qt.ControlModifier
                                onTapped: calendarPage.clickDay(dayCell.cellDate, Qt.ShiftModifier)
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: dayMenu.popup()
                            }
                            HudMenu {
                                id: dayMenu
                                HudMenuItem {
                                    text: "New session on this date"
                                    glyph: "\uE710"
                                    onTriggered: {
                                        calendarPage.selectedDate = dayCell.cellDate
                                        if (!calendarPage.isDaySelected(dayCell.key)) {
                                            const next = Object.assign({}, calendarPage.selectedDayKeys)
                                            next[dayCell.key] = true
                                            calendarPage.selectedDayKeys = next
                                        }
                                        sessionDialog.openForDate(dayCell.key)
                                    }
                                }
                                HudMenuSeparator {}
                                HudMenuItem {
                                    text: "Select all"
                                    glyph: "\uE8A5"
                                    enabled: dayCell.daySessions.length > 0
                                    onTriggered: calendarPage.selectedIds = Util.idSetAll(dayCell.daySessions, true)
                                }
                                HudMenuItem {
                                    text: "Unselect all"
                                    glyph: "\uE711"
                                    enabled: calendarPage.selectedCount > 0
                                    onTriggered: {
                                        calendarPage.selectedIds = ({})
                                        calendarPage.selectionAnchorId = ""
                                    }
                                }
                            }
                        }
                    }
                    }
                }
            }
            Item {
                id: nightTimeline
                visible: calendarPage.viewMode === 1
                Layout.fillWidth: true
                Layout.fillHeight: true
                property real hourHeight: Theme.px(64)
                property real itemOffset: Theme.px(5)
                // A whole night at a fixed scale leaves an hour of sessions squeezed into
                // a sliver of a very tall, empty track, so the scale follows the content
                // until the user zooms with Ctrl+wheel.
                property real hoverMinutes: -1
                property bool zoomLocked: false
                readonly property real minHourHeight: Theme.px(32)
                readonly property real maxHourHeight: Theme.px(2880)
                readonly property real autoFitMinHourHeight: Theme.px(56)
                readonly property real autoFitMaxHourHeight: Theme.px(220)
                readonly property real trackHeight: 24 * hourHeight + 24
                // Hour fraction under the cursor, kept on screen across the
                // Flickable contentHeight update that follows a scale change.
                property real zoomAnchorHour: -1
                property real zoomAnchorOffset: 0
                readonly property int tickMinutes: {
                    const ppm = hourHeight / 60
                    if (ppm >= 12)
                        return 1
                    if (ppm >= 3.5)
                        return 5
                    if (ppm >= 1.6)
                        return 15
                    if (ppm >= 0.85)
                        return 30
                    return 60
                }
                function firstSessionMinutes() {
                    const items = calendarPage.nightSessions
                    let lo = 1440
                    for (let i = 0; i < items.length; i++)
                        lo = Math.min(lo, calendarPage.timelineMinutesFromEpoch(items[i].start_epoch_ms, calendarPage.nightKey(), items[i].device_id))
                    return Math.max(0, Math.min(1440, lo))
                }
                function autoFit() {
                    const items = calendarPage.nightSessions
                    if (nightTimeline.zoomLocked || timelineFlick.height < Theme.px(80))
                        return
                    if (!items.length) {
                        nightTimeline.hourHeight = Theme.px(64)
                        return
                    }
                    let lo = 1440
                    let hi = 0
                    for (let i = 0; i < items.length; i++) {
                        lo = Math.min(lo, calendarPage.timelineMinutesFromEpoch(items[i].start_epoch_ms, calendarPage.nightKey(), items[i].device_id))
                        hi = Math.max(hi, calendarPage.timelineMinutesFromEpoch(calendarPage.sessionEndMs(items[i]), calendarPage.nightKey(), items[i].device_id))
                    }
                    const hours = Math.max(1, (Math.min(1440, hi) - Math.max(0, lo)) / 60) + 1
                    nightTimeline.hourHeight = Math.max(nightTimeline.autoFitMinHourHeight, Math.min(nightTimeline.autoFitMaxHourHeight, timelineFlick.height / hours))
                }
                function applyAnchoredScroll() {
                    if (nightTimeline.zoomAnchorHour < 0)
                        return
                    const maxY = Math.max(0, nightTimeline.trackHeight - timelineFlick.height)
                    timelineFlick.contentY = Math.max(0, Math.min(maxY, nightTimeline.zoomAnchorHour * nightTimeline.hourHeight - nightTimeline.zoomAnchorOffset))
                }
                function zoomBy(factor, anchorY) {
                    const before = nightTimeline.hourHeight
                    const next = Math.max(nightTimeline.minHourHeight, Math.min(nightTimeline.maxHourHeight, before * factor))
                    if (Math.abs(next - before) < 0.01)
                        return
                    const viewH = Math.max(Theme.px(1), timelineFlick.height)
                    const offset = Math.max(0, Math.min(viewH, Number(anchorY)))
                    nightTimeline.zoomAnchorHour = (timelineFlick.contentY + offset) / before
                    nightTimeline.zoomAnchorOffset = offset
                    nightTimeline.zoomLocked = true
                    nightTimeline.hourHeight = next
                    nightTimeline.applyAnchoredScroll()
                    zoomSettleTimer.restart()
                }
                Timer {
                    id: zoomSettleTimer
                    interval: 32
                    repeat: false
                    onTriggered: {
                        nightTimeline.applyAnchoredScroll()
                        nightTimeline.zoomAnchorHour = -1
                    }
                }
                function wheelZoomFactor(event) {
                    if (event.angleDelta.y)
                        return Math.pow(1.22, event.angleDelta.y / 120)
                    if (event.pixelDelta.y)
                        return Math.pow(1.22, event.pixelDelta.y / 80)
                    return 1
                }
                function zoomT() {
                    const lo = Math.log(nightTimeline.minHourHeight)
                    const hi = Math.log(nightTimeline.maxHourHeight)
                    if (!(hi > lo))
                        return 0
                    return Math.max(0, Math.min(1, (Math.log(nightTimeline.hourHeight) - lo) / (hi - lo)))
                }
                function setZoomT(t, anchorY) {
                    const lo = Math.log(nightTimeline.minHourHeight)
                    const hi = Math.log(nightTimeline.maxHourHeight)
                    const next = Math.exp(lo + Math.max(0, Math.min(1, Number(t))) * (hi - lo))
                    nightTimeline.zoomBy(next / Math.max(Theme.px(1), nightTimeline.hourHeight), anchorY)
                }
                function visibleStartMinutes() {
                    return Math.max(0, Math.min(1440, timelineFlick.contentY / nightTimeline.hourHeight * 60))
                }
                function visibleEndMinutes() {
                    return Math.max(0, Math.min(1440, (timelineFlick.contentY + timelineFlick.height) / nightTimeline.hourHeight * 60))
                }
                function visibleRangeText() {
                    return calendarPage.timelineClock(nightTimeline.visibleStartMinutes())
                           + "–" + calendarPage.timelineClock(nightTimeline.visibleEndMinutes())
                }
                function zoomFactorText() {
                    return (nightTimeline.hourHeight / 64).toFixed(nightTimeline.hourHeight >= 640 ? 0 : 1) + "×"
                }
                function panToRatio(ratio) {
                    const viewH = Math.max(Theme.px(1), timelineFlick.height)
                    const maxY = Math.max(0, nightTimeline.trackHeight - viewH)
                    const y = Number(ratio) * nightTimeline.trackHeight - viewH / 2
                    timelineFlick.contentY = Math.max(0, Math.min(maxY, y))
                }
                // One source of truth for the horizontal grid: hour labels sit in the
                // gutter, everything else (bands, headers, chips, now line) lines up on
                // trackLeft .. width - trackPadRight.
                readonly property real gutterWidth: 58
                readonly property real trackLeft: 66
                readonly property real trackPadRight: 10
                readonly property real columnGap: 10
                readonly property real laneGap: 3
                readonly property var columnIds: calendarPage.showAllDevices ? calendarPage.nightDeviceIds(calendarPage.nightSessions) : []
                readonly property int columnCount: Math.max(1, columnIds.length)
                readonly property bool columnsVisible: columnIds.length > 1
                readonly property real trackWidth: Math.max(Theme.px(120), timelineTrack.width - trackLeft - trackPadRight)
                readonly property real columnWidth: (trackWidth - columnGap * (columnCount - 1)) / columnCount
                function columnX(index) {
                    return trackLeft + Math.max(0, index) * (columnWidth + columnGap)
                }
                // Dragging to the top or bottom edge scrolls the timeline, so a session
                // can be moved to an hour that is not currently on screen.
                readonly property real dragScrollEdge: 56
                readonly property real dragScrollMaxStep: 14
                function dragScrollStep() {
                    if (!DragCoordinator.active || !DragCoordinator.contentItem || timelineFlick.height < 8)
                        return 0
                    const local = timelineFlick.mapFromItem(DragCoordinator.contentItem, DragCoordinator.pos.x, DragCoordinator.pos.y)
                    if (local.x < -80 || local.x > timelineFlick.width + Theme.px(80))
                        return 0
                    const edge = Math.min(nightTimeline.dragScrollEdge, timelineFlick.height / 3)
                    let ratio = 0
                    if (local.y < edge)
                        ratio = (local.y - edge) / edge
                    else if (local.y > timelineFlick.height - edge)
                        ratio = (local.y - (timelineFlick.height - edge)) / edge
                    if (ratio === 0)
                        return 0
                    return Math.max(-1, Math.min(1, ratio)) * nightTimeline.dragScrollMaxStep
                }
                Timer {
                    running: DragCoordinator.active && nightTimeline.visible
                    interval: 16
                    repeat: true
                    onTriggered: {
                        const step = nightTimeline.dragScrollStep()
                        if (step === 0)
                            return
                        const maxY = Math.max(0, timelineFlick.contentHeight - timelineFlick.height)
                        const next = Math.max(0, Math.min(maxY, timelineFlick.contentY + step))
                        if (Math.abs(next - timelineFlick.contentY) < 0.01)
                            return
                        timelineFlick.contentY = next
                        // The pointer has not moved but the hour under it has.
                        DragCoordinator.refreshPreview(DragCoordinator.pos)
                    }
                }
                onVisibleChanged: {
                    if (visible)
                        calendarPage.requestNowLineScroll()
                }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.s1
                    Item {
                        id: columnHeader
                        visible: nightTimeline.columnsVisible
                        Layout.fillWidth: true
                        Layout.preferredHeight: visible ? 24 : 0
                        Repeater {
                            model: nightTimeline.columnIds
                            delegate: Item {
                                id: columnHead
                                required property int index
                                required property var modelData
                                readonly property color tone: calendarPage.deviceColor(modelData)
                                readonly property int count: calendarPage.nightSessions.filter(item => item.device_id === columnHead.modelData).length
                                x: nightTimeline.columnX(index)
                                width: nightTimeline.columnWidth
                                height: columnHeader.height
                                Row {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: Theme.s1
                                    spacing: Theme.px(6)
                                    Rectangle { width: Theme.px(6); height: Theme.px(6); radius: Theme.px(3); anchors.verticalCenter: parent.verticalCenter; color: columnHead.tone }
                                    Text {
                                        text: calendarPage.deviceName(columnHead.modelData).toUpperCase()
                                        color: columnHead.tone
                                        font.pixelSize: Theme.fontSm
                                        font.bold: true
                                        font.letterSpacing: Theme.tracking1
                                        elide: Text.ElideRight
                                        width: Math.max(Theme.s5, columnHead.width - Theme.px(18) - countLabel.implicitWidth)
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        id: countLabel
                                        text: columnHead.count + (columnHead.count === 1 ? " session" : " sessions")
                                        color: Theme.textSecondary
                                        font.pixelSize: Theme.fontXs
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: Theme.px(2)
                                    radius: Theme.px(1)
                                    color: columnHead.tone
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                Flickable {
                    id: timelineFlick
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: width
                    contentHeight: nightTimeline.trackHeight
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    onContentHeightChanged: nightTimeline.applyAnchoredScroll()
                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        onWheel: event => {
                            event.accepted = true
                            const local = timelineFlick.mapFromItem(null, point.scenePosition.x, point.scenePosition.y)
                            nightTimeline.zoomBy(nightTimeline.wheelZoomFactor(event), local.y)
                        }
                    }
                    Item {
                        id: timelineTrack
                        objectName: "nightTimelineTrack"
                        width: timelineFlick.width
                        height: timelineFlick.contentHeight
                        DropArea {
                            anchors.fill: parent
                            keys: ["session"]
                            onDropped: drop => {
                                const sid = DragCoordinator.dragSessionId(drop)
                                if (!sid)
                                    return
                                const minutes = calendarPage.timelineMinutesFromPos(DragCoordinator.pos)
                                if (minutes < 0)
                                    return
                                backend.moveSessionStart(sid, calendarPage.timelineDate(minutes, DragCoordinator.data.device_id))
                            }
                        }
                        HoverHandler {
                            id: timelinePointer
                            enabled: !DragCoordinator.active
                            onPointChanged: nightTimeline.hoverMinutes = calendarPage.hoverMinutesFromY(point.position.y)
                            onHoveredChanged: {
                                if (timelinePointer.hovered)
                                    nightTimeline.hoverMinutes = calendarPage.hoverMinutesFromY(timelinePointer.point.position.y)
                            }
                        }
                        TapHandler {
                            acceptedButtons: Qt.LeftButton
                            acceptedModifiers: Qt.NoModifier
                            grabPermissions: PointerHandler.ApprovesTakeOverByAnything
                            onDoubleTapped: eventPoint => {
                                if (calendarPage.nightSessionAtScene(eventPoint.scenePosition))
                                    return
                                calendarPage.createSessionAtMinutes(calendarPage.hoverMinutesFromY(eventPoint.position.y))
                            }
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            grabPermissions: PointerHandler.ApprovesTakeOverByAnything
                            onTapped: eventPoint => {
                                if (calendarPage.nightSessionAtScene(eventPoint.scenePosition))
                                    return
                                nightTimeline.hoverMinutes = calendarPage.hoverMinutesFromY(eventPoint.position.y)
                                nightTrackMenu.popup()
                            }
                        }
                        Repeater {
                            // Device lanes: a faint tint plus a divider so it is obvious
                            // which telescope each session belongs to.
                            model: nightTimeline.columnsVisible ? nightTimeline.columnIds : []
                            delegate: Rectangle {
                                required property int index
                                required property var modelData
                                readonly property color tone: calendarPage.deviceColor(modelData)
                                x: nightTimeline.columnX(index) - nightTimeline.columnGap / 2
                                width: nightTimeline.columnWidth + nightTimeline.columnGap
                                height: timelineTrack.height
                                color: Qt.rgba(tone.r, tone.g, tone.b, 0.035)
                                Rectangle {
                                    visible: index > 0
                                    width: Theme.px(1)
                                    height: parent.height
                                    color: Theme.outline
                                    opacity: 0.5
                                }
                            }
                        }
                        // Viewport-sized ruler: only the visible span is drawn, so
                        // deep zoom can show 1-minute marks without a 24-hour canvas.
                        Canvas {
                            id: timeScale
                            x: 0
                            y: timelineFlick.contentY
                            width: timelineTrack.width
                            height: timelineFlick.height
                            z: 0
                            enabled: false
                            readonly property real originY: timelineFlick.contentY
                            readonly property real hourHeight: nightTimeline.hourHeight
                            readonly property int tickMinutes: nightTimeline.tickMinutes
                            readonly property int cutoffHour: calendarPage.cutoffHour
                            readonly property color accent: Theme.accent
                            readonly property color outline: Theme.outline
                            readonly property color outlineSoft: Theme.outlineSoft
                            readonly property color textSecondary: Theme.textSecondary
                            readonly property color muted: Theme.muted
                            onOriginYChanged: requestPaint()
                            onHourHeightChanged: requestPaint()
                            onTickMinutesChanged: requestPaint()
                            onCutoffHourChanged: requestPaint()
                            onAccentChanged: requestPaint()
                            onOutlineChanged: requestPaint()
                            onOutlineSoftChanged: requestPaint()
                            onTextSecondaryChanged: requestPaint()
                            onMutedChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onHeightChanged: requestPaint()
                            onPaint: {
                                const ctx = getContext("2d")
                                ctx.reset()
                                const hh = timeScale.hourHeight
                                if (hh <= 0 || width < Theme.s2 || height < Theme.s2)
                                    return
                                const step = Math.max(1, timeScale.tickMinutes)
                                const contentTop = timeScale.originY
                                const startMin = Math.max(0, Math.floor((contentTop / hh) * 60 / step) * step)
                                const endMin = Math.min(1440, Math.ceil(((contentTop + height) / hh) * 60 / step) * step)
                                const gutter = nightTimeline.gutterWidth
                                const trackW = Math.max(Theme.s2, width - gutter - nightTimeline.trackPadRight)
                                const ppm = hh / 60
                                ctx.lineWidth = 1
                                ctx.textAlign = "left"
                                ctx.textBaseline = "middle"
                                for (let minutes = startMin; minutes <= endMin; minutes += step) {
                                    const y = Math.round(minutes / 60 * hh - contentTop) + 0.5
                                    const minuteOfHour = minutes % 60
                                    const hourOfDay = (timeScale.cutoffHour + Math.floor(minutes / 60)) % 24
                                    const hourMark = minuteOfHour === 0
                                    const halfMark = minuteOfHour === 30
                                    const quarterMark = minuteOfHour === 15 || minuteOfHour === 45
                                    const fiveMark = minuteOfHour % 5 === 0
                                    let lineW = 16
                                    if (hourMark)
                                        lineW = trackW
                                    else if (halfMark)
                                        lineW = trackW * 0.82
                                    else if (quarterMark)
                                        lineW = Math.max(Theme.px(64), trackW * 0.42)
                                    else if (fiveMark)
                                        lineW = 40
                                    if (hourMark && minutes % 360 === 0) {
                                        ctx.strokeStyle = timeScale.accent
                                        ctx.globalAlpha = 0.55
                                    } else if (hourMark) {
                                        ctx.strokeStyle = timeScale.outline
                                        ctx.globalAlpha = 0.4
                                    } else if (halfMark) {
                                        ctx.strokeStyle = timeScale.outline
                                        ctx.globalAlpha = 0.32
                                    } else if (quarterMark) {
                                        ctx.strokeStyle = timeScale.outlineSoft
                                        ctx.globalAlpha = 0.28
                                    } else if (fiveMark) {
                                        ctx.strokeStyle = timeScale.outlineSoft
                                        ctx.globalAlpha = 0.22
                                    } else {
                                        ctx.strokeStyle = timeScale.outlineSoft
                                        ctx.globalAlpha = 0.16
                                    }
                                    ctx.beginPath()
                                    ctx.moveTo(gutter, y)
                                    ctx.lineTo(gutter + lineW, y)
                                    ctx.stroke()
                                    let label = ""
                                    if (hourMark)
                                        label = String(hourOfDay).padStart(2, "0") + ":00"
                                    else if (halfMark && ppm * 30 >= 16)
                                        label = String(hourOfDay).padStart(2, "0") + ":30"
                                    else if (quarterMark && ppm * 15 >= 18)
                                        label = String(hourOfDay).padStart(2, "0") + ":" + String(minuteOfHour).padStart(2, "0")
                                    else if (fiveMark && ppm * 5 >= 16)
                                        label = String(hourOfDay).padStart(2, "0") + ":" + String(minuteOfHour).padStart(2, "0")
                                    else if (ppm >= 18)
                                        label = String(hourOfDay).padStart(2, "0") + ":" + String(minuteOfHour).padStart(2, "0")
                                    if (!label)
                                        continue
                                    ctx.globalAlpha = 1
                                    ctx.fillStyle = hourMark ? timeScale.textSecondary : timeScale.muted
                                    ctx.font = (hourMark ? "bold " : "") + (hourMark ? Theme.fontSm : Theme.fontXs) + "px \"" + Theme.fontMono + "\""
                                    ctx.fillText(label, 4, y)
                                }
                            }
                        }
                        Repeater {
                            id: nightSessionRepeater
                            model: calendarPage.nightSessions
                            delegate: Rectangle {
                                id: timelineSession
                                required property var modelData
                                property string sessionId: modelData.id
                                readonly property var slot: {
                                    const _layout = calendarPage.nightLayout
                                    const _width = timelineTrack.width
                                    return calendarPage.timelineSlot(modelData)
                                }
                                x: slot.x
                                y: {
                                    const minutes = Math.max(0, Math.min(1439, calendarPage.timelineMinutesFromEpoch(modelData.start_epoch_ms, calendarPage.nightKey(), modelData.device_id)))
                                    return minutes / 60 * nightTimeline.hourHeight + nightTimeline.itemOffset
                                }
                                width: slot.width
                                height: Math.max(Theme.px(26), calendarPage.sessionSpanSeconds(modelData) / 3600 * nightTimeline.hourHeight - Theme.s1)
                                z: calendarPage.nightBarZ(modelData)
                                readonly property bool tight: height < Theme.px(44)
                                readonly property bool narrow: width < Theme.px(210)
                                radius: Theme.radius
                                clip: true
                                color: Util.statusFill(modelData.status)
                                border.color: Util.statusColor(modelData.status)
                                border.width: 1
                                opacity: DragCoordinator.active && Util.sameSessionGroup(DragCoordinator.data, modelData) ? 0.35 : 0.96
                                Accessible.name: (modelData.start_time || "") + " " + calendarPage.sessionLabel(modelData) + (modelData.status && modelData.status !== "planned" ? " " + modelData.status : "")
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    height: {
                                        const planned = calendarPage.sessionSpanSeconds(timelineSession.modelData)
                                        const actual = calendarPage.sessionActualSeconds(timelineSession.modelData)
                                        if (planned <= 0 || actual <= 0)
                                            return 0
                                        return Math.max(Theme.px(2), timelineSession.height * Math.min(1, actual / planned))
                                    }
                                    color: Util.statusColor(timelineSession.modelData.status)
                                    opacity: 0.28
                                    visible: height > 0
                                }
                                SessionDragArea {
                                    dragItem: timelineSession.modelData
                                    onEditRequested: session => calendarPage.editItem(session)
                                }
                                HoverHandler { id: timelineHover }
                                TapHandler {
                                    acceptedButtons: Qt.LeftButton
                                    acceptedModifiers: Qt.ShiftModifier
                                    onTapped: calendarPage.selectClick(timelineSession.modelData.id, true, calendarPage.nightSessions)
                                }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: timelineSession.tight ? 2 : 6
                                    anchors.leftMargin: Theme.px(2)
                                    spacing: timelineSession.narrow ? Theme.s1 : Theme.px(6)
                                    RowGutter {
                                        Layout.preferredWidth: Theme.px(18)
                                        Layout.maximumWidth: Theme.px(18)
                                        Layout.fillHeight: true
                                        spineInset: 2
                                        spineColor: Util.sessionTone(timelineSession.modelData)
                                        checked: Util.idSetHas(calendarPage.selectedIds, timelineSession.modelData.id)
                                        revealed: timelineHover.hovered || calendarPage.selectedCount > 0
                                        onToggled: (shiftHeld) => calendarPage.selectClick(timelineSession.modelData.id, shiftHeld, calendarPage.nightSessions)
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignVCenter
                                        spacing: 0
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: timelineSession.narrow ? Theme.px(5) : Theme.s2
                                            Text { text: modelData.start_time; color: Theme.accent; font.family: Theme.fontMono; font.pixelSize: timelineSession.narrow ? Theme.fontSm : Theme.fontMd; font.bold: true }
                                            Text { text: calendarPage.sessionLabel(modelData); color: Theme.textPrimary; font.pixelSize: timelineSession.narrow ? Theme.fontSm : Theme.fontBase; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                            StatusChip { status: modelData.status; visible: modelData.status !== "planned" && timelineSession.width > 200 }
                                        }
                                        Text {
                                            text: {
                                                const extra = nightTimeline.columnsVisible ? modelData.duration_text : modelData.duration_text + "  ·  " + modelData.device_name
                                                return calendarPage.sessionDetail(modelData, extra)
                                            }
                                            color: Theme.textSecondary
                                            font.pixelSize: Theme.fontSm
                                            visible: !timelineSession.tight
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                    HudButton { text: "EDIT"; implicitHeight: Theme.px(24); visible: !timelineSession.tight && timelineSession.width > 260; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: calendarPage.editItem(timelineSession.modelData) }
                                    HudButton {
                                        text: modelData.status === "running" ? "STOP" : "RUN"
                                        implicitHeight: Theme.px(24)
                                        visible: !timelineSession.tight && timelineSession.width > 260
                                        enabled: calendarPage.sessionRunEnabled(modelData)
                                        tooltip: modelData.status === "running" || calendarPage.deviceConnected(modelData.device_id) ? "" : "Connect the telescope to run"
                                        busy: root.sessionStopping(modelData)
                                        busyText: modelData.status === "running" ? "STOPPING…" : "STARTING…"
                                        busyMs: modelData.status === "running" ? 0 : 1400
                                        buttonColor: modelData.status === "running" ? Theme.fillDanger : Theme.surfaceHigh
                                        foregroundColor: modelData.status === "running" ? Theme.danger : Theme.textPrimary
                                        onClicked: modelData.status === "running"
                                            ? backend.stopSession(modelData.id)
                                            : backend.runNow(modelData.id)
                                    }
                                }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: calendarPage.openSessionMenu(timelineSession.modelData, calendarPage.nightSessions) }
                            }
                        }
                        Rectangle {
                            id: hoverLine
                            visible: timelinePointer.hovered && !DragCoordinator.active && !zoomHudHover.hovered
                                     && nightTimeline.hoverMinutes >= 0
                            x: nightTimeline.gutterWidth
                            width: parent.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                            height: Theme.px(1)
                            z: 19
                            color: Theme.accent
                            opacity: 0.35
                            y: nightTimeline.hoverMinutes / 60 * nightTimeline.hourHeight
                            Text {
                                anchors.left: parent.left
                                anchors.bottom: parent.top
                                text: calendarPage.timelineClock(nightTimeline.hoverMinutes)
                                color: Theme.accent
                                opacity: 0.7
                                font.pixelSize: Theme.fontXs
                                font.bold: true
                                font.family: Theme.fontMono
                            }
                        }
                        Rectangle {
                            id: nowLine
                            visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey()
                            x: nightTimeline.gutterWidth
                            width: parent.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                            height: Theme.px(2)
                            z: 20
                            color: Theme.warning
                            y: {
                                const epoch = Number(calendarPage.observingNow().epoch_ms || 0)
                                const minutes = epoch
                                    ? calendarPage.timelineMinutesFromEpoch(epoch)
                                    : calendarPage.timelineMinutes(String(backend.clockText).substring(0, 5))
                                return minutes / 60 * nightTimeline.hourHeight
                            }
                            Text { anchors.right: parent.right; anchors.bottom: parent.top; text: "NOW"; color: Theme.warning; font.pixelSize: Theme.fontXs; font.bold: true }
                        }
                        Rectangle {
                            visible: DragCoordinator.active && DragCoordinator.previewMinutes >= 0
                            x: nightTimeline.gutterWidth
                            width: parent.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                            height: Theme.px(2)
                            color: Theme.accent
                            y: DragCoordinator.previewMinutes / 60 * nightTimeline.hourHeight
                            z: 30
                            Text {
                                anchors.left: parent.left
                                anchors.bottom: parent.top
                                text: DragCoordinator.previewTime
                                color: Theme.accent
                                font.pixelSize: Theme.fontSm
                                font.bold: true
                                font.family: Theme.fontMono
                            }
                        }
                        Rectangle {
                            visible: DragCoordinator.active && DragCoordinator.previewMinutes >= 0
                            readonly property var slot: calendarPage.timelineSlot(DragCoordinator.data)
                            x: slot.x
                            y: DragCoordinator.previewMinutes / 60 * nightTimeline.hourHeight + nightTimeline.itemOffset
                            width: slot.width
                            height: Math.max(Theme.px(26), calendarPage.sessionSpanSeconds(DragCoordinator.data) / 3600 * nightTimeline.hourHeight - Theme.s1)
                            radius: Theme.px(3)
                            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                            border.color: Theme.accent
                            border.width: 2
                            z: 25
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: Theme.s3
                                anchors.top: parent.top
                                anchors.topMargin: Theme.s2
                                text: DragCoordinator.previewTime
                                color: Theme.accent
                                font.family: Theme.fontMono
                                font.pixelSize: Theme.fontMd
                                font.bold: true
                            }
                        }
                    }
                }
                }

                Item {
                    id: nightZoomHud
                    objectName: "nightZoomHud"
                    z: 40
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.rightMargin: Theme.s2
                    anchors.bottomMargin: Theme.s2
                    width: Theme.px(118)
                    height: Theme.px(196)
                    HoverHandler { id: zoomHudHover }
                    Accessible.role: Accessible.Dial
                    Accessible.name: "Night zoom"
                    Accessible.description: nightTimeline.visibleRangeText() + "  " + nightTimeline.zoomFactorText()

                    Rectangle {
                        anchors.fill: parent
                        color: Theme.surfaceHigh
                        border.color: Theme.outline
                        radius: Theme.radius
                        opacity: 0.94
                    }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Theme.s1
                        spacing: Theme.s1

                        Text {
                            Layout.fillWidth: true
                            text: nightTimeline.visibleRangeText()
                            color: Theme.accent
                            font.pixelSize: Theme.fontXs
                            font.family: Theme.fontMono
                            font.bold: true
                            horizontalAlignment: Text.AlignHCenter
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: nightTimeline.zoomFactorText()
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontXs
                            font.family: Theme.fontMono
                            horizontalAlignment: Text.AlignHCenter
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.s1
                            HudButton {
                                objectName: "night-zoom-out"
                                text: "−"
                                implicitHeight: Theme.compactControlHeight
                                Layout.preferredWidth: Theme.px(24)
                                Layout.preferredHeight: Theme.compactControlHeight
                                tooltip: "Zoom out"
                                onClicked: nightTimeline.zoomBy(1 / 1.22, timelineFlick.height / 2)
                            }
                            Item {
                                id: zoomMeter
                                Layout.fillWidth: true
                                Layout.preferredHeight: Theme.px(10)
                                Accessible.role: Accessible.Slider
                                Accessible.name: "Zoom level"
                                Rectangle {
                                    anchors.fill: parent
                                    color: Theme.inputBg
                                    border.color: Theme.outlineSoft
                                    radius: height / 2
                                    Rectangle {
                                        x: Theme.px(1)
                                        y: Theme.px(1)
                                        height: parent.height - Theme.px(2)
                                        width: Math.max(0, (parent.width - Theme.px(2)) * nightTimeline.zoomT())
                                        radius: height / 2
                                        color: Theme.accent
                                        opacity: 0.7
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onPressed: mouse => nightTimeline.setZoomT(mouse.x / Math.max(Theme.px(1), width), timelineFlick.height / 2)
                                    onPositionChanged: mouse => {
                                        if (pressed)
                                            nightTimeline.setZoomT(mouse.x / Math.max(Theme.px(1), width), timelineFlick.height / 2)
                                    }
                                }
                            }
                            HudButton {
                                objectName: "night-zoom-in"
                                text: "+"
                                implicitHeight: Theme.compactControlHeight
                                Layout.preferredWidth: Theme.px(24)
                                Layout.preferredHeight: Theme.compactControlHeight
                                tooltip: "Zoom in"
                                onClicked: nightTimeline.zoomBy(1.22, timelineFlick.height / 2)
                            }
                        }

                        Item {
                            id: nightMini
                            objectName: "nightZoomMini"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: Theme.px(72)

                            Rectangle {
                                anchors.fill: parent
                                color: Theme.inputBg
                                border.color: Theme.outlineSoft
                                radius: Theme.radius
                            }
                            Repeater {
                                model: calendarPage.nightSessions
                                delegate: Rectangle {
                                    required property var modelData
                                    readonly property real startMin: Math.max(0, Math.min(1440, calendarPage.timelineMinutesFromEpoch(modelData.start_epoch_ms, calendarPage.nightKey(), modelData.device_id)))
                                    readonly property real spanMin: Math.max(2, calendarPage.sessionSpanSeconds(modelData) / 60)
                                    x: Theme.px(3)
                                    width: parent.width - Theme.px(6)
                                    y: startMin / 1440 * nightMini.height
                                    height: Math.max(Theme.px(2), spanMin / 1440 * nightMini.height)
                                    radius: Theme.px(1)
                                    color: Util.statusColor(modelData.status)
                                    opacity: 0.55
                                }
                            }
                            Rectangle {
                                id: miniThumb
                                x: Theme.px(1)
                                width: parent.width - Theme.px(2)
                                y: {
                                    const h = Math.max(Theme.px(1), nightTimeline.trackHeight)
                                    return timelineFlick.contentY / h * nightMini.height
                                }
                                height: {
                                    const h = Math.max(Theme.px(1), nightTimeline.trackHeight)
                                    return Math.max(Theme.px(10), timelineFlick.height / h * nightMini.height)
                                }
                                radius: Theme.px(2)
                                color: "transparent"
                                border.color: Theme.accent
                                border.width: 1
                                opacity: 0.9
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onPressed: mouse => nightTimeline.panToRatio(mouse.y / Math.max(Theme.px(1), height))
                                onPositionChanged: mouse => {
                                    if (pressed)
                                        nightTimeline.panToRatio(mouse.y / Math.max(Theme.px(1), height))
                                }
                                onDoubleClicked: calendarPage.fitNightZoom()
                            }
                        }

                        HudButton {
                            objectName: "night-zoom-fit"
                            Layout.fillWidth: true
                            implicitHeight: Theme.compactControlHeight
                            Layout.preferredHeight: Theme.compactControlHeight
                            text: "FIT"
                            tooltip: "Fit this night's sessions"
                            onClicked: calendarPage.fitNightZoom()
                        }
                    }
                }

                HudMenu {
                    id: nightTrackMenu
                    objectName: "nightTrackMenu"
                    HudMenuItem {
                        text: "New session at " + calendarPage.timelineClock(nightTimeline.hoverMinutes)
                        glyph: "\uE710"
                        onTriggered: calendarPage.createSessionAtMinutes(nightTimeline.hoverMinutes)
                    }
                    HudMenuSeparator {}
                    HudMenuItem {
                        text: "Zoom in"
                        glyph: "\uE8A3"
                        onTriggered: nightTimeline.zoomBy(1.22, timelineFlick.height / 2)
                    }
                    HudMenuItem {
                        text: "Zoom out"
                        glyph: "\uE71F"
                        onTriggered: nightTimeline.zoomBy(1 / 1.22, timelineFlick.height / 2)
                    }
                    HudMenuItem {
                        text: "Fit night"
                        glyph: "\uE9A6"
                        onTriggered: calendarPage.fitNightZoom()
                    }
                    HudMenuSeparator {}
                    HudMenuItem {
                        info: true
                        enabled: false
                        text: calendarPage.dateKey(calendarPage.selectedDate)
                              + "  ·  " + nightTimeline.visibleRangeText()
                              + "  ·  " + nightTimeline.zoomFactorText()
                              + "  ·  " + calendarPage.nightSessions.length
                              + (calendarPage.nightSessions.length === 1 ? " session" : " sessions")
                    }
                }
            }
        }
        HudPanel {
            id: nightPanel
            readonly property var nightSessions: calendarPage.sidebarSessions
            readonly property int nightSeconds: nightSessions.reduce((sum, item) => sum + calendarPage.sessionSpanSeconds(item), 0)
            visible: calendarPage.viewMode === 0
            title: {
                calendarPage.selectedDayKeys
                calendarPage.selectedDate
                return calendarPage.selectedNightsTitle()
            }
            SplitView.preferredWidth: Theme.px(312)
            SplitView.minimumWidth: Theme.px(220)
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.px(6)
                HudChip { visible: calendarPage.selectedDayCount > 1; label: calendarPage.selectedDayCount + " NIGHTS"; tone: Theme.accent }
                HudChip { label: nightPanel.nightSessions.length + (nightPanel.nightSessions.length === 1 ? " SESSION" : " SESSIONS"); tone: nightPanel.nightSessions.length > 0 ? Theme.accent : Theme.textSecondary }
                HudChip { visible: nightPanel.nightSeconds > 0; label: "PLAN"; value: Util.formatDuration(nightPanel.nightSeconds); tone: Theme.textSecondary }
                HudChip { visible: calendarPage.isDaySelected(calendarPage.currentObservingKey()); label: "TONIGHT"; tone: Theme.warning; glow: true }
                Item { Layout.fillWidth: true }
            }
            SelectionBar {
                selectedCount: nightPanel.nightSessions.filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).length
                totalCount: nightPanel.nightSessions.length
                noun: "session"
                allowMove: true
                sessionIds: nightPanel.nightSessions.filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).map(item => item.id)
                onSelectAllRequested: {
                    const next = Object.assign({}, calendarPage.selectedIds)
                    for (let i = 0; i < nightPanel.nightSessions.length; i++) {
                        const id = nightPanel.nightSessions[i] && nightPanel.nightSessions[i].id
                        if (id)
                            next[id] = true
                    }
                    calendarPage.selectedIds = next
                }
                onClearRequested: {
                    const drop = {}
                    for (let i = 0; i < nightPanel.nightSessions.length; i++) {
                        const id = nightPanel.nightSessions[i] && nightPanel.nightSessions[i].id
                        if (id)
                            drop[id] = true
                    }
                    const next = Object.assign({}, calendarPage.selectedIds)
                    const keys = Object.keys(drop)
                    for (let i = 0; i < keys.length; i++)
                        delete next[keys[i]]
                    calendarPage.selectedIds = next
                }
                onEditRequested: sessionDialog.openSelected(Util.itemsByIds(nightPanel.nightSessions, calendarPage.selectedIds))
                onDeleteRequested: {
                    const chosen = {}
                    for (let i = 0; i < nightPanel.nightSessions.length; i++) {
                        const id = nightPanel.nightSessions[i] && nightPanel.nightSessions[i].id
                        if (id && Util.idSetHas(calendarPage.selectedIds, id))
                            chosen[id] = true
                    }
                    root.confirmBulkDelete("deleteSessions", chosen, "session")
                }
            }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: 0
                SessionInsertDrop {
                    id: daySessionInsert
                    anchors.fill: parent
                    targetList: daySessionList
                    rowHeight: Theme.px(76)
                    observingDate: calendarPage.selectedDayCount <= 1 ? calendarPage.dateKey(calendarPage.selectedDate) : ""
                    ListView {
                        id: daySessionList
                        anchors.fill: parent
                        clip: true
                        spacing: Theme.px(6)
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: HiddenBar {}
                        ScrollBar.horizontal: HiddenBar {}
                        model: nightPanel.nightSessions
                        delegate: Rectangle {
                            id: daySessionRow
                            required property var modelData
                            property string sessionId: modelData.id
                            objectName: "calendar-sidebar-" + modelData.id
                            width: ListView.view.width
                            height: Theme.px(76)
                            radius: Theme.radius
                            color: Util.statusFill(modelData.status)
                            border.color: Qt.rgba(Util.statusColor(modelData.status).r, Util.statusColor(modelData.status).g, Util.statusColor(modelData.status).b, 0.5)
                            opacity: DragCoordinator.active && Util.sameSessionGroup(DragCoordinator.data, modelData) ? 0.35 : 1
                            Accessible.name: calendarPage.sessionWhenText(modelData) + " " + calendarPage.sessionLabel(modelData)
                            SessionDragArea {
                                dragItem: daySessionRow.modelData
                                onEditRequested: session => calendarPage.editItem(session)
                            }
                            HoverHandler { id: daySessionHover }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ShiftModifier
                                onTapped: calendarPage.selectClick(daySessionRow.modelData.id, true, nightPanel.nightSessions)
                            }
                            RowGutter {
                                x: Theme.px(2)
                                width: Theme.s5
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                spineColor: Util.sessionTone(daySessionRow.modelData)
                                checked: Util.idSetHas(calendarPage.selectedIds, daySessionRow.modelData.id)
                                revealed: daySessionHover.hovered || calendarPage.selectedCount > 0
                                onToggled: (shiftHeld) => calendarPage.selectClick(daySessionRow.modelData.id, shiftHeld, nightPanel.nightSessions)
                            }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.s2
                                anchors.leftMargin: Theme.px(28)
                                spacing: Theme.px(2)
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Theme.px(6)
                                    Text { text: calendarPage.sessionWhenText(modelData); color: Theme.accent; font.pixelSize: Theme.fontMd; font.bold: true; font.family: Theme.fontMono }
                                    Text { text: calendarPage.sessionLabel(modelData); color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                }
                                Text { text: calendarPage.sessionDetail(modelData, modelData.subtitle + " · " + modelData.duration_text); color: Theme.textSecondary; font.pixelSize: Theme.fontSm; elide: Text.ElideRight; Layout.fillWidth: true }
                                RowLayout {
                                    HudButton { text: "EDIT"; implicitHeight: Theme.px(24); enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: calendarPage.editItem(modelData) }
                                    HudButton { text: "RESET"; implicitHeight: Theme.px(24); visible: Util.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                    HudButton {
                                        text: modelData.status === "running" ? "STOP" : "RUN"
                                        implicitHeight: Theme.px(24)
                                        enabled: calendarPage.sessionRunEnabled(modelData)
                                        tooltip: modelData.status === "running" || calendarPage.deviceConnected(modelData.device_id) ? "" : "Connect the telescope to run"
                                        busy: root.sessionStopping(modelData)
                                        busyText: modelData.status === "running" ? "STOPPING…" : "STARTING…"
                                        busyMs: modelData.status === "running" ? 0 : 1400
                                        buttonColor: modelData.status === "running" ? Theme.fillDanger : Theme.surfaceHigh
                                        foregroundColor: modelData.status === "running" ? Theme.danger : Theme.textPrimary
                                        onClicked: modelData.status === "running"
                                            ? backend.stopSession(modelData.id)
                                            : backend.runNow(modelData.id)
                                    }
                                }
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: calendarPage.openSessionMenu(daySessionRow.modelData, nightPanel.nightSessions)
                            }
                        }
                    }
                }
                EmptyHint {
                    anchors.centerIn: parent
                    glyph: "☾"
                    visible: nightPanel.nightSessions.length === 0
                    text: calendarPage.showAllDevices
                          ? (calendarPage.selectedDayCount > 1 ? "No sessions on these observing nights" : "No sessions this observing night")
                          : (calendarPage.selectedDayCount > 1 ? "No sessions on this telescope for these nights" : "No sessions on this telescope for this night")
                }
            }
        }
    }
    SessionContextMenu {
        id: sessionMenu
        sessionData: calendarPage.contextSession
        selectionItems: calendarPage.contextItems
        selectedMap: calendarPage.selectedIds
        onEditRequested: session => calendarPage.editItem(session)
        onEditSelectedRequested: sessionDialog.openSelected(Util.itemsByIds(calendarPage.contextItems, calendarPage.selectedIds))
        onDuplicateRequested: (session, mode) => duplicateSessionDialog.openFor(session, mode)
        onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(calendarPage.contextItems, true)
        onUnselectAllRequested: {
            calendarPage.selectedIds = ({})
            calendarPage.selectionAnchorId = ""
        }
    }
}
