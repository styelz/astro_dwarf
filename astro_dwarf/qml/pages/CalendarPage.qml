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
    function sessionEndMs(item) {
        return Number(item.start_epoch_ms || 0) + Number(item.planned_duration_seconds || 0) * 1000
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
            width: Math.max(28, laneW * span + laneGap * (span - 1))
        }
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
    function nightStartMs(key) {
        if (!key || key === calendarPage.nightKey())
            return calendarPage.nightOriginMs
        return Number(backend.nightStartEpochMs(key))
    }
    function timelineMinutes(timeText) {
        const bits = String(timeText || "00:00").split(":")
        let minutes = Number(bits[0]) * 60 + Number(bits[1]) - cutoffHour * 60
        if (minutes < 0)
            minutes += 1440
        return minutes
    }
    function timelineMinutesFromEpoch(epochMs, key) {
        const start = calendarPage.nightStartMs(key)
        if (!start)
            return 0
        return (Number(epochMs) - start) / 60000
    }
    function snapTimelineMinutes(minutes) {
        return Math.max(0, Math.min(1435, Math.round(Number(minutes) / 5) * 5))
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
    function timelineDate(minutes) {
        return backend.nightTimelineIso(calendarPage.nightKey(), calendarPage.snapTimelineMinutes(minutes))
    }
    function currentObservingKey() {
        return String(calendarPage.observingNow().observing_date || calendarPage.dateKey(new Date()))
    }
    function openNight(value) {
        calendarPage.setSingleDay(value)
        viewMode = 1
        requestNowLineScroll()
    }
    function openNightUnlessChip(cellDate, repeater, eventPoint) {
        const scene = eventPoint.scenePosition
        for (let i = 0; i < repeater.count; i++) {
            const chip = repeater.itemAt(i)
            if (!chip)
                continue
            const local = chip.mapFromItem(null, scene.x, scene.y)
            if (local.x >= 0 && local.y >= 0 && local.x < chip.width && local.y < chip.height)
                return
        }
        calendarPage.openNight(cellDate)
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
            SplitView.minimumWidth: 420
            spacing: 10
            PageHeader {
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
                    text: "ALL DEVICES"
                    buttonColor: calendarPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                    foregroundColor: calendarPage.showAllDevices ? Theme.accent : Theme.textSecondary
                    onClicked: calendarPage.showAllDevices = true
                }
                HudButton {
                    visible: (backend.devices || []).length > 1
                    text: "THIS DEVICE"
                    buttonColor: !calendarPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                    foregroundColor: !calendarPage.showAllDevices ? Theme.accent : Theme.textSecondary
                    onClicked: calendarPage.showAllDevices = false
                }
                HudButton {
                    text: "‹"; implicitWidth: 40
                    onClicked: {
                        if (calendarPage.viewMode === 0)
                            calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() - 1, 1)
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
                    text: "›"; implicitWidth: 40
                    onClicked: {
                        if (calendarPage.viewMode === 0)
                            calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() + 1, 1)
                        else {
                            const value = new Date(calendarPage.selectedDate)
                            value.setDate(value.getDate() + 1)
                            calendarPage.setSingleDay(value)
                        }
                    }
                }
                HudButton { text: "+ NEW SESSION"; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate)) }
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
            RowLayout {
                visible: calendarPage.viewMode === 0
                Layout.fillWidth: true
                Repeater { model: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]; Text { required property string modelData; text: modelData; color: Theme.accent; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } }
            }
            GridLayout {
                visible: calendarPage.viewMode === 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                columns: 7
                rows: 6
                rowSpacing: 5
                columnSpacing: 5
                Repeater {
                    model: 42
                    delegate: Rectangle {
                        id: dayCell
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
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: 3
                        color: isSelected ? Theme.hsl(0.036, 0.640, 0.196, 0.753) : cellHover.hovered ? Theme.hsl(0.068, 0.517, 0.114, 0.690) : inMonth ? Theme.hsl(0.079, 0.517, 0.057, 0.600) : Theme.hsl(0.079, 0.517, 0.057, 0.333)
                        border.color: dropArea.containsDrag ? Theme.accent : isSelected ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) : Theme.outline
                        Behavior on color { ColorAnimation { duration: 120 } }
                        HoverHandler { id: cellHover }
                        Rectangle {
                            // animated accent ring on tonight's cell
                            anchors.fill: parent
                            anchors.margins: 2
                            radius: 3
                            color: "transparent"
                            border.color: Theme.accent
                            border.width: 1
                            visible: dayCell.isToday
                            opacity: 0.6
                            SequentialAnimation on opacity {
                                running: dayCell.isToday && calendarPage.visible && calendarPage.viewMode === 0
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.15; duration: 1500; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 0.8; duration: 1500; easing.type: Easing.InOutSine }
                            }
                        }
                        Text {
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 5
                            visible: dayCell.isToday
                            text: "TONIGHT"
                            color: Theme.accent
                            font.pixelSize: 7; font.bold: true; font.letterSpacing: 1
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
                            anchors.margins: 6
                            spacing: 3
                            Text { text: dayCell.cellDate.getDate(); color: dayCell.isToday ? Theme.accent : dayCell.inMonth ? Theme.textPrimary : Theme.hsl(0.040, 0.262, 0.329); font.pixelSize: 11; font.bold: dayCell.isToday; font.family: Theme.fontMono }
                            Repeater {
                                id: chipRepeater
                                model: dayCell.daySessions.slice(0, 3)
                                delegate: Rectangle {
                                    id: sessionChip
                                    required property var modelData
                                    property string sessionId: modelData.id
                                    readonly property color deviceTone: Util.sessionTone(modelData)
                                    width: parent.width
                                    height: 22
                                    radius: 2
                                    color: Util.statusFill(modelData.status)
                                    border.color: Qt.rgba(Util.statusColor(modelData.status).r, Util.statusColor(modelData.status).g, Util.statusColor(modelData.status).b, 0.55)
                                    opacity: DragCoordinator.active && DragCoordinator.data.id === sessionId ? 0.35 : 1
                                    Rectangle { x: 1; y: 1; width: 3; height: parent.height - 2; radius: 1; color: sessionChip.deviceTone }
                                    Rectangle {
                                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 3
                                        width: 5; height: 5; radius: 2.5
                                        color: Util.statusColor(modelData.status)
                                        visible: String(modelData.status) !== "planned"
                                    }
                                    Text { anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 10; anchors.topMargin: 4; anchors.bottomMargin: 4; text: calendarPage.chipText(modelData); color: Theme.textPrimary; font.pixelSize: 9; elide: Text.ElideRight }
                                    SessionDragArea {
                                        dragItem: sessionChip.modelData
                                        pressedAction: function() { calendarPage.setSingleDay(dayCell.cellDate) }
                                        onEditRequested: session => sessionDialog.openExisting(session)
                                    }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: calendarPage.openSessionMenu(sessionChip.modelData, dayCell.daySessions) }
                                }
                            }
                            Text {
                                visible: dayCell.daySessions.length > 3
                                text: "+" + (dayCell.daySessions.length - 3) + " more"
                                color: Theme.accent
                                font.pixelSize: 9
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
                            onDoubleTapped: (eventPoint) => calendarPage.openNightUnlessChip(dayCell.cellDate, chipRepeater, eventPoint)
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
            Item {
                id: nightTimeline
                visible: calendarPage.viewMode === 1
                Layout.fillWidth: true
                Layout.fillHeight: true
                property real hourHeight: 64
                property real itemOffset: 5
                // A whole night at a fixed scale leaves an hour of sessions squeezed into
                // a sliver of a very tall, empty track, so the scale follows the content
                // until the user zooms with Ctrl+wheel.
                property bool zoomLocked: false
                readonly property real minHourHeight: 40
                readonly property real maxHourHeight: 260
                function firstSessionMinutes() {
                    const items = calendarPage.nightSessions
                    let lo = 1440
                    for (let i = 0; i < items.length; i++)
                        lo = Math.min(lo, calendarPage.timelineMinutesFromEpoch(items[i].start_epoch_ms))
                    return Math.max(0, Math.min(1440, lo))
                }
                function autoFit() {
                    const items = calendarPage.nightSessions
                    if (nightTimeline.zoomLocked || timelineFlick.height < 80)
                        return
                    if (!items.length) {
                        nightTimeline.hourHeight = 64
                        return
                    }
                    let lo = 1440
                    let hi = 0
                    for (let i = 0; i < items.length; i++) {
                        lo = Math.min(lo, calendarPage.timelineMinutesFromEpoch(items[i].start_epoch_ms))
                        hi = Math.max(hi, calendarPage.timelineMinutesFromEpoch(calendarPage.sessionEndMs(items[i])))
                    }
                    const hours = Math.max(1, (Math.min(1440, hi) - Math.max(0, lo)) / 60) + 1
                    nightTimeline.hourHeight = Math.max(nightTimeline.minHourHeight, Math.min(nightTimeline.maxHourHeight, timelineFlick.height / hours))
                }
                function zoomBy(factor, anchorY) {
                    const before = nightTimeline.hourHeight
                    const next = Math.max(nightTimeline.minHourHeight, Math.min(nightTimeline.maxHourHeight, before * factor))
                    if (Math.abs(next - before) < 0.01)
                        return
                    const offset = Math.max(0, anchorY)
                    const anchor = (timelineFlick.contentY + offset) / before
                    nightTimeline.zoomLocked = true
                    nightTimeline.hourHeight = next
                    const maxY = Math.max(0, timelineFlick.contentHeight - timelineFlick.height)
                    timelineFlick.contentY = Math.max(0, Math.min(maxY, anchor * next - offset))
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
                readonly property real trackWidth: Math.max(120, timelineTrack.width - trackLeft - trackPadRight)
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
                    if (local.x < -80 || local.x > timelineFlick.width + 80)
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
                    spacing: 4
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
                                    anchors.bottomMargin: 4
                                    spacing: 6
                                    Rectangle { width: 6; height: 6; radius: 3; anchors.verticalCenter: parent.verticalCenter; color: columnHead.tone }
                                    Text {
                                        text: calendarPage.deviceName(columnHead.modelData).toUpperCase()
                                        color: columnHead.tone
                                        font.pixelSize: Theme.fontSm
                                        font.bold: true
                                        font.letterSpacing: Theme.tracking1
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        text: columnHead.count + (columnHead.count === 1 ? " session" : " sessions")
                                        color: Theme.textSecondary
                                        font.pixelSize: Theme.fontXs
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 2
                                    radius: 1
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
                    contentHeight: 24 * nightTimeline.hourHeight + 24
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    WheelHandler {
                        acceptedModifiers: Qt.ControlModifier
                        onWheel: event => nightTimeline.zoomBy(event.angleDelta.y > 0 ? 1.15 : 1 / 1.15, point.position.y)
                    }
                    Item {
                        id: timelineTrack
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
                                backend.moveSessionStart(sid, calendarPage.timelineDate(minutes))
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
                                    width: 1
                                    height: parent.height
                                    color: Theme.outline
                                    opacity: 0.5
                                }
                            }
                        }
                        Repeater {
                            model: 25
                            delegate: Item {
                                required property int index
                                y: index * nightTimeline.hourHeight
                                width: timelineTrack.width
                                height: 1
                                Text {
                                    x: 4; y: -7; width: nightTimeline.gutterWidth - 8
                                    text: String((calendarPage.cutoffHour + index) % 24).padStart(2, "0") + ":00"
                                    color: Theme.textSecondary
                                    font.pixelSize: 10
                                    font.family: Theme.fontMono
                                }
                                Rectangle {
                                    x: nightTimeline.gutterWidth
                                    width: timelineTrack.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                                    height: 1
                                    color: index % 6 === 0 ? Theme.accent : Theme.outline
                                    opacity: index % 6 === 0 ? 0.55 : 0.4
                                }
                            }
                        }
                        Repeater {
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
                                    const minutes = Math.max(0, Math.min(1435, calendarPage.timelineMinutesFromEpoch(modelData.start_epoch_ms)))
                                    return minutes / 60 * nightTimeline.hourHeight + nightTimeline.itemOffset
                                }
                                width: slot.width
                                height: Math.max(26, Number(modelData.planned_duration_seconds || 0) / 3600 * nightTimeline.hourHeight - 4)
                                readonly property bool tight: height < 44
                                readonly property bool narrow: width < 210
                                radius: 3
                                clip: true
                                color: Util.statusFill(modelData.status)
                                border.color: Util.statusColor(modelData.status)
                                border.width: 1
                                opacity: DragCoordinator.active && DragCoordinator.data.id === sessionId ? 0.35 : 0.96
                                SessionDragArea {
                                    dragItem: timelineSession.modelData
                                    onEditRequested: session => sessionDialog.openExisting(session)
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
                                    anchors.leftMargin: 2
                                    spacing: timelineSession.narrow ? 4 : 6
                                    RowGutter {
                                        Layout.preferredWidth: 18
                                        Layout.maximumWidth: 18
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
                                            spacing: timelineSession.narrow ? 5 : 8
                                            Text { text: modelData.start_time; color: Theme.accent; font.family: Theme.fontMono; font.pixelSize: timelineSession.narrow ? 10 : 12; font.bold: true }
                                            Text { text: calendarPage.sessionLabel(modelData); color: Theme.textPrimary; font.pixelSize: timelineSession.narrow ? 11 : 13; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                            StatusChip { status: modelData.status; visible: modelData.status !== "planned" && timelineSession.width > 200 }
                                        }
                                        Text {
                                            text: {
                                                const extra = nightTimeline.columnsVisible ? modelData.duration_text : modelData.duration_text + "  ·  " + modelData.device_name
                                                return calendarPage.sessionDetail(modelData, extra)
                                            }
                                            color: Theme.textSecondary
                                            font.pixelSize: 10
                                            visible: !timelineSession.tight
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                    HudButton { text: "EDIT"; implicitHeight: 24; visible: !timelineSession.tight && timelineSession.width > 260; onClicked: sessionDialog.openExisting(timelineSession.modelData) }
                                    HudButton { text: "RUN"; implicitHeight: 24; visible: !timelineSession.tight && timelineSession.width > 260; enabled: modelData.status !== "running"; onClicked: backend.runNow(modelData.id) }
                                }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: calendarPage.openSessionMenu(timelineSession.modelData, calendarPage.nightSessions) }
                            }
                        }
                        Rectangle {
                            id: nowLine
                            visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey()
                            x: nightTimeline.gutterWidth
                            width: parent.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                            height: 2
                            z: 20
                            color: Theme.warning
                            y: {
                                const epoch = Number(calendarPage.observingNow().epoch_ms || 0)
                                const minutes = epoch
                                    ? calendarPage.timelineMinutesFromEpoch(epoch)
                                    : calendarPage.timelineMinutes(String(backend.clockText).substring(0, 5))
                                return minutes / 60 * nightTimeline.hourHeight
                            }
                            Text { anchors.right: parent.right; anchors.bottom: parent.top; text: "NOW"; color: Theme.warning; font.pixelSize: 9; font.bold: true }
                        }
                        Rectangle {
                            visible: DragCoordinator.active && DragCoordinator.previewMinutes >= 0
                            x: nightTimeline.gutterWidth
                            width: parent.width - nightTimeline.gutterWidth - nightTimeline.trackPadRight
                            height: 2
                            color: Theme.accent
                            y: DragCoordinator.previewMinutes / 60 * nightTimeline.hourHeight
                            z: 30
                            Text {
                                anchors.left: parent.left
                                anchors.bottom: parent.top
                                text: DragCoordinator.previewTime
                                color: Theme.accent
                                font.pixelSize: 11
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
                            height: Math.max(26, Number(DragCoordinator.data.planned_duration_seconds || 0) / 3600 * nightTimeline.hourHeight - 4)
                            radius: 3
                            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                            border.color: Theme.accent
                            border.width: 2
                            z: 25
                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 12
                                anchors.top: parent.top
                                anchors.topMargin: 8
                                text: DragCoordinator.previewTime
                                color: Theme.accent
                                font.family: Theme.fontMono
                                font.pixelSize: 12
                                font.bold: true
                            }
                        }
                    }
                }
                }
                EmptyHint {
                    anchors.centerIn: parent
                    glyph: "☾"
                    visible: calendarPage.nightSessions.length === 0
                    text: calendarPage.showAllDevices
                          ? "Nothing scheduled for this night. Drop a session onto the timeline, or create a new one."
                          : "Nothing scheduled on this telescope for this night."
                }
            }
        }
        HudPanel {
            id: nightPanel
            readonly property var nightSessions: calendarPage.sidebarSessions
            readonly property int nightSeconds: nightSessions.reduce((sum, item) => sum + Number(item.planned_duration_seconds || 0), 0)
            visible: calendarPage.viewMode === 0
            title: {
                calendarPage.selectedDayKeys
                calendarPage.selectedDate
                return calendarPage.selectedNightsTitle()
            }
            SplitView.preferredWidth: 312
            SplitView.minimumWidth: 220
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
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
                    rowHeight: 64
                    ListView {
                        id: daySessionList
                        anchors.fill: parent
                        clip: true
                        spacing: 6
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: HiddenBar {}
                        ScrollBar.horizontal: HiddenBar {}
                        model: nightPanel.nightSessions
                        delegate: Rectangle {
                            id: daySessionRow
                            required property var modelData
                            property string sessionId: modelData.id
                            width: ListView.view.width
                            height: 64
                            radius: 3
                            color: Util.statusFill(modelData.status)
                            border.color: Qt.rgba(Util.statusColor(modelData.status).r, Util.statusColor(modelData.status).g, Util.statusColor(modelData.status).b, 0.5)
                            opacity: DragCoordinator.active && DragCoordinator.data.id === sessionId ? 0.35 : 1
                            SessionDragArea {
                                dragItem: daySessionRow.modelData
                                onEditRequested: session => sessionDialog.openExisting(session)
                            }
                            HoverHandler { id: daySessionHover }
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ShiftModifier
                                onTapped: calendarPage.selectClick(daySessionRow.modelData.id, true, nightPanel.nightSessions)
                            }
                            RowGutter {
                                x: 2
                                width: 20
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                spineColor: Util.sessionTone(daySessionRow.modelData)
                                checked: Util.idSetHas(calendarPage.selectedIds, daySessionRow.modelData.id)
                                revealed: daySessionHover.hovered || calendarPage.selectedCount > 0
                                onToggled: (shiftHeld) => calendarPage.selectClick(daySessionRow.modelData.id, shiftHeld, nightPanel.nightSessions)
                            }
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 8
                                anchors.leftMargin: 28
                                spacing: 2
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text { text: calendarPage.sessionWhenText(modelData); color: Theme.accent; font.pixelSize: 12; font.bold: true; font.family: Theme.fontMono }
                                    Text { text: calendarPage.sessionLabel(modelData); color: Theme.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                }
                                Text { text: calendarPage.sessionDetail(modelData, modelData.subtitle + " · " + modelData.duration_text); color: Theme.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                RowLayout {
                                    HudButton { text: "EDIT"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                    HudButton { text: "RESET"; implicitHeight: 24; visible: Util.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                    HudButton { text: "RUN"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
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
        onEditRequested: session => sessionDialog.openExisting(session)
        onEditSelectedRequested: sessionDialog.openSelected(Util.itemsByIds(calendarPage.contextItems, calendarPage.selectedIds))
        onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(calendarPage.contextItems, true)
        onUnselectAllRequested: {
            calendarPage.selectedIds = ({})
            calendarPage.selectionAnchorId = ""
        }
    }
}
