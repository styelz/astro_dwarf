import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtQml
import QtCore
import "."
import "components"
import "pages"
import "dialogs"

ApplicationWindow {
    id: root
    objectName: "astroWindow"
    width: {
        Theme.screenHeight = Screen.height
        Math.min(Math.max(Theme.px(1480), Math.round(Screen.desktopAvailableWidth * 0.72)), Screen.desktopAvailableWidth - Theme.px(24))
    }
    height: {
        Theme.screenHeight = Screen.height
        Math.min(Math.max(Theme.px(920), Math.round(Screen.desktopAvailableHeight * 0.80)), Screen.desktopAvailableHeight - Theme.px(48))
    }
    minimumWidth: Theme.px(1040)
    minimumHeight: Theme.px(620)
    visible: true
    title: "ASTRO DWARF"
    color: Theme.windowBase
    font.family: Theme.fontUi
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
    readonly property bool windowMaximized: visibility === Window.Maximized
    onClosing: (close) => {
        PanelSwap.persist()
        if (root.currentPage === root.settingsPageIndex && settingsPage.isDirty()) {
            close.accepted = false
            root.askLeaveSettings(-2, "")
        }
    }

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
    readonly property int sessionsPageIndex: 2
    readonly property int mediaPageIndex: 4
    readonly property int skyPageIndex: 5
    readonly property int settingsPageIndex: 6
    readonly property alias skyToolsEnabled: layoutSettings.skyToolsEnabled
    // Native sky map paints above QML. Park it while these dialogs are open.
    readonly property bool appModalOpen: locationDialog.visible
        || settingsLeaveDialog.visible
        || confirmDialog.visible
        || scheduleTemplateDialog.visible
        || sessionDialog.visible
    property real joySpeed: 1
    readonly property real joyMin: 0.004
    readonly property real mappedJoySpeed: {
        const t = Math.max(0, Math.min(1, joySpeed))
        return joyMin * Math.pow(1 / joyMin, t)
    }
    readonly property string mappedJoySpeedText: {
        const pct = mappedJoySpeed * 100
        if (pct < 9.95)
            return pct.toFixed(1) + "%"
        return Math.round(pct) + "%"
    }
    readonly property bool targetLocked: backend.selectedDevice.connected && backend.currentSession.status === "running"
    readonly property bool dataPage: currentPage !== 0
    readonly property bool scopeOnline: !!(backend.selectedDevice && backend.selectedDevice.connected)
    readonly property bool scopeImaging: !!(backend.selectedDevice && backend.selectedDevice.busy)
    readonly property bool scopeLinking: !!(backend.selectedDevice && (backend.selectedDevice.connecting || backend.selectedDevice.cancelling || backend.selectedDevice.disconnecting))
    readonly property string scopePending: String((backend.selectedDevice && backend.selectedDevice.pending_action) || "")
    readonly property string scopePendingDetail: String((backend.selectedDevice && backend.selectedDevice.pending_detail) || "")
    readonly property string scopeActivity: String((backend.selectedDevice && backend.selectedDevice.activity) || "")
    function previewStatusIsRetry(status) {
        const s = String(status || "").toLowerCase()
        return s.indexOf("retry") >= 0
    }
    function previewStatusFailed(status) {
        const s = String(status || "").toLowerCase()
        if (!s || previewStatusIsRetry(s))
            return false
        return s.indexOf("fail") >= 0
            || s.indexOf("could not") >= 0
            || s.indexOf("no frames") >= 0
            || s.indexOf("invalid data") >= 0
            || s.indexOf("error opening") >= 0
    }
    readonly property bool previewFailed: previewStatusFailed(backend.previewStatus)
    readonly property bool previewStarting: backend.previewActive && !backend.previewPlaying && !previewFailed
    readonly property bool scopeMosaicRunning: {
        const mosaic = backend.mosaicPreview || ({})
        return !!(mosaic.active && mosaic.phase)
    }
    readonly property bool scopeStacking: !!(scopeTelemetry && scopeTelemetry.capture_active)
        || scopeMosaicRunning
        || scopeActivity === "imaging"
        || scopePending === "stack"
    readonly property bool scopeOccupied: scopeImaging || scopePending !== "" || scopeActivity !== "" || previewStarting || scopeStacking
    readonly property bool scopeStopping: scopePending === "stop_all" || scopePending === "stop_session"
    readonly property bool cameraLiveEnabled: commandEnabled("set_exposure")
    readonly property bool motionEnabled: commandEnabled("joystick")

    function confirmBulkDelete(kind, idMap, noun) {
        const ids = typeof idMap === "string"
            ? (idMap ? [idMap] : [])
            : Array.isArray(idMap) ? idMap : Util.idSetKeys(idMap)
        if (!ids.length)
            return
        const plural = ids.length === 1 ? noun : noun + "s"
        confirmDialog.kind = kind
        confirmDialog.pendingIds = ids
        confirmDialog.headingText = "DELETE " + plural.toUpperCase()
        confirmDialog.confirmLabel = ids.length === 1 ? "DELETE" : "DELETE " + ids.length
        confirmDialog.summary = kind === "deleteSessions"
            ? "Delete " + ids.length + " " + plural + "? Running sessions will be skipped. This cannot be undone."
            : kind === "deleteMedia" && backend.mediaSource !== "local"
            ? "Delete " + ids.length + " " + plural + " from the telescope? This wipes them from the SD card. Astro, burst, panorama, and folder items remove the whole session. Album category folders stay. Downloaded copies in Local are kept. This cannot be undone."
            : kind === "deleteMedia"
            ? "Delete " + ids.length + " " + plural + " from the local album? This cannot be undone."
            : "Delete " + ids.length + " " + plural + "? This cannot be undone."
        confirmDialog.open()
    }
    function confirmRemoveDevice(deviceId) {
        const id = String(deviceId || backend.selectedDeviceId || "")
        if (!id)
            return
        if (!backend.devices || backend.devices.length <= 1)
            return
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
    function devicePending(deviceId) {
        const devices = backend.devices
        const id = String(deviceId || "")
        for (let i = 0; i < devices.length; i++) {
            if (devices[i].id === id)
                return String(devices[i].pending_action || "")
        }
        return ""
    }
    function sessionStopping(session) {
        if (!session || session.status !== "running")
            return false
        const pending = root.devicePending(session.device_id)
        return pending === "stop_all" || pending === "stop_session"
    }
    function scopeActivityText() {
        backend.clockText
        if (root.scopeStopping)
            return (root.scopePendingDetail || "Stopping").toUpperCase()
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
        if (root.scopeStopping)
            return Theme.warning
        if (root.scopePending)
            return Theme.accent
        switch (root.scopeActivity) {
        case "imaging":
        case "record":
        case "burst":
        case "timelapse": return Theme.danger
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
            goto: "stop_goto",
            imaging: "stop_astro",
            stack: "stop_astro"
        }
        if (op === "stop_all")
            return pending !== "stop_session"
        if (op === "cancel_prime")
            return pending !== op
        if (op === "stop_session")
            return backend.currentSession.status === "running" && !root.scopeStopping
        const isStop = op === "stop_goto" || op.indexOf("stop_") === 0 || op.slice(-5) === "_stop"
        if (isStop) {
            if (op === "stop_goto" && root.scopeStacking)
                return false
            if (op === stopFor[pending] || op === stopFor[activity])
                return true
            if (op === "stop_astro")
                return !!root.scopeTelemetry.capture_active || root.scopeMosaicRunning
            return op === "stop_goto" && !!root.scopeTelemetry.tracking_active
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
            if (idx === root.settingsPageIndex && !settingsPage.isDirty())
                settingsPage.load()
            return
        }
        if (root.currentPage === root.settingsPageIndex && settingsPage.isDirty()) {
            root.askLeaveSettings(idx, "")
            return
        }
        root.currentPage = idx
        if (idx === root.settingsPageIndex)
            settingsPage.load()
    }

    function isTextEditor(item) {
        return !!(item && (item instanceof TextInput || item instanceof TextEdit))
    }

    function editorChrome(item) {
        let node = item
        while (node) {
            if (node instanceof SpinBox || node instanceof TextField)
                return node
            node = node.parent
        }
        return item
    }

    function releaseEditorFocusAt(scenePos) {
        const focused = root.activeFocusItem
        if (!root.isTextEditor(focused))
            return
        const chrome = root.editorChrome(focused)
        if (!chrome)
            return
        const local = chrome.mapFromItem(null, scenePos.x, scenePos.y)
        if (local.x >= -2 && local.y >= -2 && local.x <= chrome.width + Theme.px(2) && local.y <= chrome.height + Theme.px(2))
            return
        focused.focus = false
        if (chrome.focus)
            chrome.focus = false
    }

    component EditorClickAway: HoverHandler {
        property bool pressArmed: false
        acceptedButtons: Qt.LeftButton
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad | PointerDevice.TouchScreen
        onPointChanged: {
            const down = (point.pressedButtons & Qt.LeftButton) !== 0
            if (!down) {
                pressArmed = false
                return
            }
            if (pressArmed)
                return
            pressArmed = true
            root.releaseEditorFocusAt(point.scenePosition)
        }
    }

    EditorClickAway { }

        QtObject {
        id: testHarness
        objectName: "testHarness"
        property string skyEvalResult: ""
        property bool skyEvalDone: false

        function _byId(items, id) {
            const key = String(id || "")
            const list = items || []
            for (let i = 0; i < list.length; i++) {
                if (String(list[i].id || "") === key)
                    return list[i]
            }
            return null
        }

        function sessionDrag(id, phase, dx, dy) {
            const item = testHarness._byId(backend.upcomingSessions, id) || testHarness._byId(backend.sessions, id)
            if (!item)
                return "missing"
            const start = Qt.point(420, 280)
            const pos = Qt.point(start.x + Number(dx || 0), start.y + Number(dy || 80))
            const step = String(phase || "all")
            if (step === "reorder") {
                backend.reorderPlanned(String(item.id), "", "")
                return "reorder"
            }
            if (step === "start" || step === "all")
                DragCoordinator.startDrag(item, start, 8)
            if (step === "move" || step === "all")
                DragCoordinator.moveDrag(pos)
            if (step === "finish" || step === "all")
                DragCoordinator.completeDrag(pos)
            if (step === "cancel")
                DragCoordinator.cancelDrag()
            return step
        }

        function goToNamedPage(name) {
            const key = String(name || "").toLowerCase()
            const index = key === "control" ? 0
                        : key === "calendar" ? 1
                        : key === "sessions" ? 2
                        : key === "history" ? 3
                        : key === "media" ? 4
                        : key === "sky" ? 5
                        : -1
            if (index < 0)
                return "blocked"
            root.goToPage(index)
            return key
        }

        function selectById(deviceId) {
            const id = String(deviceId || "")
            if (!id)
                return "missing"
            backend.selectDevice(id)
            return id
        }

        function disconnectSelected() {
            backend.disconnectDevice(backend.selectedDeviceId)
            return backend.selectedDeviceId
        }

        function cancelConnectSelected() {
            backend.cancelConnect(backend.selectedDeviceId)
            return backend.selectedDeviceId
        }

        function centerPreview(nx, ny) {
            backend.centerOnTap(backend.selectedDeviceId, Number(nx), Number(ny), "harness")
            return "ok"
        }

        function joystickNudge(angle) {
            return controlPage.harnessJoystickNudge(Number(angle))
        }

        function clickPad(start) {
            return controlPage.harnessClickPad(String(start || ""))
        }

        function padList() {
            return controlPage.harnessPadList()
        }

        function openItem(kind, id, action) {
            const key = String(kind || "")
            const op = String(action || "edit")
            if (key === "sessions" || key === "calendar" || key === "upcoming") {
                const item = testHarness._byId(backend.sessions, id)
                if (!item)
                    return "missing"
                if (op === "reset") {
                    backend.resetSession(item.id)
                    return "ok"
                }
                sessionDialog.openExisting(item)
                return "ok"
            }
            if (key === "templates") {
                const item = testHarness._byId(backend.templates, id)
                if (!item)
                    return "missing"
                if (op === "schedule") {
                    scheduleTemplateDialog.openFor(item)
                    return "ok"
                }
                sessionDialog.openTemplate(item)
                return "ok"
            }
            if (key === "history") {
                historyPage.toggleExpanded(id)
                return "ok"
            }
            if (key === "media") {
                backend.selectMedia(String(id || ""))
                if (op === "source") {
                    mediaPage.showSource(String(id || "folders"))
                    return "ok"
                }
                mediaPage.openSelected()
                return "ok"
            }
            if (key === "night") {
                root.goToPage(1)
                calendarPage.openNight(calendarPage.dateFromKey(String(id || "")))
                return "ok"
            }
            return "unknown"
        }

        function deleteItem(kind, id) {
            const key = String(kind || "")
            if (key === "sessions" || key === "upcoming" || key === "calendar") {
                root.confirmBulkDelete("deleteSessions", id, "session")
                return "ok"
            }
            if (key === "templates") {
                root.confirmBulkDelete("deleteTemplates", id, "template")
                return "ok"
            }
            if (key === "history") {
                root.confirmBulkDelete("deleteHistory", id, "run")
                return "ok"
            }
            if (key === "media") {
                mediaPage.confirmDelete([String(id || "")])
                return "ok"
            }
            return "unknown"
        }

        function runItem(kind, id) {
            const key = String(kind || "")
            if (key === "sessions" || key === "upcoming" || key === "calendar") {
                const item = testHarness._byId(backend.sessions, id)
                if (!item)
                    return "missing"
                if (item.status === "running")
                    backend.stopSession(item.id)
                else
                    backend.runNow(item.id)
                return "ok"
            }
            if (key === "history") {
                const item = testHarness._byId(backend.history, id)
                if (!item || !item.session_id)
                    return "missing"
                backend.runNow(item.session_id)
                return "ok"
            }
            if (key === "media") {
                mediaPage.downloadItems([String(id || "")])
                return "ok"
            }
            return "unknown"
        }

        function skyHarvest(action) {
            skyPage.withSkySources(String(action || "import"))
            return String(action || "import")
        }

        function skyView(raHours, decDegrees) {
            return skyPage.harnessSetView(Number(raHours), Number(decDegrees))
        }

        function skyLock(name, raHours, decDegrees) {
            skyPage.queueSkyLock({
                name: String(name || ""),
                ra_hours: Number(raHours),
                dec_degrees: Number(decDegrees)
            })
            return "ok"
        }

        function skyMenu(action) {
            return skyPage.harnessMenu(String(action || ""))
        }

        function skyEval(script) {
            testHarness.skyEvalDone = false
            testHarness.skyEvalResult = ""
            return skyPage.harnessEval(String(script || ""), result => {
                testHarness.skyEvalResult = String(result ?? "")
                testHarness.skyEvalDone = true
            })
        }

        function confirmAction(action) {
            return confirmDialog.harnessConfirm(String(action || "accept"))
        }

        function requestAction(operation, label) {
            const op = String(operation || "")
            const name = String(label || op)
            if ((op === "power_down" || op === "reboot") && root.scopeOnline && !root.scopeLinking) {
                confirmDialog.kind = "device"
                confirmDialog.headingText = "CONFIRM COMMAND"
                confirmDialog.confirmLabel = "CONFIRM"
                confirmDialog.operation = op
                confirmDialog.summary = "Run " + name + " on " + (backend.selectedDevice.name || "this telescope") + "?"
                confirmDialog.open()
                return "confirm"
            }
            if (!root.commandEnabled(op))
                return "blocked"
            root.requestDeviceAction(op, name)
            return "ok"
        }
    }

    function harvestStellarium(action) {
        skyPage.withSkySources(action)
    }

    function revealTemplates(ids) {
        root.goToPage(root.sessionsPageIndex)
        Qt.callLater(() => sessionsPage.revealTemplates(ids))
    }

    function askLeaveSettings(page, deviceId) {
        if (settingsLeaveDialog.visible)
            return
        settingsLeaveDialog.pendingPage = page
        settingsLeaveDialog.pendingDeviceId = deviceId || ""
        settingsLeaveDialog.open()
    }

    Settings {
        id: layoutSettings
        category: "controlLayout"
        property bool navBarOnTop: true
        property bool skyToolsEnabled: true
        onSkyToolsEnabledChanged: {
            if (!layoutSettings.skyToolsEnabled && root.currentPage === root.skyPageIndex)
                root.goToPage(0)
        }
    }

    Binding {
        target: Theme
        property: "screenHeight"
        value: Screen.height
    }

    Shortcut {
        sequences: [StandardKey.ZoomIn, "Ctrl+=", "Ctrl++"]
        context: Qt.ApplicationShortcut
        onActivated: Theme.zoomIn()
    }
    Shortcut {
        sequences: [StandardKey.ZoomOut]
        context: Qt.ApplicationShortcut
        onActivated: Theme.zoomOut()
    }
    Shortcut {
        sequences: [StandardKey.ZoomNative, "Ctrl+0"]
        context: Qt.ApplicationShortcut
        onActivated: Theme.resetZoom()
    }

    Component.onCompleted: {
        Theme.screenHeight = Screen.height
        // Break the startup size bindings so maximize / restore can own geometry.
        root.width = root.width
        root.height = root.height
        DragCoordinator.contentItem = root.contentItem
        DragCoordinator.proxy = sessionDragProxy
        DragCoordinator.timeline = calendarPage
        root.syncWindowFrame()
        backend.setEnhanceImages(Theme.enhanceImages)
        backend.setDeepCleanImages(Theme.deepCleanImages)
        backend.setEnhanceDenoise(Theme.enhanceDenoise)
        backend.setEnhanceSkyCrush(Theme.enhanceSkyCrush)
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
        function onPaletteJsonChanged() { frameSyncTimer.restart() }
        function onEnhanceImagesChanged() {
            backend.setEnhanceImages(Theme.enhanceImages)
            backend.setDeepCleanImages(Theme.deepCleanImages)
        }
        function onDeepCleanImagesChanged() {
            backend.setEnhanceImages(Theme.enhanceImages)
            backend.setDeepCleanImages(Theme.deepCleanImages)
        }
        function onEnhanceDenoiseChanged() { enhanceLevelTimer.restart() }
        function onEnhanceSkyCrushChanged() { enhanceLevelTimer.restart() }
    }
    Timer {
        id: frameSyncTimer
        interval: 150
        repeat: false
        onTriggered: root.syncWindowFrame()
    }
    Timer {
        id: enhanceLevelTimer
        interval: 150
        repeat: false
        onTriggered: {
            backend.setEnhanceDenoise(Theme.enhanceDenoise)
            backend.setEnhanceSkyCrush(Theme.enhanceSkyCrush)
        }
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
        if (backend.needsFirstDevice) {
            if (!locationDialog.visible)
                locationDialog.openForAdd()
            return
        }
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
        MouseArea {
            anchors.fill: parent
            z: -1
            acceptedButtons: Qt.LeftButton
            onPressed: (mouse) => {
                root.releaseEditorFocusAt(mapToItem(null, mouse.x, mouse.y))
                mouse.accepted = false
            }
        }
        Image {
            anchors.fill: parent
            source: root.asset("hud-background.png")
            fillMode: Image.PreserveAspectCrop
            visible: Theme.hudBackground
            opacity: {
                if (!Theme.hudBackground)
                    return 0
                const base = Math.max(0, Math.min(1, Theme.hudBackgroundOpacity))
                return root.dataPage ? base * (0.14 / 0.42) : base
            }
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
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
            readonly property bool compact: width < Theme.px(1380)
            readonly property bool narrow: width < Theme.px(1120)
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(64)
            Layout.maximumHeight: Theme.px(64)
            Layout.fillHeight: false
            color: Theme.hsl(0.082, 0.565, 0.045, 0.753)
            border.color: Theme.outline
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Theme.px(2)
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
                anchors.leftMargin: Theme.s4
                anchors.rightMargin: Theme.px(10)
                spacing: titleBar.compact ? Theme.s2 : Theme.px(14)
                Item {
                    implicitWidth: brand.implicitWidth
                    implicitHeight: brand.implicitHeight
                    Column {
                        id: brand
                        Text { text: "ASTRO DWARF"; color: Theme.accent; font.pixelSize: Theme.fontLg; font.letterSpacing: 3; font.bold: true }
                        Text { visible: !titleBar.compact; text: "OBSERVATORY COMMAND  ·  v" + backend.appVersion; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Rectangle { width: Theme.px(1); Layout.fillHeight: true; Layout.topMargin: Theme.s3; Layout.bottomMargin: Theme.s3; color: Theme.outline }
                DeviceCombo {
                    Layout.preferredWidth: titleBar.compact ? 150 : 200
                    Layout.maximumWidth: Layout.preferredWidth
                    accessibleName: "Selected telescope"
                    accessibleDescription: "Choose which telescope this window controls"
                }
                HudButton {
                    objectName: "titleConnect"
                    text: backend.selectedDevice.connected ? "DISCONNECT" : "CONNECT"
                    busy: backend.selectedDevice.connecting || backend.selectedDevice.cancelling || backend.selectedDevice.disconnecting
                    busyText: backend.selectedDevice.disconnecting ? "DISCONNECTING…"
                              : backend.selectedDevice.cancelling ? "CANCELLING…"
                              : "CANCEL"
                    busyMs: 0
                    enabled: !backend.selectedDevice.disconnecting && !backend.selectedDevice.cancelling
                    buttonColor: backend.selectedDevice.connecting || backend.selectedDevice.cancelling
                                 ? Theme.fillDanger
                                 : backend.selectedDevice.connected ? Theme.fillSuccess : Theme.fillActive
                    foregroundColor: backend.selectedDevice.connecting || backend.selectedDevice.cancelling
                                     ? Theme.danger : Theme.accent
                    onClicked: {
                        if (backend.selectedDevice.connecting)
                            backend.cancelConnect(backend.selectedDeviceId)
                        else if (backend.selectedDevice.connected)
                            backend.disconnectDevice(backend.selectedDeviceId)
                        else
                            backend.connectDevice(backend.selectedDeviceId)
                    }
                }
                HudButton {
                    text: titleBar.narrow
                        ? (backend.schedulerEnabled ? "SCHED ON" : "SCHED OFF")
                        : (backend.schedulerEnabled ? "SCHEDULER ON" : "SCHEDULER OFF")
                    busyMs: 0
                    enabled: backend.schedulerEnabled || backend.anyDeviceConnected
                    buttonColor: backend.schedulerEnabled ? Theme.fillSuccess : Theme.surfaceHigh
                    foregroundColor: backend.schedulerEnabled ? Theme.success : Theme.textPrimary
                    onClicked: backend.setSchedulerEnabled(!backend.schedulerEnabled)
                }
                HudButton {
                    text: titleBar.narrow ? "STOP RUN" : "STOP SESSION"
                    busy: backend.selectedDevice.pending_action === "stop_session"
                    busyText: "STOPPING…"
                    busyMs: 0
                    enabled: root.commandEnabled("stop_session") || (backend.currentSession.status === "running" && !root.scopeStopping)
                    buttonColor: Theme.fillDanger
                    foregroundColor: Theme.danger
                    onClicked: backend.stopSession(backend.currentSession.id)
                }
                HudButton {
                    text: "STOP ALL"
                    busy: backend.selectedDevice.pending_action === "stop_all"
                    busyText: "STOPPING…"
                    busyMs: 0
                    // A running session must always be stoppable, even while the link is still coming up.
                    // A running session must always be stoppable, even while the link is still coming up.
                    enabled: root.commandEnabled("stop_all") || (root.scopeImaging && !root.scopeStopping)
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
                    spacing: titleBar.compact ? Theme.px(6) : Theme.px(10)
                    Repeater {
                        model: [
                            {label: "LINK", on: root.scopeOnline, color: Theme.success},
                            {label: "AUTO", on: backend.schedulerEnabled, color: Theme.success},
                            {label: "IMAGE", on: root.scopeImaging || root.scopeActivity === "imaging", color: Theme.danger}
                        ]
                        delegate: RowLayout {
                            required property var modelData
                            spacing: Theme.s1
                            Accessible.role: Accessible.Indicator
                            Accessible.name: modelData.label + (modelData.on ? " active" : " off")
                            LedDot { on: modelData.on; onColor: modelData.color; pulse: true }
                            Text { visible: !titleBar.compact; text: modelData.label; color: modelData.on ? Theme.textPrimary : Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true }
                        }
                    }
                    Rectangle { width: Theme.px(1); Layout.preferredHeight: Theme.px(18); color: Theme.outline; visible: root.scopeOnline }
                    RowLayout {
                        id: titleBattery
                        readonly property var t: root.scopeTelemetry
                        readonly property int percent: root.scopeOnline && t.battery_percent !== undefined ? Number(t.battery_percent) : -1
                        readonly property color tone: percent < 0 ? Theme.muted : Util.toneColor(Util.batteryTone(percent))
                        visible: root.scopeOnline
                        spacing: Theme.px(5)
                        Item {
                            implicitWidth: Theme.px(22)
                            implicitHeight: Theme.px(11)
                            Rectangle {
                                anchors.left: parent.left; anchors.top: parent.top
                                width: Theme.px(19); height: Theme.px(11); radius: Theme.px(2)
                                color: "transparent"
                                border.color: titleBattery.tone
                                Rectangle {
                                    x: Theme.px(2); y: Theme.px(2)
                                    height: parent.height - Theme.s1
                                    width: Math.max(0, (parent.width - Theme.s1) * Math.max(0, titleBattery.percent) / 100)
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
                            Rectangle { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; width: Theme.px(2); height: Theme.px(5); color: titleBattery.tone }
                        }
                        Text {
                            text: titleBattery.percent >= 0 ? titleBattery.percent + "%" + (titleBattery.t.charging ? "⚡" : "") : "—"
                            color: titleBattery.percent >= 0 ? Theme.textPrimary : Theme.textSecondary
                            font.pixelSize: Theme.fontSm; font.family: Theme.fontMono; font.bold: true
                        }
                        HudToolTip {
                            visible: batteryHover.hovered
                            text: "Battery " + (titleBattery.t.battery_text || "—") + (titleBattery.t.charging_text ? "  ·  " + titleBattery.t.charging_text : "") + (titleBattery.t.battery_health_text ? "\n" + titleBattery.t.battery_health_text : "")
                        }
                        HoverHandler { id: batteryHover }
                    }
                    RowLayout {
                        id: titleStorage
                        readonly property var t: root.scopeTelemetry
                        visible: root.scopeOnline && !titleBar.narrow
                        spacing: Theme.px(5)
                        Text { text: "▤"; color: titleStorage.t.storage_tone === "bad" ? Theme.danger : titleStorage.t.storage_tone === "warn" ? Theme.warning : Theme.accent; font.pixelSize: Theme.fontPx(11) }
                        Text {
                            text: root.scopeOnline && titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? String(titleStorage.t.storage_free_text || titleStorage.t.storage_text) : "—"
                            color: titleStorage.t.storage_tone === "bad" ? Theme.danger : titleStorage.t.storage_tone === "warn" ? Theme.warning : (titleStorage.t.storage_text && titleStorage.t.storage_text !== "—" ? Theme.textPrimary : Theme.textSecondary)
                            font.pixelSize: Theme.fontSm; font.family: Theme.fontMono; font.bold: true
                        }
                        HudToolTip {
                            visible: storageHover.hovered
                            text: "Storage " + (titleStorage.t.storage_text || "—")
                        }
                        HoverHandler { id: storageHover }
                    }
                }
                Column {
                    visible: !titleBar.compact
                    Text { text: backend.selectedDevice.status || "OFFLINE"; color: backend.selectedDevice.connected ? Theme.success : Theme.textSecondary; font.pixelSize: Theme.fontPx(11); font.bold: true; horizontalAlignment: Text.AlignRight; width: Theme.px(160) }
                    Text { text: root.deviceLabel(); color: Theme.textSecondary; font.pixelSize: Theme.fontSm; horizontalAlignment: Text.AlignRight; width: Theme.px(160); elide: Text.ElideRight }
                }
                Column {
                    Text { text: backend.clockText; color: Theme.accent; font.pixelSize: titleBar.compact ? Theme.fontPx(18) : Theme.fontXl; font.family: Theme.fontMono; font.letterSpacing: 1; horizontalAlignment: Text.AlignRight; width: titleBar.compact ? Theme.px(124) : Theme.px(168) }
                    Text {
                        text: backend.selectedDevice.timezone_name || "UTC"
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontPx(9)
                        font.family: Theme.fontMono
                        horizontalAlignment: Text.AlignRight
                        width: titleBar.compact ? Theme.px(124) : Theme.px(168)
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
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: Theme.px(1); color: Theme.outline }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.s4
                anchors.rightMargin: Theme.s4
                spacing: Theme.s3
                Text {
                    text: "DEVICES"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontPx(9)
                    font.bold: true
                    font.letterSpacing: Theme.tracking2
                }
                Rectangle { width: Theme.px(1); Layout.preferredHeight: Theme.px(14); color: Theme.outline }
                HudButton {
                    text: "‹"
                    busyMs: 0
                    Layout.preferredWidth: Theme.px(26)
                    Layout.maximumWidth: Theme.px(26)
                    implicitHeight: Theme.compactControlHeight
                    enabled: deviceChips.contentX > deviceChips.originX + 1
                    Accessible.name: "Scroll devices left"
                    onClicked: deviceChips.scrollBy(-deviceChips.width * 0.7)
                }
                ListView {
                    id: deviceChips
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    orientation: ListView.Horizontal
                    spacing: Theme.s1
                    clip: true
                    model: backend.devices
                    function scrollBy(distance) {
                        const minimum = originX
                        const maximum = Math.max(minimum, originX + contentWidth - width)
                        contentX = Math.max(minimum, Math.min(maximum, contentX + distance))
                    }
                    WheelHandler {
                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                        blocking: true
                        onWheel: event => {
                            const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
                            if (!delta)
                                return
                            deviceChips.scrollBy(-delta)
                            event.accepted = true
                        }
                    }
                    delegate: Item {
                        id: deviceCard
                        required property var modelData
                        readonly property bool selected: modelData.id === backend.selectedDeviceId
                        width: chipRow.implicitWidth + Theme.px(24)
                        height: deviceChips.height
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.name + ", " + (modelData.connected ? "connected" : "offline")
                        Accessible.description: modelData.status + (modelData.ip_address ? ", " + modelData.ip_address : "")
                        Keys.onReturnPressed: backend.selectDevice(deviceCard.modelData.id)
                        Keys.onSpacePressed: backend.selectDevice(deviceCard.modelData.id)
                        Rectangle {
                            anchors.fill: parent
                            anchors.topMargin: Theme.px(3)
                            anchors.bottomMargin: Theme.px(3)
                            radius: Theme.px(3)
                            color: deviceCard.selected ? Theme.hsl(0.036, 0.640, 0.196, 0.627) : (chipHover.hovered || deviceCard.activeFocus ? Theme.hsl(0.057, 0.548, 0.122, 0.314) : "transparent")
                            Behavior on color { ColorAnimation { duration: 120 } }
                        }
                        Rectangle {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            height: Theme.px(2)
                            width: deviceCard.selected ? parent.width - Theme.s4 : 0
                            color: Theme.accent
                            Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: Theme.px(1)
                            radius: Theme.px(3)
                            color: "transparent"
                            border.color: Theme.accent
                            border.width: Theme.focusStroke
                            visible: deviceCard.activeFocus
                        }
                        RowLayout {
                            id: chipRow
                            anchors.centerIn: parent
                            spacing: Theme.px(7)
                            Rectangle { width: Theme.s2; height: Theme.s2; radius: Theme.s1; color: deviceCard.modelData.color }
                            Text {
                                text: deviceCard.modelData.name
                                color: deviceCard.selected ? Theme.textPrimary : Theme.textSecondary
                                font.pixelSize: Theme.fontPx(11)
                                font.bold: deviceCard.selected
                            }
                            Text {
                                text: deviceCard.modelData.model
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontPx(9)
                                opacity: 0.8
                            }
                            Text {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && t.battery_percent !== undefined && Number(t.battery_percent) >= 0
                                text: (t.battery_percent !== undefined ? t.battery_percent : "") + "%" + (t.charging ? "⚡" : "")
                                color: Util.toneColor(Util.batteryTone(t.battery_percent))
                                font.pixelSize: Theme.fontPx(9); font.family: Theme.fontMono; font.bold: true
                            }
                            HudChip {
                                readonly property var t: deviceCard.modelData.telemetry || ({})
                                visible: deviceCard.modelData.connected && (deviceCard.modelData.busy || !!t.capture_active)
                                label: t.capture_active ? "STACK" : "IMAGING"
                                value: String(t.capture_text || "")
                                tone: Theme.danger
                                implicitHeight: Theme.s4
                            }
                            Rectangle {
                                width: Theme.px(6); height: Theme.px(6); radius: Theme.px(3)
                                color: deviceCard.modelData.connected ? (deviceCard.modelData.busy ? Theme.danger : Theme.success) : Theme.muted
                                border.color: deviceCard.modelData.connected ? Theme.hsl(-0.021, 1.000, 0.924) : "transparent"
                                border.width: deviceCard.modelData.connected ? Theme.px(1) : 0
                                SequentialAnimation on opacity {
                                    running: deviceCard.modelData.connecting || deviceCard.modelData.cancelling || deviceCard.modelData.disconnecting
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
                                text: deviceCard.modelData.cancelling ? "Cancelling…"
                                      : deviceCard.modelData.connecting ? "Cancel connect"
                                      : deviceCard.modelData.connected ? "Disconnect" : "Connect"
                                glyph: deviceCard.modelData.connecting || deviceCard.modelData.cancelling
                                       ? "\uE711"
                                       : deviceCard.modelData.connected ? "\uE8CD" : "\uE774"
                                enabled: !deviceCard.modelData.disconnecting && !deviceCard.modelData.cancelling
                                onTriggered: {
                                    backend.selectDevice(deviceCard.modelData.id)
                                    if (deviceCard.modelData.connecting)
                                        backend.cancelConnect(deviceCard.modelData.id)
                                    else if (deviceCard.modelData.connected)
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
                                    root.goToPage(root.settingsPageIndex)
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
                HudButton {
                    text: "›"
                    busyMs: 0
                    Layout.preferredWidth: Theme.px(26)
                    Layout.maximumWidth: Theme.px(26)
                    implicitHeight: Theme.compactControlHeight
                    enabled: deviceChips.contentX + deviceChips.width < deviceChips.originX + deviceChips.contentWidth - 1
                    Accessible.name: "Scroll devices right"
                    onClicked: deviceChips.scrollBy(deviceChips.width * 0.7)
                }
            }
        }

        PageNavBar {
            visible: layoutSettings.navBarOnTop
            Layout.topMargin: Theme.s2
            currentIndex: root.currentPage
            skyToolsEnabled: layoutSettings.skyToolsEnabled
            barOnTop: true
            attentionIndex: settingsPage.dirty ? root.settingsPageIndex : -1
            attentionDescription: "Unsaved settings"
            onPageRequested: index => root.goToPage(index)
            onPlacementRequested: onTop => layoutSettings.navBarOnTop = onTop
        }

        StackLayout {
            id: pages
            currentIndex: root.currentPage
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: Theme.px(360)
            Layout.margins: Theme.px(10)

            ControlPage { id: controlPage; objectName: "controlPage" }
            CalendarPage { id: calendarPage; objectName: "calendarPage" }
            SessionsPage { id: sessionsPage; objectName: "sessionsPage" }
            HistoryPage { id: historyPage; objectName: "historyPage" }
            MediaPage { id: mediaPage }
            SkyPage { id: skyPage }
            SettingsPage { id: settingsPage }
        }

        PageNavBar {
            visible: !layoutSettings.navBarOnTop
            Layout.bottomMargin: Theme.s2
            currentIndex: root.currentPage
            skyToolsEnabled: layoutSettings.skyToolsEnabled
            barOnTop: false
            attentionIndex: settingsPage.dirty ? root.settingsPageIndex : -1
            attentionDescription: "Unsaved settings"
            onPageRequested: index => root.goToPage(index)
            onPlacementRequested: onTop => layoutSettings.navBarOnTop = onTop
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
        objectName: "sessionDragProxy"
        parent: root.contentItem
        visible: DragCoordinator.active
        enabled: false
        z: 4000
        width: Theme.px(220)
        height: Theme.px(30)
        radius: Theme.px(2)
        property string sessionId: ""
        color: Util.statusFill(DragCoordinator.data.group_collapsed ? (DragCoordinator.data.group_status || DragCoordinator.data.status) : DragCoordinator.data.status)
        border.color: Util.statusColor(DragCoordinator.data.group_collapsed ? (DragCoordinator.data.group_status || DragCoordinator.data.status) : DragCoordinator.data.status)
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
            // Do not set Drag.active. Qt delivers that drop on mouse
            // release and re-enters drag-and-drop from the pointer
            // handler, which hangs UP NEXT and the calendar sidebar.
        }
        function moveDrag(pos) {
            x = pos.x - width / 2
            y = pos.y - height / 2
            DragCoordinator.update(pos)
        }
        function finishDrag() {
            DragCoordinator.active = false
            Drag.active = false
            DragCoordinator.end()
            sessionId = ""
        }
        function cancelDrag() {
            DragCoordinator.active = false
            Drag.active = false
            DragCoordinator.end()
            sessionId = ""
        }
        Row {
            anchors.fill: parent
            anchors.margins: Theme.px(5)
            spacing: Theme.px(6)
            Text {
                text: DragCoordinator.previewTime || (DragCoordinator.data.start_time || "")
                color: Theme.accent
                font.pixelSize: Theme.fontSm
                font.bold: true
                font.family: Theme.fontMono
                width: Theme.px(40)
            }
            Text {
                width: Math.max(Theme.s5, sessionDragProxy.width - Theme.px(56))
                text: DragCoordinator.data.group_collapsed
                      ? (DragCoordinator.data.group_title || DragCoordinator.data.target_name || "Mosaic")
                      : (DragCoordinator.data.pane_name || DragCoordinator.data.target_name || DragCoordinator.data.name || "Session")
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSm
                font.bold: true
                elide: Text.ElideRight
            }
        }
    }

    EditorClickAway {
        parent: Overlay.overlay
    }

    Item {
        // Stacked toast notifications, top-right below the title bar.
        id: toastHost
        parent: Overlay.overlay
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: Theme.px(74)
        anchors.rightMargin: Theme.px(14)
        width: Math.min(Theme.px(380), root.width - Theme.px(40))
        height: toastColumn.implicitHeight
        z: 900
        readonly property int maxToasts: 4
        property int nextId: 1

        function durationFor(level, hasLink) {
            if (hasLink)
                return 7000
            switch (String(level || "").toLowerCase()) {
            case "error": return 8000
            case "warning": return 6000
            case "success": return 4000
            default: return 3000
            }
        }
        function actionIdsFrom(meta) {
            const raw = meta && meta.ids
            if (Array.isArray(raw))
                return raw.map(id => String(id || "").trim()).filter(id => id !== "").join(",")
            return String(raw || "").trim()
        }
        function push(message, level, detail, meta) {
            const text = String(message || "").trim()
            if (text === "")
                return
            const tone = String(level || "info").toLowerCase()
            const info = meta || ({})
            const actionKind = String(info.kind || "")
            const actionIds = toastHost.actionIdsFrom(info)
            const actionLabel = String(info.link || "")
            const hasLink = actionKind !== "" && actionLabel !== ""
            for (let i = 0; i < toastModel.count; i++) {
                const existing = toastModel.get(i)
                if (existing.message === text && existing.level === tone) {
                    toastModel.setProperty(i, "count", existing.count + 1)
                    toastModel.setProperty(i, "detail", String(detail || existing.detail || ""))
                    toastModel.setProperty(i, "actionKind", actionKind || existing.actionKind)
                    toastModel.setProperty(i, "actionIds", actionIds || existing.actionIds)
                    toastModel.setProperty(i, "actionLabel", actionLabel || existing.actionLabel)
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
                actionKind: actionKind,
                actionIds: actionIds,
                actionLabel: actionLabel,
                count: 1,
                restart: 0,
                duration: durationFor(tone, hasLink)
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
            spacing: Theme.s2
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
                    required property string actionKind
                    required property string actionIds
                    required property string actionLabel
                    required property int count
                    required property int restart
                    required property int duration
                    readonly property color tone: Util.toneForLevel(level)
                    readonly property bool hovering: toastHover.hovered
                    Accessible.role: Accessible.AlertMessage
                    Accessible.name: message + (detail ? ". " + detail : "")
                    width: toastColumn.width
                    height: toastBody.implicitHeight + Theme.px(18)
                    radius: Theme.s1
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
                        anchors.fill: parent; anchors.margins: Theme.px(-3); radius: Theme.px(7)
                        color: "transparent"; border.color: toastCard.tone; opacity: 0.18
                    }
                    Rectangle { x: 0; y: 0; width: Theme.px(3); height: parent.height; color: toastCard.tone }
                    RowLayout {
                        id: toastBody
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.leftMargin: Theme.s3
                        anchors.rightMargin: Theme.px(10)
                        spacing: Theme.px(10)
                        Rectangle {
                            width: Theme.px(26); height: Theme.px(26); radius: Theme.px(13)
                            color: Qt.rgba(toastCard.tone.r, toastCard.tone.g, toastCard.tone.b, 0.16)
                            border.color: Qt.rgba(toastCard.tone.r, toastCard.tone.g, toastCard.tone.b, 0.6)
                            Layout.alignment: Qt.AlignTop
                            Text { anchors.centerIn: parent; text: Util.glyphForLevel(toastCard.level); color: toastCard.tone; font.pixelSize: Theme.fontBase; font.bold: true }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.px(2)
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Theme.px(6)
                                Text {
                                    text: toastCard.message
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontMd
                                    font.bold: true
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 2
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Rectangle {
                                    visible: toastCard.count > 1
                                    width: toastCount.implicitWidth + Theme.px(10); height: Theme.s4; radius: Theme.s2
                                    color: toastCard.tone
                                    Text { id: toastCount; anchors.centerIn: parent; text: "×" + toastCard.count; color: Theme.windowBase; font.pixelSize: Theme.fontPx(9); font.bold: true }
                                }
                            }
                            Text {
                                visible: toastCard.detail !== ""
                                text: toastCard.detail
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontSm
                                wrapMode: Text.Wrap
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            RowLayout {
                                visible: toastCard.level === "error" || toastCard.level === "warning" || toastCard.actionKind === "template"
                                spacing: Theme.px(10)
                                Layout.topMargin: Theme.px(2)
                                Text {
                                    visible: toastCard.actionKind === "template"
                                    text: toastCard.actionLabel || "VIEW TEMPLATE"
                                    color: viewTemplateHover.hovered ? Theme.textPrimary : toastCard.tone
                                    font.pixelSize: Theme.fontPx(9); font.bold: true; font.letterSpacing: Theme.tracking2
                                    HoverHandler { id: viewTemplateHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler {
                                        onTapped: {
                                            root.revealTemplates(toastCard.actionIds)
                                            toastHost.dismiss(toastCard.toastId)
                                        }
                                    }
                                }
                                Text {
                                    visible: toastCard.level === "error" || toastCard.level === "warning"
                                    text: "VIEW LOG"
                                    color: viewLogHover.hovered ? Theme.textPrimary : toastCard.tone
                                    font.pixelSize: Theme.fontPx(9); font.bold: true; font.letterSpacing: Theme.tracking2
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
                                    font.pixelSize: Theme.fontPx(9); font.bold: true; font.letterSpacing: Theme.tracking2
                                    HoverHandler { id: dismissHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: toastHost.dismiss(toastCard.toastId) }
                                }
                            }
                        }
                        Text {
                            text: "✕"
                            color: closeHover.hovered ? Theme.textPrimary : Theme.muted
                            font.pixelSize: Theme.fontPx(11)
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
                        anchors.leftMargin: Theme.px(3)
                        height: Theme.px(2)
                        color: toastCard.tone
                        opacity: 0.8
                        width: parent.width - Theme.px(3)
                        function restartSweep() {
                            sweep.stop()
                            width = toastCard.width - Theme.px(3)
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
                        onTapped: {
                            if (toastCard.actionKind === "template")
                                root.revealTemplates(toastCard.actionIds)
                            toastHost.dismiss(toastCard.toastId)
                        }
                    }
                }
            }
        }
    }

    Connections {
        target: backend
        function onToast(message, level, detail, meta) {
            toastHost.push(message, level, detail, meta)
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
    ConfirmDialog {
        id: confirmDialog
        onViewerCloseRequested: mediaPage.closeViewer()
    }
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
    SkyRaDecDialog {
        id: skyRaDecDialog
        transientParent: root
        hostActive: root.currentPage === root.skyPageIndex
        onGotoRequested: (raHours, decDegrees) => skyPage.gotoRaDec(raHours, decDegrees)
    }
}
