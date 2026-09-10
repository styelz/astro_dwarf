import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import "."
import "components"
import "pages"
import "dialogs"

ApplicationWindow {
    id: root
    width: Math.min(1480, Screen.desktopAvailableWidth - 24)
    height: Math.min(920, Screen.desktopAvailableHeight - 48)
    minimumWidth: 1040
    minimumHeight: 620
    visible: true
    title: "ASTRO DWARF"
    color: Theme.windowBase
    font.family: Theme.fontUi
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

    readonly property var scopeTelemetry: (backend.selectedDevice && backend.selectedDevice.telemetry) || ({})
    readonly property string scopeActivityDetail: String((backend.selectedDevice && backend.selectedDevice.activity_detail) || "")
    readonly property bool scopeActivityFromDevice: !!(backend.selectedDevice && backend.selectedDevice.activity_from_device)
    property int currentPage: 0
    property real joySpeed: 1
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

    function confirmBulkDelete(kind, idMap, noun) {
        const ids = Util.idSetKeys(idMap)
        if (!ids.length)
            return
        const plural = ids.length === 1 ? noun : noun + "s"
        confirmDialog.kind = kind
        confirmDialog.pendingIds = ids
        confirmDialog.headingText = "DELETE " + plural.toUpperCase()
        confirmDialog.confirmLabel = ids.length === 1 ? "DELETE" : "DELETE " + ids.length
        confirmDialog.summary = kind === "deleteSessions"
            ? "Delete " + ids.length + " " + plural + "? Running sessions will be skipped. This cannot be undone."
            : "Delete " + ids.length + " " + plural + "? This cannot be undone."
        confirmDialog.open()
    }
    function confirmRemoveDevice(deviceId) {
        const id = String(deviceId || backend.selectedDeviceId || "")
        if (!id)
            return
        if (!backend.devices || backend.devices.length <= 1) {
            backend.deleteDevice(id)
            return
        }
        let name = "this telescope"
        const devices = backend.devices
        for (let i = 0; i < devices.length; i++) {
            if (devices[i].id === id) {
                name = devices[i].name || name
                break
            }
        }
        confirmDialog.kind = "deleteDevice"
        confirmDialog.pendingIds = [id]
        confirmDialog.headingText = "REMOVE DEVICE"
        confirmDialog.confirmLabel = "REMOVE"
        confirmDialog.summary = "Remove " + name + "? This cannot be undone."
        confirmDialog.open()
    }
    function scopeActivityText() {
        if (root.scopePending)
            return "SENDING · " + root.scopePending.replace(/_/g, " ").toUpperCase()
        const label = Util.activityLabel(root.scopeActivity)
        if (label)
            return root.scopeActivityDetail ? label + " · " + root.scopeActivityDetail : label
        if (root.scopeImaging)
            return "SESSION RUNNING"
        return root.scopeOnline ? "IDLE" : "OFFLINE"
    }
    function activityColor() {
        if (!root.scopeOnline)
            return Theme.textSecondary
        if (root.scopePending)
            return Theme.accent
        switch (root.scopeActivity) {
        case "imaging":
        case "record": return Theme.danger
        case "poweroff": return Theme.danger
        case "": return root.scopeImaging ? Theme.danger : Theme.success
        default: return Theme.notice
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

    function nextSessionCountdown() {
        backend.clockText
        if (!backend.upcomingSessions || backend.upcomingSessions.length === 0)
            return "No planned sessions"
        const startMs = Number(backend.upcomingSessions[0].start_epoch_ms)
        const seconds = Math.floor(((isNaN(startMs) ? new Date(backend.upcomingSessions[0].scheduled_start).getTime() : startMs) - Date.now()) / 1000)
        return seconds <= 0 ? "Due now" : "T− " + Util.durationLabel(seconds)
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

    Settings {
        id: layoutSettings
        category: "controlLayout"
        property bool navBarOnTop: false
    }

    Component.onCompleted: {
        DragCoordinator.contentItem = root.contentItem
        DragCoordinator.proxy = sessionDragProxy
        DragCoordinator.timeline = calendarPage
        root.syncWindowFrame()
    }

    // Keep the native Windows caption in step with the theme hue (debounced while the slider moves).
    function syncWindowFrame() {
        backend.applyWindowFrame(String(Theme.surface), String(Theme.outlineStrong), String(Theme.accent))
    }
    readonly property real hueDistance: Theme.hueDistance
    Connections {
        target: Theme
        function onHueChanged() { frameSyncTimer.restart() }
        function onBrightnessChanged() { frameSyncTimer.restart() }
    }
    Timer {
        id: frameSyncTimer
        interval: 150
        repeat: false
        onTriggered: root.syncWindowFrame()
    }

    Timer {
        interval: 1
        running: true
        repeat: false
        onTriggered: root.maybeAskLocation()
    }

    function maybeAskLocation() {
        if (locationDialog.addingDevice)
            return
        const configured = !!backend.selectedDevice.location_configured
        if (!configured) {
            if (!locationDialog.visible)
                locationDialog.open()
            return
        }
        if (locationDialog.visible)
            locationDialog.close()
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
        Rectangle { anchors.fill: parent; color: root.dataPage ? Theme.hsl(0.082, 0.684, 0.037, 0.800) : Theme.hsl(0.082, 0.684, 0.037, 0.600) }
        Rectangle {
            // Tints the (cyan) background art toward the chosen hue; stronger the further from default.
            // Eases off as brightness drops so a dimmed HUD isn't still flooded by the wash.
            anchors.fill: parent
            color: Theme.accent
            opacity: ((root.dataPage ? 0.03 : 0.07) + root.hueDistance * (root.dataPage ? 0.25 : 0.5))
                     * (Theme.brightness < 0 ? 1 + Theme.brightness * 0.85 : 1)
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.maximumHeight: 64
            Layout.fillHeight: false
            color: Theme.hsl(0.082, 0.565, 0.045, 0.753)
            border.color: Theme.outline
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.15; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) }
                    GradientStop { position: 0.85; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.7) }
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
                        Text { text: "ASTRO DWARF"; color: Theme.accent; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                        Text { text: "OBSERVATORY COMMAND  ·  v" + backend.appVersion; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 12; Layout.bottomMargin: 12; color: Theme.outline }
                DeviceCombo {}
                HudButton {
                    text: backend.selectedDevice.connected ? "DISCONNECT" : "CONNECT"
                    busy: backend.selectedDevice.connecting || backend.selectedDevice.disconnecting
                    busyText: backend.selectedDevice.connecting ? "CONNECTING…" : "DISCONNECTING…"
                    busyMs: 0
                    enabled: !busy
                    buttonColor: backend.selectedDevice.connected ? Theme.fillSuccess : Theme.fillActive
                    foregroundColor: Theme.accent
                    onClicked: backend.selectedDevice.connected
                        ? backend.disconnectDevice(backend.selectedDeviceId)
                        : backend.connectDevice(backend.selectedDeviceId)
                }
                HudButton {
                    text: backend.schedulerEnabled ? "SCHEDULER ON" : "SCHEDULER OFF"
                    busyText: "UPDATING…"
                    enabled: backend.schedulerEnabled || backend.anyDeviceConnected
                    buttonColor: backend.schedulerEnabled ? Theme.fillSuccess : Theme.surfaceHigh
                    foregroundColor: backend.schedulerEnabled ? Theme.success : Theme.textPrimary
                    onClicked: backend.setSchedulerEnabled(!backend.schedulerEnabled)
                }
                HudButton {
                    text: "STOP ALL"
                    busy: backend.selectedDevice.pending_action === "stop_all"
                    busyText: "STOPPING…"
                    busyMs: 0
                    // A running session must always be stoppable, even while the link is still coming up.
                    enabled: root.commandEnabled("stop_all") || (root.scopeImaging && root.scopePending !== "stop_all")
                    buttonColor: Theme.fillDanger
                    foregroundColor: Theme.danger
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
                            {label: "LINK", on: root.scopeOnline, color: Theme.success},
                            {label: "AUTO", on: backend.schedulerEnabled, color: Theme.success},
                            {label: "IMAGE", on: root.scopeImaging || root.scopeActivity === "imaging", color: Theme.danger}
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            spacing: 4
                            LedDot { on: modelData.on; onColor: modelData.color; pulse: true }
                            Text { text: modelData.label; color: modelData.on ? Theme.textPrimary : Theme.textSecondary; font.pixelSize: 8; font.bold: true }
                        }
                    }
                    Rectangle { width: 1; Layout.preferredHeight: 18; color: Theme.outline; visible: root.scopeOnline }
                    RowLayout {
                        // mini battery readout
                        id: titleBattery
                        readonly property var t: root.scopeTelemetry
                        readonly property int percent: root.scopeOnline && t.battery_percent !== undefined ? Number(t.battery_percent) : -1
                        readonly property color tone: percent < 0 ? Theme.muted : Util.toneColor(Util.batteryTone(percent))
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
                            color: titleBattery.percent >= 0 ? Theme.textPrimary : Theme.textSecondary
                            font.pixelSize: 10; font.family: Theme.fontMono; font.bold: true
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
                        Text { text: "▤"; color: titleStorage.t.storage_tone === "bad" ? Theme.danger : titleStorage.t.storage_tone === "warn" ? Theme.warning : Theme.accent; font.pixelSize: 11 }
                        Text {
                            text: root.scopeOnline && titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? String(titleStorage.t.storage_free_text || titleStorage.t.storage_text) : "—"
                            color: titleStorage.t.storage_tone === "bad" ? Theme.danger : titleStorage.t.storage_tone === "warn" ? Theme.warning : (titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? Theme.textPrimary : Theme.textSecondary)
                            font.pixelSize: 10; font.family: Theme.fontMono; font.bold: true
                        }
                        ToolTip.visible: storageHover.hovered
                        ToolTip.delay: 400
                        ToolTip.text: "Storage " + (titleStorage.t.storage_text || "—")
                        HoverHandler { id: storageHover }
                    }
                }
                Column {
                    Text { text: backend.selectedDevice.status || "OFFLINE"; color: backend.selectedDevice.connected ? Theme.success : Theme.textSecondary; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignRight; width: 160 }
                    Text { text: root.deviceLabel(); color: Theme.textSecondary; font.pixelSize: 10; horizontalAlignment: Text.AlignRight; width: 160; elide: Text.ElideRight }
                }
                Column {
                    Text { text: backend.clockText; color: Theme.accent; font.pixelSize: 22; font.family: Theme.fontMono; font.letterSpacing: 1; horizontalAlignment: Text.AlignRight; width: 168 }
                    Text {
                        text: backend.selectedDevice.timezone_name || "UTC"
                        color: Theme.textSecondary
                        font.pixelSize: 9
                        font.family: Theme.fontMono
                        horizontalAlignment: Text.AlignRight
                        width: 168
                        elide: Text.ElideRight
                    }
                }
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
            color: Theme.hsl(0.082, 0.565, 0.045, 0.502)
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.outline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12
                Text {
                    text: "DEVICES"
                    color: Theme.textSecondary
                    font.pixelSize: 9
                    font.bold: true
                    font.letterSpacing: 1.6
                }
                Rectangle { width: 1; Layout.preferredHeight: 14; color: Theme.outline }
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
                            color: deviceCard.selected ? Theme.hsl(0.036, 0.640, 0.196, 0.627) : (chipHover.hovered ? Theme.hsl(0.057, 0.548, 0.122, 0.314) : "transparent")
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            height: 2
                            width: deviceCard.selected ? parent.width - 16 : 0
                            color: Theme.accent
                            Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        }
                        RowLayout {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: 7
                            Rectangle { width: 8; height: 8; radius: 4; color: deviceCard.modelData.color }
                            Text {
                                text: deviceCard.modelData.name
                                color: deviceCard.selected ? Theme.textPrimary : Theme.textSecondary
                                font.pixelSize: 11
                                font.bold: deviceCard.selected
                            }
                            Text {
                                text: deviceCard.modelData.model
                                color: Theme.textSecondary
                                font.pixelSize: 9
                                opacity: 0.8
                            }
                            Text {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && t.battery_percent !== undefined && Number(t.battery_percent) >= 0
                                text: (t.battery_percent !== undefined ? t.battery_percent : "") + "%" + (t.charging ? "⚡" : "")
                                color: Util.toneColor(Util.batteryTone(t.battery_percent))
                                font.pixelSize: 9; font.family: Theme.fontMono; font.bold: true
                            }
                            HudChip {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && (deviceCard.modelData.busy || !!t.capture_active)
                                label: t.capture_active ? "STACK" : "IMAGING"
                                value: String(t.capture_text || "")
                                tone: Theme.danger
                                implicitHeight: 16
                            }
                            Rectangle {
                                width: 6; height: 6; radius: 3
                                color: deviceCard.modelData.connected ? (deviceCard.modelData.busy ? Theme.danger : Theme.success) : "#526077"
                                border.color: deviceCard.modelData.connected ? Theme.hsl(-0.021, 1.000, 0.924) : "transparent"
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
                                onTriggered: root.confirmRemoveDevice(deviceCard.modelData.id)
                            }
                        }
                    }
                }
            }
        }

        PageNavBar {
            visible: layoutSettings.navBarOnTop
            Layout.topMargin: 8
            currentIndex: root.currentPage
            onPageRequested: index => root.goToPage(index)
        }

        StackLayout {
            id: pages
            currentIndex: root.currentPage
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 360
            Layout.margins: 10

            ControlPage { id: controlPage }
            CalendarPage { id: calendarPage }
            SessionsPage { id: sessionsPage }
            HistoryPage { id: historyPage }
            SettingsPage { id: settingsPage }
        }

        PageNavBar {
            visible: !layoutSettings.navBarOnTop
            Layout.bottomMargin: 8
            currentIndex: root.currentPage
            onPageRequested: index => root.goToPage(index)
        }
        }

        Rectangle {
            anchors.fill: parent
            enabled: false
            color: "transparent"
            border.color: Theme.hsl(0.029, 0.347, 0.378)
            border.width: 2
            z: 2000
        }
    }

    Rectangle {
        id: sessionDragProxy
        parent: root.contentItem
        visible: DragCoordinator.active
        enabled: false
        z: 4000
        width: 220
        height: 30
        radius: 2
        property string sessionId: ""
        color: Util.statusFill(DragCoordinator.data.status || "")
        border.color: Util.statusColor(DragCoordinator.data.status || "")
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
            DragCoordinator.begin(item, pos)
            Drag.active = true
        }
        function moveDrag(pos) {
            x = pos.x - width / 2
            y = pos.y - height / 2
            DragCoordinator.update(pos)
        }
        function finishDrag() {
            DragCoordinator.active = false
            if (Drag.active)
                Drag.drop()
            Drag.active = false
            DragCoordinator.end()
            sessionId = ""
        }
        function cancelDrag() {
            DragCoordinator.active = false
            if (Drag.active)
                Drag.cancel()
            Drag.active = false
            DragCoordinator.end()
            sessionId = ""
        }
        Row {
            anchors.fill: parent
            anchors.margins: 5
            spacing: 6
            Text {
                text: DragCoordinator.previewTime || (DragCoordinator.data.start_time || "")
                color: Theme.accent
                font.pixelSize: 10
                font.bold: true
                font.family: Theme.fontMono
                width: 40
            }
            Text {
                width: Math.max(20, sessionDragProxy.width - 56)
                text: (DragCoordinator.data.target_name || DragCoordinator.data.name || "Session")
                color: Theme.textPrimary
                font.pixelSize: 10
                font.bold: true
                elide: Text.ElideRight
            }
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
                    readonly property color tone: Util.toneForLevel(level)
                    readonly property bool hovering: toastHover.hovered
                    width: toastColumn.width
                    height: toastBody.implicitHeight + 18
                    radius: 4
                    color: Theme.hsl(0.085, 0.524, 0.082, 0.941)
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
                            Text { anchors.centerIn: parent; text: Util.glyphForLevel(toastCard.level); color: toastCard.tone; font.pixelSize: 13; font.bold: true }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Text {
                                    text: toastCard.message
                                    color: Theme.textPrimary
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
                                    Text { id: toastCount; anchors.centerIn: parent; text: "×" + toastCard.count; color: Theme.windowBase; font.pixelSize: 9; font.bold: true }
                                }
                            }
                            Text {
                                visible: toastCard.detail !== ""
                                text: toastCard.detail
                                color: Theme.textSecondary
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
                                    color: viewLogHover.hovered ? Theme.textPrimary : toastCard.tone
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
                                    color: dismissHover.hovered ? Theme.textPrimary : Theme.textSecondary
                                    font.pixelSize: 9; font.bold: true; font.letterSpacing: 1.2
                                    HoverHandler { id: dismissHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: toastHost.dismiss(toastCard.toastId) }
                                }
                            }
                        }
                        Text {
                            text: "✕"
                            color: closeHover.hovered ? Theme.textPrimary : Theme.muted
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

    LocationDialog { id: locationDialog }
    SettingsLeaveDialog { id: settingsLeaveDialog }
    ConfirmDialog { id: confirmDialog }
    ScheduleTemplateDialog { id: scheduleTemplateDialog }

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

    SessionDialog { id: sessionDialog }
}
