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
    property int viewMode: 0
    property var selectedIds: ({})
    property string selectionAnchorId: ""
    property int nowLineScrollTries: 0
    readonly property int selectedCount: Util.idSetCount(selectedIds)
    function selectClick(id, shift, items) {
        const result = Util.clickSelect(selectedIds, items || backend.sessions, id, shift, selectionAnchorId)
        selectedIds = result.map
        selectionAnchorId = result.anchor
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
    function sessionsForDay(key) {
        return backend.sessions.filter(item => item.observing_date === key)
    }
    function chipText(item) {
        return item.start_time + "  " + (item.pane_index < 1000000 ? "pane " + item.pane_index : item.target_name)
    }
    readonly property int cutoffHour: Number(backend.selectedDevice.observing_day_cutoff_hour || 12)
    function timelineMinutes(timeText) {
        const bits = String(timeText || "00:00").split(":")
        let minutes = Number(bits[0]) * 60 + Number(bits[1]) - cutoffHour * 60
        if (minutes < 0)
            minutes += 1440
        return minutes
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
        const value = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate(), cutoffHour, 0, 0, 0)
        value.setMinutes(value.getMinutes() + calendarPage.snapTimelineMinutes(minutes))
        return dateKey(value) + "T" + String(value.getHours()).padStart(2, "0") + ":" + String(value.getMinutes()).padStart(2, "0")
    }
    function currentObservingKey() {
        return String(calendarPage.observingNow().observing_date || calendarPage.dateKey(new Date()))
    }
    function openNight(value) {
        selectedDate = value
        viewMode = 1
        requestNowLineScroll()
    }
    function requestNowLineScroll() {
        nowLineScrollTries = 0
        nowLineScrollTimer.restart()
    }
    function scrollNowLineIntoView() {
        if (calendarPage.viewMode !== 1 || !nightTimeline.visible)
            return
        if (calendarPage.dateKey(calendarPage.selectedDate) !== calendarPage.currentObservingKey())
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
        const y = nowLine.y
        const maxY = Math.max(0, timelineFlick.contentHeight - viewH)
        const target = Math.max(0, Math.min(maxY, y - viewH / 2 + nowLine.height / 2))
        timelineFlick.contentY = target
    }
    Timer {
        id: nowLineScrollTimer
        interval: 16
        repeat: false
        onTriggered: calendarPage.scrollNowLineIntoView()
    }
    Component.onCompleted: {
        const today = calendarPage.dateFromKey(calendarPage.currentObservingKey())
        selectedDate = today
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
                    const total = backend.sessions.filter(item => item.status === "planned").length
                    const night = calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length
                    return total + " planned session" + (total === 1 ? "" : "s") + "  ·  " + night + " on the selected night  ·  night rolls over at " + String(calendarPage.cutoffHour).padStart(2, "0") + ":00  ·  " + (backend.selectedDevice.timezone_name || "UTC")
                }
                HudButton { text: "MONTH"; buttonColor: calendarPage.viewMode === 0 ? Theme.fillActive : Theme.surfaceHigh; foregroundColor: calendarPage.viewMode === 0 ? Theme.accent : Theme.textSecondary; onClicked: calendarPage.viewMode = 0 }
                HudButton { text: "NIGHT"; buttonColor: calendarPage.viewMode === 1 ? Theme.fillActive : Theme.surfaceHigh; foregroundColor: calendarPage.viewMode === 1 ? Theme.accent : Theme.textSecondary; onClicked: calendarPage.openNight(calendarPage.selectedDate) }
                HudButton {
                    text: "‹"; implicitWidth: 40
                    onClicked: {
                        if (calendarPage.viewMode === 0)
                            calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() - 1, 1)
                        else {
                            const value = new Date(calendarPage.selectedDate)
                            value.setDate(value.getDate() - 1)
                            calendarPage.selectedDate = value
                        }
                    }
                }
                HudButton { text: "TODAY"; onClicked: {
                    const key = calendarPage.currentObservingKey()
                    const today = calendarPage.dateFromKey(key)
                    calendarPage.shownMonth = today
                    calendarPage.selectedDate = today
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
                            calendarPage.selectedDate = value
                        }
                    }
                }
                HudButton { text: "+ NEW SESSION"; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate)) }
            }
            SelectionBar {
                active: calendarPage.viewMode === 1
                selectedCount: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).length
                totalCount: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length
                noun: "session"
                onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)), true)
                onClearRequested: calendarPage.selectedIds = ({})
                onDeleteRequested: {
                    const chosen = {}
                    const items = calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
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
                        property var daySessions: calendarPage.sessionsForDay(key)
                        readonly property bool isToday: key === calendarPage.currentObservingKey()
                        readonly property bool isSelected: key === calendarPage.dateKey(calendarPage.selectedDate)
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
                                calendarPage.selectedDate = dayCell.cellDate
                            }
                        }
                        Column {
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: 3
                            Text { text: dayCell.cellDate.getDate(); color: dayCell.isToday ? Theme.accent : dayCell.inMonth ? Theme.textPrimary : Theme.hsl(0.040, 0.262, 0.329); font.pixelSize: 11; font.bold: dayCell.isToday; font.family: Theme.fontMono }
                            Repeater {
                                model: dayCell.daySessions.slice(0, 3)
                                delegate: Rectangle {
                                    id: sessionChip
                                    required property var modelData
                                    property string sessionId: modelData.id
                                    readonly property color deviceTone: modelData.device_color || Theme.accent
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
                                        pressedAction: function() { calendarPage.selectedDate = dayCell.cellDate }
                                    }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: sessionMenu.open() }
                                    SessionContextMenu {
                                        onEditRequested: session => sessionDialog.openExisting(session)
                                        id: sessionMenu
                                        sessionData: sessionChip.modelData
                                        selectionItems: dayCell.daySessions
                                        selectedMap: calendarPage.selectedIds
                                        onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(dayCell.daySessions, true)
                                        onUnselectAllRequested: {
                                            calendarPage.selectedIds = ({})
                                            calendarPage.selectionAnchorId = ""
                                        }
                                    }
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
                                    onClicked: calendarPage.selectedDate = dayCell.cellDate
                                    onDoubleClicked: calendarPage.openNight(dayCell.cellDate)
                                }
                            }
                        }
                        TapHandler {
                            onTapped: calendarPage.selectedDate = dayCell.cellDate
                            onDoubleTapped: calendarPage.openNight(dayCell.cellDate)
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
                onVisibleChanged: {
                    if (visible)
                        calendarPage.requestNowLineScroll()
                }
                Flickable {
                    id: timelineFlick
                    anchors.fill: parent
                    clip: true
                    contentWidth: width
                    contentHeight: 24 * nightTimeline.hourHeight + 24
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
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
                            model: 25
                            delegate: Item {
                                required property int index
                                y: index * nightTimeline.hourHeight
                                width: timelineTrack.width
                                height: 1
                                Text {
                                    x: 4; y: -7; width: 52
                                    text: String((calendarPage.cutoffHour + index) % 24).padStart(2, "0") + ":00"
                                    color: Theme.textSecondary
                                    font.pixelSize: 10
                                    font.family: Theme.fontMono
                                }
                                Rectangle { x: 58; width: parent.width - 66; height: 1; color: index % 6 === 0 ? Theme.accent : Theme.outline; opacity: index % 6 === 0 ? 0.55 : 0.4 }
                            }
                        }
                        Repeater {
                            model: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
                            delegate: Rectangle {
                                id: timelineSession
                                required property var modelData
                                property string sessionId: modelData.id
                                x: 66
                                y: calendarPage.timelineMinutes(modelData.start_time) / 60 * nightTimeline.hourHeight + nightTimeline.itemOffset
                                width: timelineTrack.width - 82
                                height: Math.max(36, Number(modelData.planned_duration_seconds || 0) / 3600 * nightTimeline.hourHeight - 6)
                                radius: 3
                                color: Util.statusFill(modelData.status)
                                border.color: Util.statusColor(modelData.status)
                                border.width: 1
                                opacity: DragCoordinator.active && DragCoordinator.data.id === sessionId ? 0.35 : 0.96
                                SessionDragArea {
                                    dragItem: timelineSession.modelData
                                }
                                HoverHandler { id: timelineHover }
                                TapHandler {
                                    acceptedButtons: Qt.LeftButton
                                    acceptedModifiers: Qt.ShiftModifier
                                    onTapped: calendarPage.selectClick(timelineSession.modelData.id, true, calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)))
                                }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    anchors.leftMargin: 2
                                    spacing: 6
                                    RowGutter {
                                        Layout.preferredWidth: 20
                                        Layout.maximumWidth: 20
                                        Layout.fillHeight: true
                                        spineInset: 2
                                        spineColor: timelineSession.modelData.device_color || Theme.accent
                                        checked: Util.idSetHas(calendarPage.selectedIds, timelineSession.modelData.id)
                                        revealed: timelineHover.hovered || calendarPage.selectedCount > 0
                                        onToggled: (shiftHeld) => calendarPage.selectClick(timelineSession.modelData.id, shiftHeld, calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)))
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 0
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8
                                            Text { text: modelData.start_time; color: Theme.accent; font.family: Theme.fontMono; font.pixelSize: 12; font.bold: true }
                                            Text { text: modelData.target_name; color: Theme.textPrimary; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                            StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                        }
                                        Text { text: modelData.duration_text + "  ·  " + modelData.device_name; color: Theme.textSecondary; font.pixelSize: 10; visible: timelineSession.height > 48 }
                                    }
                                    HudButton { text: "EDIT"; implicitHeight: 24; visible: timelineSession.height > 44; onClicked: sessionDialog.openExisting(timelineSession.modelData) }
                                    HudButton { text: "RUN"; implicitHeight: 24; visible: timelineSession.height > 44; enabled: modelData.status !== "running"; onClicked: backend.runNow(modelData.id) }
                                }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: timelineMenu.popup() }
                                SessionContextMenu {
                                    onEditRequested: session => sessionDialog.openExisting(session)
                                    id: timelineMenu
                                    sessionData: timelineSession.modelData
                                    selectionItems: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
                                    selectedMap: calendarPage.selectedIds
                                    onSelectAllRequested: calendarPage.selectedIds = Util.idSetAll(calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)), true)
                                    onUnselectAllRequested: {
                                        calendarPage.selectedIds = ({})
                                        calendarPage.selectionAnchorId = ""
                                    }
                                }
                            }
                        }
                        Rectangle {
                            id: nowLine
                            visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey()
                            x: 58
                            width: parent.width - 66
                            height: 2
                            z: 20
                            color: Theme.warning
                            y: calendarPage.timelineMinutes(String(backend.clockText).substring(0, 5)) / 60 * nightTimeline.hourHeight
                            Text { anchors.right: parent.right; anchors.bottom: parent.top; text: "NOW"; color: Theme.warning; font.pixelSize: 9; font.bold: true }
                        }
                        Rectangle {
                            visible: DragCoordinator.active && DragCoordinator.previewMinutes >= 0
                            x: 58
                            width: parent.width - 66
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
                            x: 66
                            y: DragCoordinator.previewMinutes / 60 * nightTimeline.hourHeight + nightTimeline.itemOffset
                            width: timelineTrack.width - 82
                            height: Math.max(36, Number(DragCoordinator.data.planned_duration_seconds || 0) / 3600 * nightTimeline.hourHeight - 6)
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
                EmptyHint {
                    anchors.centerIn: parent
                    glyph: "☾"
                    visible: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length === 0
                    text: "Nothing scheduled for this night. Drop a session onto the timeline, or create a new one."
                }
            }
        }
        HudPanel {
            id: nightPanel
            readonly property var nightSessions: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
            readonly property int nightSeconds: nightSessions.reduce((sum, item) => sum + Number(item.planned_duration_seconds || 0), 0)
            visible: calendarPage.viewMode === 0
            title: Qt.formatDate(calendarPage.selectedDate, "ddd d MMM").toUpperCase()
            SplitView.preferredWidth: 312
            SplitView.minimumWidth: 220
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                HudChip { label: nightPanel.nightSessions.length + (nightPanel.nightSessions.length === 1 ? " SESSION" : " SESSIONS"); tone: nightPanel.nightSessions.length > 0 ? Theme.accent : Theme.textSecondary }
                HudChip { visible: nightPanel.nightSeconds > 0; label: "PLAN"; value: Util.formatDuration(nightPanel.nightSeconds); tone: Theme.textSecondary }
                HudChip { visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey(); label: "TONIGHT"; tone: Theme.warning; glow: true }
                Item { Layout.fillWidth: true }
            }
            SelectionBar {
                selectedCount: nightPanel.nightSessions.filter(item => Util.idSetHas(calendarPage.selectedIds, item.id)).length
                totalCount: nightPanel.nightSessions.length
                noun: "session"
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
                        model: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
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
                                spineColor: daySessionRow.modelData.device_color || Theme.accent
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
                                    Text { text: modelData.start_time; color: Theme.accent; font.pixelSize: 12; font.bold: true; font.family: Theme.fontMono }
                                    Text { text: modelData.target_name; color: Theme.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                }
                                Text { text: modelData.subtitle + " · " + modelData.duration_text; color: Theme.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                RowLayout {
                                    HudButton { text: "EDIT"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                    HudButton { text: "RESET"; implicitHeight: 24; visible: Util.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                    HudButton { text: "RUN"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
                                }
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: daySessionMenu.popup()
                            }
                            SessionContextMenu {
                                onEditRequested: session => sessionDialog.openExisting(session)
                                id: daySessionMenu
                                sessionData: daySessionRow.modelData
                                selectionItems: nightPanel.nightSessions
                                selectedMap: calendarPage.selectedIds
                                onSelectAllRequested: {
                                    const next = Object.assign({}, calendarPage.selectedIds)
                                    for (let i = 0; i < nightPanel.nightSessions.length; i++) {
                                        const id = nightPanel.nightSessions[i] && nightPanel.nightSessions[i].id
                                        if (id)
                                            next[id] = true
                                    }
                                    calendarPage.selectedIds = next
                                }
                                onUnselectAllRequested: {
                                    calendarPage.selectedIds = ({})
                                    calendarPage.selectionAnchorId = ""
                                }
                            }
                        }
                    }
                }
                EmptyHint {
                    anchors.centerIn: parent
                    glyph: "☾"
                    visible: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length === 0
                    text: "No sessions this observing night"
                }
            }
        }
    }
}
