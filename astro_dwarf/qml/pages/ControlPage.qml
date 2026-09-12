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
    id: controlPage
    property var selectedUpcomingIds: ({})
    property string selectionAnchorId: ""
    readonly property int selectedUpcomingCount: Util.idSetCount(selectedUpcomingIds)
    readonly property var clusteredUpcoming: Util.clusterSessions(backend.upcomingSessions)
    function selectClick(id, shift) {
        const result = Util.clickSelect(selectedUpcomingIds, controlPage.clusteredUpcoming, id, shift, selectionAnchorId)
        selectedUpcomingIds = result.map
        selectionAnchorId = result.anchor
    }
    property var contextSession: ({})
    function openSessionMenu(session) {
        contextSession = session || ({})
        upcomingMenu.popup()
    }
    Connections {
        target: backend
        function onSessionsChanged() {
            controlPage.selectedUpcomingIds = Util.pruneIdSet(controlPage.selectedUpcomingIds, backend.upcomingSessions)
        }
    }
    HudSplitView {
        id: controlColumns
        settingsKey: "controlColumns"
        anchors.fill: parent
        orientation: Qt.Horizontal

        HudSplitView {
            id: controlLeft
            settingsKey: "controlLeft"
            orientation: Qt.Vertical
            SplitView.preferredWidth: 268
            SplitView.minimumWidth: 196

            HudPanel {
                title: "SYSTEM STATUS"
                SplitView.preferredHeight: 180
                SplitView.minimumHeight: 120
                headerExtra: Row {
                    spacing: 4
                    HudChip {
                        label: root.scopeTelemetry.host_text && root.scopeTelemetry.host_text !== "—" ? root.scopeTelemetry.host_text : ""
                        tone: root.scopeTelemetry.host_mode === false ? Theme.warning : Theme.success
                        visible: root.scopeOnline && label !== ""
                        dim: !root.scopeOnline
                    }
                    Rectangle {
                        // compact activity badge derived from device telemetry
                        id: activityBadge
                        anchors.verticalCenter: parent.verticalCenter
                        height: 20
                        width: Math.min(140, activityBadgeRow.implicitWidth + 14)
                        radius: 3
                        readonly property color tone: root.activityColor()
                        color: Qt.rgba(tone.r, tone.g, tone.b, root.scopeOnline ? 0.14 : 0.05)
                        border.color: Qt.rgba(tone.r, tone.g, tone.b, root.scopeOnline ? 0.55 : 0.25)
                        opacity: root.scopeOnline ? 1 : 0.7
                        Behavior on color { ColorAnimation { duration: 220 } }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: -2
                            radius: 5
                            color: "transparent"
                            border.color: activityBadge.tone
                            visible: root.scopePending !== ""
                            opacity: 0
                            SequentialAnimation on opacity {
                                running: root.scopePending !== ""
                                loops: Animation.Infinite
                                NumberAnimation { from: 0.65; to: 0.08; duration: 500; easing.type: Easing.InOutSine }
                                NumberAnimation { from: 0.08; to: 0.65; duration: 500; easing.type: Easing.InOutSine }
                            }
                        }
                        RowLayout {
                            id: activityBadgeRow
                            anchors.fill: parent
                            anchors.leftMargin: 7
                            anchors.rightMargin: 7
                            spacing: 5
                            Text { text: root.scopePending ? "⇡" : root.scopeActivity !== "" ? "◈" : root.scopeImaging ? "●" : root.scopeOnline ? "◇" : "○"; color: activityBadge.tone; font.pixelSize: 9 }
                            Text {
                                text: root.scopeActivityText()
                                color: activityBadge.tone
                                font.pixelSize: 8; font.bold: true; font.letterSpacing: 1
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: root.scopeActivityFromDevice
                                text: "DEV"
                                color: Theme.textSecondary
                                font.pixelSize: 6; font.bold: true; font.letterSpacing: 1
                            }
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    LedDot {
                        width: 10; height: 10; radius: 5
                        on: true
                        pulse: root.scopeOnline && (root.scopeImaging || root.scopeActivity !== "")
                        onColor: root.scopeLinking ? Theme.warning : root.scopeImaging ? Theme.danger : root.scopeOnline ? Theme.success : Theme.danger
                    }
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 0
                        Text {
                            id: statusHeading
                            text: String(backend.selectedDevice.status || "OFFLINE").toUpperCase()
                            color: root.scopeLinking ? Theme.warning : root.scopeImaging ? Theme.danger : root.scopeOnline ? Theme.success : Theme.textSecondary
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
                        Text { text: root.deviceLabel(); color: Theme.textSecondary; font.pixelSize: 9 }
                    }
                }
                Repeater {
                    model: [
                        {label: "ENDPOINT", value: backend.selectedDevice.ip_address || "—", tone: root.scopeOnline ? Theme.textPrimary : Theme.textSecondary},
                        {label: "SCHEDULER", value: backend.schedulerEnabled ? root.nextSessionCountdown() : "Disarmed", tone: backend.schedulerEnabled ? Theme.success : Theme.textSecondary},
                        {label: "PREVIEW", value: root.scopeStopping ? (root.scopePendingDetail || "Stopping") : (backend.previewHeld ? "Paused for session" : (backend.previewActive ? (backend.previewPlaying ? "Live" : backend.previewStatus || "Starting") : "Stopped")), tone: root.scopeStopping ? Theme.warning : (backend.previewPlaying ? Theme.danger : (backend.previewHeld || backend.previewActive ? Theme.warning : Theme.textSecondary))},
                        {label: "SESSION", value: Util.sessionStepLabel(backend.currentSession, backend.localNow.epoch_ms) || backend.currentSession.current_step || Util.idleScheduleLabel(backend.upcomingSessions, backend.schedulerEnabled, backend.localNow.epoch_ms), tone: backend.currentSession.id ? Theme.accent : Theme.textSecondary},
                        {label: "REMAINING", value: backend.currentSession.id ? Util.durationLabel(Number(backend.currentSession.planned_duration_seconds || 0) * (1 - backend.sessionProgress)) : "—", tone: Theme.textPrimary},
                        {label: "TIMEZONE", value: backend.selectedDevice.timezone_name || "UTC", tone: Theme.textPrimary},
                        {label: "LAT / LON", value: Number(backend.selectedDevice.latitude || 0).toFixed(2) + "°, " + Number(backend.selectedDevice.longitude || 0).toFixed(2) + "°", tone: Theme.textPrimary}
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 6
                        Text { text: modelData.label; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true; font.letterSpacing: 0.8; Layout.preferredWidth: 72 }
                        Rectangle { Layout.fillWidth: true; Layout.minimumWidth: 12; Layout.preferredHeight: 1; color: Theme.outlineSoft; opacity: 0.7 }
                        Text { text: modelData.value; color: modelData.tone; font.pixelSize: 10; font.family: Theme.fontMono; elide: Text.ElideRight; horizontalAlignment: Text.AlignRight; Layout.fillWidth: true; Layout.maximumWidth: implicitWidth }
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
                        tone: vitalsPanel.stale ? Theme.warning : vitalsPanel.live ? Theme.success : Theme.muted
                        glow: vitalsPanel.live && !vitalsPanel.stale
                        dim: !vitalsPanel.live
                    }
                }
                Item {
                    id: vitalsBody
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: 0
                    clip: true
                    readonly property int gaugeSize: {
                        const minGrid = 62
                        const fromHeight = height - minGrid - 6
                        return Math.round(Math.max(36, Math.min(74, fromHeight)))
                    }
                    readonly property bool compact: gaugeSize < 56
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.preferredHeight: vitalsBody.gaugeSize
                            Layout.maximumHeight: 74
                            Layout.minimumHeight: 36
                            spacing: 10
                            BatteryGauge {
                                percent: vitalsPanel.live && vitalsPanel.t.battery_percent !== undefined ? Number(vitalsPanel.t.battery_percent) : -1
                                charging: !!vitalsPanel.t.charging && vitalsPanel.live
                                Layout.preferredWidth: vitalsBody.gaugeSize
                                Layout.preferredHeight: vitalsBody.gaugeSize
                                Layout.minimumWidth: 36
                                Layout.minimumHeight: 36
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: vitalsBody.compact ? 3 : 5
                                RowLayout {
                                    Layout.fillWidth: true
                                    Text { text: "STORAGE"; color: Theme.textSecondary; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.1; Layout.fillWidth: true }
                                    Text {
                                        text: vitalsPanel.live ? String(vitalsPanel.t.storage_text || "—") : "—"
                                        color: vitalsPanel.live && vitalsPanel.t.storage_tone && vitalsPanel.t.storage_tone !== "unknown" && vitalsPanel.t.storage_tone !== "good" ? Util.toneColor(vitalsPanel.t.storage_tone) : Theme.textPrimary
                                        font.pixelSize: 11; font.family: Theme.fontMono; font.bold: true
                                        elide: Text.ElideRight
                                    }
                                }
                                StorageBar {
                                    Layout.fillWidth: true
                                    fraction: vitalsPanel.live ? Number(vitalsPanel.t.storage_percent || 0) : 0
                                    tone: vitalsPanel.live ? String(vitalsPanel.t.storage_tone || "unknown") : "unknown"
                                    valid: !vitalsPanel.live || vitalsPanel.t.storage_valid !== false
                                }
                                Text {
                                    visible: !vitalsBody.compact
                                    Layout.fillWidth: true
                                    text: vitalsPanel.live ? (vitalsPanel.t.storage_percent ? Math.round(Number(vitalsPanel.t.storage_percent) * 100) + "% USED" : (vitalsPanel.t.storage_valid === false ? "CARD MISSING" : "")) : ""
                                    color: Theme.textSecondary; font.pixelSize: 8; font.letterSpacing: 0.8; elide: Text.ElideRight
                                }
                                RowLayout {
                                    visible: !vitalsBody.compact
                                    Layout.fillWidth: true
                                    spacing: 4
                                    HudChip { label: vitalsPanel.t.charging_text || "BATT"; tone: vitalsPanel.t.charging ? Theme.warning : Theme.textSecondary; dim: !vitalsPanel.live; visible: vitalsPanel.live && !!vitalsPanel.t.charging_text }
                                    Text { visible: !!vitalsPanel.t.battery_health_text && vitalsPanel.live; text: vitalsPanel.t.battery_health_text || ""; color: Theme.textSecondary; font.pixelSize: 8; font.letterSpacing: 0.6; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Item { Layout.fillWidth: true; visible: !vitalsPanel.t.battery_health_text }
                                }
                            }
                        }
                        GridLayout {
                            id: vitalsGrid
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 0
                            readonly property int tileCount: 6
                            columns: {
                                if (width <= 0)
                                    return 2
                                const minTile = 76
                                const fit = Math.max(1, Math.floor((width + columnSpacing) / (minTile + columnSpacing)))
                                const minRowH = 28
                                const rowsOk = (cols) => {
                                    const rows = Math.ceil(tileCount / cols)
                                    return rows * minRowH + (rows - 1) * rowSpacing <= height + 0.5
                                }
                                if (fit >= 3 && !rowsOk(2))
                                    return 3
                                if (fit >= 2)
                                    return 2
                                return 1
                            }
                            columnSpacing: height > 0 && height < 90 ? 4 : 6
                            rowSpacing: height > 0 && height < 90 ? 4 : 6
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "♨"; label: "BODY TEMP"; value: vitalsPanel.live ? String(vitalsPanel.t.temperature_c_text || "—") : "—"; unit: vitalsPanel.live ? String(vitalsPanel.t.temperature_f_text || "") : ""; tone: Theme.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "◉"; label: backend.selectedDevice.camera === "wide" ? "WIDE SENSOR" : "TELE SENSOR"; value: vitalsPanel.live ? String((backend.selectedDevice.camera === "wide" ? vitalsPanel.t.cmos_wide_c_text : vitalsPanel.t.cmos_tele_c_text) || "—") : "—"; unit: vitalsPanel.live ? String((backend.selectedDevice.camera === "wide" ? vitalsPanel.t.cmos_wide_f_text : vitalsPanel.t.cmos_tele_f_text) || "") : ""; tone: Theme.notice; stale: vitalsPanel.stale; live: vitalsPanel.live }
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "⌾"; label: "FOCUS"; value: vitalsPanel.live ? String(vitalsPanel.t.focus_text || "—") : "—"; unit: "STEPS"; tone: root.scopeActivity === "autofocus" || root.scopeActivity === "infinity" ? Theme.notice : Theme.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "⛭"; label: "MOUNT"; value: vitalsPanel.live ? String(vitalsPanel.t.mount_text || "—") : "—"; unit: vitalsPanel.t.mount_mode === "EQ" ? "EQUATORIAL" : vitalsPanel.t.mount_mode === "AZ" ? "ALT-AZ" : ""; tone: vitalsPanel.t.mount_mode === "EQ" ? Theme.success : Theme.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "▶"; label: "STREAM"; value: vitalsPanel.live ? String(vitalsPanel.t.stream_text || "—") : "—"; unit: vitalsPanel.t.shooting_mode_text && vitalsPanel.t.shooting_mode_text !== "—" ? vitalsPanel.t.shooting_mode_text : ""; tone: backend.previewPlaying ? Theme.danger : Theme.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                            VitalTile { Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: 0; Layout.preferredHeight: 46; Layout.minimumWidth: 0; glyph: "✦"; label: "LIGHTS"; value: vitalsPanel.live ? (vitalsPanel.t.lights_on ? "RING ON" : "RING OFF") : "—"; unit: vitalsPanel.live ? (vitalsPanel.t.indicator_on ? "· LED ON" : "· LED OFF") : ""; tone: vitalsPanel.t.lights_on ? Theme.warning : Theme.accent; stale: vitalsPanel.stale; live: vitalsPanel.live }
                        }
                        Text {
                            visible: !root.scopeOnline
                            Layout.fillWidth: true
                            text: "Connect the telescope to stream battery, storage and sensor telemetry."
                            color: Theme.textSecondary; font.pixelSize: 9; elide: Text.ElideRight; maximumLineCount: 1
                        }
                        Text {
                            id: vitalsWaiting
                            visible: root.scopeOnline && !vitalsPanel.live
                            Layout.fillWidth: true
                            text: "Waiting for the first device report…"
                            color: Theme.textSecondary; font.pixelSize: 9
                            SequentialAnimation on opacity { running: vitalsWaiting.visible; loops: Animation.Infinite; NumberAnimation { to: 0.4; duration: 700 } NumberAnimation { to: 1; duration: 700 } }
                        }
                    }
                }
            }

            HudPanel {
                id: targetPanel
                title: "TARGET"
                SplitView.preferredHeight: 140
                SplitView.minimumHeight: 80
                overlay: [
                    TapHandler {
                        acceptedButtons: Qt.LeftButton
                        enabled: !!backend.currentSession.id && backend.currentSession.status !== "running"
                        grabPermissions: PointerHandler.CanTakeOverFromAnything | PointerHandler.ApprovesTakeOverByAnything
                        onDoubleTapped: sessionDialog.openExisting(backend.currentSession)
                    },
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        enabled: !!backend.currentSession.id
                        onTapped: targetMenu.popup()
                    }
                ]
                headerExtra: Row {
                    spacing: 4
                    HudChip {
                        readonly property var t: root.scopeTelemetry
                        visible: root.scopeOnline && !!t.capture_active
                        label: "STACKING"
                        value: String(t.capture_text || "")
                        tone: Theme.danger
                        glow: true
                    }
                    HudChip {
                        // compact lock-state badge (replaces the old full-width link banner)
                        id: lockBadge
                        readonly property bool tracking: root.scopeOnline && !!root.scopeTelemetry.tracking_active
                        readonly property bool slewing: root.scopeOnline && root.scopeActivity === "goto"
                        readonly property bool locked: root.targetLocked || tracking
                        label: slewing ? "GOTO" : tracking ? "TRACKING" : root.targetLocked ? "TARGET LOCKED" : (backend.selectedDevice.connected ? "NO TARGET LOCK" : "LINK DOWN")
                        tone: locked ? Theme.success : slewing ? Theme.notice : (backend.selectedDevice.connected ? Theme.accent : Theme.danger)
                        glow: locked || slewing
                        dim: !backend.selectedDevice.connected
                        TapHandler {
                            enabled: lockBadge.tracking && !lockBadge.slewing && root.commandEnabled("stop_goto")
                            onTapped: root.requestDeviceAction("stop_goto", "EXIT TRACKING")
                        }
                    }
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
                    color: Theme.textPrimary
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
                    color: Theme.textSecondary
                    font.pixelSize: 11
                }
                Text {
                    text: {
                        const t = root.scopeTelemetry
                        if (backend.currentSession.current_step) {
                            const step = Util.sessionStepLabel(backend.currentSession, backend.localNow.epoch_ms) || backend.currentSession.current_step
                            const frames = String(t.capture_text || "")
                            if (frames && t.capture_active && step.indexOf(frames) < 0)
                                return step + "  ·  " + frames + " frames"
                            return step
                        }
                        if (!backend.selectedDevice.connected)
                            return "Connect to acquire a lock"
                        if (root.scopeActivity === "goto")
                            return "Slewing to " + (t.tracking_target || root.scopeActivityDetail || "target")
                        if (t.tracking_active)
                            return "Tracking " + (t.tracking_target || "target") + (t.capture_active && t.stacked_text ? "  ·  " + t.stacked_text : "")
                        return "Telescope ready"
                    }
                    color: root.scopeTelemetry.tracking_active || root.scopeActivity === "goto" ? Theme.notice : Theme.textSecondary
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: backend.currentSession.duration_text ? "PLANNED  " + backend.currentSession.duration_text : Util.idleScheduleLabel(backend.upcomingSessions, backend.schedulerEnabled, backend.localNow.epoch_ms); color: Theme.accent; font.pixelSize: 11; font.letterSpacing: 0.8; Layout.fillWidth: true; elide: Text.ElideRight }
                    Text { visible: !!backend.currentSession.id; text: Math.round(backend.sessionProgress * 100) + "%"; color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono }
                }
                ProgressBar {
                    id: sessionBar
                    Layout.fillWidth: true
                    from: 0
                    to: 1
                    value: backend.sessionProgress
                    readonly property bool idle: !backend.currentSession.id
                    readonly property bool waitingForNext: idle && backend.schedulerEnabled && backend.upcomingSessions.length > 0
                    background: Rectangle { implicitHeight: 8; color: Theme.inputBg; border.color: Theme.outline }
                    contentItem: Item {
                        implicitHeight: 8
                        clip: true
                        Rectangle {
                            visible: !sessionBar.idle
                            width: sessionBar.visualPosition * parent.width
                            height: parent.height
                            color: Theme.accent
                        }
                        Rectangle {
                            id: idleSweep
                            visible: sessionBar.waitingForNext && controlPage.visible
                            width: 46
                            height: parent.height
                            opacity: 0.55
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: "transparent" }
                                GradientStop { position: 0.5; color: Theme.accent }
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
                HudButton {
                    Layout.fillWidth: true
                    visible: backend.currentSession.status === "running"
                    text: "STOP SESSION"
                    busy: root.scopeStopping
                    busyText: "STOPPING…"
                    busyMs: 0
                    enabled: !root.scopeStopping
                    buttonColor: Theme.fillDanger
                    foregroundColor: Theme.danger
                    onClicked: backend.stopSession(backend.currentSession.id)
                }
                HudMenu {
                    id: targetMenu
                    readonly property string coordinates: Util.targetCoordinates(backend.currentSession)
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
                        text: "Stop session"
                        glyph: "\uE71A"
                        destructive: true
                        enabled: backend.currentSession.status === "running" && !root.scopeStopping
                        onTriggered: backend.stopSession(backend.currentSession.id)
                    }
                }
            }

            HudPanel {
                id: cameraPanel
                title: "CAMERA"
                SplitView.fillHeight: true
                SplitView.minimumHeight: 120
                readonly property bool teleSelected: backend.selectedDevice.camera !== "wide"
                readonly property string shootingMode: String(root.scopeTelemetry.shooting_mode_text || "—")
                readonly property bool photoMode: shootingMode === "PHOTO"
                readonly property bool dsoMode: shootingMode === "DSO"
                FieldLabel { text: "SHOOTING MODE · " + (cameraPanel.shootingMode === "—" ? "UNKNOWN" : cameraPanel.shootingMode) }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    HudButton {
                        text: "PHOTO"
                        Layout.fillWidth: true
                        buttonColor: cameraPanel.photoMode ? Theme.fillChecked : Theme.surfaceHigh
                        foregroundColor: cameraPanel.photoMode ? Theme.accent : Theme.textPrimary
                        busy: root.scopePending === "photo_mode"
                        busyText: "SWITCHING…"
                        busyMs: 0
                        enabled: root.commandEnabled("photo_mode")
                        Accessible.description: cameraPanel.photoMode ? "Current shooting mode" : "Switch to photo shooting mode"
                        onClicked: if (!cameraPanel.photoMode) backend.deviceAction(backend.selectedDeviceId, "photo_mode")
                    }
                    HudButton {
                        text: "DSO"
                        Layout.fillWidth: true
                        buttonColor: cameraPanel.dsoMode ? Theme.fillChecked : Theme.surfaceHigh
                        foregroundColor: cameraPanel.dsoMode ? Theme.accent : Theme.textPrimary
                        busy: root.scopePending === "astro_mode"
                        busyText: "SWITCHING…"
                        busyMs: 0
                        enabled: root.commandEnabled("astro_mode")
                        Accessible.description: cameraPanel.dsoMode ? "Current shooting mode" : "Switch to deep-sky shooting mode"
                        onClicked: if (!cameraPanel.dsoMode) backend.deviceAction(backend.selectedDeviceId, "astro_mode")
                    }
                }
                FieldLabel { text: "FOCUS"; visible: cameraPanel.teleSelected }
                HudField {
                    id: liveFocus
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
                    placeholderText: "steps"
                    inputMethodHints: Qt.ImhDigitsOnly
                    enabled: root.commandEnabled("set_focus")
                    readonly property string liveValue: {
                        const value = root.scopeTelemetry.focus_text
                        return value && value !== "—" ? String(value) : ""
                    }
                    onLiveValueChanged: if (!activeFocus) text = liveValue
                    Component.onCompleted: text = liveValue
                    onEditingFinished: {
                        const value = text.trim()
                        if (!value) {
                            text = liveValue
                            return
                        }
                        if (value === liveValue)
                            return
                        backend.setCameraParam(backend.selectedDeviceId, "focus", value)
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
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
                    visible: cameraPanel.teleSelected
                }
                HudCombo {
                    id: liveFilter
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
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
                        readonly property string liveValue: {
                            const value = backend.selectedDevice.camera === "wide"
                                ? root.scopeTelemetry.wide_exposure_text
                                : root.scopeTelemetry.exposure_text
                            return value && value !== "—" ? String(value) : ""
                        }
                        onLiveValueChanged: if (!activeFocus) text = liveValue
                        Component.onCompleted: text = liveValue
                        onEditingFinished: {
                            const value = text.trim()
                            if (!value) {
                                text = liveValue
                                return
                            }
                            if (value !== liveValue)
                                backend.setCameraParam(backend.selectedDeviceId, "exposure", value)
                        }
                    }
                    HudField {
                        id: liveGain
                        Layout.fillWidth: true
                        enabled: root.commandEnabled("set_gain")
                        placeholderText: "gain"
                        readonly property string liveValue: {
                            const value = backend.selectedDevice.camera === "wide"
                                ? root.scopeTelemetry.wide_gain
                                : root.scopeTelemetry.gain
                            return value !== undefined && value !== null ? String(value) : ""
                        }
                        onLiveValueChanged: if (!activeFocus) text = liveValue
                        Component.onCompleted: text = liveValue
                        onEditingFinished: {
                            const value = text.trim()
                            if (!value) {
                                text = liveValue
                                return
                            }
                            if (value !== liveValue)
                                backend.setCameraParam(backend.selectedDeviceId, "gain", value)
                        }
                    }
                }
                FieldLabel { text: "WHITE BALANCE"; visible: cameraPanel.teleSelected }
                HudCombo {
                    id: liveWb
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
                    enabled: root.commandEnabled("set_wb_preset")
                    model: ["Incandescent", "Warm Fluorescent", "Fluorescent", "Sunlight", "Cloudy", "Shadow", "Twilight"]
                    onActivated: backend.setCameraParam(backend.selectedDeviceId, "wb_preset", currentText)
                    readonly property int liveIndex: {
                        const value = backend.selectedDevice.camera === "wide"
                            ? root.scopeTelemetry.wide_wb_scene
                            : root.scopeTelemetry.wb_scene
                        const index = Number(value)
                        return isFinite(index) && index >= 0 && index < count ? index : -1
                    }
                    onLiveIndexChanged: if (liveIndex >= 0) currentIndex = liveIndex
                }
                HudField {
                    id: liveWbKelvin
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
                    enabled: root.commandEnabled("set_wb")
                    placeholderText: "Kelvin 2800–7500"
                    readonly property string liveValue: {
                        const value = backend.selectedDevice.camera === "wide"
                            ? root.scopeTelemetry.wide_wb_value
                            : root.scopeTelemetry.wb_value
                        return value !== undefined && value !== null ? String(value) : ""
                    }
                    onLiveValueChanged: if (!activeFocus) text = liveValue
                    Component.onCompleted: text = liveValue
                    onEditingFinished: {
                        const value = text.trim()
                        if (!value) {
                            text = liveValue
                            return
                        }
                        if (value !== liveValue)
                            backend.setCameraParam(backend.selectedDeviceId, "wb", value)
                    }
                }
                FieldLabel { text: "IMAGE"; visible: cameraPanel.teleSelected }
                RowLayout {
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
                    HudField { id: liveBrightness; Layout.fillWidth: true; placeholderText: "bri"; enabled: root.commandEnabled("set_brightness"); readonly property var liveRaw: backend.selectedDevice.camera === "wide" ? root.scopeTelemetry.wide_brightness : root.scopeTelemetry.brightness; readonly property string liveValue: liveRaw !== undefined && liveRaw !== null ? String(liveRaw) : ""; onLiveValueChanged: if (!activeFocus) text = liveValue; Component.onCompleted: text = liveValue; onEditingFinished: { const value = text.trim(); if (!value) { text = liveValue; return } if (value !== liveValue) backend.setCameraParam(backend.selectedDeviceId, "brightness", value) } }
                    HudField { id: liveContrast; Layout.fillWidth: true; placeholderText: "con"; enabled: root.commandEnabled("set_contrast"); readonly property var liveRaw: backend.selectedDevice.camera === "wide" ? root.scopeTelemetry.wide_contrast : root.scopeTelemetry.contrast; readonly property string liveValue: liveRaw !== undefined && liveRaw !== null ? String(liveRaw) : ""; onLiveValueChanged: if (!activeFocus) text = liveValue; Component.onCompleted: text = liveValue; onEditingFinished: { const value = text.trim(); if (!value) { text = liveValue; return } if (value !== liveValue) backend.setCameraParam(backend.selectedDeviceId, "contrast", value) } }
                    HudField { id: liveSaturation; Layout.fillWidth: true; placeholderText: "sat"; enabled: root.commandEnabled("set_saturation"); readonly property var liveRaw: backend.selectedDevice.camera === "wide" ? root.scopeTelemetry.wide_saturation : root.scopeTelemetry.saturation; readonly property string liveValue: liveRaw !== undefined && liveRaw !== null ? String(liveRaw) : ""; onLiveValueChanged: if (!activeFocus) text = liveValue; Component.onCompleted: text = liveValue; onEditingFinished: { const value = text.trim(); if (!value) { text = liveValue; return } if (value !== liveValue) backend.setCameraParam(backend.selectedDeviceId, "saturation", value) } }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: cameraPanel.teleSelected
                    HudField { id: liveHue; Layout.fillWidth: true; placeholderText: "hue"; enabled: root.commandEnabled("set_hue"); readonly property var liveRaw: backend.selectedDevice.camera === "wide" ? root.scopeTelemetry.wide_hue : root.scopeTelemetry.hue; readonly property string liveValue: liveRaw !== undefined && liveRaw !== null ? String(liveRaw) : ""; onLiveValueChanged: if (!activeFocus) text = liveValue; Component.onCompleted: text = liveValue; onEditingFinished: { const value = text.trim(); if (!value) { text = liveValue; return } if (value !== liveValue) backend.setCameraParam(backend.selectedDeviceId, "hue", value) } }
                    HudField { id: liveSharpness; Layout.fillWidth: true; placeholderText: "shp"; enabled: root.commandEnabled("set_sharpness"); readonly property var liveRaw: backend.selectedDevice.camera === "wide" ? root.scopeTelemetry.wide_sharpness : root.scopeTelemetry.sharpness; readonly property string liveValue: liveRaw !== undefined && liveRaw !== null ? String(liveRaw) : ""; onLiveValueChanged: if (!activeFocus) text = liveValue; Component.onCompleted: text = liveValue; onEditingFinished: { const value = text.trim(); if (!value) { text = liveValue; return } if (value !== liveValue) backend.setCameraParam(backend.selectedDeviceId, "sharpness", value) } }
                    HudCombo {
                        Layout.fillWidth: true
                        enabled: root.commandEnabled("set_stack_format")
                        model: ["FITS", "TIFF"]
                        onActivated: backend.setCameraParam(backend.selectedDeviceId, "stack_format", String(currentIndex))
                    }
                }
                FieldLabel { text: "STACK COUNT" }
                HudField {
                    id: liveStackCount
                    Layout.fillWidth: true
                    enabled: root.commandEnabled("set_count")
                    placeholderText: "frames"
                    text: "120"
                    inputMethodHints: Qt.ImhDigitsOnly
                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "count", text)
                }
                FieldLabel { text: "BURST / TIMELAPSE" }
                RowLayout {
                    Layout.fillWidth: true
                    HudField { Layout.fillWidth: true; placeholderText: "burst #"; enabled: root.commandEnabled("set_burst_count"); onEditingFinished: if (text.trim()) backend.setCameraParam(backend.selectedDeviceId, "burst_count", text) }
                    HudCombo {
                        Layout.fillWidth: true
                        enabled: root.commandEnabled("set_burst_interval")
                        model: ["1", "2", "3", "5", "10", "15", "20"]
                        onActivated: backend.setCameraParam(backend.selectedDeviceId, "burst_interval", currentText)
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    HudCombo {
                        Layout.fillWidth: true
                        enabled: root.commandEnabled("set_timelapse_interval")
                        model: ["1", "2", "5", "10", "15", "30", "60"]
                        onActivated: backend.setCameraParam(backend.selectedDeviceId, "timelapse_interval", currentText)
                    }
                    HudCombo {
                        Layout.fillWidth: true
                        enabled: root.commandEnabled("set_timelapse_duration")
                        model: ["30", "60", "120", "300", "600"]
                        onActivated: backend.setCameraParam(backend.selectedDeviceId, "timelapse_duration", currentText)
                    }
                }
                HudCheck {
                    text: "Auto calibration (unconfirmed)"
                    enabled: root.commandEnabled("set_auto_calibration")
                    onClicked: backend.setCameraParam(backend.selectedDeviceId, "auto_calibration", checked ? "true" : "false")
                }
                FieldLabel { text: "MEDIA" }
                HudButton {
                    text: "OPEN MEDIA"
                    Layout.fillWidth: true
                    onClicked: root.goToPage(root.mediaPageIndex)
                }
            }
        }

        HudSplitView {
            id: controlCenter
            settingsKey: "controlCenter"
            orientation: Qt.Vertical
            SplitView.fillWidth: true
            SplitView.minimumWidth: 280

            HudPanel {
                SplitView.fillHeight: true
                SplitView.minimumHeight: 150
                fill: Theme.hsl(0.090, 0.375, 0.031, 0.878)
                Item {
                    id: previewHost
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: 0
                    property string previewDeviceId: backend.selectedDeviceId
                    readonly property string statusText: {
                        if (root.scopeStopping)
                            return root.scopePendingDetail || "Stopping telescope activity"
                        if (backend.previewHeld)
                            return backend.previewHoldMessage
                        if (backend.previewStatus)
                            return backend.previewStatus
                        if (backend.selectedDevice.connected)
                            return backend.videoUrl || "Telescope connected — start the stream"
                        return "Connect a telescope to start the stream"
                    }
                    readonly property bool preferredWide: backend.selectedDevice.camera === "wide"
                    property bool pipEnabled: true
                    readonly property bool pipAvailable: backend.previewTelePlaying && backend.previewWidePlaying && !backend.previewStacking
                    readonly property bool mainIsWide: backend.previewStacking ? false : preferredWide
                    readonly property bool displayWide: backend.previewStacking ? false : (pipAvailable ? preferredWide : backend.previewWidePlaying)
                    readonly property bool mainPlaying: displayWide ? backend.previewWidePlaying : backend.previewTelePlaying
                    readonly property int stackCount: {
                        const n = Number(root.scopeTelemetry.capture_stacked)
                        return isFinite(n) && n > 0 ? n : 0
                    }
                    readonly property int stackTotal: {
                        const n = Number(root.scopeTelemetry.capture_total)
                        return isFinite(n) && n > 0 ? n : 0
                    }
                    readonly property bool awaitingFirstStack: {
                        if (root.scopeStopping)
                            return false
                        if (!backend.previewStacking && !root.scopeTelemetry.capture_active)
                            return false
                        return previewHost.stackCount < 1
                    }
                    readonly property bool pipPlaying: pipAvailable && pipEnabled
                    readonly property bool idlePreviewArt: !backend.previewPlaying && !backend.previewStacking && !previewHost.awaitingFirstStack
                    readonly property real teleFovH: {
                        const tele = Number(root.scopeTelemetry.tele_fov_h)
                        const wide = Number(root.scopeTelemetry.wide_fov_h)
                        return (tele > 0 && wide > 0) ? tele / wide : 2.95 / 45.06
                    }
                    readonly property real teleFovV: {
                        const tele = Number(root.scopeTelemetry.tele_fov_v)
                        const wide = Number(root.scopeTelemetry.wide_fov_v)
                        return (tele > 0 && wide > 0) ? tele / wide : 1.66 / 25.93
                    }
                    readonly property real teleMatchNx: {
                        const v = Number(root.scopeTelemetry.tele_match_nx)
                        return (v > 0 && v < 1) ? v : 0.5
                    }
                    readonly property real teleMatchNy: {
                        const v = Number(root.scopeTelemetry.tele_match_ny)
                        return (v > 0 && v < 1) ? v : 0.5
                    }
                    readonly property real teleMatchNw: {
                        const v = Number(root.scopeTelemetry.tele_match_nw)
                        return (v > 0 && v < 1) ? v : 0
                    }
                    readonly property real teleMatchNh: {
                        const v = Number(root.scopeTelemetry.tele_match_nh)
                        return (v > 0 && v < 1) ? v : 0
                    }
                    function liveCamera(wide) {
                        return wide ? "wide" : "tele"
                    }
                    function swapViews() {
                        if (!pipAvailable)
                            return
                        backend.setLiveCamera(backend.selectedDeviceId, preferredWide ? "tele" : "wide")
                    }
                    readonly property bool previewFailed: {
                        const s = String(backend.previewStatus || "").toLowerCase()
                        return s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0
                    }
                    readonly property bool previewStartEnabled: backend.selectedDevice.connected && !root.scopeLinking && !root.scopeStopping && (!backend.previewActive || backend.previewPlaying || previewFailed)
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
                        if (s.indexOf("download") >= 0)
                            return "DOWNLOADING PREVIEW…"
                        if (s.indexOf("tcp") >= 0 || s.indexOf("opening") >= 0)
                            return "OPENING STREAM…"
                        if (s.indexOf("starting") >= 0)
                            return "STARTING CAMERA…"
                        return "STARTING PREVIEW…"
                    }

                    function startPreview() {
                        if (!backend.selectedDevice.connected) {
                            backend.uiLog("warning", "Preview needs an active telescope connection")
                            return
                        }
                        backend.startPreview(backend.selectedDeviceId)
                    }

                    function stopPreview() {
                        backend.stopPreview()
                    }

                    // Chrome model: status (LIVE/REC badges, readout strip) is always on
                    // while streaming; controls (stop button) appear on pointer motion
                    // or a touch tap and fade after a short idle, unless the pointer is
                    // resting on a control. First stream ever shows a hint.
                    // Idle art (telescope image + scanline grid) stays off while live
                    // view or stacking is up, including on hover.
                    property bool controlsVisible: false
                    property bool controlHovered: false
                    readonly property bool chromeShown: !backend.previewPlaying || controlsVisible

                    function revealControls() {
                        controlsVisible = true
                        firstRunHint.dismiss()
                        if (!controlHovered)
                            chromeIdleTimer.restart()
                    }

                    function hideControls() {
                        if (controlHovered)
                            return
                        controlsVisible = false
                        chromeIdleTimer.stop()
                    }

                    function toggleControls() {
                        if (controlsVisible)
                            hideControls()
                        else
                            revealControls()
                    }

                    function holdControls(hold) {
                        controlHovered = hold
                        if (hold) {
                            controlsVisible = true
                            chromeIdleTimer.stop()
                        } else {
                            chromeIdleTimer.restart()
                        }
                    }

                    Timer {
                        id: chromeIdleTimer
                        interval: 2500
                        repeat: false
                        onTriggered: {
                            if (!previewHost.controlHovered)
                                previewHost.controlsVisible = false
                        }
                    }

                    HoverHandler {
                        id: previewHover
                        enabled: backend.previewPlaying
                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                        onPointChanged: previewHost.revealControls()
                        onHoveredChanged: {
                            if (!hovered)
                                previewHost.hideControls()
                        }
                    }
                    TapHandler {
                        // touch: single tap toggles the controls (mouse users hover instead)
                        enabled: backend.previewPlaying
                        acceptedDevices: PointerDevice.TouchScreen
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onSingleTapped: previewHost.toggleControls()
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
                        function onPreviewPlayingChanged() {
                            previewHost.controlHovered = false
                            previewHost.controlsVisible = false
                            chromeIdleTimer.stop()
                            if (backend.previewPlaying && !Theme.previewChromeHintSeen)
                                firstRunHint.show()
                            else
                                firstRunHint.hide()
                        }
                    }

                    LiveViewPane {
                        id: liveFrame
                        anchors.fill: parent
                        playing: previewHost.mainPlaying
                        wideView: previewHost.displayWide
                        camera: previewHost.liveCamera(previewHost.displayWide)
                        centerEnabled: playing && root.motionEnabled
                        showFootprint: wideView
                        chromeShown: previewHost.chromeShown
                        fovH: previewHost.teleFovH
                        fovV: previewHost.teleFovV
                        footprintNx: previewHost.teleMatchNx
                        footprintNy: previewHost.teleMatchNy
                        footprintNw: previewHost.teleMatchNw
                        footprintNh: previewHost.teleMatchNh
                        onCenterRequested: (nx, ny, diag) => backend.centerOnTap(backend.selectedDeviceId, nx, ny, diag)
                    }

                    Item {
                        id: pipBox
                        z: 3
                        clip: true
                        visible: previewHost.pipPlaying
                        width: Math.round(Math.max(168, Math.min(parent.width * 0.32, parent.height * 0.38, 300)))
                        height: Math.round(width * pipAspect)
                        property bool floating: false
                        readonly property real pipAspect: pipPane.sourceAspect
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.rightMargin: 14
                        anchors.bottomMargin: 46
                        function beginFloat() {
                            if (floating)
                                return
                            const pos = mapToItem(parent, 0, 0)
                            anchors.right = undefined
                            anchors.bottom = undefined
                            anchors.rightMargin = 0
                            anchors.bottomMargin = 0
                            x = pos.x
                            y = pos.y
                            floating = true
                        }
                        function clampToHost() {
                            if (!floating || !parent)
                                return
                            x = Math.max(8, Math.min(x, parent.width - width - 8))
                            y = Math.max(8, Math.min(y, parent.height - height - 8))
                        }
                        onWidthChanged: clampToHost()
                        onHeightChanged: clampToHost()
                        Connections {
                            target: previewHost
                            function onWidthChanged() { pipBox.clampToHost() }
                            function onHeightChanged() { pipBox.clampToHost() }
                        }
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.hsl(0.090, 0.375, 0.031, 0.92)
                            border.color: Theme.accent
                            border.width: 1
                        }
                        LiveViewPane {
                            id: pipPane
                            anchors.fill: parent
                            anchors.margins: 1
                            playing: previewHost.pipPlaying
                            wideView: !previewHost.displayWide
                            camera: previewHost.liveCamera(!previewHost.displayWide)
                            centerEnabled: playing && root.motionEnabled
                            inputEnabled: false
                            swallowClicks: true
                            showFootprint: wideView
                            chromeShown: previewHost.chromeShown
                            fovH: previewHost.teleFovH
                            fovV: previewHost.teleFovV
                            footprintNx: previewHost.teleMatchNx
                            footprintNy: previewHost.teleMatchNy
                            footprintNw: previewHost.teleMatchNw
                            footprintNh: previewHost.teleMatchNh
                            onCenterRequested: (nx, ny, diag) => backend.centerOnTap(backend.selectedDeviceId, nx, ny, diag)
                        }
                        MouseArea {
                            id: pipDrag
                            anchors.fill: parent
                            hoverEnabled: true
                            drag.target: pipBox
                            drag.minimumX: 8
                            drag.maximumX: Math.max(8, previewHost.width - pipBox.width - 8)
                            drag.minimumY: 8
                            drag.maximumY: Math.max(8, previewHost.height - pipBox.height - 8)
                            onPressed: pipBox.beginFloat()
                            onContainsMouseChanged: previewHost.holdControls(containsMouse)
                            onDoubleClicked: (mouse) => pipPane.centerOn(mouse.x, mouse.y)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 6
                            width: pipLabel.implicitWidth + 12
                            height: 18
                            color: Theme.hsl(0.079, 0.517, 0.057, 0.82)
                            border.color: Theme.outline
                            Text {
                                id: pipLabel
                                anchors.centerIn: parent
                                text: pipPane.wideView ? "WIDE" : "TELE"
                                color: Theme.accent
                                font.pixelSize: 9
                                font.bold: true
                                font.letterSpacing: 1
                            }
                        }
                        Row {
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 6
                            spacing: 4
                            z: 2
                            Rectangle {
                                id: pipSwap
                                width: pipSwapLabel.implicitWidth + 14
                                height: 18
                                color: Theme.fillActive
                                border.color: Theme.accent
                                Text {
                                    id: pipSwapLabel
                                    anchors.centerIn: parent
                                    text: "SWAP"
                                    color: Theme.accent
                                    font.pixelSize: 9
                                    font.bold: true
                                    font.letterSpacing: 1
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onContainsMouseChanged: previewHost.holdControls(containsMouse)
                                    onClicked: previewHost.swapViews()
                                }
                            }
                            Rectangle {
                                id: pipHide
                                width: pipHideLabel.implicitWidth + 14
                                height: 18
                                color: Theme.fillActive
                                border.color: Theme.accent
                                Text {
                                    id: pipHideLabel
                                    anchors.centerIn: parent
                                    text: "HIDE"
                                    color: Theme.accent
                                    font.pixelSize: 9
                                    font.bold: true
                                    font.letterSpacing: 1
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onContainsMouseChanged: previewHost.holdControls(containsMouse)
                                    onClicked: previewHost.pipEnabled = false
                                }
                            }
                        }
                    }
                    Image {
                        anchors.fill: parent
                        visible: previewHost.idlePreviewArt
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
                        // faint scanline grid — idle placeholder only, never over a live/stack frame
                        anchors.fill: parent
                        visible: opacity > 0
                        opacity: previewHost.idlePreviewArt ? 0.22 : 0
                        Behavior on opacity { NumberAnimation { duration: 220 } }
                        readonly property color ink: Theme.accent
                        onInkChanged: requestPaint()
                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.reset()
                            ctx.strokeStyle = ink
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
                        z: 7
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.margins: 14
                        height: 24
                        // status stays up while streaming; it just recedes when the controls are away
                        opacity: previewHost.chromeShown ? 1 : 0.62
                        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
                        color: Theme.hsl(0.079, 0.517, 0.057, 0.690)
                        border.color: Theme.outline
                        RowLayout {
                            id: readoutStrip
                            readonly property var t: root.scopeTelemetry
                            readonly property bool wide: previewHost.displayWide
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
                            Text { text: readoutStrip.wide ? "WIDE" : "TELE"; color: Theme.accent; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1 }
                            Text { text: "EXP " + readoutStrip.exposure + "s"; color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono }
                            Text { text: "GAIN " + readoutStrip.gain; color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono }
                            Text { visible: !readoutStrip.wide; text: liveFilter.currentText.toUpperCase(); color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono; elide: Text.ElideRight }
                            Text {
                                visible: root.scopeOnline && readoutStrip.t.capture_active && !!readoutStrip.t.capture_text
                                text: "FRAMES " + (readoutStrip.t.capture_text || "")
                                color: readoutStrip.t.capture_active ? Theme.danger : Theme.textPrimary
                                font.pixelSize: 10; font.family: Theme.fontMono; font.bold: true
                            }
                            Item { Layout.fillWidth: true }
                            Text { visible: root.scopeOnline && readoutStrip.sensor !== "—"; text: "SENSOR " + readoutStrip.sensor; color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono }
                            Text {
                                visible: root.scopeOnline && readoutStrip.t.battery_percent !== undefined && Number(readoutStrip.t.battery_percent) >= 0
                                text: "BATT " + (readoutStrip.t.battery_text || "—") + (readoutStrip.t.charging ? "⚡" : "")
                                color: Util.toneColor(Util.batteryTone(readoutStrip.t.battery_percent))
                                font.pixelSize: 10; font.family: Theme.fontMono
                            }
                            Text { visible: !root.scopeOnline; text: backend.selectedDevice.ip_address || "—"; color: Theme.textSecondary; font.pixelSize: 10; font.family: Theme.fontMono }
                            Text { text: backend.clockText; color: Theme.accent; font.pixelSize: 10; font.family: Theme.fontMono }
                        }
                    }
                    Column {
                        z: 5
                        anchors.centerIn: parent
                        spacing: 10
                        width: Math.min(parent.width - 48, 520)
                        visible: backend.previewHeld && !backend.previewPlaying && !root.scopeStopping && !previewHost.awaitingFirstStack
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "LIVE VIEW PAUSED"
                            color: Theme.warning
                            font.pixelSize: 16
                            font.letterSpacing: 3
                            font.bold: true
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: parent.width
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            text: backend.previewHoldMessage
                            color: Theme.textPrimary
                            font.pixelSize: 13
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: parent.width
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            text: "Streaming resumes automatically when stacking starts."
                            color: Theme.textSecondary
                            font.pixelSize: 11
                        }
                    }
                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        visible: !backend.previewPlaying && !backend.previewHeld && !root.scopeStopping && !previewHost.awaitingFirstStack
                        Text { anchors.horizontalCenter: parent.horizontalCenter; text: "LIVE VIDEO"; color: Theme.textPrimary; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: previewHost.width - 40
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                            text: previewHost.statusText
                            color: Theme.textSecondary
                        }
                        HudButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "START PREVIEW"
                            busyText: previewHost.actionLabel
                            busy: backend.previewActive && !backend.previewPlaying
                            busyMs: backend.selectedDevice.connected && !backend.previewActive ? 1800 : 0
                            enabled: previewHost.previewStartEnabled
                            buttonColor: Theme.fillActive
                            foregroundColor: Theme.accent
                            onClicked: previewHost.startPreview()
                        }
                    }
                    Item {
                        id: stackWaitOverlay
                        z: 5
                        anchors.fill: parent
                        visible: previewHost.awaitingFirstStack
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.scrim
                            opacity: backend.previewPlaying ? 0.55 : 0.28
                        }
                        Column {
                            anchors.centerIn: parent
                            spacing: 10
                            width: Math.min(parent.width - 48, 520)
                            Text {
                                id: stackWaitHeading
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "WAITING FOR FIRST STACKED FRAME"
                                color: Theme.warning
                                font.pixelSize: 16
                                font.letterSpacing: 2
                                font.bold: true
                                SequentialAnimation on opacity {
                                    running: stackWaitOverlay.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.45; duration: 700; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.45; to: 1; duration: 700; easing.type: Easing.InOutSine }
                                    onRunningChanged: if (!running) stackWaitHeading.opacity = 1
                                }
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: parent.width
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                text: previewHost.stackTotal > 0
                                    ? previewHost.stackCount + " / " + previewHost.stackTotal + " frames stacked"
                                    : (previewHost.stackCount > 0
                                        ? previewHost.stackCount + " frames stacked"
                                        : "No stacked frames yet")
                                color: Theme.textPrimary
                                font.pixelSize: 13
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: parent.width
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                text: "Live video stops when stacking starts. The stacked preview appears after the first frame is captured and added to the stack — this can take one full exposure."
                                color: Theme.textSecondary
                                font.pixelSize: 11
                            }
                        }
                    }
                    Item {
                        id: stopOverlay
                        z: 6
                        anchors.fill: parent
                        visible: root.scopeStopping
                        Rectangle {
                            anchors.fill: parent
                            color: Theme.scrim
                            opacity: backend.previewPlaying ? 0.62 : 0.28
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: stopOverlay.visible
                        }
                        Column {
                            anchors.centerIn: parent
                            spacing: 10
                            width: Math.min(parent.width - 48, 520)
                            Text {
                                id: stopHeading
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "STOPPING"
                                color: Theme.warning
                                font.pixelSize: 16
                                font.letterSpacing: 3
                                font.bold: true
                                SequentialAnimation on opacity {
                                    running: stopOverlay.visible
                                    loops: Animation.Infinite
                                    NumberAnimation { from: 1; to: 0.45; duration: 700; easing.type: Easing.InOutSine }
                                    NumberAnimation { from: 0.45; to: 1; duration: 700; easing.type: Easing.InOutSine }
                                    onRunningChanged: if (!running) stopHeading.opacity = 1
                                }
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: parent.width
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                text: previewHost.statusText
                                color: Theme.textPrimary
                                font.pixelSize: 13
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: parent.width
                                wrapMode: Text.Wrap
                                horizontalAlignment: Text.AlignHCenter
                                text: "This can take a few seconds while capture, GOTO and motors wind down."
                                color: Theme.textSecondary
                                font.pixelSize: 11
                            }
                        }
                    }
                    Row {
                        z: 7
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 6
                        opacity: previewHost.chromeShown ? 1 : 0.75
                        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
                        Rectangle {
                            id: previewBadge
                            readonly property bool stopping: root.scopeStopping
                            width: stopping ? 118 : (backend.previewHeld && !backend.previewPlaying ? 108 : 96)
                            height: 28
                            color: Theme.hsl(0.094, 0.333, 0.094, 0.753)
                            border.color: stopping ? Theme.warning : (backend.previewPlaying ? Theme.success : (backend.previewHeld ? Theme.warning : Theme.outline))
                            Row {
                                anchors.centerIn: parent
                                spacing: 7
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: previewBadge.stopping ? Theme.warning : (backend.previewPlaying ? Theme.danger : (backend.previewHeld ? Theme.warning : (backend.previewActive ? Theme.warning : "#64748B")))
                                    anchors.verticalCenter: parent.verticalCenter
                                    SequentialAnimation on opacity {
                                        running: backend.previewPlaying || previewBadge.stopping
                                        loops: Animation.Infinite
                                        NumberAnimation { from: 1; to: 0.3; duration: 600 }
                                        NumberAnimation { from: 0.3; to: 1; duration: 600 }
                                    }
                                }
                                Text { text: previewBadge.stopping ? "STOPPING" : (backend.previewPlaying ? (backend.previewStacking ? "STACK" : "LIVE") : (backend.previewHeld ? "PAUSED" : (backend.previewActive ? "STARTING" : "STANDBY"))); color: Theme.textPrimary; font.pixelSize: 11; font.bold: true }
                            }
                        }
                        Rectangle {
                            visible: backend.previewPlaying
                            width: mainCamLabel.implicitWidth + 16
                            height: 28
                            color: Theme.hsl(0.094, 0.333, 0.094, 0.753)
                            border.color: Theme.outline
                            Text {
                                id: mainCamLabel
                                anchors.centerIn: parent
                                text: previewHost.displayWide ? "WIDE" : (backend.previewStacking ? "STACK" : "TELE")
                                color: Theme.accent
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 1
                            }
                        }
                        Rectangle {
                            visible: backend.previewStacking || previewHost.awaitingFirstStack
                            width: enhanceLabel.implicitWidth + 16
                            height: 28
                            color: Theme.enhanceImages ? Theme.fillActive : Theme.hsl(0.094, 0.333, 0.094, 0.753)
                            border.color: Theme.enhanceImages ? Theme.accent : Theme.outline
                            Text {
                                id: enhanceLabel
                                anchors.centerIn: parent
                                text: "ENHANCE"
                                color: Theme.enhanceImages ? Theme.accent : Theme.textSecondary
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 1
                            }
                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onContainsMouseChanged: previewHost.holdControls(containsMouse)
                                onClicked: Theme.enhanceImages = !Theme.enhanceImages
                            }
                        }
                        Rectangle {
                            visible: (backend.previewStacking || previewHost.awaitingFirstStack) && Theme.enhanceImages
                            width: deepLabel.implicitWidth + 16
                            height: 28
                            color: Theme.deepCleanImages ? Theme.fillActive : Theme.hsl(0.094, 0.333, 0.094, 0.753)
                            border.color: Theme.deepCleanImages ? Theme.accent : Theme.outline
                            Text {
                                id: deepLabel
                                anchors.centerIn: parent
                                text: "DEEP"
                                color: Theme.deepCleanImages ? Theme.accent : Theme.textSecondary
                                font.pixelSize: 11
                                font.bold: true
                                font.letterSpacing: 1
                            }
                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onContainsMouseChanged: previewHost.holdControls(containsMouse)
                                onClicked: Theme.deepCleanImages = !Theme.deepCleanImages
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
                            border.color: Theme.danger
                            Row {
                                id: recRow
                                anchors.centerIn: parent
                                spacing: 7
                                Rectangle {
                                    width: 8; height: 8; radius: 4; color: Theme.danger
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
                                    color: Theme.danger; font.pixelSize: 11; font.bold: true; font.family: Theme.fontMono
                                }
                            }
                        }
                    }
                    Row {
                        id: previewActions
                        z: 7
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 14
                        spacing: 8
                        opacity: backend.previewActive && previewHost.chromeShown ? 1 : 0
                        visible: opacity > 0
                        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                        HudButton {
                            visible: previewHost.pipAvailable
                            text: previewHost.pipEnabled ? "HIDE PIP" : "SHOW PIP"
                            onHoveredChanged: previewHost.holdControls(hovered)
                            onClicked: previewHost.pipEnabled = !previewHost.pipEnabled
                        }
                        HudButton {
                            visible: previewHost.pipAvailable
                            text: "SWAP VIEWS"
                            onHoveredChanged: previewHost.holdControls(hovered)
                            onClicked: previewHost.swapViews()
                        }
                        HudButton {
                            id: stopPreviewButton
                            text: "STOP PREVIEW"
                            busyText: "STOPPING…"
                            onHoveredChanged: previewHost.holdControls(hovered)
                            onClicked: previewHost.stopPreview()
                        }
                    }
                    Rectangle {
                        // one-time hint the first time a stream comes up
                        id: firstRunHint
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 50
                        width: Math.min(parent.width - 24, hintRow.implicitWidth + 28)
                        height: 30
                        radius: 15
                        color: Theme.popupBg
                        border.color: Theme.accent
                        opacity: 0
                        visible: opacity > 0
                        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
                        function show() {
                            opacity = 1
                            hintTimer.restart()
                        }
                        function hide() {
                            opacity = 0
                            hintTimer.stop()
                        }
                        function dismiss() {
                            if (opacity === 0)
                                return
                            Theme.previewChromeHintSeen = true
                            hide()
                        }
                        Timer {
                            id: hintTimer
                            interval: 8000
                            repeat: false
                            onTriggered: firstRunHint.dismiss()
                        }
                        RowLayout {
                            id: hintRow
                            anchors.fill: parent
                            anchors.leftMargin: 14
                            anchors.rightMargin: 14
                            spacing: 10
                            Text { text: "\uE962"; font.family: Theme.fontIcon; font.pixelSize: 12; color: Theme.accent; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                text: "MOVE THE POINTER OVER THE STREAM FOR CONTROLS  ·  DOUBLE-CLICK THE WIDE VIEW TO CENTRE"
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontSm
                                font.letterSpacing: Theme.tracking1
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                            }
                        }
                    }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: previewMenu.popup()
                    }
                    HudMenu {
                        id: previewMenu
                        HudMenuItem {
                            text: backend.previewHeld ? "Don't resume live view" : (backend.previewActive ? "Stop preview" : "Start preview")
                            glyph: backend.previewActive || backend.previewHeld ? "\uE71A" : "\uE768"
                            enabled: backend.previewActive
                                || backend.previewHeld
                                || previewHost.previewStartEnabled
                            onTriggered: {
                                if (backend.previewActive || backend.previewHeld)
                                    previewHost.stopPreview()
                                else
                                    previewHost.startPreview()
                            }
                        }
                        HudMenuItem {
                            text: previewHost.pipEnabled ? "Hide picture-in-picture" : "Show picture-in-picture"
                            glyph: "\uE7C4"
                            enabled: previewHost.pipAvailable
                            onTriggered: previewHost.pipEnabled = !previewHost.pipEnabled
                        }
                        HudMenuItem {
                            text: "Swap views"
                            glyph: "\uE8AB"
                            enabled: previewHost.pipAvailable
                            onTriggered: previewHost.swapViews()
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
                headerExtra: Row {
                    spacing: 8
                    visible: !!(root.scopeTelemetry.eq_has_result)
                    Text {
                        text: String(root.scopeTelemetry.eq_azi_text || "")
                        color: Number(root.scopeTelemetry.eq_azi_err) > 0 ? Theme.success : (Number(root.scopeTelemetry.eq_azi_err) < 0 ? Theme.danger : Theme.textSecondary)
                        font.pixelSize: 10
                        font.family: Theme.fontMono
                    }
                    Text {
                        text: String(root.scopeTelemetry.eq_alt_text || "")
                        color: Number(root.scopeTelemetry.eq_alt_err) > 0 ? Theme.success : (Number(root.scopeTelemetry.eq_alt_err) < 0 ? Theme.danger : Theme.textSecondary)
                        font.pixelSize: 10
                        font.family: Theme.fontMono
                    }
                }
                GridLayout {
                    id: commandGrid
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    readonly property int padCount: 16
                    // pick the widest column count that still divides the pads into full rows
                    columns: {
                        const fit = Math.max(2, Math.floor((width + columnSpacing) / (150 + columnSpacing)))
                        const options = [8, 4, 3]
                        for (let i = 0; i < options.length; i++)
                            if (options[i] <= fit)
                                return options[i]
                        return 3
                    }
                    columnSpacing: 8
                    rowSpacing: 8
                    Repeater {
                    model: [
                        {label: "CALIBRATE", glyph: "◎", start: "calibrate", stop: "stop_calibrate", state: "calibrate", detail: "ALIGN", mode: "dso"},
                        {label: "AUTO FOCUS", glyph: "◉", start: "autofocus", stop: "stop_autofocus", state: "autofocus", detail: "OPTICS", mode: "both"},
                        {label: "INFINITY", glyph: "∞", start: "infinity", stop: "stop_autofocus", state: "infinity", detail: "FOCUS", mode: "both"},
                        {label: "POLAR / EQ", glyph: "⌖", start: "polar", stop: "stop_polar", state: "polar", detail: "ALIGN", mode: "dso"},
                        {label: "POLAR POS", glyph: "⊕", start: "polar_position", stop: "", state: "", detail: "MOUNT"},
                        {label: "LIGHTS", glyph: "✦", start: "lights_on", stop: "lights_off", state: "lights", detail: "CHASSIS"},
                        {label: "INDICATOR", glyph: "◉", start: "indicator_on", stop: "indicator_off", state: "indicator", detail: "CHASSIS"},
                        {label: "PHOTO", glyph: "▣", start: "photo", stop: "", state: "", detail: "CAPTURE", mode: "photo"},
                        {label: "STACK", glyph: "⧉", start: "stack", stop: "stop_astro", state: "imaging", detail: "CAPTURE", mode: "dso"},
                        {label: "GO LIVE", glyph: "▶", start: "go_live", stop: "", state: "", detail: "CAMERA", mode: "photo"},
                        {label: "TRACK", glyph: "⊛", start: "track", stop: "stop_goto", state: "goto", detail: "MOUNT", mode: "dso"},
                        {label: "BURST", glyph: "◫", start: "burst_start", stop: "burst_stop", state: "burst", detail: "CAPTURE", mode: "photo"},
                        {label: "RECORD", glyph: "●", start: "record_start", stop: "record_stop", state: "record", detail: "VIDEO", mode: "photo"},
                        {label: "TIMELAPSE", glyph: "◷", start: "timelapse_start", stop: "timelapse_stop", state: "timelapse", detail: "CAPTURE", mode: "photo"},
                        {label: "REBOOT", glyph: "↻", start: "reboot", stop: "", state: "", detail: "SYSTEM", destructive: true},
                        {label: "POWER", glyph: "⏻", start: "power_down", stop: "", state: "", detail: "SYSTEM", destructive: true}
                    ]
                    delegate: HudCommandPad {
                        id: pad
                        required property var modelData
                        readonly property var t: root.scopeTelemetry
                        readonly property bool trackingPad: modelData.start === "track"
                        readonly property bool trackingNow: trackingPad && !!t.tracking_active
                        readonly property bool slewingNow: trackingPad && root.scopeActivity === "goto"
                        readonly property bool stopping: effectiveOperation !== modelData.start
                        readonly property bool modeAllowed: {
                            if (stopping || !modelData.mode)
                                return true
                            if (modelData.mode === "both")
                                return cameraPanel.photoMode || cameraPanel.dsoMode
                            return modelData.mode === "photo" ? cameraPanel.photoMode : cameraPanel.dsoMode
                        }
                        readonly property bool activeForState: modelData.state === "lights"
                            ? !!backend.selectedDevice.lights_on
                            : modelData.state === "indicator"
                                ? !!backend.selectedDevice.indicator_on
                                : trackingPad
                                    ? (slewingNow || trackingNow)
                                    : modelData.state !== "" && root.scopeActivity === modelData.state
                        readonly property string effectiveOperation: activeForState && modelData.stop !== "" ? modelData.stop : modelData.start
                        readonly property bool isPending: root.scopePending !== "" && (root.scopePending === modelData.start || root.scopePending === modelData.stop)
                        readonly property string padLabel: {
                            if (!trackingPad)
                                return modelData.label
                            if (slewingNow)
                                return "STOP GOTO"
                            if (trackingNow)
                                return "EXIT TRACKING"
                            return "TRACK"
                        }
                        function deviceDetail() {
                            if (trackingPad && trackingNow && !slewingNow)
                                return t.tracking_target ? "TRACKING · " + t.tracking_target : "TRACKING · TAP TO STOP"
                            if (trackingPad && !backend.selectedDevice.location_configured)
                                return "SET LOCATION FIRST"
                            if (trackingPad && backend.previewPlaying)
                                return previewHost.displayWide ? "DOUBLE-CLICK TARGET FIRST" : "USE WIDE VIEW FIRST"
                            if (trackingPad)
                                return "CALIBRATE · CENTRE · TRACK"
                            if (modelData.state === "imaging" && activeForState)
                                return t.capture_text ? "STACK · " + t.capture_text : "STACKING · TAP TO STOP"
                            if (!modeAllowed)
                                return modelData.mode === "both" || cameraPanel.shootingMode === "—"
                                    ? "SELECT PHOTO OR DSO"
                                    : "SWITCH TO " + String(modelData.mode).toUpperCase()
                            if (!activeForState) {
                                if (modelData.state === "autofocus")
                                    return cameraPanel.shootingMode === "—" ? "SELECT PHOTO OR DSO" : cameraPanel.shootingMode + " · OPTICS"
                                if (modelData.state === "infinity")
                                    return cameraPanel.shootingMode === "—" ? "SELECT PHOTO OR DSO" : cameraPanel.shootingMode + " · FOCUS"
                                return modelData.detail
                            }
                            switch (modelData.state) {
                            case "calibrate":
                                return root.scopeActivityDetail ? (root.scopeActivityDetail.indexOf("SOLVE") === 0 ? "SOLVING · " + root.scopeActivityDetail.replace("SOLVE", "PHASE").trim() : root.scopeActivityDetail) : "RUNNING"
                            case "autofocus":
                            case "infinity":
                                return t.focus_text && t.focus_text !== "—" ? "RUNNING · " + t.focus_text : "RUNNING"
                            case "polar":
                                if (t.eq_has_result && !activeForState)
                                    return t.eq_azi_text || "ALIGN"
                                return root.scopeActivityDetail || "RUNNING"
                            case "record":
                                return "REC · " + (root.scopeActivityDetail || "00:00")
                            case "imaging":
                                return t.capture_text ? "STACK · " + t.capture_text : "STACKING"
                            case "lights":
                                return "ON · TAP TO STOP"
                            case "indicator":
                                return "ON · TAP TO STOP"
                            default:
                                return root.scopeActivityDetail ? root.scopeActivityDetail + " · STOP" : "ACTIVE · STOP"
                            }
                        }
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 44
                        Layout.preferredHeight: 58
                        text: padLabel
                        glyph: modelData.glyph
                        detail: deviceDetail()
                        activeState: activeForState
                        pending: isPending
                        destructive: !!modelData.destructive
                        enabled: modelData.start === "go_live"
                            ? modeAllowed && previewHost.previewStartEnabled
                            : modeAllowed && root.commandEnabled(effectiveOperation)
                        onClicked: {
                            if (modelData.start === "go_live") {
                                previewHost.startPreview()
                                return
                            }
                            if (effectiveOperation === "stack") {
                                if (liveExposure.text.trim())
                                    backend.setCameraParam(backend.selectedDeviceId, "exposure", liveExposure.text)
                                if (liveGain.text.trim())
                                    backend.setCameraParam(backend.selectedDeviceId, "gain", liveGain.text)
                                if (liveStackCount.text.trim())
                                    backend.setCameraParam(backend.selectedDeviceId, "count", liveStackCount.text)
                                if (liveFilter.visible && liveFilter.currentText)
                                    backend.setCameraParam(backend.selectedDeviceId, "ir", liveFilter.currentText)
                            }
                            root.requestDeviceAction(effectiveOperation, padLabel)
                        }
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
            settingsKey: "controlRight"
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
                        {label: "STEP", value: Util.sessionStepLabel(backend.currentSession, backend.localNow.epoch_ms) || backend.currentSession.current_step || backend.selectedDevice.status || "—"}
                    ]
                    delegate: RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Text { text: modelData.label; color: Theme.textSecondary; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 72 }
                        Text { text: modelData.value; color: Theme.textPrimary; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
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
                            color: Theme.hsl(0.075, 0.565, 0.090, 0.702)
                            border.color: Theme.outline
                            border.width: 2
                        }
                        Canvas {
                            // bearing ticks around the ring
                            anchors.fill: parent
                            anchors.margins: -10
                            readonly property color majorInk: Theme.accent
                            readonly property color minorInk: Theme.outlineStrong
                            onMajorInkChanged: requestPaint()
                            onMinorInkChanged: requestPaint()
                            onPaint: {
                                const ctx = getContext("2d")
                                ctx.reset()
                                const cx = width / 2, cy = height / 2
                                const rOuter = width / 2 - 1
                                for (let i = 0; i < 36; i++) {
                                    const major = i % 9 === 0
                                    const a = i * Math.PI * 2 / 36
                                    const len = major ? 8 : 4
                                    ctx.strokeStyle = major ? majorInk : minorInk
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
                            color: Theme.outlineStrong
                            opacity: 0.45
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.width - 18
                            height: 2
                            color: Theme.outlineStrong
                            opacity: 0.45
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: analogPad.maxThrow * 2 * analogPad.deadzone
                            height: width
                            radius: width / 2
                            color: Theme.hsl(0.062, 0.488, 0.169)
                            border.color: Theme.outlineStrong
                        }
                        Rectangle {
                            id: analogKnob
                            x: parent.width / 2 - width / 2 + analogPad.stickDx
                            y: parent.height / 2 - height / 2 + analogPad.stickDy
                            width: 28
                            height: 28
                            radius: width / 2
                            color: analogPad.moving ? Theme.accent : Theme.hsl(0.053, 0.503, 0.700)
                            border.color: Theme.hsl(0.026, 1.000, 0.924)
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
                    Text { text: "SPEED"; color: Theme.textSecondary; font.pixelSize: 10 }
                    Slider {
                        id: speedSlider
                        Layout.fillWidth: true
                        enabled: root.motionEnabled
                        from: 0.03
                        to: 1
                        value: 1
                        onMoved: root.joySpeed = value
                        background: Rectangle { x: speedSlider.leftPadding; y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 2; implicitHeight: 4; width: speedSlider.availableWidth; color: Theme.inputBg; Rectangle { width: speedSlider.visualPosition * parent.width; height: parent.height; color: Theme.accent } }
                        handle: Rectangle { x: speedSlider.leftPadding + speedSlider.visualPosition * (speedSlider.availableWidth - 12); y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 6; width: 12; height: 12; radius: 6; color: Theme.accent }
                    }
                }
            }

            HudPanel {
                title: "UP NEXT"
                SplitView.preferredHeight: 110
                SplitView.minimumHeight: 72
                headerExtra: Row {
                    spacing: 4
                    visible: backend.upcomingSessions.length > 0
                    HudButton {
                        text: controlPage.selectedUpcomingCount > 0 && controlPage.selectedUpcomingCount === backend.upcomingSessions.length ? "CLEAR" : "ALL"
                        implicitHeight: 20
                        implicitWidth: 44
                        font.pixelSize: 8
                        leftPadding: 6
                        rightPadding: 6
                        onClicked: {
                            if (controlPage.selectedUpcomingCount > 0 && controlPage.selectedUpcomingCount === backend.upcomingSessions.length)
                                controlPage.selectedUpcomingIds = ({})
                            else
                                controlPage.selectedUpcomingIds = Util.idSetAll(backend.upcomingSessions, true)
                        }
                    }
                    HudButton {
                        text: controlPage.selectedUpcomingCount > 1 ? "EDIT " + controlPage.selectedUpcomingCount : "EDIT"
                        visible: controlPage.selectedUpcomingCount > 1
                        implicitHeight: 20
                        implicitWidth: controlPage.selectedUpcomingCount > 1 ? 64 : 44
                        font.pixelSize: 8
                        leftPadding: 6
                        rightPadding: 6
                        onClicked: sessionDialog.openSelected(Util.itemsByIds(backend.upcomingSessions, controlPage.selectedUpcomingIds))
                    }
                    HudButton {
                        text: controlPage.selectedUpcomingCount > 1 ? "DEL " + controlPage.selectedUpcomingCount : "DELETE"
                        enabled: controlPage.selectedUpcomingCount > 0
                        implicitHeight: 20
                        implicitWidth: controlPage.selectedUpcomingCount > 1 ? 64 : 58
                        font.pixelSize: 8
                        leftPadding: 6
                        rightPadding: 6
                        buttonColor: Theme.fillDanger
                        foregroundColor: Theme.danger
                        onClicked: root.confirmBulkDelete("deleteSessions", controlPage.selectedUpcomingIds, "session")
                    }
                }
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
                            model: controlPage.clusteredUpcoming
                            delegate: Column {
                                id: upcomingWrap
                                required property var modelData
                                required property int index
                                width: ListView.view.width
                                spacing: 0
                                height: (showHeader ? 20 : 0) + 44
                                readonly property bool showHeader: {
                                    if (!modelData.is_grouped)
                                        return false
                                    if (index <= 0)
                                        return true
                                    const prev = controlPage.clusteredUpcoming[index - 1]
                                    return !prev || String(prev.group_key || "") !== String(modelData.group_key || "")
                                }
                                readonly property color groupTone: Util.sessionTone(modelData)
                                opacity: DragCoordinator.active && DragCoordinator.data.id === modelData.id ? 0.35 : 1
                                Item {
                                    width: parent.width
                                    height: upcomingWrap.showHeader ? 20 : 0
                                    visible: upcomingWrap.showHeader
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        spacing: 6
                                        Rectangle {
                                            Layout.preferredWidth: 3
                                            Layout.preferredHeight: 10
                                            Layout.alignment: Qt.AlignVCenter
                                            color: upcomingWrap.groupTone
                                        }
                                        Text {
                                            text: String(upcomingWrap.modelData.group_title || upcomingWrap.modelData.display_title || "").toUpperCase()
                                            color: upcomingWrap.groupTone
                                            font.pixelSize: 8
                                            font.letterSpacing: 1.1
                                            font.bold: true
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Text {
                                            text: Number(upcomingWrap.modelData.pane_count || 0) + "P"
                                            color: Theme.textSecondary
                                            font.pixelSize: 8
                                            font.family: Theme.fontMono
                                            Layout.fillWidth: false
                                        }
                                    }
                                }
                                Rectangle {
                                id: upcomingRow
                                readonly property var modelData: upcomingWrap.modelData
                                width: parent.width
                                height: 44
                                color: modelData.is_grouped ? Util.groupFill(modelData.group_id) : Theme.surfaceHigh
                                border.color: modelData.is_grouped ? Qt.rgba(upcomingWrap.groupTone.r, upcomingWrap.groupTone.g, upcomingWrap.groupTone.b, 0.45) : Theme.outline
                                SessionDragArea {
                                    dragItem: upcomingRow.modelData
                                    onEditRequested: session => sessionDialog.openExisting(session)
                                }
                                HoverHandler { id: upcomingHover }
                                TapHandler {
                                    acceptedButtons: Qt.LeftButton
                                    acceptedModifiers: Qt.ShiftModifier
                                    onTapped: controlPage.selectClick(upcomingRow.modelData.id, true)
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
                                        spineColor: upcomingWrap.groupTone
                                        checked: Util.idSetHas(controlPage.selectedUpcomingIds, upcomingRow.modelData.id)
                                        revealed: upcomingHover.hovered || controlPage.selectedUpcomingCount > 0
                                        onToggled: (shiftHeld) => controlPage.selectClick(upcomingRow.modelData.id, shiftHeld)
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 0
                                        Text { text: modelData.pane_name || modelData.target_name; color: Theme.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Text {
                                            readonly property bool due: {
                                                backend.clockText
                                                const startMs = Number(modelData.start_epoch_ms)
                                                return (isNaN(startMs) ? new Date(modelData.scheduled_start).getTime() : startMs) <= Date.now()
                                            }
                                            text: {
                                                backend.clockText
                                                const startMs = Number(modelData.start_epoch_ms)
                                                const seconds = Math.floor(((isNaN(startMs) ? new Date(modelData.scheduled_start).getTime() : startMs) - Date.now()) / 1000)
                                                return modelData.start_time + " · " + modelData.duration_text + (seconds > 0 ? " · T−" + Util.durationLabel(seconds) : " · DUE")
                                            }
                                            color: due ? Theme.warning : Theme.textSecondary; font.pixelSize: 9
                                        }
                                    }
                                }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: controlPage.openSessionMenu(upcomingRow.modelData)
                                }
                                }
                            }
                        }
                    }
                    EmptyHint { anchors.centerIn: parent; visible: backend.upcomingSessions.length === 0; text: "No upcoming sessions" }
                }
            }

            HudPanel {
                id: logPanel
                readonly property bool compactChrome: width < 420
                title: width < 280 ? "" : "LIVE LOG"
                SplitView.fillHeight: true
                SplitView.minimumHeight: 80
                headerExtra: Row {
                    id: logToolbar
                    spacing: logPanel.compactChrome ? 2 : 3
                    Repeater {
                        model: [
                            {key: "all", label: "ALL", icon: "\uE71D"},
                            {key: "device", label: "DEVICE", icon: "\uE8CD"},
                            {key: "alerts", label: "ALERTS", icon: "\uE7BA"},
                            {key: "debug", label: "DEBUG", icon: "\uE90F"}
                        ]
                        delegate: Rectangle {
                            id: pill
                            required property var modelData
                            readonly property bool active: backend.logFilter === modelData.key
                            readonly property int badge: modelData.key === "alerts" ? backend.logWarningCount + backend.logErrorCount : 0
                            width: logPanel.compactChrome ? 22 : pillRow.implicitWidth + 12
                            height: 20
                            radius: 3
                            color: active ? (modelData.key === "debug" ? Theme.fillSuccess : Theme.fillActive) : pillHover.hovered ? Theme.hsl(0.054, 0.526, 0.149) : "transparent"
                            border.color: active ? (modelData.key === "debug" ? Theme.success : Theme.accent) : Theme.outlineSoft
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row {
                                id: pillRow
                                anchors.centerIn: parent
                                spacing: 4
                                Text {
                                    text: logPanel.compactChrome ? pill.modelData.icon : pill.modelData.label
                                    color: pill.active ? (pill.modelData.key === "debug" ? Theme.success : Theme.accent) : Theme.textSecondary
                                    font.family: logPanel.compactChrome ? Theme.fontIcon : Theme.fontUi
                                    font.pixelSize: logPanel.compactChrome ? 11 : 8
                                    font.bold: !logPanel.compactChrome
                                    font.letterSpacing: logPanel.compactChrome ? 0 : 1
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                                Rectangle {
                                    visible: pill.badge > 0 && !logPanel.compactChrome
                                    width: badgeText.implicitWidth + 6; height: 12; radius: 6
                                    color: backend.logErrorCount > 0 ? Theme.danger : Theme.warning
                                    anchors.verticalCenter: parent.verticalCenter
                                    Text { id: badgeText; anchors.centerIn: parent; text: pill.badge > 99 ? "99+" : pill.badge; color: Theme.windowBase; font.pixelSize: 8; font.bold: true }
                                }
                            }
                            Rectangle {
                                visible: pill.badge > 0 && logPanel.compactChrome
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.rightMargin: -3
                                anchors.topMargin: -3
                                width: Math.max(12, compactBadgeText.implicitWidth + 4)
                                height: 12
                                radius: 6
                                z: 1
                                color: backend.logErrorCount > 0 ? Theme.danger : Theme.warning
                                Text { id: compactBadgeText; anchors.centerIn: parent; text: pill.badge > 99 ? "99+" : pill.badge; color: Theme.windowBase; font.pixelSize: 7; font.bold: true }
                            }
                            HoverHandler { id: pillHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: backend.setLogFilter(pill.modelData.key) }
                            ToolTip.visible: pillHover.hovered && logPanel.compactChrome
                            ToolTip.delay: 400
                            ToolTip.text: pill.modelData.label
                        }
                    }
                    Rectangle { width: 1; height: 16; color: Theme.outline; anchors.verticalCenter: parent.verticalCenter }
                    HudButton {
                        text: logPanel.compactChrome ? "\uE8C8" : "COPY"
                        implicitHeight: 20
                        implicitWidth: logPanel.compactChrome ? 22 : 46
                        font.family: logPanel.compactChrome ? Theme.fontIcon : Theme.fontUi
                        font.pixelSize: logPanel.compactChrome ? 11 : 8
                        font.letterSpacing: logPanel.compactChrome ? 0 : 1
                        leftPadding: logPanel.compactChrome ? 0 : 6
                        rightPadding: logPanel.compactChrome ? 0 : 6
                        busyText: logPanel.compactChrome ? "\uE73E" : "COPIED"
                        busyMs: 900
                        enabled: logList.count > 0
                        buttonColor: "transparent"
                        foregroundColor: Theme.textSecondary
                        ToolTip.visible: hovered && logPanel.compactChrome
                        ToolTip.delay: 400
                        ToolTip.text: "COPY"
                        onClicked: backend.copyText(root.allLogText())
                    }
                    HudButton {
                        text: logPanel.compactChrome ? "\uE74D" : "CLEAR"
                        implicitHeight: 20
                        implicitWidth: logPanel.compactChrome ? 22 : 50
                        font.family: logPanel.compactChrome ? Theme.fontIcon : Theme.fontUi
                        font.pixelSize: logPanel.compactChrome ? 11 : 8
                        font.letterSpacing: logPanel.compactChrome ? 0 : 1
                        leftPadding: logPanel.compactChrome ? 0 : 6
                        rightPadding: logPanel.compactChrome ? 0 : 6
                        enabled: logList.count > 0
                        buttonColor: "transparent"
                        foregroundColor: Theme.textSecondary
                        ToolTip.visible: hovered && logPanel.compactChrome
                        ToolTip.delay: 400
                        ToolTip.text: "CLEAR"
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
                        color: Theme.hsl(0.019, 0.674, 0.169, 0.878)
                        border.color: Theme.accent
                        visible: !logList.followTail && logList.count > 0
                        scale: visible ? 1 : 0.8
                        Behavior on scale { NumberAnimation { duration: 140 } }
                        Row {
                            id: newPillRow
                            anchors.centerIn: parent
                            spacing: 6
                            Text { text: "↓"; color: Theme.accent; font.pixelSize: 11; font.bold: true; anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                text: logList.unseen > 0 ? logList.unseen + " NEW" : "FOLLOW"
                                color: Theme.textPrimary; font.pixelSize: 9; font.bold: true; font.letterSpacing: 1
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
                            contentItem: Rectangle { implicitWidth: 3; radius: 1.5; color: Theme.outline; opacity: logScroll.active ? 0.9 : 0.4 }
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
                            readonly property color tone: Util.toneForLevel(level)
                            readonly property bool quiet: level === "SDK" || level === "DEBUG" || level === "INFO"
                            readonly property string lineText: time + "  " + level + "  [" + device + "]  " + message + (count > 1 ? "  (×" + count + ")" : "")
                            width: ListView.view ? ListView.view.width : 0
                            height: 18
                            color: rowHover.hovered ? Theme.hsl(0.057, 0.548, 0.122, 0.102) : (index % 2 === 0 ? "transparent" : Theme.hsl(0.070, 0.524, 0.082, 0.047))
                            Rectangle {
                                x: 0; y: 2
                                width: 2
                                height: parent.height - 4
                                radius: 1
                                color: logRow.quiet ? Theme.outline : logRow.tone
                                opacity: logRow.level === "SDK" || logRow.level === "DEBUG" ? 0.45 : 1
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 7
                                anchors.rightMargin: 6
                                spacing: 6
                                Text {
                                    text: logRow.time
                                    color: Theme.muted
                                    font.family: Theme.fontMono
                                    font.pixelSize: 9
                                    Layout.preferredWidth: 50
                                }
                                Text {
                                    text: logRow.glyph
                                    color: logRow.quiet && logRow.level !== "INFO" ? Theme.muted : logRow.tone
                                    font.pixelSize: 9
                                    font.bold: true
                                    Layout.preferredWidth: 10
                                    horizontalAlignment: Text.AlignHCenter
                                }
                                Text {
                                    visible: backend.devices.length > 1
                                    text: logRow.device
                                    color: Theme.textSecondary
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                    Layout.maximumWidth: 62
                                }
                                Text {
                                    id: logText
                                    text: logRow.message
                                    color: logRow.level === "SDK" || logRow.level === "DEBUG" ? Theme.muted : logRow.level === "INFO" ? Theme.hsl(0.033, 0.426, 0.802) : logRow.tone
                                    font.family: Theme.fontMono
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
    SessionContextMenu {
        id: upcomingMenu
        sessionData: controlPage.contextSession
        selectionItems: backend.upcomingSessions
        selectedMap: controlPage.selectedUpcomingIds
        onEditRequested: session => sessionDialog.openExisting(session)
        onEditSelectedRequested: sessionDialog.openSelected(Util.itemsByIds(backend.upcomingSessions, controlPage.selectedUpcomingIds))
        onSelectAllRequested: controlPage.selectedUpcomingIds = Util.idSetAll(backend.upcomingSessions, true)
        onUnselectAllRequested: {
            controlPage.selectedUpcomingIds = ({})
            controlPage.selectionAnchorId = ""
        }
    }
}
