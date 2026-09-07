import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import QtCore

ApplicationWindow {
    id: root
    width: Math.min(1480, Screen.desktopAvailableWidth - 24)
    height: Math.min(920, Screen.desktopAvailableHeight - 48)
    minimumWidth: 1040
    minimumHeight: 620
    visible: true
    title: "ASTRO DWARF"
    color: "#05080F"
    font.family: "Segoe UI"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
    readonly property bool windowMaximized: visibility === Window.Maximized

    function dragWindow() {
        if (!root.windowMaximized)
            root.startSystemMove()
    }

    function toggleMaximized() {
        if (root.windowMaximized)
            root.showNormal()
        else
            root.showMaximized()
    }

    property color surface: "#0B1520"
    property color surfaceHigh: "#122033"
    property color outline: "#1E4A63"
    property color textPrimary: "#E8F7FF"
    property color textSecondary: "#7FA4B8"
    property color accent: "#4DE8FF"
    property color success: "#3DFFB0"
    property color danger: "#FF6B7A"
    property color warning: "#F5C542"
    property color notice: "#5EE0D0"
    property color muted: "#4C6B80"
    property color glowAccent: "#334DE8FF"
    readonly property var scopeTelemetry: (backend.selectedDevice && backend.selectedDevice.telemetry) || ({})
    readonly property string scopeActivityDetail: String((backend.selectedDevice && backend.selectedDevice.activity_detail) || "")
    readonly property bool scopeActivityFromDevice: !!(backend.selectedDevice && backend.selectedDevice.activity_from_device)
    property int currentPage: 0
    property real joySpeed: 1
    property bool sessionDragActive: false
    property point sessionDragPos: Qt.point(0, 0)
    property var sessionDragData: ({})
    readonly property bool targetLocked: backend.selectedDevice.connected && backend.currentSession.status === "running"
    readonly property bool dataPage: currentPage !== 0
    readonly property bool scopeOnline: !!(backend.selectedDevice && backend.selectedDevice.connected)
    readonly property bool scopeImaging: !!(backend.selectedDevice && backend.selectedDevice.busy)
    readonly property bool scopeLinking: !!(backend.selectedDevice && (backend.selectedDevice.connecting || backend.selectedDevice.disconnecting))
    readonly property string scopePending: String((backend.selectedDevice && backend.selectedDevice.pending_action) || "")
    readonly property string scopeActivity: String((backend.selectedDevice && backend.selectedDevice.activity) || "")
    readonly property bool previewFailed: {
        const status = String(backend.previewStatus || "").toLowerCase()
        return status.indexOf("fail") >= 0 || status.indexOf("could not") >= 0
    }
    readonly property bool previewStarting: backend.previewActive && !backend.previewPlaying && !previewFailed
    readonly property bool scopeOccupied: scopeImaging || scopePending !== "" || scopeActivity !== "" || previewStarting
    readonly property bool cameraLiveEnabled: commandEnabled("set_exposure")
    readonly property bool motionEnabled: commandEnabled("joystick")

    function statusColor(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return root.accent
        case "error": return root.danger
        case "done": return root.success
        case "skipped": return root.textSecondary
        default: return root.textPrimary
        }
    }
    function formatDuration(seconds) {
        const total = Math.max(0, Math.round(Number(seconds || 0)))
        const h = Math.floor(total / 3600)
        const m = Math.floor((total % 3600) / 60)
        if (h > 0)
            return h + "h " + String(m).padStart(2, "0") + "m"
        if (m > 0)
            return m + "m"
        return total + "s"
    }
    function canReset(status) {
        const value = String(status || "").toLowerCase()
        return value === "error" || value === "skipped" || value === "done"
    }
    function toneForLevel(level) {
        switch (String(level || "").toLowerCase()) {
        case "error": return root.danger
        case "warning": return root.warning
        case "success": return root.success
        case "notice": return root.notice
        case "sdk":
        case "debug": return root.muted
        default: return root.accent
        }
    }
    function glyphForLevel(level) {
        switch (String(level || "").toLowerCase()) {
        case "error": return "✗"
        case "warning": return "⚠"
        case "success": return "✓"
        case "notice": return "◆"
        case "sdk": return "›"
        case "debug": return "·"
        default: return "●"
        }
    }
    function batteryTone(percent) {
        const value = Number(percent)
        if (isNaN(value) || value < 0)
            return "unknown"
        return value <= 10 ? "bad" : value <= 20 ? "warn" : "good"
    }
    function toneColor(tone) {
        switch (String(tone || "")) {
        case "bad": return root.danger
        case "warn": return root.warning
        case "good": return root.success
        default: return root.textSecondary
        }
    }
    function activityLabel(activity) {
        switch (String(activity || "")) {
        case "calibrate": return "CALIBRATING"
        case "goto": return "GOTO"
        case "polar": return "POLAR / EQ"
        case "autofocus": return "AUTOFOCUS"
        case "dark": return "DARK FRAMES"
        case "imaging": return "STACKING"
        case "record": return "RECORDING"
        case "burst": return "BURST"
        case "timelapse": return "TIMELAPSE"
        case "poweroff": return "POWER OFF"
        case "": return ""
        default: return String(activity).toUpperCase()
        }
    }
    function scopeActivityText() {
        if (root.scopePending)
            return "SENDING · " + root.scopePending.replace(/_/g, " ").toUpperCase()
        const label = root.activityLabel(root.scopeActivity)
        if (label)
            return root.scopeActivityDetail ? label + " · " + root.scopeActivityDetail : label
        if (root.scopeImaging)
            return "SESSION RUNNING"
        return root.scopeOnline ? "IDLE" : "OFFLINE"
    }
    function activityColor() {
        if (!root.scopeOnline)
            return root.textSecondary
        if (root.scopePending)
            return root.accent
        switch (root.scopeActivity) {
        case "imaging":
        case "record": return root.danger
        case "poweroff": return root.danger
        case "": return root.scopeImaging ? root.danger : root.success
        default: return root.notice
        }
    }
    function statusFill(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return "#123C52"
        case "error": return "#3A1218"
        case "done": return "#143028"
        default: return "#122033"
        }
    }
    function commandEnabled(op) {
        const pending = root.scopePending
        const activity = root.scopeActivity
        if (!root.scopeOnline || root.scopeLinking)
            return false
        if (pending === op)
            return false
        const stopFor = {
            burst: "burst_stop",
            burst_start: "burst_stop",
            record: "record_stop",
            record_start: "record_stop",
            timelapse: "timelapse_stop",
            timelapse_start: "timelapse_stop",
            calibrate: "stop_calibrate",
            autofocus: "stop_autofocus",
            infinity: "stop_autofocus",
            polar: "stop_polar",
            goto: "stop_goto"
        }
        if (op === "stop_all")
            return true
        const isStop = op === "stop_goto" || op.indexOf("stop_") === 0 || op.slice(-5) === "_stop"
        if (isStop) {
            if (op === stopFor[pending] || op === stopFor[activity])
                return true
            return op === "stop_goto" && !root.scopeOccupied
        }
        return !root.scopeOccupied
    }

    function requestDeviceAction(operation, label) {
        if (!root.commandEnabled(operation))
            return
        if (operation === "reboot" || operation === "power_down") {
            confirmDialog.kind = "device"
            confirmDialog.headingText = "CONFIRM COMMAND"
            confirmDialog.confirmLabel = "CONFIRM"
            confirmDialog.operation = operation
            confirmDialog.summary = "Run " + label + " on " + (backend.selectedDevice.name || "this telescope") + "?"
            confirmDialog.open()
            return
        }
        backend.deviceAction(backend.selectedDeviceId, operation)
    }

    function beginSessionDrag(item, pos) {
        sessionDragData = item
        sessionDragPos = pos
        sessionDragActive = true
    }
    function updateSessionDrag(pos) {
        sessionDragPos = pos
    }
    function endSessionDrag() {
        sessionDragActive = false
        sessionDragData = ({})
    }
    function startSessionDrag(item, pos) {
        sessionDragProxy.startDrag(item, pos)
    }
    function moveSessionDrag(pos) {
        sessionDragProxy.moveDrag(pos)
    }
    function finishSessionDrag() {
        sessionDragProxy.finishDrag()
    }
    function cancelSessionDrag() {
        sessionDragProxy.cancelDrag()
    }
    function dragSessionId(drop) {
        return String((sessionDragData && sessionDragData.id) || (drop && drop.source && drop.source.sessionId) || "")
    }
    function listRowAt(list, index) {
        if (!list || index < 0 || index >= list.count)
            return null
        const row = list.itemAtIndex(index)
        if (row && row.modelData)
            return row.modelData
        const model = list.model
        if (model && model[index])
            return model[index]
        return null
    }
    function reorderFromInsert(list, insertIndex, source) {
        if (!list || !source || !source.id || insertIndex < 0)
            return
        if (String(source.status || "").toLowerCase() !== "planned")
            return
        const count = list.count
        let from = -1
        for (let i = 0; i < count; i++) {
            const row = root.listRowAt(list, i)
            if (row && String(row.id) === String(source.id)) {
                from = i
                break
            }
        }
        if (from >= 0 && (insertIndex === from || insertIndex === from + 1))
            return
        let beforeId = ""
        for (let i = Math.max(0, insertIndex); i < count; i++) {
            const target = root.listRowAt(list, i)
            if (!target || String(target.id) === String(source.id))
                continue
            if (String(target.device_id) !== String(source.device_id))
                continue
            if (String(target.status || "").toLowerCase() !== "planned")
                continue
            beforeId = String(target.id)
            break
        }
        backend.reorderPlanned(String(source.id), beforeId)
    }
    function dropAreaShown(item) {
        for (let node = item; node; node = node.parent) {
            if (node.visible === false)
                return false
        }
        return !!(item && item.width > 0 && item.height > 0)
    }
    function listDropTarget(pos) {
        const areas = [upcomingInsert, daySessionInsert, scheduledInsert]
        for (let i = 0; i < areas.length; i++) {
            const area = areas[i]
            if (!root.dropAreaShown(area))
                continue
            const local = area.mapFromItem(root.contentItem, pos.x, pos.y)
            if (local.x < 0 || local.y < 0 || local.x > area.width || local.y > area.height)
                continue
            return { list: area.targetList, index: area.indexAtY(local.y) }
        }
        return null
    }
    function completeSessionDrag(pos) {
        root.moveSessionDrag(pos)
        const source = sessionDragData
        const target = root.listDropTarget(pos)
        if (target) {
            sessionDragProxy.cancelDrag()
            Qt.callLater(function() {
                root.reorderFromInsert(target.list, target.index, source)
            })
            return
        }
        sessionDragProxy.finishDrag()
    }
    function dragLabel(item) {
        if (!item || !item.id)
            return ""
        return (item.start_time || "") + "  " + (item.target_name || item.name || "Session")
    }
    function durationLabel(seconds) {
        const value = Math.max(0, Math.round(Number(seconds) || 0))
        const hours = Math.floor(value / 3600)
        const minutes = Math.floor((value % 3600) / 60)
        const secs = value % 60
        return hours > 0
            ? hours + "h " + String(minutes).padStart(2, "0") + "m"
            : minutes > 0 ? minutes + "m " + String(secs).padStart(2, "0") + "s" : secs + "s"
    }
    function nextSessionCountdown() {
        backend.clockText
        if (!backend.upcomingSessions || backend.upcomingSessions.length === 0)
            return "No planned sessions"
        const start = new Date(backend.upcomingSessions[0].scheduled_start)
        const seconds = Math.floor((start.getTime() - Date.now()) / 1000)
        return seconds <= 0 ? "Due now" : "T− " + durationLabel(seconds)
    }

    function targetCoordinates(item) {
        const target = item && item.target ? item.target : null
        if (!target || target.ra_hours === undefined || target.ra_hours === null
                || target.dec_degrees === undefined || target.dec_degrees === null)
            return ""
        return "RA " + Number(target.ra_hours).toFixed(3) + "h  DEC "
            + Number(target.dec_degrees).toFixed(3) + "°"
    }

    function logLine(item) {
        return item ? item.time + "  [" + item.device + "]  " + item.message : ""
    }

    function allLogText() {
        return backend.allLogText()
    }

    function asset(name) { return Qt.resolvedUrl("assets/" + name) }
    function deviceLabel() {
        const dev = backend.selectedDevice || {}
        const name = String(dev.name || "No device")
        const model = String(dev.model || "")
        if (model === "" || model.toLowerCase() === name.toLowerCase())
            return name
        return name + "  ·  " + model
    }
    function goToPage(idx) {
        if (idx === root.currentPage) {
            if (idx === 4 && !settingsPage.isDirty())
                settingsPage.load()
            return
        }
        if (root.currentPage === 4 && settingsPage.isDirty()) {
            settingsLeaveDialog.pendingPage = idx
            settingsLeaveDialog.open()
            return
        }
        root.currentPage = idx
        if (idx === 4)
            settingsPage.load()
    }
    function syncCombo(combo) {
        if (!combo || combo.count === 0)
            return
        for (let i = 0; i < combo.count; i++) {
            if (combo.valueAt(i) === backend.selectedDeviceId) {
                combo.currentIndex = i
                return
            }
        }
    }

    component HiddenBar: ScrollBar {
        policy: ScrollBar.AlwaysOff
        interactive: false
        visible: false
        implicitWidth: 0
        implicitHeight: 0
    }

    component HudPanel: Item {
        id: panel
        property alias title: heading.text
        property alias headerExtra: headerExtraRow.data
        property alias overlay: overlayHost.data
        property color fill: "#B3070D16"
        default property alias contents: body.data
        implicitWidth: 240
        implicitHeight: (headerRow.visible ? headerRow.implicitHeight + 17 : 0) + body.implicitHeight + 24
        clip: true

        Rectangle { anchors.fill: parent; color: panel.fill }
        Canvas {
            anchors.fill: parent
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const w = width, h = height, n = 11
                ctx.strokeStyle = "#66E8FFFF"
                ctx.lineWidth = 1.25
                ctx.beginPath()
                ctx.moveTo(n, 1.5)
                ctx.lineTo(w - n, 1.5)
                ctx.lineTo(w - 1.5, n)
                ctx.lineTo(w - 1.5, h - n)
                ctx.lineTo(w - n, h - 1.5)
                ctx.lineTo(n, h - 1.5)
                ctx.lineTo(1.5, h - n)
                ctx.lineTo(1.5, n)
                ctx.closePath()
                ctx.stroke()
                // accent corner ticks
                ctx.strokeStyle = "#CC4DE8FF"
                ctx.lineWidth = 2
                const t = 14
                ctx.beginPath()
                ctx.moveTo(n, 1.5); ctx.lineTo(n + t, 1.5)
                ctx.moveTo(1.5, n); ctx.lineTo(1.5, n + t)
                ctx.moveTo(w - n, h - 1.5); ctx.lineTo(w - n - t, h - 1.5)
                ctx.moveTo(w - 1.5, h - n); ctx.lineTo(w - 1.5, h - n - t)
                ctx.stroke()
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8
            RowLayout {
                id: headerRow
                visible: heading.text.length || headerExtraRow.children.length
                Layout.fillWidth: true
                spacing: 8
                Text {
                    id: heading
                    visible: text.length
                    color: root.accent
                    font.pixelSize: 11
                    font.letterSpacing: 1.6
                    font.bold: true
                    Layout.fillWidth: true
                }
                Row {
                    id: headerExtraRow
                    spacing: 4
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                }
            }
            Rectangle {
                visible: headerRow.visible
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                implicitHeight: 1
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.6) }
                    GradientStop { position: 0.55; color: "#331E4A63" }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
            Flickable {
                id: panelFlick
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                contentWidth: width
                contentHeight: Math.max(height, body.implicitHeight)
                interactive: contentHeight > height + 1
                ScrollBar.vertical: HiddenBar {}
                ScrollBar.horizontal: HiddenBar {}
                Item {
                    width: panelFlick.width
                    height: Math.max(body.implicitHeight, panelFlick.height)
                    ColumnLayout {
                        id: body
                        anchors.fill: parent
                        spacing: 8
                    }
                }
            }
        }
        Item {
            id: overlayHost
            anchors.fill: parent
            z: 5
        }
    }

    component HudButton: Button {
        id: hudBtn
        property color buttonColor: root.surfaceHigh
        property color foregroundColor: root.textPrimary
        property string busyText: ""
        property bool busy: false
        property int busyMs: 1400
        property bool _clickBusy: false
        readonly property bool isBusy: busy || _clickBusy
        hoverEnabled: enabled
        opacity: enabled || isBusy ? 1 : 0.42
        font.pixelSize: 12
        font.letterSpacing: 0.6
        leftPadding: 12
        rightPadding: 12
        implicitHeight: 34
        Timer {
            id: clickBusyTimer
            interval: Math.max(1, hudBtn.busyMs)
            repeat: false
            onTriggered: hudBtn._clickBusy = false
        }
        onClicked: {
            if (hudBtn.busyText === "" || hudBtn.busy || hudBtn.busyMs <= 0)
                return
            hudBtn._clickBusy = true
            clickBusyTimer.restart()
        }
        background: Rectangle {
            color: !hudBtn.enabled && !hudBtn.isBusy ? "#070B12" : hudBtn.down || hudBtn.isBusy ? Qt.darker(hudBtn.buttonColor, 1.2) : hudBtn.hovered ? Qt.lighter(hudBtn.buttonColor, 1.18) : hudBtn.buttonColor
            border.color: !hudBtn.enabled && !hudBtn.isBusy ? "#152838" : hudBtn.hovered || hudBtn.down || hudBtn.isBusy ? root.accent : root.outline
            border.width: hudBtn.hovered || hudBtn.down || hudBtn.isBusy ? 2 : 1
            radius: 3
            Rectangle { x: 3; y: 3; width: parent.width - 6; height: 1; color: hudBtn.enabled ? "#467B94" : "transparent"; opacity: 0.55 }
            Rectangle { x: 3; y: parent.height - 4; width: parent.width - 6; height: 1; color: "#02050A"; opacity: 0.9 }
        }
        contentItem: Text {
            text: (hudBtn.isBusy && hudBtn.busyText !== "") ? hudBtn.busyText : hudBtn.text
            color: hudBtn.enabled || hudBtn.isBusy ? hudBtn.foregroundColor : root.textSecondary
            font: hudBtn.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component SessionDragArea: MouseArea {
        required property var dragItem
        property var pressedAction: null
        acceptedButtons: Qt.LeftButton
        hoverEnabled: true
        preventStealing: true
        cursorShape: enabled ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor
        enabled: String((dragItem && dragItem.status) || "") !== "running"
        property bool dragging: false
        property real pressX: 0
        property real pressY: 0
        onPressed: mouse => {
            pressX = mouse.x
            pressY = mouse.y
            dragging = false
            if (pressedAction)
                pressedAction()
        }
        onPositionChanged: mouse => {
            if (!pressed)
                return
            const dx = mouse.x - pressX
            const dy = mouse.y - pressY
            if (!dragging && (dx * dx + dy * dy) < 36)
                return
            const pos = mapToItem(root.contentItem, mouse.x, mouse.y)
            if (!dragging) {
                dragging = true
                root.startSessionDrag(dragItem, pos)
            } else {
                root.moveSessionDrag(pos)
            }
        }
        onReleased: mouse => {
            if (dragging) {
                const pos = mapToItem(root.contentItem, mouse.x, mouse.y)
                root.completeSessionDrag(pos)
            }
            dragging = false
        }
        onCanceled: {
            if (dragging)
                root.cancelSessionDrag()
            dragging = false
        }
    }

    component SessionInsertDrop: DropArea {
        id: insertDrop
        required property var targetList
        required property real rowHeight
        keys: ["session"]
        readonly property int insertIndex: {
            if (!root.sessionDragActive || !insertDrop.targetList)
                return -1
            const pos = insertDrop.mapFromItem(root.contentItem, root.sessionDragPos.x, root.sessionDragPos.y)
            if (pos.x < 0 || pos.y < 0 || pos.x > insertDrop.width || pos.y > insertDrop.height)
                return -1
            return insertDrop.indexAtY(pos.y)
        }
        readonly property real insertLineY: {
            const list = insertDrop.targetList
            if (!list)
                return -999
            return insertDrop.insertIndex * (insertDrop.rowHeight + list.spacing) - list.contentY - 1
        }

        function indexAtY(y) {
            const list = insertDrop.targetList
            if (!list)
                return 0
            const stride = Math.max(1, insertDrop.rowHeight + list.spacing)
            let idx = Math.round((y + list.contentY) / stride)
            if (idx < 0)
                return 0
            if (idx > list.count)
                return list.count
            return idx
        }

        onDropped: drop => {
            drop.accept()
            root.reorderFromInsert(insertDrop.targetList, insertDrop.insertIndex, root.sessionDragData)
        }

        Rectangle {
            z: 1000
            enabled: false
            width: parent.width
            height: 2
            color: root.accent
            visible: insertDrop.insertIndex >= 0 && insertDrop.insertLineY >= -2 && insertDrop.insertLineY <= insertDrop.height
            y: insertDrop.insertLineY
        }
    }

    component HudCommandPad: Button {
        id: commandPad
        property string glyph: ""
        property string detail: ""
        property bool activeState: false
        property bool pending: false
        property bool destructive: false
        property string flash: ""   // "", "success" or "error"
        readonly property color flashColor: flash === "error" ? root.danger : root.success
        hoverEnabled: enabled
        implicitHeight: 58
        leftPadding: 8
        rightPadding: 8
        function showFlash(kind) {
            flash = kind
            flashTimer.restart()
        }
        Timer { id: flashTimer; interval: 900; onTriggered: commandPad.flash = "" }
        background: Rectangle {
            id: padBackground
            color: commandPad.flash !== "" ? Qt.rgba(commandPad.flashColor.r, commandPad.flashColor.g, commandPad.flashColor.b, 0.22)
                 : commandPad.destructive ? "#301117" : commandPad.activeState ? "#123C35" : commandPad.pending ? "#0F2A3C" : commandPad.down ? "#0B2430" : commandPad.hovered ? "#123044" : "#0B1724"
            border.color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.destructive ? root.danger : commandPad.activeState ? root.success : commandPad.pending || commandPad.hovered ? root.accent : root.outline
            border.width: commandPad.activeState || commandPad.hovered || commandPad.pending || commandPad.flash !== "" ? 2 : 1
            radius: 4
            Behavior on color { ColorAnimation { duration: 160 } }
            Behavior on border.color { ColorAnimation { duration: 160 } }
            Rectangle { x: 4; y: 4; width: parent.width - 8; height: 1; color: commandPad.destructive ? root.danger : root.accent; opacity: 0.35 }
            Rectangle {
                // pulsing ring while the device reports the command running
                anchors.fill: parent
                anchors.margins: -3
                radius: 6
                color: "transparent"
                border.color: commandPad.activeState ? root.success : root.accent
                border.width: 1
                visible: commandPad.activeState || commandPad.pending
                opacity: 0
                SequentialAnimation on opacity {
                    running: commandPad.activeState || commandPad.pending
                    loops: Animation.Infinite
                    NumberAnimation { from: 0.7; to: 0; duration: commandPad.pending ? 600 : 1100; easing.type: Easing.OutQuad }
                    PauseAnimation { duration: commandPad.pending ? 150 : 400 }
                }
            }
            Rectangle {
                anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7
                width: 7; height: 7; radius: 4
                color: commandPad.activeState ? root.success : commandPad.pending ? root.accent : commandPad.enabled ? "#31556B" : "#172631"
                border.color: commandPad.activeState ? "#C8FFE9" : root.outline
                SequentialAnimation on opacity {
                    running: commandPad.pending
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.2; duration: 320 }
                    NumberAnimation { from: 0.2; to: 1; duration: 320 }
                }
            }
        }
        contentItem: RowLayout {
            spacing: 7
            Text { text: commandPad.glyph; color: commandPad.destructive ? root.danger : commandPad.activeState ? root.success : root.accent; font.pixelSize: Math.round(Math.min(26, Math.max(16, commandPad.height * 0.32))); Layout.preferredWidth: font.pixelSize + 6; horizontalAlignment: Text.AlignHCenter }
            ColumnLayout {
                Layout.fillWidth: true; spacing: 0
                Text { text: commandPad.text; color: commandPad.enabled || commandPad.activeState ? root.textPrimary : root.textSecondary; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.7; elide: Text.ElideRight; Layout.fillWidth: true }
                Text { text: commandPad.flash === "success" ? "DONE" : commandPad.flash === "error" ? "FAILED" : commandPad.pending ? "SENDING…" : commandPad.detail; color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.activeState ? root.success : commandPad.pending ? root.accent : root.textSecondary; font.pixelSize: 8; font.family: commandPad.activeState ? "Cascadia Mono" : root.font.family; elide: Text.ElideRight; Layout.fillWidth: true }
            }
        }
    }

    component LedDot: Rectangle {
        id: led
        property bool on: false
        property color onColor: root.success
        property bool pulse: false
        width: 7; height: 7; radius: 4
        color: on ? onColor : "#263746"
        border.color: on ? "#D8FFFF" : root.outline
        Behavior on color { ColorAnimation { duration: 200 } }
        Rectangle {
            id: ledRing
            anchors.centerIn: parent
            width: led.width; height: led.height; radius: width / 2
            color: "transparent"
            border.color: led.onColor
            visible: led.on && led.pulse
            SequentialAnimation on scale {
                running: ledRing.visible
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 2.2; duration: 1200; easing.type: Easing.OutQuad }
                PauseAnimation { duration: 600 }
            }
            SequentialAnimation on opacity {
                running: ledRing.visible
                loops: Animation.Infinite
                NumberAnimation { from: 0.8; to: 0; duration: 1200 }
                PauseAnimation { duration: 600 }
            }
        }
    }

    component HudChip: Rectangle {
        id: chip
        property string label: ""
        property string value: ""
        property color tone: root.accent
        property bool glow: false
        property bool dim: false
        implicitHeight: 20
        implicitWidth: chipRowLayout.implicitWidth + 14
        radius: 3
        color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.05 : 0.14)
        border.color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.25 : 0.55)
        opacity: dim ? 0.6 : 1
        Behavior on color { ColorAnimation { duration: 200 } }
        Rectangle {
            anchors.fill: parent; anchors.margins: -2; radius: 5
            color: "transparent"; border.color: chip.tone; opacity: 0.3
            visible: chip.glow && !chip.dim
        }
        RowLayout {
            id: chipRowLayout
            anchors.centerIn: parent
            spacing: 5
            Text { visible: chip.label !== ""; text: chip.label; color: chip.tone; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
            Text { visible: chip.value !== ""; text: chip.value; color: root.textPrimary; font.pixelSize: 10; font.family: "Cascadia Mono" }
        }
    }

    component BatteryGauge: Item {
        id: gauge
        property int percent: -1
        property bool charging: false
        property string tone: root.batteryTone(percent)
        readonly property color toneColor: percent < 0 ? root.muted : root.toneColor(tone)
        property real shown: Math.max(0, percent)
        Behavior on shown { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
        implicitWidth: 72
        implicitHeight: 72
        Canvas {
            anchors.fill: parent
            readonly property real value: gauge.shown
            readonly property color ring: gauge.toneColor
            onValueChanged: requestPaint()
            onRingChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 5
                const start = Math.PI * 0.75, span = Math.PI * 1.5
                ctx.lineCap = "round"
                ctx.lineWidth = 5
                ctx.strokeStyle = "#16283A"
                ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span); ctx.stroke()
                // tick marks
                ctx.lineWidth = 1
                ctx.strokeStyle = "#2A4A62"
                for (let i = 0; i <= 10; i++) {
                    const a = start + span * i / 10
                    ctx.beginPath()
                    ctx.moveTo(cx + Math.cos(a) * (r - 8), cy + Math.sin(a) * (r - 8))
                    ctx.lineTo(cx + Math.cos(a) * (r - 11), cy + Math.sin(a) * (r - 11))
                    ctx.stroke()
                }
                if (gauge.percent >= 0) {
                    ctx.lineWidth = 5
                    ctx.strokeStyle = ring
                    ctx.shadowColor = ring
                    ctx.shadowBlur = 8
                    ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span * Math.min(1, value / 100)); ctx.stroke()
                }
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }
        Column {
            anchors.centerIn: parent
            anchors.verticalCenterOffset: 2
            spacing: -2
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: gauge.percent >= 0 ? gauge.percent + "%" : "—"
                color: gauge.percent >= 0 ? root.textPrimary : root.muted
                font.pixelSize: gauge.width >= 70 ? 16 : 13
                font.family: "Cascadia Mono"
                font.bold: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: gauge.charging ? "⚡ CHG" : "BATT"
                color: gauge.charging ? root.warning : root.textSecondary
                font.pixelSize: 8
                font.letterSpacing: 1
                font.bold: true
                SequentialAnimation on opacity {
                    running: gauge.charging
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.35; duration: 700 }
                    NumberAnimation { from: 0.35; to: 1; duration: 700 }
                }
            }
        }
    }

    component StorageBar: Item {
        id: storage
        property real fraction: 0      // used fraction 0..1
        property string text: "—"
        property string tone: "unknown"
        property bool valid: true
        readonly property color toneColor: !valid ? root.danger : tone === "unknown" ? root.muted : (tone === "good" ? root.accent : root.toneColor(tone))
        property real shown: fraction
        Behavior on shown { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
        implicitHeight: 10
        Rectangle {
            anchors.fill: parent
            radius: 2
            color: "#0A1524"
            border.color: storage.valid ? root.outline : root.danger
            Rectangle {
                x: 1; y: 1
                height: parent.height - 2
                width: Math.max(0, (parent.width - 2) * Math.min(1, storage.shown))
                radius: 1
                color: storage.toneColor
                opacity: storage.valid ? 0.9 : 0
            }
            Row {
                anchors.fill: parent
                anchors.margins: 1
                spacing: 0
                Repeater {
                    model: 8
                    Item {
                        width: parent.width / 8; height: parent.height
                        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#05080F"; opacity: 0.8; visible: index < 7 }
                    }
                }
            }
        }
    }

    component VitalTile: Rectangle {
        id: tile
        property string label: ""
        property string value: "—"
        property string unit: ""
        property string glyph: ""
        property color tone: root.accent
        property bool stale: false
        property bool live: false
        property bool dimmed: value === "—" || value === ""
        implicitHeight: 46
        radius: 3
        color: "#66091422"
        border.color: live ? Qt.rgba(tone.r, tone.g, tone.b, 0.6) : "#1A3A50"
        border.width: 1
        Behavior on border.color { ColorAnimation { duration: 200 } }
        Rectangle { x: 0; y: 5; width: 2; height: parent.height - 10; color: tile.dimmed ? "#1E4A63" : tile.tone; opacity: tile.dimmed ? 0.5 : 0.9 }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 9
            anchors.rightMargin: 8
            spacing: 6
            Text { visible: tile.glyph !== ""; text: tile.glyph; color: tile.dimmed ? root.muted : tile.tone; font.pixelSize: 14; Layout.preferredWidth: 16; horizontalAlignment: Text.AlignHCenter }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Text { text: tile.label; color: root.textSecondary; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.1; elide: Text.ElideRight; Layout.fillWidth: true }
                RowLayout {
                    spacing: 3
                    Layout.fillWidth: true
                    Text {
                        text: tile.value
                        color: tile.dimmed ? root.muted : root.textPrimary
                        font.pixelSize: 14
                        font.family: "Cascadia Mono"
                        font.bold: true
                        elide: Text.ElideRight
                        Layout.maximumWidth: tile.width - 60
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                    Text { visible: tile.unit !== "" && !tile.dimmed; text: tile.unit; color: root.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 2 }
                    Item { Layout.fillWidth: true }
                }
            }
        }
        Text {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 4
            visible: tile.stale && !tile.dimmed
            text: "STALE"
            color: root.warning
            font.pixelSize: 7
            font.bold: true
            font.letterSpacing: 1
            opacity: 0.85
        }
    }

    component HudMenu: Menu {
        id: hudMenu
        popupType: Popup.Item
        implicitWidth: 232
        padding: 6
        topPadding: 6
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6
        overlap: 2
        background: Rectangle {
            color: root.surfaceHigh
            border.color: root.outline
            border.width: 1
            radius: 8
        }
    }

    component HudMenuItem: MenuItem {
        id: hudMenuItem
        property string glyph: ""
        property string trailingText: ""
        property bool destructive: false
        implicitWidth: 220
        implicitHeight: 34
        leftPadding: 8
        rightPadding: 10
        topPadding: 0
        bottomPadding: 0
        opacity: enabled ? 1 : 0.4
        font.pixelSize: 13
        background: Rectangle {
            color: hudMenuItem.highlighted || hudMenuItem.down ? "#123C52" : "transparent"
            radius: 4
        }
        contentItem: RowLayout {
            spacing: 10
            Text {
                Layout.preferredWidth: 18
                text: hudMenuItem.glyph
                color: hudMenuItem.destructive ? root.danger : root.textSecondary
                font.family: "Segoe MDL2 Assets"
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                Layout.fillWidth: true
                text: hudMenuItem.text
                color: hudMenuItem.destructive ? root.danger : root.textPrimary
                font: hudMenuItem.font
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                visible: text.length > 0
                text: hudMenuItem.trailingText
                color: root.textSecondary
                font.pixelSize: 11
                elide: Text.ElideMiddle
                Layout.maximumWidth: 92
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    component HudMenuSeparator: MenuSeparator {
        implicitHeight: 9
        contentItem: Rectangle {
            implicitHeight: 1
            color: root.outline
        }
        leftPadding: 8
        rightPadding: 8
        topPadding: 4
        bottomPadding: 4
    }

    component SessionContextMenu: HudMenu {
        id: sessionContextMenu
        property var sessionData: ({})
        readonly property string sessionId: String((sessionData && sessionData.id) || "")
        readonly property string sessionStatus: String((sessionData && sessionData.status) || "")
        readonly property string coordinates: root.targetCoordinates(sessionData)

        HudMenuItem {
            text: "Edit"
            glyph: "\uE70F"
            enabled: sessionContextMenu.sessionStatus !== "running"
            onTriggered: sessionDialog.openExisting(sessionContextMenu.sessionData)
        }
        HudMenuItem {
            text: "Run now"
            glyph: "\uE768"
            enabled: sessionContextMenu.sessionStatus !== "running"
            onTriggered: backend.runNow(sessionContextMenu.sessionId)
        }
        HudMenuItem {
            text: "Skip"
            glyph: "\uE769"
            enabled: sessionContextMenu.sessionStatus === "planned"
            onTriggered: backend.skipSession(sessionContextMenu.sessionId)
        }
        HudMenuItem {
            text: "Reset"
            glyph: "\uE72C"
            enabled: root.canReset(sessionContextMenu.sessionStatus)
            onTriggered: backend.resetSession(sessionContextMenu.sessionId)
        }
        HudMenuItem {
            text: "Duplicate"
            glyph: "\uE8C8"
            onTriggered: backend.duplicateSession(sessionContextMenu.sessionId)
        }
        HudMenuSeparator {}
        HudMenuItem {
            text: "Copy target name"
            glyph: "\uE8C8"
            enabled: !!(sessionContextMenu.sessionData && sessionContextMenu.sessionData.target_name)
            onTriggered: backend.copyText(String(sessionContextMenu.sessionData.target_name))
        }
        HudMenuItem {
            text: "Copy RA / Dec"
            glyph: "\uE8C8"
            enabled: sessionContextMenu.coordinates !== ""
            onTriggered: backend.copyText(sessionContextMenu.coordinates)
        }
        HudMenuSeparator {}
        HudMenuItem {
            text: "Delete"
            glyph: "\uE74D"
            destructive: true
            enabled: sessionContextMenu.sessionStatus !== "running"
            onTriggered: backend.deleteSession(sessionContextMenu.sessionId)
        }
    }

    component HudSplitView: SplitView {
        handle: Rectangle {
            implicitWidth: 8
            implicitHeight: 8
            color: SplitHandle.pressed ? "#334DE8FF" : (SplitHandle.hovered ? "#221E4A63" : "transparent")
            Rectangle {
                anchors.centerIn: parent
                width: parent.width >= parent.height ? 22 : 2
                height: parent.width >= parent.height ? 2 : 22
                radius: 1
                color: SplitHandle.pressed ? root.accent : (SplitHandle.hovered ? root.accent : root.outline)
            }
        }
    }

    Settings {
        id: layoutSettings
        category: "controlLayout"
        property var columnsState
        property var leftState
        property var centerState
        property var rightState
        property var calendarState
        property bool navBarOnTop: false
    }

    function restoreSplit(view, state) {
        if (view && state)
            view.restoreState(state)
    }

    function saveLayout() {
        layoutSettings.columnsState = controlColumns.saveState()
        layoutSettings.leftState = controlLeft.saveState()
        layoutSettings.centerState = controlCenter.saveState()
        layoutSettings.rightState = controlRight.saveState()
        layoutSettings.calendarState = calendarSplit.saveState()
    }

    onClosing: saveLayout()

    Timer {
        interval: 1
        running: true
        repeat: false
        onTriggered: {
            restoreSplit(controlColumns, layoutSettings.columnsState)
            restoreSplit(controlLeft, layoutSettings.leftState)
            restoreSplit(controlCenter, layoutSettings.centerState)
            restoreSplit(controlRight, layoutSettings.rightState)
            restoreSplit(calendarSplit, layoutSettings.calendarState)
            root.maybeAskLocation()
        }
    }

    function maybeAskLocation() {
        const configured = !!backend.selectedDevice.location_configured
        if (!configured) {
            if (!locationDialog.visible)
                locationDialog.open()
            return
        }
        if (locationDialog.visible)
            locationDialog.close()
    }

    component HudField: TextField {
        id: field
        color: field.enabled ? root.textPrimary : root.textSecondary
        placeholderTextColor: root.textSecondary
        selectedTextColor: "#041018"
        selectionColor: root.accent
        opacity: field.enabled ? 1 : 0.45
        font.pixelSize: 13
        leftPadding: 10
        rightPadding: 10
        implicitHeight: 34
        background: Rectangle {
            color: field.enabled ? "#0A1524" : "#070B12"
            border.color: !field.enabled ? "#152838" : field.activeFocus ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
    }

    component HudCombo: ComboBox {
        id: combo
        implicitHeight: 34
        font.pixelSize: 13
        palette.window: "#02060C"
        palette.windowText: root.textPrimary
        palette.base: "#02060C"
        palette.text: root.textPrimary
        palette.button: "#0A1524"
        palette.buttonText: root.textPrimary
        palette.highlight: "#123C52"
        palette.highlightedText: root.accent
        opacity: combo.enabled ? 1 : 0.45
        background: Rectangle {
            color: combo.enabled ? "#0A1524" : "#070B12"
            border.color: !combo.enabled ? "#152838" : combo.hovered || combo.down ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
        contentItem: Text {
            leftPadding: 10
            rightPadding: 22
            text: combo.displayText
            color: combo.enabled ? root.textPrimary : root.textSecondary
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            text: "▾"
            color: combo.enabled ? root.accent : root.textSecondary
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
        }
        delegate: ItemDelegate {
            width: combo.width
            height: 32
            highlighted: combo.highlightedIndex === index
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.text: root.textPrimary
            palette.highlightedText: root.accent
            contentItem: Text {
                text: combo.textAt(index)
                color: highlighted ? root.accent : root.textPrimary
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                leftPadding: 10
            }
            background: Rectangle { color: highlighted ? "#123C52" : "#02060C" }
        }
        popup: Popup {
            y: combo.height + 3
            width: combo.width
            padding: 1
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.base: "#02060C"
            palette.text: root.textPrimary
            background: Rectangle { color: "#02060C"; border.color: root.accent }
            contentItem: ListView {
                clip: true
                implicitHeight: Math.min(contentHeight, 240)
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
            }
        }
    }

    component HudSearchCombo: Item {
        id: searchCombo
        property var allItems: []
        property int filterLimit: 120
        property string selectedName: ""
        property alias editText: searchField.text
        property bool listOpen: false
        property var filtered: []
        signal itemChosen(var item)
        implicitHeight: 34
        implicitWidth: 240

        function copyAllItems() {
            const items = searchCombo.allItems || []
            const out = []
            for (let i = 0; i < items.length; i++)
                out.push(items[i])
            return out
        }

        function indexOfCurrent(items) {
            const name = searchCombo.selectedName
            const text = String(searchField.text || "")
            for (let i = 0; i < items.length; i++) {
                if ((name && items[i].name === name) || items[i].name === text || items[i].label === text)
                    return i
            }
            return items.length ? 0 : -1
        }

        function revealCurrent() {
            const idx = suggestionView.currentIndex
            if (idx < 0)
                return
            suggestionView.positionViewAtIndex(idx, ListView.Center)
        }

        function openFullList() {
            const items = copyAllItems()
            const idx = searchCombo.indexOfCurrent(items)
            searchCombo.filtered = items
            searchCombo.listOpen = true
            Qt.callLater(function () {
                suggestionView.currentIndex = idx
                searchCombo.revealCurrent()
                if (searchCombo.selectedName)
                    searchField.selectAll()
            })
        }

        function refreshFilter() {
            const needle = String(searchField.text || "").toLowerCase().replace(/_/g, " ")
            if (!needle) {
                const items = copyAllItems()
                searchCombo.filtered = items
                suggestionView.currentIndex = searchCombo.indexOfCurrent(items)
                Qt.callLater(searchCombo.revealCurrent)
                return
            }
            const items = searchCombo.allItems || []
            const ranked = []
            for (let i = 0; i < items.length; i++) {
                const item = items[i]
                const hay = [item.name, item.label, item.comment].join(" ").toLowerCase().replace(/_/g, " ")
                if (hay.indexOf(needle) < 0)
                    continue
                const city = String(item.name).split("/").pop().toLowerCase().replace(/_/g, " ")
                let score = 2
                if (city === needle || String(item.name).toLowerCase() === needle)
                    score = 0
                else if (city.startsWith(needle) || String(item.name).toLowerCase().replace(/_/g, " ").startsWith(needle))
                    score = 1
                ranked.push({score: score, name: item.name, item: item})
            }
            ranked.sort(function (a, b) { return a.score - b.score || a.name.localeCompare(b.name) })
            const out = []
            for (let i = 0; i < ranked.length && i < searchCombo.filterLimit; i++)
                out.push(ranked[i].item)
            searchCombo.filtered = out
            suggestionView.currentIndex = out.length ? 0 : -1
        }

        function setFromName(name) {
            searchCombo.selectedName = name || ""
            searchCombo.listOpen = false
            let label = name || ""
            const items = searchCombo.allItems || []
            for (let i = 0; i < items.length; i++) {
                if (items[i].name === name) {
                    label = items[i].label
                    break
                }
            }
            searchField.text = label
        }

        function chooseItem(item) {
            if (!item)
                return
            searchCombo.selectedName = item.name || ""
            searchCombo.listOpen = false
            searchField.text = item.label || item.name || ""
            searchCombo.itemChosen(item)
        }

        function acceptTyped() {
            if (listOpen && suggestionView.currentIndex >= 0 && suggestionView.currentIndex < filtered.length) {
                chooseItem(filtered[suggestionView.currentIndex])
                return
            }
            backend.lookupLocation(searchField.text)
        }

        onListOpenChanged: {
            if (listOpen) {
                if (!suggestionPopup.opened)
                    suggestionPopup.open()
            } else if (suggestionPopup.opened) {
                suggestionPopup.close()
            }
        }

        HudField {
            id: searchField
            width: parent.width
            height: parent.height
            placeholderText: "Search city or timezone"
            rightPadding: 26
            Keys.priority: Keys.BeforeItem
            onTextEdited: {
                searchCombo.selectedName = ""
                searchCombo.refreshFilter()
                searchCombo.listOpen = true
            }
            onActiveFocusChanged: {
                if (activeFocus && !searchCombo.listOpen)
                    searchCombo.openFullList()
            }
            MouseArea {
                anchors.fill: parent
                anchors.rightMargin: 26
                propagateComposedEvents: true
                onPressed: function (mouse) {
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    mouse.accepted = false
                }
            }
            Keys.onPressed: function (event) {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    else if (suggestionView.currentIndex < filtered.length - 1)
                        suggestionView.incrementCurrentIndex()
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    else if (suggestionView.currentIndex > 0)
                        suggestionView.decrementCurrentIndex()
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    event.accepted = true
                    searchCombo.acceptTyped()
                } else if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    searchCombo.listOpen = false
                } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                    searchCombo.listOpen = false
                }
            }
        }
        Text {
            text: "▾"
            color: root.accent
            z: 2
            anchors.right: searchField.right
            anchors.rightMargin: 8
            anchors.verticalCenter: searchField.verticalCenter
            MouseArea {
                anchors.fill: parent
                anchors.margins: -8
                onClicked: {
                    if (searchCombo.listOpen) {
                        searchCombo.listOpen = false
                        return
                    }
                    searchField.forceActiveFocus()
                    searchCombo.openFullList()
                }
            }
        }
        Popup {
            id: suggestionPopup
            y: searchField.height + 3
            width: Math.max(searchCombo.width, 360)
            height: Math.min(Math.max(searchCombo.filtered.length, 1), 10) * 32 + 2
            padding: 1
            modal: false
            focus: false
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.base: "#02060C"
            palette.text: root.textPrimary
            background: Rectangle { color: "#02060C"; border.color: root.accent }
            onOpened: searchCombo.listOpen = true
            onClosed: searchCombo.listOpen = false
            contentItem: Item {
                ListView {
                    id: suggestionView
                    anchors.fill: parent
                    clip: true
                    visible: searchCombo.filtered.length > 0
                    boundsBehavior: Flickable.StopAtBounds
                    model: searchCombo.filtered
                    currentIndex: 0
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    onCurrentIndexChanged: {
                        if (currentIndex >= 0)
                            positionViewAtIndex(currentIndex, ListView.Contain)
                    }
                    delegate: Rectangle {
                        width: suggestionView.width
                        height: 32
                        readonly property var item: modelData
                        readonly property int row: index
                        color: suggestionView.currentIndex === row ? "#123C52" : "#02060C"
                        Text {
                            anchors.fill: parent
                            leftPadding: 10
                            rightPadding: 10
                            text: item && (item.label || item.name) || ""
                            color: suggestionView.currentIndex === row ? root.accent : root.textPrimary
                            font.pixelSize: 13
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onEntered: suggestionView.currentIndex = row
                            onClicked: searchCombo.chooseItem(item)
                        }
                    }
                }
                Text {
                    anchors.fill: parent
                    visible: searchCombo.filtered.length === 0
                    leftPadding: 10
                    text: "No matches"
                    color: root.textSecondary
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    component DeviceCombo: HudCombo {
        id: deviceCombo
        model: backend.devices
        textRole: "name"
        valueRole: "id"
        implicitWidth: 200
        onActivated: if (currentValue) backend.selectDevice(currentValue)
        Component.onCompleted: root.syncCombo(deviceCombo)
        Connections {
            target: backend
            function onSelectedDeviceChanged() { root.syncCombo(deviceCombo) }
            function onDevicesChanged() { root.syncCombo(deviceCombo) }
        }
    }

    component HudCheck: CheckBox {
        id: box
        font.pixelSize: 13
        contentItem: Text {
            text: box.text
            color: root.textPrimary
            font: box.font
            leftPadding: box.indicator.width + 8
            verticalAlignment: Text.AlignVCenter
        }
        indicator: Rectangle {
            implicitWidth: 18
            implicitHeight: 18
            x: box.leftPadding
            y: parent.height / 2 - height / 2
            color: box.checked ? "#123C52" : "#0A1524"
            border.color: root.accent
            Text { anchors.centerIn: parent; text: box.checked ? "✓" : ""; color: root.accent; font.pixelSize: 12 }
        }
    }

    component FieldLabel: Text {
        color: root.textSecondary
        font.pixelSize: 10
        font.letterSpacing: 1.1
        font.bold: true
        Layout.preferredWidth: 110
        Layout.alignment: Qt.AlignVCenter
    }

    component EmptyHint: Column {
        id: hint
        property string text: ""
        property string glyph: "◇"
        property alias font: hintText.font
        property alias color: hintText.color
        spacing: 6
        width: Math.min(360, parent ? parent.width - 24 : 320)
        // when placed inside a Layout the width binding is overridden, so size via Layout hints too
        Layout.preferredWidth: 360
        Layout.minimumWidth: 160
        Layout.fillWidth: false
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: hint.glyph !== ""
            text: hint.glyph
            color: root.accent
            opacity: 0.55
            font.pixelSize: 22
            Rectangle {
                anchors.centerIn: parent
                width: parent.implicitHeight + 18; height: width; radius: width / 2
                color: "transparent"
                border.color: root.accent
                opacity: 0.35
            }
        }
        Text {
            id: hintText
            width: hint.width
            text: hint.text
            color: root.textSecondary
            font.pixelSize: 12
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
        }
    }

    component PageHeader: RowLayout {
        id: pageHeader
        property string title: ""
        property string subtitle: ""
        property string glyph: ""
        default property alias actions: pageActions.data
        Layout.fillWidth: true
        spacing: 10
        Rectangle { width: 3; Layout.preferredHeight: 34; color: root.accent; radius: 1 }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            RowLayout {
                spacing: 8
                Text { visible: pageHeader.glyph !== ""; text: pageHeader.glyph; color: root.accent; font.pixelSize: 16 }
                Text { text: pageHeader.title; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2.4; font.bold: true }
            }
            Text { visible: pageHeader.subtitle !== ""; text: pageHeader.subtitle; color: root.textSecondary; font.pixelSize: 11; font.letterSpacing: 0.4; elide: Text.ElideRight; Layout.fillWidth: true }
        }
        Row {
            id: pageActions
            spacing: 8
            Layout.fillWidth: false
            Layout.preferredWidth: implicitWidth
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        }
    }

    component StatusChip: Rectangle {
        id: statusChip
        property string status: ""
        readonly property color tone: root.statusColor(status)
        readonly property bool running: String(status || "").toLowerCase() === "running"
        implicitHeight: 18
        implicitWidth: statusChipText.implicitWidth + 16
        radius: 3
        color: root.statusFill(status)
        border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.7)
        Rectangle {
            anchors.fill: parent; anchors.margins: -2; radius: 5
            color: "transparent"; border.color: statusChip.tone
            opacity: 0.3
            visible: statusChip.running
            SequentialAnimation on opacity {
                running: statusChip.running
                loops: Animation.Infinite
                NumberAnimation { to: 0.05; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.45; duration: 900; easing.type: Easing.InOutSine }
            }
        }
        Text {
            id: statusChipText
            anchors.centerIn: parent
            text: String(statusChip.status || "").toUpperCase()
            color: statusChip.tone
            font.pixelSize: 8
            font.bold: true
            font.letterSpacing: 1.2
        }
    }

    component PageNavBar: RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 48
        Layout.maximumHeight: 48
        Layout.fillHeight: false
        Layout.leftMargin: 10
        Layout.rightMargin: 10
        spacing: 8
        Repeater {
            model: [
                {label: "CONTROL", idx: 0},
                {label: "CALENDAR", idx: 1},
                {label: "SESSIONS", idx: 2},
                {label: "HISTORY", idx: 3},
                {label: "SETTINGS", idx: 4}
            ]
            delegate: HudButton {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Layout.fillHeight: false
                text: modelData.label
                font.pixelSize: 12
                font.letterSpacing: 1.4
                buttonColor: root.currentPage === modelData.idx ? "#0E3A48" : "#0A1524"
                foregroundColor: root.currentPage === modelData.idx ? root.accent : root.textSecondary
                onClicked: root.goToPage(modelData.idx)
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 1
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: 2
                    width: root.currentPage === parent.modelData.idx ? parent.width - 24 : 0
                    color: root.accent
                    Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                }
            }
        }
    }

    Item {
        id: shell
        anchors.fill: parent
        Image {
            anchors.fill: parent
            source: root.asset("hud-background.png")
            fillMode: Image.PreserveAspectCrop
            opacity: root.dataPage ? 0.14 : 0.42
        }
        Rectangle { anchors.fill: parent; color: root.dataPage ? "#CC030810" : "#99030810" }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.maximumHeight: 64
            Layout.fillHeight: false
            color: "#C0050A12"
            border.color: root.outline
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.15; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.7) }
                    GradientStop { position: 0.85; color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.7) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 10
                spacing: 14
                Item {
                    implicitWidth: brand.implicitWidth
                    implicitHeight: brand.implicitHeight
                    Column {
                        id: brand
                        Text { text: "ASTRO DWARF"; color: root.accent; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                        Text { text: "OBSERVATORY COMMAND  ·  v" + backend.appVersion; color: root.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 12; Layout.bottomMargin: 12; color: root.outline }
                DeviceCombo {}
                HudButton {
                    text: backend.selectedDevice.connected ? "DISCONNECT" : "CONNECT"
                    busy: backend.selectedDevice.connecting || backend.selectedDevice.disconnecting
                    busyText: backend.selectedDevice.connecting ? "CONNECTING…" : "DISCONNECTING…"
                    busyMs: 0
                    enabled: !busy
                    buttonColor: backend.selectedDevice.connected ? "#143028" : "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: backend.selectedDevice.connected
                        ? backend.disconnectDevice(backend.selectedDeviceId)
                        : backend.connectDevice(backend.selectedDeviceId)
                }
                HudButton {
                    text: backend.schedulerEnabled ? "SCHEDULER ON" : "SCHEDULER OFF"
                    busyText: "UPDATING…"
                    buttonColor: backend.schedulerEnabled ? "#143028" : root.surfaceHigh
                    foregroundColor: backend.schedulerEnabled ? root.success : root.textPrimary
                    onClicked: backend.setSchedulerEnabled(!backend.schedulerEnabled)
                }
                HudButton {
                    text: "STOP ALL"
                    busy: backend.selectedDevice.pending_action === "stop_all"
                    busyText: "STOPPING…"
                    busyMs: 0
                    // A running session must always be stoppable, even while the link is still coming up.
                    enabled: root.commandEnabled("stop_all") || (root.scopeImaging && root.scopePending !== "stop_all")
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: backend.stopDevice(backend.selectedDeviceId)
                }
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                RowLayout {
                    spacing: 10
                    Repeater {
                        model: [
                            {label: "LINK", on: root.scopeOnline, color: root.success},
                            {label: "AUTO", on: backend.schedulerEnabled, color: root.success},
                            {label: "IMAGE", on: root.scopeImaging || root.scopeActivity === "imaging", color: root.danger}
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            spacing: 4
                            LedDot { on: modelData.on; onColor: modelData.color; pulse: true }
                            Text { text: modelData.label; color: modelData.on ? root.textPrimary : root.textSecondary; font.pixelSize: 8; font.bold: true }
                        }
                    }
                    Rectangle { width: 1; Layout.preferredHeight: 18; color: root.outline; visible: root.scopeOnline }
                    RowLayout {
                        // mini battery readout
                        id: titleBattery
                        readonly property var t: root.scopeTelemetry
                        readonly property int percent: root.scopeOnline && t.battery_percent !== undefined ? Number(t.battery_percent) : -1
                        readonly property color tone: percent < 0 ? root.muted : root.toneColor(root.batteryTone(percent))
                        visible: root.scopeOnline
                        spacing: 5
                        Item {
                            implicitWidth: 22
                            implicitHeight: 11
                            Rectangle {
                                anchors.left: parent.left; anchors.top: parent.top
                                width: 19; height: 11; radius: 2
                                color: "transparent"
                                border.color: titleBattery.tone
                                Rectangle {
                                    x: 2; y: 2
                                    height: parent.height - 4
                                    width: Math.max(0, (parent.width - 4) * Math.max(0, titleBattery.percent) / 100)
                                    color: titleBattery.tone
                                    Behavior on width { NumberAnimation { duration: 500 } }
                                    SequentialAnimation on opacity {
                                        running: !!titleBattery.t.charging
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1; to: 0.35; duration: 700 }
                                        NumberAnimation { from: 0.35; to: 1; duration: 700 }
                                    }
                                }
                            }
                            Rectangle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: 2; height: 5; color: titleBattery.tone }
                        }
                        Text {
                            text: titleBattery.percent >= 0 ? titleBattery.percent + "%" + (titleBattery.t.charging ? "⚡" : "") : "—"
                            color: titleBattery.percent >= 0 ? root.textPrimary : root.textSecondary
                            font.pixelSize: 10; font.family: "Cascadia Mono"; font.bold: true
                        }
                        ToolTip.visible: batteryHover.hovered
                        ToolTip.delay: 400
                        ToolTip.text: "Battery " + (titleBattery.t.battery_text || "—") + (titleBattery.t.charging_text ? "  ·  " + titleBattery.t.charging_text : "") + (titleBattery.t.battery_health_text ? "\n" + titleBattery.t.battery_health_text : "")
                        HoverHandler { id: batteryHover }
                    }
                    RowLayout {
                        // mini storage readout
                        id: titleStorage
                        readonly property var t: root.scopeTelemetry
                        visible: root.scopeOnline
                        spacing: 5
                        Text { text: "▤"; color: titleStorage.t.storage_tone === "bad" ? root.danger : titleStorage.t.storage_tone === "warn" ? root.warning : root.accent; font.pixelSize: 11 }
                        Text {
                            text: root.scopeOnline && titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? String(titleStorage.t.storage_free_text || titleStorage.t.storage_text) : "—"
                            color: titleStorage.t.storage_tone === "bad" ? root.danger : titleStorage.t.storage_tone === "warn" ? root.warning : (titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? root.textPrimary : root.textSecondary)
                            font.pixelSize: 10; font.family: "Cascadia Mono"; font.bold: true
                        }
                        ToolTip.visible: storageHover.hovered
                        ToolTip.delay: 400
                        ToolTip.text: "Storage " + (titleStorage.t.storage_text || "—")
                        HoverHandler { id: storageHover }
                    }
                }
                Column {
                    Text { text: backend.selectedDevice.status || "OFFLINE"; color: backend.selectedDevice.connected ? root.success : root.textSecondary; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignRight; width: 160 }
                    Text { text: root.deviceLabel(); color: root.textSecondary; font.pixelSize: 10; horizontalAlignment: Text.AlignRight; width: 160; elide: Text.ElideRight }
                }
                Text { text: backend.clockText; color: root.accent; font.pixelSize: 22; font.family: "Cascadia Mono"; font.letterSpacing: 1 }
            }
        }

        Rectangle {
            id: deviceRail
            readonly property bool shown: backend.devices.length > 1
            Layout.fillWidth: true
            Layout.preferredHeight: shown ? 30 : 0
            Layout.maximumHeight: shown ? 30 : 0
            Layout.fillHeight: false
            visible: shown
            color: "#80050A12"
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: root.outline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12
                Text {
                    text: "DEVICES"
                    color: root.textSecondary
                    font.pixelSize: 9
                    font.bold: true
                    font.letterSpacing: 1.6
                }
                Rectangle { width: 1; Layout.preferredHeight: 14; color: root.outline }
                ListView {
                    id: deviceChips
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    orientation: ListView.Horizontal
                    spacing: 4
                    clip: true
                    model: backend.devices
                    delegate: Item {
                        id: deviceCard
                        required property var modelData
                        readonly property bool selected: modelData.id === backend.selectedDeviceId
                        width: chipRow.implicitWidth + 24
                        height: deviceChips.height
                        Rectangle {
                            anchors.fill: parent
                            anchors.topMargin: 3
                            anchors.bottomMargin: 3
                            radius: 3
                            color: deviceCard.selected ? "#A0123C52" : (chipHover.hovered ? "#500E2030" : "transparent")
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            height: 2
                            width: deviceCard.selected ? parent.width - 16 : 0
                            color: root.accent
                            Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        }
                        RowLayout {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 7
                            Rectangle { width: 8; height: 8; radius: 4; color: deviceCard.modelData.color }
                            Text {
                                text: deviceCard.modelData.name
                                color: deviceCard.selected ? root.textPrimary : root.textSecondary
                                font.pixelSize: 11
                                font.bold: deviceCard.selected
                            }
                            Text {
                                text: deviceCard.modelData.model
                                color: root.textSecondary
                                font.pixelSize: 9
                                opacity: 0.8
                            }
                            Text {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && t.battery_percent !== undefined && Number(t.battery_percent) >= 0
                                text: (t.battery_percent !== undefined ? t.battery_percent : "") + "%" + (t.charging ? "⚡" : "")
                                color: root.toneColor(root.batteryTone(t.battery_percent))
                                font.pixelSize: 9; font.family: "Cascadia Mono"; font.bold: true
                            }
                            HudChip {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && (deviceCard.modelData.busy || !!t.capture_active)
                                label: t.capture_active ? "STACK" : "IMAGING"
                                value: String(t.capture_text || "")
                                tone: root.danger
                                implicitHeight: 16
                            }
                            Rectangle {
                                width: 6; height: 6; radius: 3
                                color: deviceCard.modelData.connected ? (deviceCard.modelData.busy ? root.danger : root.success) : "#526077"
                                border.color: deviceCard.modelData.connected ? "#D8FFFF" : "transparent"
                                border.width: deviceCard.modelData.connected ? 1 : 0
                                SequentialAnimation on opacity {
                                    running: deviceCard.modelData.connecting || deviceCard.modelData.disconnecting
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.25; duration: 500 }
                                    NumberAnimation { from: 0.25; to: 1; duration: 500 }
                                }
                            }
                        }
                        ToolTip.visible: chipHover.hovered && !deviceMenu.visible
                        ToolTip.delay: 600
                        ToolTip.text: deviceCard.modelData.status + (deviceCard.modelData.ip_address ? "  ·  " + deviceCard.modelData.ip_address : "")
                        HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            acceptedButtons: Qt.LeftButton
                            onTapped: backend.selectDevice(deviceCard.modelData.id)
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: deviceMenu.popup()
                        }
                        HudMenu {
                            id: deviceMenu
                            HudMenuItem {
                                text: deviceCard.modelData.connected ? "Disconnect" : "Connect"
                                glyph: deviceCard.modelData.connected ? "\uE8CD" : "\uE774"
                                enabled: !deviceCard.modelData.connecting && !deviceCard.modelData.disconnecting
                                onTriggered: {
                                    backend.selectDevice(deviceCard.modelData.id)
                                    if (deviceCard.modelData.connected)
                                        backend.disconnectDevice(deviceCard.modelData.id)
                                    else
                                        backend.connectDevice(deviceCard.modelData.id)
                                }
                            }
                            HudMenuItem {
                                text: "Open settings"
                                glyph: "\uE713"
                                onTriggered: {
                                    backend.selectDevice(deviceCard.modelData.id)
                                    root.currentPage = 4
                                }
                            }
                            HudMenuSeparator {}
                            HudMenuItem {
                                text: "Copy IP address"
                                glyph: "\uE8C8"
                                trailingText: String(deviceCard.modelData.ip_address || "")
                                enabled: trailingText !== ""
                                onTriggered: backend.copyText(trailingText)
                            }
                            HudMenuSeparator {}
                            HudMenuItem {
                                text: "Remove device"
                                glyph: "\uE74D"
                                destructive: true
                                visible: backend.devices.length > 1
                                onTriggered: backend.deleteDevice(deviceCard.modelData.id)
                            }
                        }
                    }
                }
            }
        }

        PageNavBar {
            visible: layoutSettings.navBarOnTop
            Layout.topMargin: 8
        }

        StackLayout {
            id: pages
            currentIndex: root.currentPage
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 360
            Layout.margins: 10

            Item {
                id: controlPage
                HudSplitView {
                    id: controlColumns
                    anchors.fill: parent
                    orientation: Qt.Horizontal

                    HudSplitView {
                        id: controlLeft
                        orientation: Qt.Vertical
                        SplitView.preferredWidth: 268
                        SplitView.minimumWidth: 196

                        HudPanel {
                            title: "SYSTEM STATUS"
                            SplitView.preferredHeight: 214
                            SplitView.minimumHeight: 120
                            headerExtra: HudChip {
                                label: root.scopeTelemetry.host_text && root.scopeTelemetry.host_text !== "—" ? root.scopeTelemetry.host_text : ""
                                tone: root.scopeTelemetry.host_mode === false ? root.warning : root.success
                                visible: root.scopeOnline && label !== ""
                                dim: !root.scopeOnline
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                LedDot {
                                    width: 10; height: 10; radius: 5
                                    on: true
                                    pulse: root.scopeOnline && (root.scopeImaging || root.scopeActivity !== "")
                                    onColor: root.scopeLinking ? root.warning : root.scopeImaging ? root.danger : root.scopeOnline ? root.success : root.danger
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 0
                                    Text {
                                        id: statusHeading
                                        text: String(backend.selectedDevice.status || "OFFLINE").toUpperCase()
                                        color: root.scopeLinking ? root.warning : root.scopeImaging ? root.danger : root.scopeOnline ? root.success : root.textSecondary
                                        font.pixelSize: 15; font.bold: true; font.letterSpacing: 1.4
                                        Behavior on color { ColorAnimation { duration: 200 } }
                                        SequentialAnimation on opacity {
                                            running: root.scopeImaging || root.scopeLinking
                                            loops: Animation.Infinite
                                            NumberAnimation { from: 1; to: 0.55; duration: 800; easing.type: Easing.InOutSine }
                                            NumberAnimation { from: 0.55; to: 1; duration: 800; easing.type: Easing.InOutSine }
                                            onRunningChanged: if (!running) statusHeading.opacity = 1
                                        }
                                    }
                                    Text { text: root.deviceLabel(); color: root.textSecondary; font.pixelSize: 9 }
                                }
                            }
                            Rectangle {
                                // derived activity line from device telemetry
                                id: activityLine
                                Layout.fillWidth: true
                                implicitHeight: 30
                                radius: 3
                                readonly property color tone: root.activityColor()
                                color: Qt.rgba(tone.r, tone.g, tone.b, root.scopeOnline ? 0.12 : 0.04)
                                border.color: Qt.rgba(tone.r, tone.g, tone.b, root.scopeOnline ? 0.5 : 0.2)
                                Behavior on color { ColorAnimation { duration: 220 } }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 9
                                    anchors.rightMargin: 9
                                    spacing: 8
                                    Text { text: root.scopePending ? "⇡" : root.scopeActivity !== "" ? "◈" : root.scopeImaging ? "●" : root.scopeOnline ? "◇" : "○"; color: activityLine.tone; font.pixelSize: 12 }
                                    Text {
                                        text: root.scopeActivityText()
                                        color: activityLine.tone
                                        font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2
                                        font.family: "Cascadia Mono"
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    Text {
                                        visible: root.scopeActivityFromDevice
                                        text: "DEVICE"
                                        color: root.textSecondary
                                        font.pixelSize: 7; font.bold: true; font.letterSpacing: 1
                                    }
                                }
                            }
                            Repeater {
                                model: [
                                    {label: "ENDPOINT", value: backend.selectedDevice.ip_address || "—", tone: root.scopeOnline ? root.textPrimary : root.textSecondary},
                                    {label: "SCHEDULER", value: backend.schedulerEnabled ? root.nextSessionCountdown() : "Disarmed", tone: backend.schedulerEnabled ? root.success : root.textSecondary},
                                    {label: "PREVIEW", value: backend.previewActive ? (backend.previewPlaying ? "Live" : backend.previewStatus || "Starting") : "Stopped", tone: backend.previewPlaying ? root.danger : backend.previewActive ? root.warning : root.textSecondary},
                                    {label: "SESSION", value: backend.currentSession.current_step || "No active session", tone: backend.currentSession.id ? root.accent : root.textSecondary},
                                    {label: "REMAINING", value: backend.currentSession.id ? root.durationLabel(Number(backend.currentSession.planned_duration_seconds || 0) * (1 - backend.sessionProgress)) : "—", tone: root.textPrimary},
                                    {label: "TIMEZONE", value: backend.selectedDevice.timezone_name || "UTC", tone: root.textPrimary},
                                    {label: "LAT / LON", value: Number(backend.selectedDevice.latitude || 0).toFixed(2) + "°, " + Number(backend.selectedDevice.longitude || 0).toFixed(2) + "°", tone: root.textPrimary}
                                ]
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 6
                                    Text { text: modelData.label; color: root.textSecondary; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.8; Layout.preferredWidth: 72 }
                                    Rectangle { Layout.fillWidth: true; Layout.minimumWidth: 12; Layout.preferredHeight: 1; color: "#1A3A50"; opacity: 0.7 }
                                    Text { text: modelData.value; color: modelData.tone; font.pixelSize: 10; font.family: "Cascadia Mono"; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true; Layout.maximumWidth: implicitWidth }
                                }
                            }
                        }

                        HudPanel {
                            id: vitalsPanel
                            title: "VITALS"
                            SplitView.preferredHeight: 262
                            SplitView.minimumHeight: 150
                            readonly property var t: root.scopeTelemetry
                            readonly property bool live: root.scopeOnline && !!t.has_data
                            readonly property bool stale: !!t.stale
                            opacity: root.scopeOnline ? 1 : 0.55
                            Behavior on opacity { NumberAnimation { duration: 240 } }
                            headerExtra: Row {
                                spacing: 4
                                HudChip {
                                    label: vitalsPanel.stale ? "STALE" : vitalsPanel.live ? "LIVE" : "NO DATA"
                                    tone: vitalsPanel.stale ? root.warning : vitalsPanel.live ? root.success : root.muted
                                    glow: vitalsPanel.live && !vitalsPanel.stale
                                    dim: !vitalsPanel.live
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                BatteryGauge {
                                    percent: vitalsPanel.live && vitalsPanel.t.battery_percent !== undefined ? Number(vitalsPanel.t.battery_percent) : -1
                                    charging: !!vitalsPanel.t.charging && vitalsPanel.live
                                    Layout.preferredWidth: 74
                                    Layout.preferredHeight: 74
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { text: "STORAGE"; color: root.textSecondary; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.1; Layout.fillWidth: true }
                                        Text {
                                            text: vitalsPanel.live ? String(vitalsPanel.t.storage_text || "—") : "—"
                                            color: vitalsPanel.live && vitalsPanel.t.storage_tone && vitalsPanel.t.storage_tone !== "unknown" && vitalsPanel.t.storage_tone !== "good" ? root.toneColor(vitalsPanel.t.storage_tone) : root.textPrimary
                                            font.pixelSize: 11; font.family: "Cascadia Mono"; font.bold: true
                                        }
                                    }
                                    StorageBar {
                                        Layout.fillWidth: true
                                        fraction: vitalsPanel.live ? Number(vitalsPanel.t.storage_percent || 0) : 0
                                        tone: vitalsPanel.live ? String(vitalsPanel.t.storage_tone || "unknown") : "unknown"
                                        valid: !vitalsPanel.live || vitalsPanel.t.storage_valid !== false
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: vitalsPanel.live ? (vitalsPanel.t.storage_percent ? Math.round(Number(vitalsPanel.t.storage_percent) * 100) + "% USED" : (vitalsPanel.t.storage_valid === false ? "CARD MISSING" : "")) : ""
                                        color: root.textSecondary; font.pixelSize: 8; font.letterSpacing: 0.8; elide: Text.ElideRight
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 4
                                        HudChip { label: vitalsPanel.t.charging_text || "BATT"; tone: vitalsPanel.t.charging ? root.warning : root.textSecondary; dim: !vitalsPanel.live; visible: vitalsPanel.live && !!vitalsPanel.t.charging_text }
                                        Text { visible: !!vitalsPanel.t.battery_health_text && vitalsPanel.live; text: vitalsPanel.t.battery_health_text || ""; color: root.textSecondary; font.pixelSize: 8; font.letterSpacing: 0.6; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Item { Layout.fillWidth: true; visible: !vitalsPanel.t.battery_health_text }
                                    }
                                }
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: width >= 250 ? 2 : 1
                                columnSpacing: 6
                                rowSpacing: 6
                                VitalTile { Layout.fillWidth: true; glyph: "♨"; label: "BODY TEMP"; value: vitalsPanel.live ? String(vitalsPanel.t.temperature_text || "—") : "—"; tone: root.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                                VitalTile { Layout.fillWidth: true; glyph: "◉"; label: backend.selectedDevice.camera === "wide" ? "WIDE SENSOR" : "TELE SENSOR"; value: vitalsPanel.live ? String((backend.selectedDevice.camera === "wide" ? vitalsPanel.t.cmos_wide_text : vitalsPanel.t.cmos_tele_text) || "—") : "—"; tone: root.notice; stale: vitalsPanel.stale; live: vitalsPanel.live }
                                VitalTile { Layout.fillWidth: true; glyph: "⌾"; label: "FOCUS"; value: vitalsPanel.live ? String(vitalsPanel.t.focus_text || "—") : "—"; unit: "STEPS"; tone: root.scopeActivity === "autofocus" ? root.notice : root.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                                VitalTile { Layout.fillWidth: true; glyph: "⛭"; label: "MOUNT"; value: vitalsPanel.live ? String(vitalsPanel.t.mount_text || "—") : "—"; unit: vitalsPanel.t.mount_mode === "EQ" ? "EQUATORIAL" : vitalsPanel.t.mount_mode === "AZ" ? "ALT-AZ" : ""; tone: vitalsPanel.t.mount_mode === "EQ" ? root.success : root.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                                VitalTile { Layout.fillWidth: true; glyph: "▶"; label: "STREAM"; value: vitalsPanel.live ? String(vitalsPanel.t.stream_text || "—") : "—"; unit: vitalsPanel.t.shooting_mode_text && vitalsPanel.t.shooting_mode_text !== "—" ? vitalsPanel.t.shooting_mode_text : ""; tone: backend.previewPlaying ? root.danger : root.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                                VitalTile {
                                    Layout.fillWidth: true
                                    glyph: "✦"
                                    label: "LIGHTS"
                                    value: vitalsPanel.live ? (vitalsPanel.t.lights_on ? "RING ON" : "RING OFF") : "—"
                                    unit: vitalsPanel.live ? (vitalsPanel.t.indicator_on ? "· LED ON" : "· LED OFF") : ""
                                    tone: vitalsPanel.t.lights_on ? root.warning : root.accent
                                    stale: vitalsPanel.stale
                                    live: vitalsPanel.live
                                }
                            }
                            Text {
                                visible: !root.scopeOnline
                                Layout.fillWidth: true
                                text: "Connect the telescope to stream battery, storage and sensor telemetry."
                                color: root.textSecondary; font.pixelSize: 9; wrapMode: Text.Wrap
                            }
                            Text {
                                id: vitalsWaiting
                                visible: root.scopeOnline && !vitalsPanel.live
                                Layout.fillWidth: true
                                text: "Waiting for the first device report…"
                                color: root.textSecondary; font.pixelSize: 9
                                SequentialAnimation on opacity { running: vitalsWaiting.visible; loops: Animation.Infinite; NumberAnimation { to: 0.4; duration: 700 } NumberAnimation { to: 1; duration: 700 } }
                            }
                        }

                        HudPanel {
                            id: targetPanel
                            title: "TARGET"
                            SplitView.preferredHeight: 140
                            SplitView.minimumHeight: 80
                            headerExtra: HudChip {
                                readonly property var t: root.scopeTelemetry
                                readonly property bool tracking: !!t.tracking_active
                                readonly property bool slewing: root.scopeActivity === "goto"
                                visible: root.scopeOnline && (tracking || slewing || !!t.capture_active)
                                label: slewing ? "GOTO" : t.capture_active ? "STACKING" : "TRACKING"
                                value: slewing ? "" : String(t.capture_text || "")
                                tone: slewing ? root.notice : t.capture_active ? root.danger : root.success
                                glow: true
                            }
                            Text {
                                text: {
                                    const t = root.scopeTelemetry
                                    const deviceTarget = String(t.capture_target || t.tracking_target || "")
                                    if (backend.currentSession.target_name)
                                        return backend.currentSession.target_name
                                    if (root.scopeOnline && deviceTarget)
                                        return deviceTarget
                                    return backend.selectedDevice.connected ? "No active lock" : "No telescope link"
                                }
                                color: root.textPrimary
                                font.pixelSize: 18
                                font.bold: true
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: !!(backend.currentSession.target && (backend.currentSession.target.ra_hours || backend.currentSession.target.ra_hours === 0))
                                text: backend.currentSession.target
                                    ? "RA  " + Number(backend.currentSession.target.ra_hours).toFixed(3) + "h   DEC  " + Number(backend.currentSession.target.dec_degrees).toFixed(3) + "°"
                                    : ""
                                color: root.textSecondary
                                font.pixelSize: 11
                            }
                            Text {
                                text: {
                                    const t = root.scopeTelemetry
                                    if (backend.currentSession.current_step) {
                                        const frames = String(t.capture_text || "")
                                        return frames && t.capture_active ? backend.currentSession.current_step + "  ·  " + frames + " frames" : backend.currentSession.current_step
                                    }
                                    if (!backend.selectedDevice.connected)
                                        return "Connect to acquire a lock"
                                    if (root.scopeActivity === "goto")
                                        return "Slewing to " + (t.tracking_target || root.scopeActivityDetail || "target")
                                    if (t.tracking_active)
                                        return "Tracking " + (t.tracking_target || "target") + (t.stacked_text ? "  ·  " + t.stacked_text : "")
                                    return "Telescope ready"
                                }
                                color: root.scopeTelemetry.tracking_active || root.scopeActivity === "goto" ? root.notice : root.textSecondary
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: backend.currentSession.duration_text ? "PLANNED  " + backend.currentSession.duration_text : "WAITING FOR SCHEDULE"; color: root.accent; font.pixelSize: 11; font.letterSpacing: 0.8; Layout.fillWidth: true; elide: Text.ElideRight }
                                Text { visible: !!backend.currentSession.id; text: Math.round(backend.sessionProgress * 100) + "%"; color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono" }
                            }
                            ProgressBar {
                                id: sessionBar
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: backend.sessionProgress
                                readonly property bool idle: !backend.currentSession.id
                                background: Rectangle { implicitHeight: 8; color: "#0A1524"; border.color: root.outline }
                                contentItem: Item {
                                    implicitHeight: 8
                                    clip: true
                                    Rectangle {
                                        visible: !sessionBar.idle
                                        width: sessionBar.visualPosition * parent.width
                                        height: parent.height
                                        color: root.accent
                                    }
                                    Rectangle {
                                        id: idleSweep
                                        visible: sessionBar.idle && controlPage.visible
                                        width: 46
                                        height: parent.height
                                        opacity: 0.55
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: "transparent" }
                                            GradientStop { position: 0.5; color: root.accent }
                                            GradientStop { position: 1.0; color: "transparent" }
                                        }
                                        SequentialAnimation on x {
                                            running: idleSweep.visible
                                            loops: Animation.Infinite
                                            NumberAnimation { from: -idleSweep.width; to: sessionBar.width; duration: 2600; easing.type: Easing.InOutSine }
                                            PauseAnimation { duration: 900 }
                                        }
                                    }
                                }
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                enabled: !!backend.currentSession.id
                                onTapped: targetMenu.popup()
                            }
                            HudMenu {
                                id: targetMenu
                                readonly property string coordinates: root.targetCoordinates(backend.currentSession)
                                HudMenuItem {
                                    text: "Edit session"
                                    glyph: "\uE70F"
                                    enabled: backend.currentSession.status !== "running"
                                    onTriggered: sessionDialog.openExisting(backend.currentSession)
                                }
                                HudMenuItem {
                                    text: "Copy target name"
                                    glyph: "\uE8C8"
                                    onTriggered: backend.copyText(String(backend.currentSession.target_name || ""))
                                }
                                HudMenuItem {
                                    text: "Copy RA / Dec"
                                    glyph: "\uE8C8"
                                    enabled: targetMenu.coordinates !== ""
                                    onTriggered: backend.copyText(targetMenu.coordinates)
                                }
                                HudMenuSeparator {}
                                HudMenuItem {
                                    text: "Stop all"
                                    glyph: "\uE71A"
                                    destructive: true
                                    enabled: backend.currentSession.status === "running"
                                        && root.commandEnabled("stop_all")
                                    onTriggered: backend.stopDevice(backend.selectedDeviceId)
                                }
                            }
                        }

                        Rectangle {
                            SplitView.preferredHeight: 48
                            SplitView.minimumHeight: 40
                            SplitView.maximumHeight: 64
                            id: linkBanner
                            readonly property bool tracking: root.scopeOnline && !!root.scopeTelemetry.tracking_active
                            readonly property bool slewing: root.scopeOnline && root.scopeActivity === "goto"
                            readonly property bool locked: root.targetLocked || tracking
                            readonly property color tone: locked ? root.success : slewing ? root.notice : (backend.selectedDevice.connected ? root.accent : root.danger)
                            color: locked ? "#C0143C28" : slewing ? "#C0113A3A" : (backend.selectedDevice.connected ? "#C0123C52" : "#C03A1218")
                            Behavior on color { ColorAnimation { duration: 240 } }
                            border.color: tone
                            Rectangle {
                                id: bannerGlow
                                anchors.fill: parent
                                anchors.margins: 3
                                color: "transparent"
                                border.color: linkBanner.tone
                                border.width: 1
                                opacity: 0.25
                                SequentialAnimation on opacity {
                                    running: controlPage.visible && !linkBanner.locked
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.05; duration: linkBanner.slewing ? 500 : 1400; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 0.45; duration: linkBanner.slewing ? 500 : 1400; easing.type: Easing.InOutSine }
                                }
                            }
                            Row {
                                anchors.centerIn: parent
                                spacing: 10
                                Rectangle { width: 6; height: 6; radius: 3; color: linkBanner.tone; anchors.verticalCenter: parent.verticalCenter }
                                Text {
                                    text: {
                                        const target = String(root.scopeTelemetry.tracking_target || root.scopeTelemetry.goto_target || "")
                                        if (linkBanner.slewing)
                                            return "GOTO" + (target ? " · " + target.toUpperCase() : "")
                                        if (linkBanner.tracking)
                                            return "TRACKING" + (target ? " · " + target.toUpperCase() : "")
                                        if (root.targetLocked)
                                            return "TARGET LOCKED"
                                        return backend.selectedDevice.connected ? "NO TARGET LOCK" : "LINK DOWN"
                                    }
                                    color: linkBanner.tone
                                    font.bold: true
                                    font.letterSpacing: 2
                                }
                                Rectangle { width: 6; height: 6; radius: 3; color: linkBanner.tone; anchors.verticalCenter: parent.verticalCenter }
                            }
                        }

                        HudPanel {
                            title: "CAMERA"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 120
                            FieldLabel { text: "FOCUS" }
                            RowLayout {
                                Layout.fillWidth: true
                                HudButton {
                                    text: "NEAR"
                                    Layout.fillWidth: true
                                    busy: backend.selectedDevice.pending_action === "focus_near"
                                    busyText: "FOCUSING…"
                                    busyMs: 0
                                    enabled: root.commandEnabled("focus_near")
                                    onClicked: backend.manualFocus(backend.selectedDeviceId, 1)
                                }
                                HudButton {
                                    text: "FAR"
                                    Layout.fillWidth: true
                                    busy: backend.selectedDevice.pending_action === "focus_far"
                                    busyText: "FOCUSING…"
                                    busyMs: 0
                                    enabled: root.commandEnabled("focus_far")
                                    onClicked: backend.manualFocus(backend.selectedDeviceId, 0)
                                }
                            }
                            FieldLabel {
                                text: "FILTER"
                                visible: backend.selectedDevice.camera !== "wide"
                            }
                            HudCombo {
                                id: liveFilter
                                Layout.fillWidth: true
                                visible: backend.selectedDevice.camera !== "wide"
                                enabled: root.commandEnabled("set_ir")
                                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                                onActivated: backend.setCameraParam(backend.selectedDeviceId, "ir", currentText)
                            }
                            FieldLabel { text: "CAMERA" }
                            HudCombo {
                                id: liveCamera
                                Layout.fillWidth: true
                                enabled: !root.scopeOccupied && !root.scopeLinking
                                model: ["Tele", "Wide"]
                                Component.onCompleted: currentIndex = backend.selectedDevice.camera === "wide" ? 1 : 0
                                onActivated: backend.setLiveCamera(backend.selectedDeviceId, currentIndex === 1 ? "wide" : "tele")
                                Connections {
                                    target: backend
                                    function onSelectedDeviceChanged() { liveCamera.currentIndex = backend.selectedDevice.camera === "wide" ? 1 : 0 }
                                }
                            }
                            FieldLabel { text: "EXPOSURE / GAIN" }
                            RowLayout {
                                Layout.fillWidth: true
                                HudField {
                                    id: liveExposure
                                    Layout.fillWidth: true
                                    enabled: root.cameraLiveEnabled
                                    placeholderText: "sec"
                                    text: "15"
                                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "exposure", text)
                                }
                                HudField {
                                    id: liveGain
                                    Layout.fillWidth: true
                                    enabled: root.commandEnabled("set_gain")
                                    placeholderText: "gain"
                                    text: "80"
                                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "gain", text)
                                }
                            }
                        }
                    }

                    HudSplitView {
                        id: controlCenter
                        orientation: Qt.Vertical
                        SplitView.fillWidth: true
                        SplitView.minimumWidth: 280

                        HudPanel {
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 150
                            fill: "#E005070B"
                            Item {
                                id: previewHost
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                property string previewDeviceId: backend.selectedDeviceId
                                property string statusText: backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"
                                readonly property bool previewFailed: {
                                    const s = String(backend.previewStatus || "").toLowerCase()
                                    return s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0
                                }
                                readonly property string actionLabel: {
                                    if (!backend.previewActive || backend.previewPlaying)
                                        return "STARTING CAMERA…"
                                    const s = String(backend.previewStatus || "").toLowerCase()
                                    if (s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0)
                                        return "PREVIEW FAILED"
                                    if (s.indexOf("udp") >= 0)
                                        return "RETRYING UDP…"
                                    if (s.indexOf("waiting") >= 0)
                                        return "WAITING FOR STREAM…"
                                    if (s.indexOf("tcp") >= 0 || s.indexOf("opening") >= 0)
                                        return "OPENING STREAM…"
                                    if (s.indexOf("starting") >= 0)
                                        return "STARTING CAMERA…"
                                    return "STARTING PREVIEW…"
                                }

                                function startPreview() {
                                    if (!backend.selectedDevice.connected) {
                                        statusText = "Connect a telescope to start the stream"
                                        backend.uiLog("warning", "Preview needs an active telescope connection")
                                        return
                                    }
                                    statusText = "Starting live camera…"
                                    backend.startPreview(backend.selectedDeviceId)
                                }

                                function stopPreview() {
                                    backend.stopPreview()
                                    statusText = backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"
                                }

                                property bool chromeVisible: true
                                property bool chromeHold: false
                                readonly property bool chromeShown: !backend.previewPlaying || chromeVisible

                                function revealChrome() {
                                    chromeVisible = true
                                    if (!chromeHold)
                                        chromeIdleTimer.restart()
                                }

                                function leaveChrome() {
                                    if (chromeHold)
                                        return
                                    chromeVisible = false
                                    chromeIdleTimer.stop()
                                }

                                function beginChromeHold() {
                                    chromeVisible = true
                                    chromeHold = true
                                    chromeIdleTimer.stop()
                                    chromeHoldTimer.restart()
                                }

                                function clearChromeHold() {
                                    chromeHold = false
                                    chromeVisible = true
                                    chromeHoldTimer.stop()
                                    chromeIdleTimer.stop()
                                }

                                Timer {
                                    id: chromeHoldTimer
                                    interval: 5000
                                    repeat: false
                                    onTriggered: {
                                        previewHost.chromeHold = false
                                        if (!previewHover.hovered)
                                            previewHost.chromeVisible = false
                                        else
                                            chromeIdleTimer.restart()
                                    }
                                }
                                Timer {
                                    id: chromeIdleTimer
                                    interval: 3000
                                    repeat: false
                                    onTriggered: previewHost.chromeVisible = false
                                }

                                HoverHandler {
                                    id: previewHover
                                    enabled: backend.previewPlaying
                                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                    onPointChanged: previewHost.revealChrome()
                                    onHoveredChanged: {
                                        if (!hovered)
                                            previewHost.leaveChrome()
                                    }
                                }

                                Connections {
                                    target: backend
                                    function onSelectedDeviceChanged() {
                                        const deviceId = backend.selectedDeviceId
                                        if (deviceId === previewHost.previewDeviceId)
                                            return
                                        previewHost.previewDeviceId = deviceId
                                        previewHost.stopPreview()
                                    }
                                    function onPreviewStatusChanged() {
                                        if (backend.previewStatus)
                                            previewHost.statusText = backend.previewStatus
                                    }
                                    function onPreviewPlayingChanged() {
                                        if (backend.previewPlaying)
                                            previewHost.beginChromeHold()
                                        else
                                            previewHost.clearChromeHold()
                                    }
                                }

                                Image {
                                    anchors.fill: parent
                                    visible: backend.previewPlaying
                                    cache: false
                                    fillMode: Image.PreserveAspectFit
                                    source: backend.previewPlaying ? ("image://live/frame/" + backend.previewGeneration) : ""
                                }
                                Image {
                                    anchors.fill: parent
                                    visible: !backend.previewPlaying
                                    source: {
                                        const model = String((backend.selectedDevice && backend.selectedDevice.model) || "")
                                        if (model === "Dwarf II")
                                            return root.asset("hud-dwarf-ii.png")
                                        if (model === "Dwarf Mini")
                                            return root.asset("hud-dwarf-mini.png")
                                        return root.asset("hud-dwarf-3.png")
                                    }
                                    fillMode: Image.PreserveAspectFit
                                    opacity: 0.18
                                }
                                Canvas {
                                    // faint scanline grid
                                    anchors.fill: parent
                                    visible: opacity > 0
                                    opacity: !backend.previewPlaying ? 0.22 : (previewHost.chromeShown ? 0.10 : 0)
                                    Behavior on opacity { NumberAnimation { duration: 220 } }
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        ctx.strokeStyle = "#4DE8FF"
                                        ctx.lineWidth = 1
                                        ctx.globalAlpha = 0.35
                                        for (let y = 0.5; y < height; y += 4) {
                                            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                                        }
                                        ctx.globalAlpha = 0.5
                                        const step = 48
                                        for (let x = (width / 2) % step + 0.5; x < width; x += step) {
                                            ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
                                        }
                                        for (let y = (height / 2) % step + 0.5; y < height; y += step) {
                                            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke()
                                        }
                                    }
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                }
                                Rectangle {
                                    // readout strip
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 14
                                    height: 24
                                    visible: previewHost.chromeShown
                                    color: "#B0070D16"
                                    border.color: root.outline
                                    RowLayout {
                                        id: readoutStrip
                                        readonly property var t: root.scopeTelemetry
                                        readonly property bool wide: backend.selectedDevice.camera === "wide"
                                        readonly property string exposure: {
                                            const value = wide ? t.wide_exposure_text : t.exposure_text
                                            return root.scopeOnline && value && value !== "—" ? String(value) : liveExposure.text
                                        }
                                        readonly property string gain: {
                                            const value = wide ? t.wide_gain : t.gain
                                            return root.scopeOnline && value !== undefined && value !== null ? String(value) : liveGain.text
                                        }
                                        readonly property string sensor: String((wide ? t.cmos_wide_text : t.cmos_tele_text) || "—")
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 12
                                        Text { text: readoutStrip.wide ? "WIDE" : "TELE"; color: root.accent; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1 }
                                        Text { text: "EXP " + readoutStrip.exposure + "s"; color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono" }
                                        Text { text: "GAIN " + readoutStrip.gain; color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono" }
                                        Text { visible: !readoutStrip.wide; text: liveFilter.currentText.toUpperCase(); color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono"; elide: Text.ElideRight }
                                        Text {
                                            visible: root.scopeOnline && !!readoutStrip.t.capture_text
                                            text: "FRAMES " + (readoutStrip.t.capture_text || "")
                                            color: readoutStrip.t.capture_active ? root.danger : root.textPrimary
                                            font.pixelSize: 10; font.family: "Cascadia Mono"; font.bold: true
                                        }
                                        Item { Layout.fillWidth: true }
                                        Text { visible: root.scopeOnline && readoutStrip.sensor !== "—"; text: "SENSOR " + readoutStrip.sensor; color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono" }
                                        Text {
                                            visible: root.scopeOnline && readoutStrip.t.battery_percent !== undefined && Number(readoutStrip.t.battery_percent) >= 0
                                            text: "BATT " + (readoutStrip.t.battery_text || "—") + (readoutStrip.t.charging ? "⚡" : "")
                                            color: root.toneColor(root.batteryTone(readoutStrip.t.battery_percent))
                                            font.pixelSize: 10; font.family: "Cascadia Mono"
                                        }
                                        Text { visible: !root.scopeOnline; text: backend.selectedDevice.ip_address || "—"; color: root.textSecondary; font.pixelSize: 10; font.family: "Cascadia Mono" }
                                        Text { text: backend.clockText; color: root.accent; font.pixelSize: 10; font.family: "Cascadia Mono" }
                                    }
                                }
                                Canvas {
                                    anchors.fill: parent
                                    opacity: previewHost.chromeShown ? 0.9 : 0
                                    readonly property bool reticle: backend.previewPlaying
                                    onReticleChanged: requestPaint()
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        if (!reticle)
                                            return
                                        const cx = width / 2, cy = height / 2
                                        ctx.strokeStyle = "#88E8FFFF"
                                        ctx.lineWidth = 1.2
                                        ctx.beginPath()
                                        ctx.moveTo(cx - 80, cy); ctx.lineTo(cx - 16, cy)
                                        ctx.moveTo(cx + 16, cy); ctx.lineTo(cx + 80, cy)
                                        ctx.moveTo(cx, cy - 80); ctx.lineTo(cx, cy - 16)
                                        ctx.moveTo(cx, cy + 16); ctx.lineTo(cx, cy + 80)
                                        ctx.stroke()
                                        ctx.beginPath(); ctx.arc(cx, cy, 52, 0, Math.PI * 2); ctx.stroke()
                                    }
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                }
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    visible: !backend.previewPlaying
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "LIVE VIDEO"; color: root.textPrimary; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: previewHost.width - 40
                                        wrapMode: Text.Wrap
                                        horizontalAlignment: Text.AlignHCenter
                                        text: previewHost.statusText
                                        color: root.textSecondary
                                    }
                                    HudButton {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "START PREVIEW"
                                        busyText: previewHost.actionLabel
                                        busy: backend.previewActive && !backend.previewPlaying
                                        busyMs: backend.selectedDevice.connected && !backend.previewActive ? 1800 : 0
                                        enabled: root.commandEnabled("open_camera") && (!backend.previewActive || backend.previewPlaying || previewHost.previewFailed)
                                        buttonColor: "#0E3A48"
                                        foregroundColor: root.accent
                                        onClicked: previewHost.startPreview()
                                    }
                                }
                                Row {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    spacing: 6
                                    visible: previewHost.chromeShown
                                    Rectangle {
                                        width: 96
                                        height: 28
                                        color: "#C0101520"
                                        border.color: backend.previewPlaying ? root.success : root.outline
                                        Row {
                                            anchors.centerIn: parent
                                            spacing: 7
                                            Rectangle {
                                                width: 8; height: 8; radius: 4
                                                color: backend.previewPlaying ? root.danger : (backend.previewActive ? root.warning : "#64748B")
                                                anchors.verticalCenter: parent.verticalCenter
                                                SequentialAnimation on opacity {
                                                    running: backend.previewPlaying
                                                    loops: Animation.Infinite
                                                    NumberAnimation { from: 1; to: 0.3; duration: 600 }
                                                    NumberAnimation { from: 0.3; to: 1; duration: 600 }
                                                }
                                            }
                                            Text { text: backend.previewPlaying ? "LIVE" : (backend.previewActive ? "STARTING" : "STANDBY"); color: root.textPrimary; font.pixelSize: 11; font.bold: true }
                                        }
                                    }
                                    Rectangle {
                                        id: recBadge
                                        readonly property var t: root.scopeTelemetry
                                        readonly property bool rec: root.scopeOnline && (root.scopeActivity === "record" || !!t.capture_active)
                                        visible: rec
                                        width: recRow.implicitWidth + 20
                                        height: 28
                                        color: "#C0301117"
                                        border.color: root.danger
                                        Row {
                                            id: recRow
                                            anchors.centerIn: parent
                                            spacing: 7
                                            Rectangle {
                                                width: 8; height: 8; radius: 4; color: root.danger
                                                anchors.verticalCenter: parent.verticalCenter
                                                SequentialAnimation on opacity {
                                                    running: recBadge.rec
                                                    loops: Animation.Infinite
                                                    NumberAnimation { from: 1; to: 0.2; duration: 500 }
                                                    NumberAnimation { from: 0.2; to: 1; duration: 500 }
                                                }
                                            }
                                            Text {
                                                text: root.scopeActivity === "record" ? "REC " + root.scopeActivityDetail : "STACKING " + (recBadge.t.capture_text || "")
                                                color: root.danger; font.pixelSize: 11; font.bold: true; font.family: "Cascadia Mono"
                                            }
                                        }
                                    }
                                }
                                HudButton {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    visible: backend.previewActive && previewHost.chromeShown
                                    text: "STOP PREVIEW"
                                    busyText: "STOPPING…"
                                    onClicked: previewHost.stopPreview()
                                }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: previewMenu.popup()
                                }
                                HudMenu {
                                    id: previewMenu
                                    HudMenuItem {
                                        text: backend.previewActive ? "Stop preview" : "Start preview"
                                        glyph: backend.previewActive ? "\uE71A" : "\uE768"
                                        enabled: backend.previewActive
                                            || root.commandEnabled("open_camera")
                                        onTriggered: {
                                            if (backend.previewActive)
                                                previewHost.stopPreview()
                                            else
                                                previewHost.startPreview()
                                        }
                                    }
                                    HudMenuItem {
                                        text: "Copy stream URL"
                                        glyph: "\uE8C8"
                                        enabled: backend.selectedDevice.connected && backend.videoUrl !== ""
                                        onTriggered: backend.copyText(backend.videoUrl)
                                    }
                                }
                            }
                        }

                        HudPanel {
                            title: "COMMANDS"
                            SplitView.preferredHeight: 244
                            SplitView.minimumHeight: 140
                            GridLayout {
                                id: commandGrid
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                readonly property int padCount: 12
                                // pick the widest column count that still divides the pads into full rows
                                columns: {
                                    const fit = Math.max(2, Math.floor((width + columnSpacing) / (150 + columnSpacing)))
                                    const options = [6, 4, 3, 2]
                                    for (let i = 0; i < options.length; i++)
                                        if (options[i] <= fit)
                                            return options[i]
                                    return 2
                                }
                                columnSpacing: 8
                                rowSpacing: 8
                                Repeater {
                                model: [
                                    {label: "CALIBRATE", glyph: "◎", start: "calibrate", stop: "stop_calibrate", state: "calibrate", detail: "ALIGN"},
                                    {label: "AUTO FOCUS", glyph: "◉", start: "autofocus", stop: "stop_autofocus", state: "autofocus", detail: "OPTICS"},
                                    {label: "INFINITY", glyph: "∞", start: "infinity", stop: "stop_autofocus", state: "autofocus", detail: "FOCUS"},
                                    {label: "POLAR / EQ", glyph: "⌖", start: "polar", stop: "stop_polar", state: "polar", detail: "ALIGN"},
                                    {label: "LIGHTS", glyph: "✦", start: "lights_on", stop: "lights_off", state: "lights", detail: "CHASSIS"},
                                    {label: "GO LIVE", glyph: "▶", start: "go_live", stop: "", state: "", detail: "CAMERA"},
                                    {label: "STOP GOTO", glyph: "■", start: "stop_goto", stop: "", state: "goto", detail: "MOUNT"},
                                    {label: "BURST", glyph: "◫", start: "burst_start", stop: "burst_stop", state: "burst", detail: "CAPTURE"},
                                    {label: "RECORD", glyph: "●", start: "record_start", stop: "record_stop", state: "record", detail: "VIDEO"},
                                    {label: "TIMELAPSE", glyph: "◷", start: "timelapse_start", stop: "timelapse_stop", state: "timelapse", detail: "CAPTURE"},
                                    {label: "REBOOT", glyph: "↻", start: "reboot", stop: "", state: "", detail: "SYSTEM", destructive: true},
                                    {label: "POWER", glyph: "⏻", start: "power_down", stop: "", state: "", detail: "SYSTEM", destructive: true}
                                ]
                                delegate: HudCommandPad {
                                    id: pad
                                    required property var modelData
                                    readonly property var t: root.scopeTelemetry
                                    readonly property bool activeForState: modelData.state === "lights"
                                        ? !!backend.selectedDevice.lights_on
                                        : modelData.state !== "" && root.scopeActivity === modelData.state
                                    readonly property string effectiveOperation: activeForState && modelData.stop !== "" ? modelData.stop : modelData.start
                                    readonly property bool isPending: root.scopePending !== "" && (root.scopePending === modelData.start || root.scopePending === modelData.stop)
                                    function deviceDetail() {
                                        if (!activeForState)
                                            return modelData.detail
                                        switch (modelData.state) {
                                        case "calibrate":
                                            return root.scopeActivityDetail ? (root.scopeActivityDetail.indexOf("SOLVE") === 0 ? "SOLVING · " + root.scopeActivityDetail.replace("SOLVE", "PHASE").trim() : root.scopeActivityDetail) : "RUNNING"
                                        case "autofocus":
                                            return t.focus_text && t.focus_text !== "—" ? "RUNNING · " + t.focus_text : "RUNNING"
                                        case "polar":
                                            return root.scopeActivityDetail || "RUNNING"
                                        case "record":
                                            return "REC · " + (root.scopeActivityDetail || "00:00")
                                        case "lights":
                                            return "ON · TAP TO STOP"
                                        default:
                                            return root.scopeActivityDetail ? root.scopeActivityDetail + " · STOP" : "ACTIVE · STOP"
                                        }
                                    }
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: 44
                                    Layout.preferredHeight: 58
                                    text: modelData.label
                                    glyph: modelData.glyph
                                    detail: deviceDetail()
                                    activeState: activeForState
                                    pending: isPending
                                    destructive: !!modelData.destructive
                                    enabled: root.commandEnabled(effectiveOperation)
                                    onClicked: root.requestDeviceAction(effectiveOperation, modelData.label)
                                    Connections {
                                        target: backend
                                        function onCommandFeedback(deviceId, operation, ok) {
                                            if (deviceId !== backend.selectedDeviceId)
                                                return
                                            if (operation === pad.modelData.start || (pad.modelData.stop !== "" && operation === pad.modelData.stop))
                                                pad.showFlash(ok ? "success" : "error")
                                        }
                                    }
                                }
                                }
                            }
                        }
                    }

                    HudSplitView {
                        id: controlRight
                        orientation: Qt.Vertical
                        SplitView.preferredWidth: 312
                        SplitView.minimumWidth: 220

                        HudPanel {
                            title: "SCOPE STATUS"
                            visible: false
                            SplitView.preferredHeight: 0
                            SplitView.minimumHeight: 0
                            SplitView.maximumHeight: 0
                            Repeater {
                                model: [
                                    {label: "LINK", value: backend.selectedDevice.connected ? "Connected" : "Offline"},
                                    {label: "ACTIVITY", value: backend.selectedDevice.busy ? "Imaging" : (root.targetLocked ? "On target" : "Idle")},
                                    {label: "TARGET", value: backend.currentSession.target_name || "None"},
                                    {label: "STEP", value: backend.currentSession.current_step || backend.selectedDevice.status || "—"}
                                ]
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Text { text: modelData.label; color: root.textSecondary; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 72 }
                                    Text { text: modelData.value; color: root.textPrimary; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }

                        HudPanel {
                            title: "MOTION"
                            SplitView.preferredHeight: 188
                            SplitView.minimumHeight: 136
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 128
                                opacity: root.motionEnabled ? 1 : 0.38
                                Item {
                                    id: analogPad
                                    anchors.centerIn: parent
                                    width: 108
                                    height: 108
                                    property real stickDx: 0
                                    property real stickDy: 0
                                    property bool moving: false
                                    readonly property real maxThrow: width / 2 - 15
                                    readonly property real deadzone: 0.15

                                    function updateStick(px, py) {
                                        let dx = px - width / 2
                                        let dy = py - height / 2
                                        const distance = Math.sqrt(dx * dx + dy * dy)
                                        const limited = Math.min(distance, maxThrow)
                                        const scale = distance > 0 ? limited / distance : 0
                                        stickDx = dx * scale
                                        stickDy = dy * scale
                                        const amount = maxThrow > 0 ? limited / maxThrow : 0
                                        if (amount <= deadzone) {
                                            if (moving)
                                                backend.stopMotors(backend.selectedDeviceId)
                                            moving = false
                                            return
                                        }
                                        let angle = Math.atan2(-dy, dx) * 180 / Math.PI
                                        if (angle < 0)
                                            angle += 360
                                        moving = true
                                        backend.joystick(backend.selectedDeviceId, angle, amount * root.joySpeed)
                                    }

                                    function releaseStick() {
                                        stickDx = 0
                                        stickDy = 0
                                        moving = false
                                        backend.stopMotors(backend.selectedDeviceId)
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: width / 2
                                        color: "#B30A1524"
                                        border.color: root.outline
                                        border.width: 2
                                    }
                                    Canvas {
                                        // bearing ticks around the ring
                                        anchors.fill: parent
                                        anchors.margins: -10
                                        onPaint: {
                                            const ctx = getContext("2d")
                                            ctx.reset()
                                            const cx = width / 2, cy = height / 2
                                            const rOuter = width / 2 - 1
                                            for (let i = 0; i < 36; i++) {
                                                const major = i % 9 === 0
                                                const a = i * Math.PI * 2 / 36
                                                const len = major ? 8 : 4
                                                ctx.strokeStyle = major ? "#4DE8FF" : "#34597A"
                                                ctx.lineWidth = major ? 2 : 1
                                                ctx.beginPath()
                                                ctx.moveTo(cx + Math.cos(a) * (rOuter - len), cy + Math.sin(a) * (rOuter - len))
                                                ctx.lineTo(cx + Math.cos(a) * rOuter, cy + Math.sin(a) * rOuter)
                                                ctx.stroke()
                                            }
                                        }
                                        onWidthChanged: requestPaint()
                                        onHeightChanged: requestPaint()
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 2
                                        height: parent.height - 18
                                        color: "#34597A"
                                        opacity: 0.45
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: parent.width - 18
                                        height: 2
                                        color: "#34597A"
                                        opacity: 0.45
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: analogPad.maxThrow * 2 * analogPad.deadzone
                                        height: width
                                        radius: width / 2
                                        color: "#162B40"
                                        border.color: "#34597A"
                                    }
                                    Rectangle {
                                        id: analogKnob
                                        x: parent.width / 2 - width / 2 + analogPad.stickDx
                                        y: parent.height / 2 - height / 2 + analogPad.stickDy
                                        width: 28
                                        height: 28
                                        radius: width / 2
                                        color: analogPad.moving ? root.accent : "#8CB7D9"
                                        border.color: "#D8F4FF"
                                        border.width: 2
                                        Behavior on x { NumberAnimation { duration: stickArea.pressed ? 0 : 90 } }
                                        Behavior on y { NumberAnimation { duration: stickArea.pressed ? 0 : 90 } }
                                    }
                                    MouseArea {
                                        id: stickArea
                                        anchors.fill: parent
                                        enabled: root.motionEnabled
                                        preventStealing: true
                                        cursorShape: root.motionEnabled ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor
                                        onPressed: mouse => analogPad.updateStick(mouse.x, mouse.y)
                                        onPositionChanged: mouse => {
                                            if (pressed)
                                                analogPad.updateStick(mouse.x, mouse.y)
                                        }
                                        onReleased: analogPad.releaseStick()
                                        onCanceled: analogPad.releaseStick()
                                        onEnabledChanged: {
                                            if (!enabled && analogPad.moving)
                                                analogPad.releaseStick()
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                opacity: root.motionEnabled ? 1 : 0.42
                                Text { text: "SPEED"; color: root.textSecondary; font.pixelSize: 10 }
                                Slider {
                                    id: speedSlider
                                    Layout.fillWidth: true
                                    enabled: root.motionEnabled
                                    from: 0.2
                                    to: 1
                                    value: 1
                                    onMoved: root.joySpeed = value
                                    background: Rectangle { x: speedSlider.leftPadding; y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 2; implicitHeight: 4; width: speedSlider.availableWidth; color: "#0A1524"; Rectangle { width: speedSlider.visualPosition * parent.width; height: parent.height; color: root.accent } }
                                    handle: Rectangle { x: speedSlider.leftPadding + speedSlider.visualPosition * (speedSlider.availableWidth - 12); y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 6; width: 12; height: 12; radius: 6; color: root.accent }
                                }
                            }
                        }

                        HudPanel {
                            title: "UP NEXT"
                            SplitView.preferredHeight: 110
                            SplitView.minimumHeight: 72
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                SessionInsertDrop {
                                    id: upcomingInsert
                                    anchors.fill: parent
                                    targetList: upcomingList
                                    rowHeight: 44
                                    ListView {
                                        id: upcomingList
                                        anchors.fill: parent
                                        clip: true
                                        spacing: 4
                                        boundsBehavior: Flickable.StopAtBounds
                                        ScrollBar.vertical: HiddenBar {}
                                        ScrollBar.horizontal: HiddenBar {}
                                        model: backend.upcomingSessions
                                        delegate: Rectangle {
                                            id: upcomingRow
                                            required property var modelData
                                            width: ListView.view.width
                                            height: 44
                                            color: "#122033"
                                            border.color: root.outline
                                            opacity: root.sessionDragActive && root.sessionDragData.id === modelData.id ? 0.35 : 1
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 6
                                                Text { text: "⋮⋮"; color: root.accent; font.pixelSize: 15 }
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 0
                                                    Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                    Text {
                                                        readonly property bool due: {
                                                            backend.clockText
                                                            return new Date(modelData.scheduled_start).getTime() <= Date.now()
                                                        }
                                                        text: {
                                                            backend.clockText
                                                            const seconds = Math.floor((new Date(modelData.scheduled_start).getTime() - Date.now()) / 1000)
                                                            return modelData.start_time + " · " + modelData.duration_text + (seconds > 0 ? " · T−" + root.durationLabel(seconds) : " · DUE")
                                                        }
                                                        color: due ? root.warning : root.textSecondary; font.pixelSize: 9
                                                    }
                                                }
                                            }
                                            SessionDragArea {
                                                anchors.fill: parent
                                                dragItem: upcomingRow.modelData
                                            }
                                            TapHandler {
                                                acceptedButtons: Qt.RightButton
                                                onTapped: upcomingMenu.popup()
                                            }
                                            SessionContextMenu {
                                                id: upcomingMenu
                                                sessionData: upcomingRow.modelData
                                            }
                                        }
                                    }
                                }
                                EmptyHint { anchors.centerIn: parent; visible: backend.upcomingSessions.length === 0; text: "No upcoming sessions" }
                            }
                        }

                        HudPanel {
                            id: logPanel
                            title: "LIVE LOG"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 80
                            headerExtra: Row {
                                spacing: 3
                                Repeater {
                                    model: [
                                        {key: "all", label: "ALL"},
                                        {key: "device", label: "DEVICE"},
                                        {key: "alerts", label: "ALERTS"},
                                        {key: "debug", label: "DEBUG"}
                                    ]
                                    delegate: Rectangle {
                                        id: pill
                                        required property var modelData
                                        readonly property bool active: backend.logFilter === modelData.key
                                        readonly property int badge: modelData.key === "alerts" ? backend.logWarningCount + backend.logErrorCount : 0
                                        width: pillRow.implicitWidth + 12
                                        height: 20
                                        radius: 3
                                        color: active ? (modelData.key === "debug" ? "#143028" : "#0E3A48") : pillHover.hovered ? "#12283A" : "transparent"
                                        border.color: active ? (modelData.key === "debug" ? root.success : root.accent) : "#1A3A50"
                                        Behavior on color { ColorAnimation { duration: 120 } }
                                        Row {
                                            id: pillRow
                                            anchors.centerIn: parent
                                            spacing: 4
                                            Text {
                                                text: pill.modelData.label
                                                color: pill.active ? (pill.modelData.key === "debug" ? root.success : root.accent) : root.textSecondary
                                                font.pixelSize: 8; font.bold: true; font.letterSpacing: 1
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                            Rectangle {
                                                visible: pill.badge > 0
                                                width: badgeText.implicitWidth + 6; height: 12; radius: 6
                                                color: backend.logErrorCount > 0 ? root.danger : root.warning
                                                anchors.verticalCenter: parent.verticalCenter
                                                Text { id: badgeText; anchors.centerIn: parent; text: pill.badge > 99 ? "99+" : pill.badge; color: "#05080F"; font.pixelSize: 8; font.bold: true }
                                            }
                                        }
                                        HoverHandler { id: pillHover; cursorShape: Qt.PointingHandCursor }
                                        TapHandler { onTapped: backend.setLogFilter(pill.modelData.key) }
                                    }
                                }
                                Rectangle { width: 1; height: 16; color: root.outline; anchors.verticalCenter: parent.verticalCenter }
                                HudButton {
                                    text: "COPY"
                                    implicitHeight: 20
                                    implicitWidth: 46
                                    font.pixelSize: 8
                                    font.letterSpacing: 1
                                    leftPadding: 6; rightPadding: 6
                                    busyText: "COPIED"
                                    busyMs: 900
                                    enabled: logList.count > 0
                                    buttonColor: "transparent"
                                    foregroundColor: root.textSecondary
                                    onClicked: backend.copyText(root.allLogText())
                                }
                                HudButton {
                                    text: "CLEAR"
                                    implicitHeight: 20
                                    implicitWidth: 50
                                    font.pixelSize: 8
                                    font.letterSpacing: 1
                                    leftPadding: 6; rightPadding: 6
                                    enabled: logList.count > 0
                                    buttonColor: "transparent"
                                    foregroundColor: root.textSecondary
                                    onClicked: backend.clearLog()
                                }
                            }
                            overlay: Item {
                                anchors.fill: parent
                                Rectangle {
                                    // "N new" follow-tail pill
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 14
                                    width: newPillRow.implicitWidth + 22
                                    height: 22
                                    radius: 11
                                    color: "#E00E3A48"
                                    border.color: root.accent
                                    visible: !logList.followTail && logList.count > 0
                                    scale: visible ? 1 : 0.8
                                    Behavior on scale { NumberAnimation { duration: 140 } }
                                    Row {
                                        id: newPillRow
                                        anchors.centerIn: parent
                                        spacing: 6
                                        Text { text: "↓"; color: root.accent; font.pixelSize: 11; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                                        Text {
                                            text: logList.unseen > 0 ? logList.unseen + " NEW" : "FOLLOW"
                                            color: root.textPrimary; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: logList.resumeFollow() }
                                }
                            }
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                ListView {
                                    id: logList
                                    property bool followTail: true
                                    property int unseen: 0
                                    property bool _programmatic: false
                                    anchors.fill: parent
                                    clip: true
                                    spacing: 1
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: ScrollBar {
                                        id: logScroll
                                        policy: ScrollBar.AsNeeded
                                        onPressedChanged: if (pressed && logList.contentHeight > logList.height) logList.followTail = false
                                        contentItem: Rectangle { implicitWidth: 3; radius: 1.5; color: root.outline; opacity: logScroll.active ? 0.9 : 0.4 }
                                        background: Item {}
                                    }
                                    ScrollBar.horizontal: HiddenBar {}
                                    model: backend.logModel
                                    reuseItems: true
                                    function resumeFollow() {
                                        followTail = true
                                        unseen = 0
                                        _programmatic = true
                                        positionViewAtEnd()
                                        _programmatic = false
                                    }
                                    function scrollToTail() {
                                        _programmatic = true
                                        positionViewAtEnd()
                                        _programmatic = false
                                    }
                                    onCountChanged: {
                                        if (followTail)
                                            Qt.callLater(scrollToTail)
                                        else if (count > 0)
                                            unseen += 1
                                    }
                                    onDraggingChanged: {
                                        if (dragging && !_programmatic && contentHeight > height)
                                            followTail = false
                                    }
                                    onAtYEndChanged: {
                                        if (atYEnd && !followTail)
                                            Qt.callLater(resumeFollow)
                                    }
                                    WheelHandler {
                                        // wheel-up disengages follow-tail; reaching the end again re-engages it
                                        blocking: false
                                        onWheel: event => {
                                            if (event.angleDelta.y > 0 && logList.contentHeight > logList.height)
                                                logList.followTail = false
                                        }
                                    }
                                    delegate: Rectangle {
                                        id: logRow
                                        required property int index
                                        required property string time
                                        required property string level
                                        required property string device
                                        required property string message
                                        required property string glyph
                                        required property int count
                                        readonly property color tone: root.toneForLevel(level)
                                        readonly property bool quiet: level === "SDK" || level === "DEBUG" || level === "INFO"
                                        readonly property string lineText: time + "  " + level + "  [" + device + "]  " + message + (count > 1 ? "  (×" + count + ")" : "")
                                        width: ListView.view ? ListView.view.width : 0
                                        height: 18
                                        color: rowHover.hovered ? "#1A0E2030" : (index % 2 === 0 ? "transparent" : "#0C0A1420")
                                        Rectangle {
                                            x: 0; y: 2
                                            width: 2
                                            height: parent.height - 4
                                            radius: 1
                                            color: logRow.quiet ? "#1E4A63" : logRow.tone
                                            opacity: logRow.level === "SDK" || logRow.level === "DEBUG" ? 0.45 : 1
                                        }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 7
                                            anchors.rightMargin: 6
                                            spacing: 6
                                            Text {
                                                text: logRow.time
                                                color: root.muted
                                                font.family: "Cascadia Mono"
                                                font.pixelSize: 9
                                                Layout.preferredWidth: 50
                                            }
                                            Text {
                                                text: logRow.glyph
                                                color: logRow.quiet && logRow.level !== "INFO" ? root.muted : logRow.tone
                                                font.pixelSize: 9
                                                font.bold: true
                                                Layout.preferredWidth: 10
                                                horizontalAlignment: Text.AlignHCenter
                                            }
                                            Text {
                                                visible: backend.devices.length > 1
                                                text: logRow.device
                                                color: root.textSecondary
                                                font.pixelSize: 9
                                                elide: Text.ElideRight
                                                Layout.maximumWidth: 62
                                            }
                                            Text {
                                                id: logText
                                                text: logRow.message
                                                color: logRow.level === "SDK" || logRow.level === "DEBUG" ? root.muted : logRow.level === "INFO" ? "#B7D4E2" : logRow.tone
                                                font.family: "Cascadia Mono"
                                                font.pixelSize: 10
                                                elide: Text.ElideRight
                                                maximumLineCount: 1
                                                Layout.fillWidth: true
                                            }
                                            Rectangle {
                                                visible: logRow.count > 1
                                                width: countText.implicitWidth + 8
                                                height: 13
                                                radius: 6
                                                color: Qt.rgba(logRow.tone.r, logRow.tone.g, logRow.tone.b, 0.2)
                                                border.color: Qt.rgba(logRow.tone.r, logRow.tone.g, logRow.tone.b, 0.6)
                                                Text { id: countText; anchors.centerIn: parent; text: "×" + logRow.count; color: logRow.tone; font.pixelSize: 8; font.bold: true }
                                            }
                                        }
                                        HoverHandler { id: rowHover }
                                        ToolTip.visible: rowHover.hovered && logText.truncated
                                        ToolTip.delay: 500
                                        ToolTip.text: logRow.message
                                        TapHandler {
                                            acceptedButtons: Qt.RightButton
                                            onTapped: {
                                                logMenu.lineText = logRow.lineText
                                                logMenu.popup()
                                            }
                                        }
                                    }
                                    HudMenu {
                                        id: logMenu
                                        property string lineText: ""
                                        HudMenuItem {
                                            text: "Copy line"
                                            glyph: "\uE8C8"
                                            onTriggered: backend.copyText(logMenu.lineText)
                                        }
                                        HudMenuItem {
                                            text: "Copy all"
                                            glyph: "\uE8C8"
                                            enabled: logList.count > 0
                                            onTriggered: backend.copyText(root.allLogText())
                                        }
                                        HudMenuSeparator {}
                                        HudMenuItem {
                                            text: "Clear log"
                                            glyph: "\uE74D"
                                            destructive: true
                                            enabled: logList.count > 0
                                            onTriggered: backend.clearLog()
                                        }
                                    }
                                }
                                EmptyHint {
                                    anchors.centerIn: parent
                                    visible: logList.count === 0
                                    width: parent.width - 24
                                    glyph: backend.logFilter === "alerts" ? "✓" : "◇"
                                    text: backend.logFilter === "alerts" ? "No warnings or errors" : backend.logFilter === "device" ? "No device reports yet" : "Log is empty"
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: calendarPage
                property date shownMonth: new Date()
                property date selectedDate: new Date()
                property int viewMode: 0
                function dateKey(value) {
                    return value.getFullYear() + "-" + String(value.getMonth() + 1).padStart(2, "0") + "-" + String(value.getDate()).padStart(2, "0")
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
                function timelineDate(minutes) {
                    const value = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate(), cutoffHour, 0, 0, 0)
                    value.setMinutes(value.getMinutes() + Math.max(0, Math.min(1435, Math.round(minutes / 5) * 5)))
                    return dateKey(value) + "T" + String(value.getHours()).padStart(2, "0") + ":" + String(value.getMinutes()).padStart(2, "0")
                }
                function currentObservingKey() {
                    const value = new Date()
                    if (value.getHours() < cutoffHour)
                        value.setDate(value.getDate() - 1)
                    return dateKey(value)
                }
                HudSplitView {
                    id: calendarSplit
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
                                return total + " planned session" + (total === 1 ? "" : "s") + "  ·  " + night + " on the selected night  ·  night rolls over at " + String(calendarPage.cutoffHour).padStart(2, "0") + ":00"
                            }
                            HudButton { text: "MONTH"; buttonColor: calendarPage.viewMode === 0 ? "#0E3A48" : root.surfaceHigh; foregroundColor: calendarPage.viewMode === 0 ? root.accent : root.textSecondary; onClicked: calendarPage.viewMode = 0 }
                            HudButton { text: "NIGHT"; buttonColor: calendarPage.viewMode === 1 ? "#0E3A48" : root.surfaceHigh; foregroundColor: calendarPage.viewMode === 1 ? root.accent : root.textSecondary; onClicked: calendarPage.viewMode = 1 }
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
                            HudButton { text: "TODAY"; onClicked: { calendarPage.shownMonth = new Date(); calendarPage.selectedDate = new Date() } }
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
                            HudButton { text: "+ NEW SESSION"; busyText: "OPENING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate)) }
                        }
                        RowLayout {
                            visible: calendarPage.viewMode === 0
                            Layout.fillWidth: true
                            Repeater { model: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]; Text { required property string modelData; text: modelData; color: root.accent; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } }
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
                                    color: isSelected ? "#C0123C52" : cellHover.hovered ? "#B00E1C2C" : inMonth ? "#99070D16" : "#55070D16"
                                    border.color: dropArea.containsDrag ? root.accent : isSelected ? Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.7) : root.outline
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                    HoverHandler { id: cellHover }
                                    Rectangle {
                                        // animated accent ring on tonight's cell
                                        anchors.fill: parent
                                        anchors.margins: 2
                                        radius: 3
                                        color: "transparent"
                                        border.color: root.accent
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
                                        color: root.accent
                                        font.pixelSize: 7; font.bold: true; font.letterSpacing: 1
                                    }
                                    DropArea {
                                        id: dropArea
                                        anchors.fill: parent
                                        keys: ["session"]
                                        onDropped: drop => {
                                            const sid = root.dragSessionId(drop)
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
                                        Text { text: dayCell.cellDate.getDate(); color: dayCell.isToday ? root.accent : dayCell.inMonth ? root.textPrimary : "#3E5A6A"; font.pixelSize: 11; font.bold: dayCell.isToday; font.family: "Cascadia Mono" }
                                        Repeater {
                                            model: dayCell.daySessions.slice(0, 3)
                                            delegate: Rectangle {
                                                id: sessionChip
                                                required property var modelData
                                                property string sessionId: modelData.id
                                                readonly property color deviceTone: modelData.device_color || root.accent
                                                width: parent.width
                                                height: 22
                                                radius: 2
                                                color: root.statusFill(modelData.status)
                                                border.color: Qt.rgba(root.statusColor(modelData.status).r, root.statusColor(modelData.status).g, root.statusColor(modelData.status).b, 0.55)
                                                opacity: root.sessionDragActive && root.sessionDragData.id === sessionId ? 0.35 : 1
                                                Rectangle { x: 1; y: 1; width: 3; height: parent.height - 2; radius: 1; color: sessionChip.deviceTone }
                                                Rectangle {
                                                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 3
                                                    width: 5; height: 5; radius: 2.5
                                                    color: root.statusColor(modelData.status)
                                                    visible: String(modelData.status) !== "planned"
                                                }
                                                Text { anchors.fill: parent; anchors.leftMargin: 8; anchors.rightMargin: 10; anchors.topMargin: 4; anchors.bottomMargin: 4; text: calendarPage.chipText(modelData); color: root.textPrimary; font.pixelSize: 9; elide: Text.ElideRight }
                                                SessionDragArea {
                                                    anchors.fill: parent
                                                    dragItem: sessionChip.modelData
                                                    pressedAction: function() { calendarPage.selectedDate = dayCell.cellDate }
                                                }
                                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: sessionMenu.open() }
                                                SessionContextMenu {
                                                    id: sessionMenu
                                                    sessionData: sessionChip.modelData
                                                }
                                            }
                                        }
                                        Text {
                                            visible: dayCell.daySessions.length > 3
                                            text: "+" + (dayCell.daySessions.length - 3) + " more"
                                            color: root.accent
                                            font.pixelSize: 9
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: calendarPage.selectedDate = dayCell.cellDate
                                            }
                                        }
                                    }
                                    TapHandler { onTapped: calendarPage.selectedDate = dayCell.cellDate }
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
                                            const sid = root.dragSessionId(drop)
                                            if (sid)
                                                backend.moveSessionStart(sid, calendarPage.timelineDate(drop.y / nightTimeline.hourHeight * 60))
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
                                                color: root.textSecondary
                                                font.pixelSize: 10
                                                font.family: "Cascadia Mono"
                                            }
                                            Rectangle { x: 58; width: parent.width - 66; height: 1; color: index % 6 === 0 ? root.accent : root.outline; opacity: index % 6 === 0 ? 0.55 : 0.4 }
                                        }
                                    }
                                    Repeater {
                                        model: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
                                        delegate: Rectangle {
                                            id: timelineSession
                                            required property var modelData
                                            property string sessionId: modelData.id
                                            x: 66
                                            y: calendarPage.timelineMinutes(modelData.start_time) / 60 * nightTimeline.hourHeight + 5
                                            width: timelineTrack.width - 82
                                            height: Math.max(36, Number(modelData.planned_duration_seconds || 0) / 3600 * nightTimeline.hourHeight - 6)
                                            radius: 3
                                            color: root.statusFill(modelData.status)
                                            border.color: root.statusColor(modelData.status)
                                            border.width: 1
                                            opacity: root.sessionDragActive && root.sessionDragData.id === sessionId ? 0.35 : 0.96
                                            Rectangle { x: 0; y: 0; width: 4; height: parent.height; radius: 2; color: modelData.device_color || root.accent }
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 8
                                                anchors.leftMargin: 12
                                                Text { text: "⋮⋮"; color: root.accent; font.pixelSize: 16 }
                                                ColumnLayout {
                                                    Layout.fillWidth: true; spacing: 0
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 8
                                                        Text { text: modelData.start_time; color: root.accent; font.family: "Cascadia Mono"; font.pixelSize: 12; font.bold: true }
                                                        Text { text: modelData.target_name; color: root.textPrimary; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                        StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                                    }
                                                    Text { text: modelData.duration_text + "  ·  " + modelData.device_name; color: root.textSecondary; font.pixelSize: 10; visible: timelineSession.height > 48 }
                                                }
                                                HudButton { text: "EDIT"; implicitHeight: 24; visible: timelineSession.height > 44; onClicked: sessionDialog.openExisting(timelineSession.modelData) }
                                                HudButton { text: "RUN"; implicitHeight: 24; visible: timelineSession.height > 44; enabled: modelData.status !== "running"; onClicked: backend.runNow(modelData.id) }
                                            }
                                            SessionDragArea {
                                                anchors.left: parent.left
                                                anchors.top: parent.top
                                                anchors.bottom: parent.bottom
                                                width: 48
                                                dragItem: timelineSession.modelData
                                            }
                                            TapHandler { acceptedButtons: Qt.RightButton; onTapped: timelineMenu.popup() }
                                            SessionContextMenu { id: timelineMenu; sessionData: timelineSession.modelData }
                                        }
                                    }
                                    Rectangle {
                                        visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey()
                                        x: 58
                                        width: parent.width - 66
                                        height: 2
                                        color: root.warning
                                        y: calendarPage.timelineMinutes(Qt.formatTime(new Date(), "HH:mm")) / 60 * nightTimeline.hourHeight
                                        Text { anchors.right: parent.right; anchors.bottom: parent.top; text: "NOW"; color: root.warning; font.pixelSize: 9; font.bold: true }
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
                            HudChip { label: nightPanel.nightSessions.length + (nightPanel.nightSessions.length === 1 ? " SESSION" : " SESSIONS"); tone: nightPanel.nightSessions.length > 0 ? root.accent : root.textSecondary }
                            HudChip { visible: nightPanel.nightSeconds > 0; label: "PLAN"; value: root.formatDuration(nightPanel.nightSeconds); tone: root.textSecondary }
                            HudChip { visible: calendarPage.dateKey(calendarPage.selectedDate) === calendarPage.currentObservingKey(); label: "TONIGHT"; tone: root.warning; glow: true }
                            Item { Layout.fillWidth: true }
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
                                        color: root.statusFill(modelData.status)
                                        border.color: Qt.rgba(root.statusColor(modelData.status).r, root.statusColor(modelData.status).g, root.statusColor(modelData.status).b, 0.5)
                                        opacity: root.sessionDragActive && root.sessionDragData.id === sessionId ? 0.35 : 1
                                        Rectangle { x: 0; y: 0; width: 3; height: parent.height; radius: 1; color: modelData.device_color || root.accent }
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 8
                                            anchors.leftMargin: 11
                                            spacing: 2
                                            RowLayout {
                                                Layout.fillWidth: true
                                                spacing: 6
                                                Text { text: modelData.start_time; color: root.accent; font.pixelSize: 12; font.bold: true; font.family: "Cascadia Mono" }
                                                Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                StatusChip { status: modelData.status; visible: modelData.status !== "planned" }
                                            }
                                            Text { text: modelData.subtitle + " · " + modelData.duration_text; color: root.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                            RowLayout {
                                                HudButton { text: "EDIT"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                                HudButton { text: "RESET"; implicitHeight: 24; visible: root.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                                HudButton { text: "RUN"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
                                            }
                                        }
                                        SessionDragArea {
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.top: parent.top
                                            height: 36
                                            dragItem: daySessionRow.modelData
                                        }
                                        TapHandler {
                                            acceptedButtons: Qt.RightButton
                                            onTapped: daySessionMenu.popup()
                                        }
                                        SessionContextMenu {
                                            id: daySessionMenu
                                            sessionData: daySessionRow.modelData
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

            Item {
                Flickable {
                    id: sessionsFlick
                    anchors.fill: parent
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick
                    contentWidth: width
                    contentHeight: Math.max(height, sessionsColumn.implicitHeight)
                    interactive: contentHeight > height + 1
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                ColumnLayout {
                    id: sessionsColumn
                    width: sessionsFlick.width
                    height: Math.max(implicitHeight, sessionsFlick.height)
                    spacing: 10
                    PageHeader {
                        title: "SESSIONS"
                        subtitle: {
                            const planned = backend.sessions.filter(item => item.status === "planned").length
                            const running = backend.sessions.filter(item => item.status === "running").length
                            return planned + " planned · " + (running > 0 ? running + " running · " : "") + backend.templates.length + " template" + (backend.templates.length === 1 ? "" : "s")
                        }
                        HudButton { text: "IMPORT STELLARIUM"; busy: backend.uiBusy === "stellarium"; busyText: "IMPORTING…"; busyMs: 0; enabled: backend.uiBusy === ""; onClicked: backend.importStellarium() }
                        HudButton { text: "IMPORT TELESCOPIUS"; busy: backend.uiBusy === "telescopius"; busyText: backend.uiBusy === "telescopius" ? "IMPORTING…" : "OPENING…"; enabled: backend.uiBusy === ""; onClicked: telescopiusDialog.open() }
                        HudButton { text: "+ MANUAL SESSION"; busyText: "OPENING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(Qt.formatDate(new Date(), "yyyy-MM-dd")) }
                    }
                    TabBar {
                        id: sessionsTabs
                        Layout.fillWidth: true
                        background: Rectangle { color: "transparent" }
                        TabButton {
                            text: "SCHEDULED"
                            font.letterSpacing: 1.2
                            contentItem: Text { text: parent.text; color: parent.checked ? root.accent : root.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                            background: Rectangle { color: parent.checked ? "#123C52" : "#0A1524"; border.color: parent.checked ? root.accent : root.outline }
                        }
                        TabButton {
                            text: "TEMPLATES"
                            font.letterSpacing: 1.2
                            contentItem: Text { text: parent.text; color: parent.checked ? root.accent : root.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                            background: Rectangle { color: parent.checked ? "#123C52" : "#0A1524"; border.color: parent.checked ? root.accent : root.outline }
                        }
                    }
                    StackLayout {
                        currentIndex: sessionsTabs.currentIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 280
                        Layout.preferredHeight: 0
                        Item {
                            EmptyHint { visible: backend.sessions.length === 0; glyph: "✦"; text: "No scheduled sessions yet. Create one manually or import a Stellarium / Telescopius target list."; anchors.centerIn: parent }
                            SessionInsertDrop {
                                id: scheduledInsert
                                anchors.fill: parent
                                targetList: scheduledList
                                rowHeight: 84
                                ListView {
                                    id: scheduledList
                                    anchors.fill: parent
                                    clip: true
                                    spacing: 8
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: HiddenBar {}
                                    ScrollBar.horizontal: HiddenBar {}
                                    model: backend.sessions
                                    delegate: HudPanel {
                                        id: scheduledRow
                                        required property var modelData
                                        width: ListView.view.width
                                        height: 84
                                        opacity: root.sessionDragActive && root.sessionDragData.id === modelData.id ? 0.35 : 1
                                        overlay: [
                                            SessionDragArea {
                                                anchors.left: parent.left
                                                anchors.top: parent.top
                                                anchors.bottom: parent.bottom
                                                width: 56
                                                dragItem: scheduledRow.modelData
                                            }
                                        ]
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Rectangle { width: 4; Layout.fillHeight: true; color: modelData.device_color || root.accent }
                                            Text { text: "⋮⋮"; color: root.accent; font.pixelSize: 16 }
                                            ColumnLayout {
                                                Layout.preferredWidth: 280
                                                Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                Text { text: modelData.subtitle; color: root.textSecondary; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true; visible: modelData.subtitle !== modelData.target_name }
                                            }
                                            Text { text: modelData.start_date + "  " + modelData.start_time; color: root.textPrimary; font.family: "Cascadia Mono"; Layout.preferredWidth: 150 }
                                            RowLayout {
                                                Layout.preferredWidth: 120
                                                spacing: 6
                                                Rectangle { width: 6; height: 6; radius: 3; color: modelData.device_color || root.accent }
                                                Text { text: modelData.device_name; color: root.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                                            }
                                            Text { text: modelData.duration_text; color: root.textSecondary; font.family: "Cascadia Mono"; Layout.preferredWidth: 80 }
                                            StatusChip { status: modelData.status; implicitWidth: 86; implicitHeight: 22 }
                                            HudButton { text: "EDIT"; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                            HudButton { text: "RESET"; visible: root.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                            HudButton { text: "RUN"; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
                                        }
                                        TapHandler { acceptedButtons: Qt.RightButton; onTapped: scheduledMenu.popup() }
                                        SessionContextMenu {
                                            id: scheduledMenu
                                            sessionData: modelData
                                        }
                                    }
                                }
                            }
                        }
                        Item {
                            EmptyHint { anchors.centerIn: parent; visible: backend.templates.length === 0; glyph: "❖"; text: "No templates yet. Save a session as a reusable template, or import Stellarium / Telescopius." }
                            GridView {
                                anchors.fill: parent
                                clip: true
                                cellWidth: 340
                                cellHeight: 170
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: HiddenBar {}
                                ScrollBar.horizontal: HiddenBar {}
                                model: backend.templates
                                delegate: HudPanel {
                                    id: templateCard
                                    required property var modelData
                                    width: 324
                                    height: 156
                                    title: modelData.name
                                    Text {
                                        visible: modelData.target_name !== modelData.name
                                        text: modelData.target_name
                                        color: root.textPrimary
                                        font.pixelSize: 16
                                        Layout.fillWidth: true
                                        wrapMode: Text.WordWrap
                                    }
                                    Text { text: modelData.summary; color: root.textSecondary; Layout.fillWidth: true }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        HudButton { text: "EDIT"; busyText: "OPENING…"; onClicked: sessionDialog.openTemplate(templateCard.modelData) }
                                        HudButton { text: "SCHEDULE"; Layout.fillWidth: true; busyText: "SCHEDULING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.scheduleTemplate(modelData.id) }
                                        HudButton { text: "DELETE"; busyText: "DELETING…"; onClicked: backend.deleteTemplate(modelData.id) }
                                    }
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: templateMenu.popup()
                                    }
                                    HudMenu {
                                        id: templateMenu
                                        HudMenuItem {
                                            text: "Edit"
                                            glyph: "\uE70F"
                                            onTriggered: sessionDialog.openTemplate(templateCard.modelData)
                                        }
                                        HudMenuItem {
                                            text: "Schedule"
                                            glyph: "\uE768"
                                            onTriggered: backend.scheduleTemplate(templateCard.modelData.id)
                                        }
                                        HudMenuSeparator {}
                                        HudMenuItem {
                                            text: "Delete"
                                            glyph: "\uE74D"
                                            destructive: true
                                            onTriggered: backend.deleteTemplate(templateCard.modelData.id)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                }
            }

            Item {
                id: historyPage
                property string query: ""
                property int outcomeFilter: 0
                property int expandedIndex: -1
                readonly property var filteredHistory: {
                    const items = backend.history || []
                    const q = historyPage.query.trim().toLowerCase()
                    const out = []
                    for (let i = 0; i < items.length; i++) {
                        const item = items[i]
                        if (historyPage.outcomeFilter === 1 && !item.ok)
                            continue
                        if (historyPage.outcomeFilter === 2 && item.ok)
                            continue
                        if (q) {
                            const hay = [item.date, item.target_name, item.device_name, item.outcome, item.summary, item.notes].join(" ").toLowerCase()
                            if (hay.indexOf(q) < 0)
                                continue
                        }
                        out.push(item)
                    }
                    return out
                }
                readonly property int filteredCount: filteredHistory.length
                readonly property int filteredFrames: filteredHistory.reduce((sum, item) => sum + (item.frame_count || 0), 0)
                readonly property int filteredOk: filteredHistory.filter(item => item.ok).length
                readonly property int filteredSeconds: filteredHistory.reduce((sum, item) => sum + (item.actual_duration_seconds || 0), 0)
                function formatHours(seconds) {
                    const hours = Math.max(0, seconds) / 3600
                    return hours >= 10 ? hours.toFixed(0) + "h" : hours.toFixed(1) + "h"
                }
                function resetExpanded() { historyPage.expandedIndex = -1 }
                onQueryChanged: resetExpanded()
                onOutcomeFilterChanged: resetExpanded()
                Connections { target: backend; function onHistoryChanged() { historyPage.resetExpanded() } }

                Flickable {
                    id: historyFlick
                    anchors.fill: parent
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick
                    contentWidth: width
                    contentHeight: Math.max(height, historyColumn.implicitHeight)
                    interactive: contentHeight > height + 1
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                ColumnLayout {
                    id: historyColumn
                    width: historyFlick.width
                    height: Math.max(implicitHeight, historyFlick.height)
                    spacing: 10
                    PageHeader {
                        title: "HISTORY"
                        subtitle: backend.history.length === 0
                            ? "Completed runs appear here with timing, frames and outcome"
                            : backend.history.length + " recorded run" + (backend.history.length === 1 ? "" : "s") + "  ·  click a row for timing, frames and outcome details"
                        HudButton {
                            text: "CLEAR HISTORY"
                            enabled: backend.history.length > 0
                            busyText: "CLEARING…"
                            buttonColor: "#3A1218"
                            foregroundColor: root.danger
                            onClicked: {
                                confirmDialog.kind = "clearHistory"
                                confirmDialog.headingText = "CLEAR HISTORY"
                                confirmDialog.confirmLabel = "CLEAR ALL"
                                confirmDialog.summary = "Delete every recorded run? This cannot be undone."
                                confirmDialog.open()
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                ["SESSIONS", String(historyPage.filteredCount), "◈", root.accent],
                                ["FRAMES", String(historyPage.filteredFrames), "▦", root.accent],
                                ["SUCCESS", historyPage.filteredCount ? Math.round(100 * historyPage.filteredOk / historyPage.filteredCount) + "%" : "—", "✓",
                                    historyPage.filteredCount === 0 ? root.textSecondary : (historyPage.filteredOk === historyPage.filteredCount ? root.success : (historyPage.filteredOk * 2 >= historyPage.filteredCount ? root.warning : root.danger))],
                                ["IMAGED", historyPage.formatHours(historyPage.filteredSeconds), "◷", root.notice]
                            ]
                            delegate: HudPanel {
                                id: statTile
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 90
                                overlay: [
                                    Text {
                                        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                                        text: statTile.modelData[2]
                                        color: statTile.modelData[3]
                                        opacity: 0.35
                                        font.pixelSize: 20
                                    }
                                ]
                                Text { text: modelData[1]; color: modelData[3]; font.pixelSize: 28; font.bold: true; font.family: "Cascadia Mono" }
                                Text { text: modelData[0]; color: root.textSecondary; font.pixelSize: 11; font.letterSpacing: 1.4 }
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        HudField {
                            Layout.fillWidth: true
                            placeholderText: "Search target, device, or outcome"
                            onTextChanged: historyPage.query = text
                        }
                        HudCombo {
                            Layout.preferredWidth: 160
                            model: ["All outcomes", "Completed", "Failed"]
                            currentIndex: historyPage.outcomeFilter
                            onActivated: historyPage.outcomeFilter = currentIndex
                        }
                    }
                    HudPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 240
                        Layout.preferredHeight: 0
                        EmptyHint {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.topMargin: 40
                            visible: historyPage.filteredCount === 0
                            glyph: backend.history.length === 0 ? "◷" : "⌕"
                            text: backend.history.length === 0
                                ? "No completed runs yet. History appears after a session finishes."
                                : "No runs match this search."
                        }
                        ColumnLayout {
                            visible: historyPage.filteredCount > 0
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredHeight: 0
                            spacing: 0
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                Row {
                                    anchors.fill: parent
                                    Text { width: 22; height: parent.height; text: ""; color: root.accent }
                                    Repeater {
                                        model: [
                                            {label: "DATE", w: 0.12}, {label: "TARGET", w: 0.24}, {label: "DEVICE", w: 0.13},
                                            {label: "FRAMES", w: 0.08}, {label: "PLANNED", w: 0.10}, {label: "ACTUAL", w: 0.10},
                                            {label: "OUTCOME", w: 0.23}
                                        ]
                                        Text {
                                            required property var modelData
                                            width: (parent.width - 22) * modelData.w
                                            height: parent.height
                                            text: modelData.label
                                            color: root.accent
                                            font.pixelSize: 10
                                            font.bold: true
                                            verticalAlignment: Text.AlignVCenter
                                            elide: Text.ElideRight
                                            leftPadding: 6
                                        }
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: root.outline }
                            ListView {
                                id: historyList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                clip: true
                                spacing: 0
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: HiddenBar {}
                                ScrollBar.horizontal: HiddenBar {}
                                model: historyPage.filteredHistory
                                delegate: Rectangle {
                                    id: historyRow
                                    required property var modelData
                                    required property int index
                                    readonly property bool expanded: historyPage.expandedIndex === index
                                    width: ListView.view.width
                                    height: rowBody.implicitHeight
                                    readonly property color outcomeTone: modelData.ok ? root.success : root.danger
                                    readonly property real deltaSeconds: Number(modelData.delta_seconds || 0)
                                    readonly property color deltaTone: Math.abs(deltaSeconds) < 60 ? root.textSecondary : (deltaSeconds > 0 ? root.warning : root.notice)
                                    color: expanded ? "#22123C52" : (rowHover.hovered ? "#180E1C2C" : (index % 2 ? "#140A1520" : "transparent"))
                                    border.color: expanded ? root.outline : "transparent"
                                    Behavior on color { ColorAnimation { duration: 100 } }
                                    HoverHandler { id: rowHover }
                                    Rectangle { x: 0; y: 0; width: 2; height: parent.height; color: historyRow.outcomeTone; opacity: historyRow.expanded ? 1 : 0.55 }
                                    Column {
                                        id: rowBody
                                        width: parent.width
                                        Item {
                                            width: parent.width
                                            height: 42
                                            Row {
                                                anchors.fill: parent
                                                Text {
                                                    width: 22
                                                    height: parent.height
                                                    text: historyRow.expanded ? "▾" : "▸"
                                                    color: root.accent
                                                    font.pixelSize: 10
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                                Repeater {
                                                    model: [
                                                        {text: historyRow.modelData.date, w: 0.12, color: root.textPrimary, mono: true},
                                                        {text: historyRow.modelData.target_name, w: 0.24, color: root.textPrimary, bold: true},
                                                        {text: historyRow.modelData.device_name, w: 0.13, color: root.textPrimary, dot: historyRow.modelData.device_color || root.accent},
                                                        {text: String(historyRow.modelData.frame_count || 0), w: 0.08, color: root.textSecondary, mono: true},
                                                        {text: historyRow.modelData.planned_text, w: 0.10, color: root.textSecondary, mono: true},
                                                        {text: historyRow.modelData.actual_text, w: 0.10, color: historyRow.deltaTone, mono: true},
                                                        {text: (historyRow.modelData.ok ? "✓ " : "✗ ") + historyRow.modelData.outcome, w: 0.23, color: historyRow.outcomeTone}
                                                    ]
                                                    Item {
                                                        required property var modelData
                                                        width: (parent.width - 22) * modelData.w
                                                        height: parent.height
                                                        Rectangle {
                                                            visible: !!parent.modelData.dot
                                                            anchors.left: parent.left; anchors.leftMargin: 6
                                                            anchors.verticalCenter: parent.verticalCenter
                                                            width: 6; height: 6; radius: 3
                                                            color: parent.modelData.dot || "transparent"
                                                        }
                                                        Text {
                                                            anchors.fill: parent
                                                            text: parent.modelData.text
                                                            color: parent.modelData.color
                                                            font.pixelSize: 12
                                                            font.bold: !!parent.modelData.bold
                                                            font.family: parent.modelData.mono ? "Cascadia Mono" : root.font.family
                                                            elide: Text.ElideRight
                                                            verticalAlignment: Text.AlignVCenter
                                                            leftPadding: parent.modelData.dot ? 16 : 6
                                                            rightPadding: 6
                                                        }
                                                    }
                                                }
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                acceptedButtons: Qt.LeftButton
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: historyPage.expandedIndex = historyRow.expanded ? -1 : historyRow.index
                                            }
                                            TapHandler {
                                                acceptedButtons: Qt.RightButton
                                                onTapped: historyMenu.popup()
                                            }
                                            HudMenu {
                                                id: historyMenu
                                                HudMenuItem {
                                                    text: "Run again"
                                                    glyph: "\uE768"
                                                    enabled: !!historyRow.modelData.has_session
                                                    onTriggered: backend.runNow(historyRow.modelData.session_id)
                                                }
                                                HudMenuSeparator {}
                                                HudMenuItem {
                                                    text: "Copy target name"
                                                    glyph: "\uE8C8"
                                                    enabled: !!historyRow.modelData.target_name
                                                    onTriggered: backend.copyText(String(historyRow.modelData.target_name))
                                                }
                                                HudMenuItem {
                                                    text: "Copy outcome"
                                                    glyph: "\uE8C8"
                                                    enabled: !!historyRow.modelData.outcome
                                                    onTriggered: backend.copyText(String(historyRow.modelData.outcome))
                                                }
                                                HudMenuSeparator {}
                                                HudMenuItem {
                                                    text: "Remove"
                                                    glyph: "\uE74D"
                                                    destructive: true
                                                    onTriggered: backend.deleteHistoryRecord(historyRow.modelData.id)
                                                }
                                            }
                                        }
                                        Item {
                                            visible: historyRow.expanded
                                            width: parent.width
                                            height: visible ? detailCol.implicitHeight + 16 : 0
                                            ColumnLayout {
                                                id: detailCol
                                                width: parent.width - 30
                                                x: 22
                                                y: 4
                                                spacing: 6
                                                Text {
                                                    visible: !!(historyRow.modelData.summary)
                                                    text: historyRow.modelData.summary
                                                    color: root.textPrimary
                                                    font.pixelSize: 12
                                                }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: 4
                                                    columnSpacing: 16
                                                    rowSpacing: 4
                                                    Text { text: "SCHEDULED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "STARTED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "ENDED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "VARIANCE"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: historyRow.modelData.scheduled_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text { text: historyRow.modelData.started_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text { text: historyRow.modelData.ended_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text {
                                                        text: (historyRow.deltaSeconds > 60 ? "▲ " : historyRow.deltaSeconds < -60 ? "▼ " : "● ") + historyRow.modelData.delta_text
                                                        color: Math.abs(historyRow.deltaSeconds) < 60 ? root.success : historyRow.deltaTone
                                                        font.pixelSize: 12
                                                        font.family: "Cascadia Mono"
                                                    }
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: historyRow.modelData.outcome
                                                    color: historyRow.modelData.ok ? root.success : root.danger
                                                    wrapMode: Text.Wrap
                                                    font.pixelSize: 12
                                                }
                                                Text {
                                                    visible: !!(historyRow.modelData.notes)
                                                    Layout.fillWidth: true
                                                    text: historyRow.modelData.notes
                                                    color: root.textSecondary
                                                    wrapMode: Text.Wrap
                                                    font.pixelSize: 11
                                                }
                                                RowLayout {
                                                    HudButton {
                                                        text: "RUN AGAIN"
                                                        enabled: !!historyRow.modelData.has_session
                                                        busyText: "STARTING…"
                                                        buttonColor: "#0E3A48"
                                                        foregroundColor: root.accent
                                                        onClicked: backend.runNow(historyRow.modelData.session_id)
                                                    }
                                                    HudButton {
                                                        text: "REMOVE"
                                                        busyText: "REMOVING…"
                                                        onClicked: backend.deleteHistoryRecord(historyRow.modelData.id)
                                                    }
                                                    Item { Layout.fillWidth: true }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                }
            }

            Item {
                id: settingsPage
                property string loadedDeviceId: ""
                property string loadedSnapshot: ""
                function currentPayload() {
                    return {
                        id: backend.selectedDeviceId, name: nameField.text, model: modelField.currentText,
                        ip_address: ipField.text, camera: cameraField.currentIndex === 1 ? "wide" : "tele",
                        ble_enabled: bleField.checked,
                        latitude: Number(latField.text), longitude: Number(lonField.text),
                        timezone_name: timezoneField.selectedName || timezoneField.editText, stellarium_url: stellariumField.text,
                        wifi_mode: ["auto", "ap", "sta"][wifiModeField.currentIndex],
                        wifi_ssid: ssidField.text, wifi_password: wifiField.text,
                        ble_password: blePasswordField.text,
                        observing_day_cutoff_hour: cutoffField.value, slew_seconds: Number(slewField.text),
                        settle_seconds: Number(settleField.text), calibration_seconds: Number(calibrationField.text),
                        autofocus_seconds: Number(autofocusField.text), infinite_focus_seconds: Number(infinityField.text),
                        polar_seconds: Number(polarField.text), readout_seconds: Number(readoutField.text),
                        pane_slew_seconds: Number(paneField.text), startup_seconds: Number(startupField.text)
                    }
                }
                readonly property bool dirty: JSON.stringify(currentPayload()) !== loadedSnapshot
                function isDirty() { return dirty }
                function saveCurrent() {
                    backend.saveDevice(JSON.stringify(currentPayload()))
                    loadedSnapshot = JSON.stringify(currentPayload())
                }
                function load() {
                    const d = backend.selectedDevice
                    loadedDeviceId = d.id || ""
                    const hw = d.hardware || {}
                    nameField.text = d.name || ""
                    modelField.currentIndex = Math.max(0, ["Dwarf II", "Dwarf 3", "Dwarf Mini"].indexOf(d.model))
                    ipField.text = d.ip_address || ""
                    cameraField.currentIndex = d.camera === "wide" ? 1 : 0
                    bleField.checked = d.ble_enabled !== false
                    latField.text = d.latitude
                    lonField.text = d.longitude
                    timezoneField.setFromName(d.timezone_name || "")
                    stellariumField.text = d.stellarium_url || "http://localhost:8090"
                    wifiModeField.currentIndex = Math.max(0, ["auto", "ap", "sta"].indexOf(d.wifi_mode || "auto"))
                    ssidField.text = d.wifi_ssid || ""
                    wifiField.text = d.wifi_password || ""
                    blePasswordField.text = d.ble_password || "DWARF_12345678"
                    cutoffField.value = d.observing_day_cutoff_hour || 12
                    slewField.text = hw.slew_seconds || 20
                    settleField.text = hw.settle_seconds || 10
                    calibrationField.text = hw.calibration_seconds || 90
                    autofocusField.text = hw.autofocus_seconds || 45
                    infinityField.text = hw.infinite_focus_seconds || 15
                    polarField.text = hw.polar_seconds || 180
                    readoutField.text = hw.readout_seconds || 1.2
                    paneField.text = hw.pane_slew_seconds || 12
                    startupField.text = hw.startup_seconds || 8
                    loadedSnapshot = JSON.stringify(currentPayload())
                }
                Component.onCompleted: load()
                Connections {
                    target: backend
                    function onSelectedDeviceChanged() {
                        if (settingsPage.loadedDeviceId !== backend.selectedDeviceId)
                            settingsPage.load()
                        else if (!ipField.text && backend.selectedDevice.ip_address)
                            ipField.text = backend.selectedDevice.ip_address
                    }
                }

                function applyLocation(item) {
                    if (!item)
                        return
                    timezoneField.setFromName(item.name)
                    if (item.latitude !== undefined && item.latitude !== null)
                        latField.text = Number(item.latitude).toFixed(5)
                    if (item.longitude !== undefined && item.longitude !== null)
                        lonField.text = Number(item.longitude).toFixed(5)
                }

                Flickable {
                    id: settingsFlick
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: settingsFooter.top
                    anchors.bottomMargin: 8
                    contentWidth: width
                    contentHeight: settingsColumn.implicitHeight + 24
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                    Column {
                        id: settingsColumn
                        width: settingsFlick.width
                        spacing: 12
                        PageHeader {
                            width: parent.width
                            title: "SETTINGS"
                            subtitle: "Device, connection and timing profiles  ·  Astro Dwarf v" + backend.appVersion
                            DeviceCombo {}
                            HudButton { text: "+ ADD DEVICE"; busyText: "ADDING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.addDevice() }
                            HudButton { text: "REMOVE DEVICE"; busyText: "REMOVING…"; buttonColor: "#3A1218"; foregroundColor: root.danger; onClicked: backend.deleteDevice(backend.selectedDeviceId) }
                        }
                        HudPanel {
                            title: "◫  INTERFACE"
                            width: parent.width
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "NAV BUTTONS" }
                                HudCombo {
                                    Layout.fillWidth: true
                                    model: ["Bottom", "Top (below header)"]
                                    currentIndex: layoutSettings.navBarOnTop ? 1 : 0
                                    onActivated: layoutSettings.navBarOnTop = currentIndex === 1
                                }
                                Item { Layout.fillWidth: true }
                                Item { Layout.fillWidth: true }
                            }
                            Text {
                                text: "Applies immediately. Choose whether the page buttons and icon sit under the header or at the bottom of the window."
                                color: root.textSecondary
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                        HudPanel {
                            title: "◈  DEVICE"
                            width: parent.width
                            headerExtra: [
                                HudChip {
                                    label: backend.selectedDevice.connected ? "ONLINE" : "OFFLINE"
                                    tone: backend.selectedDevice.connected ? root.success : root.textSecondary
                                    dim: !backend.selectedDevice.connected
                                    glow: !!backend.selectedDevice.connected
                                }
                            ]
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "NAME" }
                                HudField { id: nameField; Layout.fillWidth: true }
                                FieldLabel { text: "MODEL" }
                                HudCombo { id: modelField; model: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]; Layout.fillWidth: true }
                                FieldLabel { text: "CAMERA" }
                                HudCombo { id: cameraField; model: ["Tele", "Wide"]; Layout.fillWidth: true }
                                FieldLabel { text: "TIMEZONE" }
                                HudSearchCombo {
                                    id: timezoneField
                                    Layout.fillWidth: true
                                    allItems: backend.timezones
                                    onItemChosen: (item) => settingsPage.applyLocation(item)
                                }
                                FieldLabel { text: "LATITUDE" }
                                HudField { id: latField; Layout.fillWidth: true }
                                FieldLabel { text: "LONGITUDE" }
                                HudField { id: lonField; Layout.fillWidth: true }
                                FieldLabel { text: "STELLARIUM" }
                                HudField { id: stellariumField; Layout.fillWidth: true }
                                FieldLabel { text: "NIGHT CUTOFF" }
                                SpinBox {
                                    id: cutoffField
                                    from: 0
                                    to: 23
                                    value: 12
                                    editable: true
                                    Layout.fillWidth: true
                                    palette.text: root.textPrimary
                                    palette.base: "#0A1524"
                                    palette.button: "#122033"
                                    palette.buttonText: root.accent
                                    palette.highlight: root.accent
                                }
                            }
                        }
                        HudPanel {
                            title: "⇌  CONNECTION"
                            width: parent.width
                            Text {
                                text: "Bluetooth finds the telescope and sets its Wi‑Fi. In AP mode this app then joins the Dwarf hotspot on this computer. Commands and the live stream always use that Wi‑Fi link."
                                color: root.textSecondary
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "IP ADDRESS" }
                                HudField { id: ipField; Layout.fillWidth: true; placeholderText: "192.168.88.1 or LAN IP" }
                                FieldLabel { text: "CONNECTION MODE" }
                                HudCombo { id: wifiModeField; model: ["Auto", "AP hotspot", "STA station"]; Layout.fillWidth: true }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.columnSpan: 4
                                    wrapMode: Text.Wrap
                                    color: root.textSecondary
                                    text: wifiModeField.currentIndex === 1
                                        ? "AP: the telescope broadcasts a hotspot such as DWARF3_1. This app joins it using the hotspot password (Bluetooth password if you leave hotspot password empty). The IP is usually 192.168.88.1."
                                        : wifiModeField.currentIndex === 2
                                            ? "STA: Bluetooth tells the telescope to join your home or public router. Enter that router's name and password. This computer must already be on the same Wi-Fi."
                                            : "Auto: keep the mode already set on the telescope. If it is on its hotspot, this app joins that Wi-Fi automatically."
                                }
                                FieldLabel { text: "ROUTER WIFI NAME"; visible: wifiModeField.currentIndex === 2 }
                                HudField {
                                    id: ssidField
                                    Layout.fillWidth: true
                                    visible: wifiModeField.currentIndex === 2
                                    placeholderText: "Router name, not DWARF3_…"
                                }
                                FieldLabel { text: wifiModeField.currentIndex === 1 ? "HOTSPOT PASSWORD" : "ROUTER WIFI PASSWORD"; visible: wifiModeField.currentIndex !== 0 }
                                HudField {
                                    id: wifiField
                                    echoMode: TextInput.Password
                                    Layout.fillWidth: true
                                    visible: wifiModeField.currentIndex !== 0
                                    placeholderText: wifiModeField.currentIndex === 1 ? "Leave empty to use the Bluetooth password" : ""
                                }
                                FieldLabel { text: "BLUETOOTH PASSWORD" }
                                HudField {
                                    id: blePasswordField
                                    echoMode: TextInput.Password
                                    Layout.fillWidth: true
                                    placeholderText: "Factory default DWARF_12345678"
                                }
                                Item { Layout.fillWidth: true }
                                Item { Layout.fillWidth: true }
                                HudCheck {
                                    id: bleField
                                    text: "Use Bluetooth when the IP is empty or this computer cannot reach it"
                                    Layout.columnSpan: 4
                                }
                            }
                        }
                        HudPanel {
                            title: "◷  HARDWARE DURATION PROFILE"
                            width: parent.width
                            Text { text: "These overheads size calendar blocks and remaining-time estimates."; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 6
                                columnSpacing: 8
                                rowSpacing: 6
                                FieldLabel { text: "SLEW S" }
                                HudField { id: slewField; Layout.fillWidth: true }
                                FieldLabel { text: "SETTLE S" }
                                HudField { id: settleField; Layout.fillWidth: true }
                                FieldLabel { text: "CALIBRATE S" }
                                HudField { id: calibrationField; Layout.fillWidth: true }
                                FieldLabel { text: "AUTOFOCUS S" }
                                HudField { id: autofocusField; Layout.fillWidth: true }
                                FieldLabel { text: "INFINITY S" }
                                HudField { id: infinityField; Layout.fillWidth: true }
                                FieldLabel { text: "POLAR S" }
                                HudField { id: polarField; Layout.fillWidth: true }
                                FieldLabel { text: "READOUT S" }
                                HudField { id: readoutField; Layout.fillWidth: true }
                                FieldLabel { text: "PANE SLEW S" }
                                HudField { id: paneField; Layout.fillWidth: true }
                                FieldLabel { text: "STARTUP S" }
                                HudField { id: startupField; Layout.fillWidth: true }
                            }
                        }
                        HudPanel {
                            title: "⇩  LEGACY IMPORT"
                            width: parent.width
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Import old Astro_Sessions JSON without modifying the old app."; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                }
                                HudButton { text: "CHOOSE FOLDER…"; busyText: "OPENING…"; onClicked: legacyDialog.open() }
                            }
                        }
                    }
                }
                Rectangle {
                    // sticky save bar
                    id: settingsFooter
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 46
                    radius: 3
                    color: settingsPage.dirty ? "#C00E2A3A" : "#B3070D16"
                    border.color: settingsPage.dirty ? Qt.rgba(root.warning.r, root.warning.g, root.warning.b, 0.6) : root.outline
                    Behavior on color { ColorAnimation { duration: 180 } }
                    Behavior on border.color { ColorAnimation { duration: 180 } }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 10
                        spacing: 10
                        LedDot { on: true; onColor: settingsPage.dirty ? root.warning : root.success; pulse: settingsPage.dirty }
                        Text {
                            Layout.fillWidth: true
                            text: settingsPage.dirty
                                ? "UNSAVED CHANGES · " + (backend.selectedDevice.name || "device").toUpperCase()
                                : "ALL CHANGES SAVED · " + (backend.selectedDevice.name || "device").toUpperCase()
                            color: settingsPage.dirty ? root.warning : root.textSecondary
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 1.2
                            elide: Text.ElideRight
                        }
                        HudButton {
                            text: "REVERT"
                            visible: settingsPage.dirty
                            onClicked: settingsPage.load()
                        }
                        HudButton {
                            text: settingsPage.dirty ? "SAVE DEVICE" : "SAVED"
                            enabled: settingsPage.dirty
                            busyText: "SAVING…"
                            buttonColor: settingsPage.dirty ? "#0E3A48" : root.surfaceHigh
                            foregroundColor: settingsPage.dirty ? root.accent : root.textSecondary
                            onClicked: settingsPage.saveCurrent()
                        }
                    }
                }
            }
        }

        PageNavBar {
            visible: !layoutSettings.navBarOnTop
            Layout.bottomMargin: 8
        }
        }

        Rectangle {
            anchors.fill: parent
            enabled: false
            color: "transparent"
            border.color: "#3F6E82"
            border.width: 2
            z: 2000
        }
    }

    Rectangle {
        id: sessionDragProxy
        parent: root.contentItem
        visible: root.sessionDragActive
        enabled: false
        z: 4000
        width: 196
        height: 30
        radius: 2
        property string sessionId: ""
        color: root.statusFill(root.sessionDragData.status || "")
        border.color: root.statusColor(root.sessionDragData.status || "")
        border.width: 2
        opacity: 0.92
        Drag.keys: ["session"]
        Drag.hotSpot.x: width / 2
        Drag.hotSpot.y: height / 2
        Drag.proposedAction: Qt.MoveAction
        Drag.supportedActions: Qt.MoveAction
        function startDrag(item, pos) {
            sessionId = item.id || ""
            x = pos.x - width / 2
            y = pos.y - height / 2
            root.beginSessionDrag(item, pos)
            Drag.active = true
        }
        function moveDrag(pos) {
            x = pos.x - width / 2
            y = pos.y - height / 2
            root.updateSessionDrag(pos)
        }
        function finishDrag() {
            root.sessionDragActive = false
            if (Drag.active)
                Drag.drop()
            Drag.active = false
            root.endSessionDrag()
            sessionId = ""
        }
        function cancelDrag() {
            root.sessionDragActive = false
            if (Drag.active)
                Drag.cancel()
            Drag.active = false
            root.endSessionDrag()
            sessionId = ""
        }
        Text {
            anchors.fill: parent
            anchors.margins: 5
            text: root.dragLabel(root.sessionDragData)
            color: root.textPrimary
            font.pixelSize: 10
            font.bold: true
            elide: Text.ElideRight
        }
    }

    Item {
        // Stacked toast notifications, top-right below the title bar.
        id: toastHost
        parent: Overlay.overlay
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 74
        anchors.rightMargin: 14
        width: Math.min(380, root.width - 40)
        height: toastColumn.implicitHeight
        z: 900
        readonly property int maxToasts: 4
        property int nextId: 1

        function durationFor(level) {
            switch (String(level || "").toLowerCase()) {
            case "error": return 8000
            case "warning": return 6000
            case "success": return 4000
            default: return 3000
            }
        }
        function push(message, level, detail) {
            const text = String(message || "").trim()
            if (text === "")
                return
            const tone = String(level || "info").toLowerCase()
            for (let i = 0; i < toastModel.count; i++) {
                const existing = toastModel.get(i)
                if (existing.message === text && existing.level === tone) {
                    toastModel.setProperty(i, "count", existing.count + 1)
                    toastModel.setProperty(i, "detail", String(detail || existing.detail || ""))
                    toastModel.setProperty(i, "restart", existing.restart + 1)
                    return
                }
            }
            while (toastModel.count >= maxToasts)
                toastModel.remove(0)
            toastModel.append({
                toastId: nextId++,
                message: text,
                level: tone,
                detail: String(detail || ""),
                count: 1,
                restart: 0,
                duration: durationFor(tone)
            })
        }
        function dismiss(toastId) {
            for (let i = 0; i < toastModel.count; i++) {
                if (toastModel.get(i).toastId === toastId) {
                    toastModel.remove(i)
                    return
                }
            }
        }

        ListModel { id: toastModel }

        Column {
            id: toastColumn
            anchors.right: parent.right
            width: parent.width
            spacing: 8
            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220 }
                NumberAnimation { property: "x"; from: 60; to: 0; duration: 260; easing.type: Easing.OutCubic }
            }
            move: Transition { NumberAnimation { properties: "y"; duration: 200; easing.type: Easing.OutCubic } }
            Repeater {
                model: toastModel
                delegate: Rectangle {
                    id: toastCard
                    required property int index
                    required property int toastId
                    required property string message
                    required property string level
                    required property string detail
                    required property int count
                    required property int restart
                    required property int duration
                    readonly property color tone: root.toneForLevel(level)
                    readonly property bool hovering: toastHover.hovered
                    width: toastColumn.width
                    height: toastBody.implicitHeight + 18
                    radius: 4
                    color: "#F00A1220"
                    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.75)
                    border.width: 1
                    opacity: 1
                    clip: true
                    onRestartChanged: {
                        toastTimer.restart()
                        toastProgress.restartSweep()
                    }
                    Rectangle {
                        // soft glow
                        anchors.fill: parent; anchors.margins: -3; radius: 7
                        color: "transparent"; border.color: toastCard.tone; opacity: 0.18
                    }
                    Rectangle { x: 0; y: 0; width: 3; height: parent.height; color: toastCard.tone }
                    RowLayout {
                        id: toastBody
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: 12
                        anchors.rightMargin: 10
                        spacing: 10
                        Rectangle {
                            width: 26; height: 26; radius: 13
                            color: Qt.rgba(toastCard.tone.r, toastCard.tone.g, toastCard.tone.b, 0.16)
                            border.color: Qt.rgba(toastCard.tone.r, toastCard.tone.g, toastCard.tone.b, 0.6)
                            Layout.alignment: Qt.AlignTop
                            Text { anchors.centerIn: parent; text: root.glyphForLevel(toastCard.level); color: toastCard.tone; font.pixelSize: 13; font.bold: true }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    text: toastCard.message
                                    color: root.textPrimary
                                    font.pixelSize: 12
                                    font.bold: true
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Rectangle {
                                    visible: toastCard.count > 1
                                    width: toastCount.implicitWidth + 10; height: 16; radius: 8
                                    color: toastCard.tone
                                    Text { id: toastCount; anchors.centerIn: parent; text: "×" + toastCard.count; color: "#05080F"; font.pixelSize: 9; font.bold: true }
                                }
                            }
                            Text {
                                visible: toastCard.detail !== ""
                                text: toastCard.detail
                                color: root.textSecondary
                                font.pixelSize: 10
                                wrapMode: Text.Wrap
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            RowLayout {
                                visible: toastCard.level === "error" || toastCard.level === "warning"
                                spacing: 10
                                Layout.topMargin: 2
                                Text {
                                    text: "VIEW LOG"
                                    color: viewLogHover.hovered ? root.textPrimary : toastCard.tone
                                    font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.2
                                    HoverHandler { id: viewLogHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler {
                                        onTapped: {
                                            root.goToPage(0)
                                            backend.setLogFilter("alerts")
                                            toastHost.dismiss(toastCard.toastId)
                                        }
                                    }
                                }
                                Text {
                                    text: "DISMISS"
                                    color: dismissHover.hovered ? root.textPrimary : root.textSecondary
                                    font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.2
                                    HoverHandler { id: dismissHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: toastHost.dismiss(toastCard.toastId) }
                                }
                            }
                        }
                        Text {
                            text: "✕"
                            color: closeHover.hovered ? root.textPrimary : root.muted
                            font.pixelSize: 11
                            Layout.alignment: Qt.AlignTop
                            HoverHandler { id: closeHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: toastHost.dismiss(toastCard.toastId) }
                        }
                    }
                    Rectangle {
                        // auto-dismiss progress rail
                        id: toastProgress
                        anchors.left: parent.left
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: 3
                        height: 2
                        color: toastCard.tone
                        opacity: 0.8
                        width: parent.width - 3
                        function restartSweep() {
                            sweep.stop()
                            width = toastCard.width - 3
                            sweep.restart()
                        }
                        NumberAnimation on width {
                            id: sweep
                            to: 0
                            duration: toastCard.duration
                            running: true
                            paused: running && toastCard.hovering
                        }
                    }
                    Timer {
                        id: toastTimer
                        interval: toastCard.duration
                        running: !toastCard.hovering
                        repeat: false
                        onTriggered: toastHost.dismiss(toastCard.toastId)
                    }
                    HoverHandler { id: toastHover }
                    TapHandler {
                        acceptedButtons: Qt.LeftButton
                        onTapped: toastHost.dismiss(toastCard.toastId)
                    }
                }
            }
        }
    }

    Connections {
        target: backend
        function onToast(message, level, detail) {
            toastHost.push(message, level, detail)
        }
        function onLocationLookupReady(item) {
            if (locationDialog.visible)
                locationDialog.applyLocation(item)
            else
                settingsPage.applyLocation(item)
        }
        function onSelectedDeviceChanged() { root.maybeAskLocation() }
    }

    Dialog {
        id: locationDialog
        modal: true
        closePolicy: Popup.NoAutoClose
        anchors.centerIn: Overlay.overlay
        width: 520
        padding: 18
        height: Math.min(root.height - 60, locationColumn.implicitHeight + padding * 2)
        background: Rectangle { color: "#0B1520"; border.color: root.accent }
        function applyLocation(item) {
            if (!item)
                return
            locationTimezone.setFromName(item.name)
            if (item.latitude !== undefined && item.latitude !== null)
                locationLat.text = Number(item.latitude).toFixed(5)
            if (item.longitude !== undefined && item.longitude !== null)
                locationLon.text = Number(item.longitude).toFixed(5)
        }
        onOpened: {
            const d = backend.selectedDevice
            locationTimezone.setFromName(d.timezone_name && d.location_configured ? d.timezone_name : "")
            locationLat.text = d.location_configured ? d.latitude : ""
            locationLon.text = d.location_configured ? d.longitude : ""
        }
        contentItem: ColumnLayout {
            id: locationColumn
            spacing: 12
            Text { text: "OBSERVING LOCATION"; color: root.accent; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text {
                text: "Choose a timezone or city so Astro Dwarf can set longitude and latitude for this telescope. A location is required before connecting or running sessions."
                color: root.textPrimary
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            FieldLabel { text: "TIMEZONE / CITY" }
            HudSearchCombo {
                id: locationTimezone
                Layout.fillWidth: true
                allItems: backend.timezones
                onItemChosen: (item) => locationDialog.applyLocation(item)
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                FieldLabel { text: "LAT" }
                HudField { id: locationLat; Layout.fillWidth: true; readOnly: true }
                FieldLabel { text: "LON" }
                HudField { id: locationLon; Layout.fillWidth: true; readOnly: true }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton {
                    text: "SAVE LOCATION"
                    enabled: locationTimezone.selectedName.length > 0 || locationTimezone.editText.length > 0
                    busyText: "SAVING…"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: backend.saveObservingLocation(JSON.stringify({
                        id: backend.selectedDeviceId,
                        timezone_name: locationTimezone.selectedName || locationTimezone.editText,
                        latitude: Number(locationLat.text),
                        longitude: Number(locationLon.text)
                    }))
                }
            }
        }
    }

    Dialog {
        id: settingsLeaveDialog
        property int pendingPage: -1
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 480
        height: 176
        padding: 16
        background: Rectangle { color: "#0B1520"; border.color: root.warning }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "UNSAVED SETTINGS"; color: root.warning; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text { text: "Save your device settings before leaving this page?"; color: root.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: settingsLeaveDialog.close() }
                HudButton {
                    text: "DISCARD"
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: {
                        const idx = settingsLeaveDialog.pendingPage
                        settingsLeaveDialog.close()
                        settingsPage.load()
                        root.currentPage = idx
                    }
                }
                HudButton {
                    text: "SAVE"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: {
                        const idx = settingsLeaveDialog.pendingPage
                        settingsPage.saveCurrent()
                        settingsLeaveDialog.close()
                        root.currentPage = idx
                    }
                }
            }
        }
    }

    Dialog {
        id: confirmDialog
        property string operation: ""
        property string summary: ""
        property string kind: "device"
        property string headingText: "CONFIRM COMMAND"
        property string confirmLabel: "CONFIRM"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 420
        height: 176
        padding: 16
        background: Rectangle { color: "#0B1520"; border.color: root.danger }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: confirmDialog.headingText; color: root.danger; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text { text: confirmDialog.summary; color: root.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: confirmDialog.close() }
                HudButton {
                    text: confirmDialog.confirmLabel
                    busyText: "WORKING…"
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: {
                        if (confirmDialog.kind === "clearHistory")
                            backend.clearHistory()
                        else
                            backend.deviceAction(backend.selectedDeviceId, confirmDialog.operation)
                        confirmDialog.close()
                    }
                }
            }
        }
    }

    FileDialog {
        id: telescopiusDialog
        title: "Import Telescopius CSV"
        nameFilters: ["CSV files (*.csv)"]
        onAccepted: backend.importTelescopius(selectedFile)
    }
    FolderDialog {
        id: legacyDialog
        title: "Select old Astro_Sessions folder"
        onAccepted: backend.importLegacy(selectedFolder)
    }

    Dialog {
        id: sessionDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 900)
        height: Math.min(root.height - 80, 720)
        property string editingId: ""
        property bool editingTemplate: false
        padding: 0

        function fillForm(data) {
            sessionName.text = data.pane_name || data.name || ""
            targetName.text = (data.target && data.target.name) ? data.target.name : (data.target_name || "")
            const kind = data.target ? data.target.kind : "equatorial"
            targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
            ra.text = data.target && data.target.ra_hours != null ? data.target.ra_hours : ""
            dec.text = data.target && data.target.dec_degrees != null ? data.target.dec_degrees : ""
            exposure.text = data.camera.exposure_seconds
            gain.text = data.camera.gain
            frames.text = data.camera.frame_count
            camera.currentIndex = data.camera.camera === "wide" ? 1 : 0
            binning.currentIndex = Math.max(0, ["1", "2"].indexOf(String(data.camera.binning)))
            const ir = data.camera.ir_filter || "VIS Filter"
            irFilter.currentIndex = Math.max(0, ["VIS Filter", "Astro Filter", "Duo-Band Filter", "VIS"].indexOf(ir) % 3)
            rows.text = data.mosaic.rows
            columns.text = data.mosaic.columns
            rotation.text = data.mosaic.rotation_degrees
            hScale.text = data.mosaic.horizontal_scale
            vScale.text = data.mosaic.vertical_scale
            waitBefore.text = data.workflow.wait_before_seconds
            waitAfter.text = data.workflow.wait_after_seconds
            notes.text = data.notes || ""
            calibrate.checked = data.workflow.calibrate
            autofocus.checked = data.workflow.autofocus
            infiniteFocus.checked = data.workflow.infinite_focus
            polar.checked = data.workflow.polar_align
            doGoto.checked = data.workflow.goto
            saveTemplate.checked = false
        }
        function formPayload() {
            return {
                id: sessionDialog.editingId, name: sessionName.text, target: targetName.text,
                target_kind: targetType.currentText, ra: ra.text, dec: dec.text,
                scheduled_start: startTime.text, device_id: backend.selectedDeviceId,
                camera: camera.currentIndex === 1 ? "wide" : "tele", exposure: Number(exposure.text),
                gain: Number(gain.text), frame_count: Number(frames.text), binning: Number(binning.currentText),
                ir_filter: irFilter.currentText, rows: Number(rows.text), columns: Number(columns.text),
                rotation: Number(rotation.text), horizontal_scale: Number(hScale.text), vertical_scale: Number(vScale.text),
                wait_before: Number(waitBefore.text), wait_after: Number(waitAfter.text), notes: notes.text,
                calibrate: calibrate.checked, autofocus: autofocus.checked, infinite_focus: infiniteFocus.checked,
                polar_align: polar.checked, goto: doGoto.checked, save_template: saveTemplate.checked
            }
        }
        function openForDate(day) {
            editingId = ""
            editingTemplate = false
            sessionName.text = ""
            targetName.text = ""
            targetType.currentIndex = 0
            ra.text = ""
            dec.text = ""
            startTime.text = day + "T22:00"
            exposure.text = "15"
            gain.text = "80"
            frames.text = "120"
            binning.currentIndex = 0
            irFilter.currentIndex = 0
            camera.currentIndex = 0
            rows.text = "1"
            columns.text = "1"
            rotation.text = "0"
            hScale.text = "150"
            vScale.text = "150"
            waitBefore.text = "0"
            waitAfter.text = "10"
            notes.text = ""
            calibrate.checked = true
            autofocus.checked = true
            infiniteFocus.checked = false
            polar.checked = false
            doGoto.checked = true
            saveTemplate.checked = false
            open()
        }
        function openExisting(data) {
            editingId = data.id
            editingTemplate = false
            fillForm(data)
            startTime.text = String(data.scheduled_start).substring(0, 16)
            open()
        }
        function openTemplate(data) {
            editingId = data.id
            editingTemplate = true
            fillForm(data)
            startTime.text = ""
            open()
        }

        background: Rectangle { color: "#0B1520"; border.color: root.accent }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text { text: sessionDialog.editingTemplate ? "EDIT TEMPLATE" : (sessionDialog.editingId ? "EDIT SESSION" : "NEW SESSION"); color: root.accent; font.pixelSize: 20; font.letterSpacing: 2; Layout.fillWidth: true }
                HudButton { text: "×"; implicitWidth: 40; onClicked: sessionDialog.close() }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 10
                rowSpacing: 8
                FieldLabel { text: "SESSION NAME" }
                HudField { id: sessionName; Layout.fillWidth: true; Layout.columnSpan: 2 }
                FieldLabel { text: "TARGET TYPE" }
                HudCombo { id: targetType; model: ["equatorial", "solar", "none"]; Layout.fillWidth: true }
                HudField { id: targetName; placeholderText: "Target name"; Layout.fillWidth: true }
                FieldLabel { text: "RA HOURS" }
                HudField { id: ra; Layout.fillWidth: true }
                HudField { id: dec; placeholderText: "Dec degrees"; Layout.fillWidth: true }
                FieldLabel { text: "START"; visible: !sessionDialog.editingTemplate }
                HudField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2; visible: !sessionDialog.editingTemplate }
                FieldLabel { text: "CAMERA" }
                HudCombo { id: camera; model: ["Tele", "Wide"]; Layout.fillWidth: true; Layout.columnSpan: currentIndex === 1 ? 2 : 1 }
                HudCombo {
                    id: irFilter
                    visible: camera.currentIndex === 0
                    model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                    Layout.fillWidth: true
                }
                FieldLabel { text: "EXPOSURE" }
                HudField { id: exposure; Layout.fillWidth: true }
                HudField { id: gain; placeholderText: "Gain"; Layout.fillWidth: true }
                FieldLabel { text: "FRAMES" }
                HudField { id: frames; Layout.fillWidth: true }
                HudCombo { id: binning; model: ["1", "2"]; Layout.fillWidth: true }
                FieldLabel { text: "MOSAIC" }
                HudField { id: rows; placeholderText: "Rows"; Layout.fillWidth: true }
                HudField { id: columns; placeholderText: "Columns"; Layout.fillWidth: true }
                FieldLabel { text: "ROTATION / SCALE" }
                HudField { id: rotation; placeholderText: "Rotation °"; Layout.fillWidth: true }
                RowLayout {
                    HudField { id: hScale; placeholderText: "H scale"; Layout.fillWidth: true }
                    HudField { id: vScale; placeholderText: "V scale"; Layout.fillWidth: true }
                }
                FieldLabel { text: "WAIT S" }
                HudField { id: waitBefore; placeholderText: "Before"; Layout.fillWidth: true }
                HudField { id: waitAfter; placeholderText: "After"; Layout.fillWidth: true }
                FieldLabel { text: "NOTES" }
                HudField { id: notes; Layout.fillWidth: true; Layout.columnSpan: 2 }
            }
            RowLayout {
                HudCheck { id: calibrate; text: "Calibrate" }
                HudCheck { id: autofocus; text: "Auto focus" }
                HudCheck { id: infiniteFocus; text: "Infinity focus" }
                HudCheck { id: polar; text: "Polar / EQ" }
                HudCheck { id: doGoto; text: "GOTO" }
                HudCheck { id: saveTemplate; text: "Save template"; visible: !sessionDialog.editingTemplate }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: sessionDialog.close() }
                HudButton {
                    text: sessionDialog.editingTemplate ? "SAVE TEMPLATE" : "SAVE SESSION"
                    busyText: "SAVING…"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: {
                        const payload = JSON.stringify(sessionDialog.formPayload())
                        if (sessionDialog.editingTemplate)
                            backend.saveTemplate(payload)
                        else
                            backend.saveSession(payload)
                        sessionDialog.close()
                    }
                }
            }
        }
    }
}
