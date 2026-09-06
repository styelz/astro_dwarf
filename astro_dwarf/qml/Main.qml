import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia
import QtQuick.Window
import QtCore

ApplicationWindow {
    id: root
    width: 1480
    height: 920
    minimumWidth: 1180
    minimumHeight: 760
    visible: true
    title: "Astro Dwarf"
    color: "#05080F"
    font.family: "Segoe UI"
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowSystemMenuHint
    property bool customMaximized: false
    property rect restoreGeometry
    property int workX: 0
    property int workY: 0
    property int workW: 0
    property int workH: 0
    readonly property bool windowMaximized: customMaximized || visibility === Window.Maximized

    function dragWindow() {
        if (!root.windowMaximized)
            root.startSystemMove()
    }

    function toggleMaximized() {
        if (root.visibility === Window.Maximized) {
            root.showNormal()
            root.customMaximized = false
            return
        }
        if (root.customMaximized) {
            root.customMaximized = false
            root.x = root.restoreGeometry.x
            root.y = root.restoreGeometry.y
            root.width = root.restoreGeometry.width
            root.height = root.restoreGeometry.height
            return
        }
        root.restoreGeometry = Qt.rect(root.x, root.y, root.width, root.height)
        root.customMaximized = true
        root.x = root.workW ? root.workX : shell.workX
        root.y = root.workW ? root.workY : shell.workY
        root.width = root.workW ? root.workW : shell.workW
        root.height = root.workW ? root.workH : shell.workH
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
    property int currentPage: 0
    property real joySpeed: 1
    readonly property bool targetLocked: backend.selectedDevice.connected && backend.currentSession.status === "running"
    readonly property bool dataPage: currentPage !== 0

    function statusColor(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return root.accent
        case "error": return root.danger
        case "done": return root.success
        case "skipped": return root.textSecondary
        default: return root.textPrimary
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
    function requestDeviceAction(operation, label) {
        if (operation === "reboot" || operation === "power_down") {
            confirmDialog.operation = operation
            confirmDialog.summary = "Run " + label + " on " + (backend.selectedDevice.name || "this telescope") + "?"
            confirmDialog.open()
            return
        }
        backend.deviceAction(backend.selectedDeviceId, operation)
    }

    function asset(name) { return Qt.resolvedUrl("assets/" + name) }
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

    component HudPanel: Item {
        id: panel
        property alias title: heading.text
        property color fill: "#B3070D16"
        default property alias contents: body.data
        implicitWidth: 240
        implicitHeight: body.implicitHeight + 24
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
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }
        ColumnLayout {
            id: body
            anchors.fill: parent
            anchors.margins: 12
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
        }
    }

    component HudButton: Button {
        id: hudBtn
        property color buttonColor: root.surfaceHigh
        property color foregroundColor: root.textPrimary
        font.pixelSize: 12
        font.letterSpacing: 0.6
        leftPadding: 12
        rightPadding: 12
        implicitHeight: 34
        background: Rectangle {
            color: !hudBtn.enabled ? "#0A1018" : hudBtn.down ? Qt.darker(hudBtn.buttonColor, 1.2) : hudBtn.hovered ? Qt.lighter(hudBtn.buttonColor, 1.18) : hudBtn.buttonColor
            border.color: hudBtn.hovered || hudBtn.down ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
        contentItem: Text {
            text: hudBtn.text
            color: hudBtn.enabled ? hudBtn.foregroundColor : root.textSecondary
            font: hudBtn.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component ChromeButton: Item {
        id: chrome
        property string glyph: ""
        property bool danger: false
        signal clicked()
        implicitWidth: 36
        implicitHeight: 28
        Rectangle {
            anchors.fill: parent
            color: area.containsMouse ? (chrome.danger ? "#C8A01828" : "#3312E8FF") : "transparent"
            border.color: area.containsMouse ? (chrome.danger ? root.danger : root.accent) : root.outline
            border.width: 1
            radius: 2
        }
        Text {
            anchors.centerIn: parent
            text: chrome.glyph
            color: chrome.danger && area.containsMouse ? root.danger : (area.containsMouse ? root.accent : root.textSecondary)
            font.pixelSize: 13
            font.bold: true
        }
        MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: chrome.clicked()
        }
    }

    component EdgeResize: MouseArea {
        required property int edges
        required property int cursor
        cursorShape: cursor
        visible: !root.windowMaximized
        hoverEnabled: true
        onPressed: root.startSystemResize(edges)
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
        }
    }

    component HudField: TextField {
        id: field
        color: root.textPrimary
        placeholderTextColor: root.textSecondary
        selectedTextColor: "#041018"
        selectionColor: root.accent
        font.pixelSize: 13
        leftPadding: 10
        rightPadding: 10
        implicitHeight: 34
        background: Rectangle {
            color: "#0A1524"
            border.color: field.activeFocus ? root.accent : root.outline
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
        background: Rectangle {
            color: "#0A1524"
            border.color: combo.hovered || combo.down ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
        contentItem: Text {
            leftPadding: 10
            rightPadding: 22
            text: combo.displayText
            color: root.textPrimary
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            text: "▾"
            color: root.accent
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

    component EmptyHint: Text {
        color: root.textSecondary
        font.pixelSize: 13
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
    }

    Item {
        id: shell
        anchors.fill: parent
        readonly property int workX: Screen.virtualX
        readonly property int workY: Screen.virtualY
        readonly property int workW: Screen.desktopAvailableWidth
        readonly property int workH: Screen.desktopAvailableHeight
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
            MouseArea {
                id: topResize
                z: 4
                height: 5
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.rightMargin: 128
                anchors.top: parent.top
                cursorShape: Qt.SizeVerCursor
                visible: !root.windowMaximized
                onPressed: root.startSystemResize(Qt.TopEdge)
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
                        Text { text: "OBSERVATORY COMMAND"; color: root.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4 }
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
                    buttonColor: backend.selectedDevice.connected ? "#143028" : "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: backend.selectedDevice.connected
                        ? backend.disconnectDevice(backend.selectedDeviceId)
                        : backend.connectDevice(backend.selectedDeviceId)
                }
                HudButton {
                    text: backend.schedulerEnabled ? "SCHEDULER ON" : "SCHEDULER OFF"
                    buttonColor: backend.schedulerEnabled ? "#143028" : root.surfaceHigh
                    foregroundColor: backend.schedulerEnabled ? root.success : root.textPrimary
                    onClicked: backend.setSchedulerEnabled(!backend.schedulerEnabled)
                }
                HudButton { text: "STOP ALL"; buttonColor: "#3A1218"; foregroundColor: root.danger; onClicked: backend.stopDevice(backend.selectedDeviceId) }
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Column {
                    Text { text: backend.selectedDevice.status || "OFFLINE"; color: backend.selectedDevice.connected ? root.success : root.textSecondary; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignRight; width: 160 }
                    Text { text: (backend.selectedDevice.name || "No device") + " · " + (backend.selectedDevice.model || ""); color: root.textSecondary; font.pixelSize: 10; horizontalAlignment: Text.AlignRight; width: 160; elide: Text.ElideRight }
                }
                Text { text: backend.clockText; color: root.accent; font.pixelSize: 22; font.family: "Cascadia Mono"; font.letterSpacing: 1 }
                Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 12; Layout.bottomMargin: 12; color: root.outline }
                Row {
                    id: windowControls
                    z: 5
                    spacing: 6
                    Layout.alignment: Qt.AlignVCenter
                    ChromeButton { glyph: "–"; onClicked: root.showMinimized() }
                    ChromeButton { glyph: root.windowMaximized ? "❐" : "□"; onClicked: root.toggleMaximized() }
                    ChromeButton { glyph: "✕"; danger: true; onClicked: root.close() }
                }
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.preferredHeight: backend.devices.length > 1 ? 64 : 0
            Layout.maximumHeight: backend.devices.length > 1 ? 64 : 0
            Layout.fillHeight: false
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: backend.devices.length > 1 ? 8 : 0
            visible: backend.devices.length > 1
            orientation: ListView.Horizontal
            spacing: 8
            clip: true
            model: backend.devices
            delegate: HudPanel {
                required property var modelData
                width: 210
                height: 56
                fill: modelData.id === backend.selectedDeviceId ? "#C0123C52" : "#99070D16"
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    RowLayout {
                        anchors.fill: parent
                        spacing: 8
                        Rectangle { width: 4; Layout.fillHeight: true; color: modelData.color }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: modelData.name; color: root.textPrimary; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: modelData.model + "  ·  " + modelData.status; color: root.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        Rectangle {
                            width: 8; height: 8; radius: 4
                            color: modelData.connected ? root.success : (modelData.demo_mode ? root.warning : "#526077")
                        }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: backend.selectDevice(modelData.id) }
                }
            }
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
                            SplitView.preferredHeight: 168
                            SplitView.minimumHeight: 96
                            Image {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                source: root.asset("hud-radar.png")
                                fillMode: Image.PreserveAspectFit
                            }
                            Text {
                                text: backend.selectedDevice.connected ? "SCOPE ONLINE" : (backend.selectedDevice.demo_mode ? "DEMO STANDBY" : "LINK DOWN")
                                color: backend.selectedDevice.connected ? root.success : root.warning
                                font.pixelSize: 11
                                font.bold: true
                                Layout.fillWidth: true
                            }
                        }

                        HudPanel {
                            title: "TARGET"
                            SplitView.preferredHeight: 148
                            SplitView.minimumHeight: 88
                            Text {
                                text: backend.currentSession.target_name || (backend.selectedDevice.connected ? "No active lock" : "No telescope link")
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
                            Text { text: backend.currentSession.current_step || (backend.selectedDevice.connected ? "Telescope ready" : "Connect to acquire a lock"); color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Text { text: backend.currentSession.duration_text ? "PLANNED  " + backend.currentSession.duration_text : "WAITING FOR SCHEDULE"; color: root.accent; font.pixelSize: 11 }
                            ProgressBar {
                                id: sessionBar
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: backend.sessionProgress
                                background: Rectangle { implicitHeight: 8; color: "#0A1524"; border.color: root.outline }
                                contentItem: Rectangle { width: sessionBar.visualPosition * parent.width; height: parent.height; color: root.accent }
                            }
                        }

                        Rectangle {
                            SplitView.preferredHeight: 48
                            SplitView.minimumHeight: 40
                            SplitView.maximumHeight: 64
                            color: root.targetLocked ? "#C0143C28" : (backend.selectedDevice.connected ? "#C0123C52" : "#C03A1218")
                            border.color: root.targetLocked ? root.success : (backend.selectedDevice.connected ? root.accent : root.danger)
                            Text {
                                anchors.centerIn: parent
                                text: root.targetLocked ? "TARGET LOCKED" : (backend.selectedDevice.connected ? "NO TARGET LOCK" : "LINK DOWN")
                                color: root.targetLocked ? root.success : (backend.selectedDevice.connected ? root.accent : root.danger)
                                font.bold: true
                                font.letterSpacing: 2
                            }
                        }

                        HudPanel {
                            title: "CAMERA"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 140
                            FieldLabel { text: "FOCUS" }
                            RowLayout {
                                Layout.fillWidth: true
                                HudButton { text: "NEAR"; Layout.fillWidth: true; onClicked: backend.manualFocus(backend.selectedDeviceId, 1) }
                                HudButton { text: "FAR"; Layout.fillWidth: true; onClicked: backend.manualFocus(backend.selectedDeviceId, 0) }
                            }
                            FieldLabel { text: "FILTER" }
                            HudCombo {
                                id: liveFilter
                                Layout.fillWidth: true
                                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                                onActivated: backend.setCameraParam(backend.selectedDeviceId, "ir", currentText)
                            }
                            FieldLabel { text: "CAMERA" }
                            HudCombo {
                                id: liveCamera
                                Layout.fillWidth: true
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
                                    placeholderText: "sec"
                                    text: "15"
                                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "exposure", text)
                                }
                                HudField {
                                    id: liveGain
                                    Layout.fillWidth: true
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
                            SplitView.minimumHeight: 180
                            fill: "#E005070B"
                            Item {
                                id: previewHost
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                property string statusText: backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"

                                function startPreview() {
                                    if (!backend.selectedDevice.connected) {
                                        statusText = "Connect a telescope to start the stream"
                                        backend.uiLog("warning", "Preview needs an active telescope connection")
                                        return
                                    }
                                    statusText = "Opening live camera…"
                                    backend.startPreview(backend.selectedDeviceId)
                                    const url = backend.videoUrl
                                    player.stop()
                                    player.source = url
                                    statusText = "Connecting  " + url
                                    previewStartTimer.restart()
                                }

                                function stopPreview() {
                                    previewStartTimer.stop()
                                    player.stop()
                                    statusText = backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"
                                }

                                Timer {
                                    id: previewStartTimer
                                    interval: 350
                                    onTriggered: player.play()
                                }
                                Connections {
                                    target: backend
                                    function onSelectedDeviceChanged() { previewHost.stopPreview() }
                                }

                                MediaPlayer {
                                    id: player
                                    videoOutput: videoOutput
                                    audioOutput: AudioOutput { muted: true }
                                    onPlaybackStateChanged: {
                                        if (playbackState === MediaPlayer.PlayingState)
                                            previewHost.statusText = backend.videoUrl
                                    }
                                    onErrorOccurred: function(error, errorString) {
                                        previewHost.statusText = errorString || "Preview failed"
                                        backend.uiLog("error", errorString || "Video preview failed")
                                    }
                                    onMediaStatusChanged: {
                                        if (mediaStatus === MediaPlayer.Loading)
                                            previewHost.statusText = "Loading stream…"
                                        else if (mediaStatus === MediaPlayer.InvalidMedia)
                                            previewHost.statusText = "Stream not available at " + backend.videoUrl
                                    }
                                }
                                VideoOutput {
                                    id: videoOutput
                                    anchors.fill: parent
                                    fillMode: VideoOutput.PreserveAspectFit
                                }
                                Image {
                                    anchors.fill: parent
                                    visible: player.playbackState !== MediaPlayer.PlayingState
                                    source: root.asset("hud-telescope.png")
                                    fillMode: Image.PreserveAspectFit
                                    opacity: 0.18
                                }
                                Canvas {
                                    anchors.fill: parent
                                    opacity: 0.9
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const cx = width / 2, cy = height / 2, m = 18
                                        ctx.strokeStyle = "#88E8FFFF"
                                        ctx.lineWidth = 1.2
                                        ctx.beginPath()
                                        ctx.moveTo(cx - 80, cy); ctx.lineTo(cx - 16, cy)
                                        ctx.moveTo(cx + 16, cy); ctx.lineTo(cx + 80, cy)
                                        ctx.moveTo(cx, cy - 80); ctx.lineTo(cx, cy - 16)
                                        ctx.moveTo(cx, cy + 16); ctx.lineTo(cx, cy + 80)
                                        ctx.stroke()
                                        ctx.beginPath(); ctx.arc(cx, cy, 52, 0, Math.PI * 2); ctx.stroke()
                                        ctx.beginPath()
                                        ctx.moveTo(m, m + 24); ctx.lineTo(m, m); ctx.lineTo(m + 24, m)
                                        ctx.moveTo(width - m - 24, m); ctx.lineTo(width - m, m); ctx.lineTo(width - m, m + 24)
                                        ctx.moveTo(m, height - m - 24); ctx.lineTo(m, height - m); ctx.lineTo(m + 24, height - m)
                                        ctx.moveTo(width - m - 24, height - m); ctx.lineTo(width - m, height - m); ctx.lineTo(width - m, height - m - 24)
                                        ctx.stroke()
                                    }
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                }
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    visible: player.playbackState !== MediaPlayer.PlayingState
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
                                        buttonColor: "#0E3A48"
                                        foregroundColor: root.accent
                                        onClicked: previewHost.startPreview()
                                    }
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    width: 96
                                    height: 28
                                    color: "#C0101520"
                                    border.color: player.playbackState === MediaPlayer.PlayingState ? root.success : root.outline
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 7
                                        Rectangle { width: 8; height: 8; radius: 4; color: player.playbackState === MediaPlayer.PlayingState ? root.danger : "#64748B"; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: player.playbackState === MediaPlayer.PlayingState ? "LIVE" : "STANDBY"; color: root.textPrimary; font.pixelSize: 11; font.bold: true }
                                    }
                                }
                                HudButton {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    visible: player.playbackState === MediaPlayer.PlayingState
                                    text: "STOP PREVIEW"
                                    onClicked: previewHost.stopPreview()
                                }
                            }
                        }

                        HudPanel {
                            title: "COMMANDS"
                            SplitView.preferredHeight: 210
                            SplitView.minimumHeight: 120
                            Repeater {
                                model: [
                                    {label: "ALIGN", items: [["CALIBRATE", "calibrate"], ["AUTO FOCUS", "autofocus"], ["INFINITY", "infinity"], ["POLAR / EQ", "polar"]]},
                                    {label: "LIVE", items: [["LIGHTS ON", "lights_on"], ["LIGHTS OFF", "lights_off"], ["GO LIVE", "go_live"], ["STOP GOTO", "stop_goto"]]},
                                    {label: "CAPTURE", items: [["BURST", "burst_start"], ["STOP BURST", "burst_stop"], ["RECORD", "record_start"], ["STOP REC", "record_stop"], ["TIMELAPSE", "timelapse_start"], ["STOP TL", "timelapse_stop"]]},
                                    {label: "SYSTEM", items: [["REBOOT", "reboot"], ["POWER DOWN", "power_down"]]}
                                ]
                                delegate: ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text { text: modelData.label; color: root.textSecondary; font.pixelSize: 9; font.letterSpacing: 1.2; font.bold: true }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Repeater {
                                            model: modelData.items
                                            delegate: HudButton {
                                                required property var modelData
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 26
                                                leftPadding: 4
                                                rightPadding: 4
                                                font.pixelSize: 9
                                                text: modelData[0]
                                                buttonColor: (modelData[1] === "reboot" || modelData[1] === "power_down") ? "#3A1218" : root.surfaceHigh
                                                foregroundColor: (modelData[1] === "reboot" || modelData[1] === "power_down") ? root.danger : root.textPrimary
                                                onClicked: root.requestDeviceAction(modelData[1], modelData[0])
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
                            SplitView.preferredHeight: 132
                            SplitView.minimumHeight: 80
                            Repeater {
                                model: [
                                    {label: "LINK", value: backend.selectedDevice.connected ? "Connected" : (backend.selectedDevice.demo_mode ? "Demo" : "Offline")},
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
                            SplitView.minimumHeight: 150
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 118
                                Image { anchors.fill: parent; source: root.asset("hud-dpad.png"); fillMode: Image.PreserveAspectFit }
                                Grid {
                                    anchors.centerIn: parent
                                    columns: 3
                                    spacing: 6
                                    Repeater {
                                        model: [
                                            [135, "↖"], [90, "↑"], [45, "↗"],
                                            [180, "←"], [-1, "■"], [0, "→"],
                                            [225, "↙"], [270, "↓"], [315, "↘"]
                                        ]
                                        delegate: Item {
                                            required property var modelData
                                            width: 34
                                            height: 34
                                            MouseArea {
                                                anchors.fill: parent
                                                onPressed: modelData[0] < 0 ? backend.deviceAction(backend.selectedDeviceId, "stop_motors") : backend.joystick(backend.selectedDeviceId, modelData[0], root.joySpeed)
                                                onReleased: backend.deviceAction(backend.selectedDeviceId, "stop_motors")
                                            }
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "SPEED"; color: root.textSecondary; font.pixelSize: 10 }
                                Slider {
                                    id: speedSlider
                                    Layout.fillWidth: true
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
                                ListView {
                                    id: upcomingList
                                    anchors.fill: parent
                                    clip: true
                                    spacing: 4
                                    model: backend.upcomingSessions
                                    delegate: Rectangle {
                                        required property var modelData
                                        width: ListView.view.width
                                        height: 36
                                        color: "#122033"
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 6
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 0
                                                Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                Text { text: modelData.start_time + " · " + modelData.duration_text; color: root.textSecondary; font.pixelSize: 10 }
                                            }
                                        }
                                    }
                                }
                                EmptyHint { anchors.centerIn: parent; visible: backend.upcomingSessions.length === 0; text: "No upcoming sessions" }
                            }
                        }

                        HudPanel {
                            title: "LIVE LOG"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 80
                            ListView {
                                id: logList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                spacing: 2
                                model: backend.logs
                                onCountChanged: positionViewAtEnd()
                                delegate: Text {
                                    required property var modelData
                                    width: ListView.view.width
                                    text: modelData.time + "  [" + modelData.device + "]  " + modelData.message
                                    color: modelData.level === "ERROR" ? root.danger : modelData.level === "SUCCESS" ? root.success : "#B7D4E2"
                                    font.family: "Cascadia Mono"
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
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
                HudSplitView {
                    id: calendarSplit
                    anchors.fill: parent
                    orientation: Qt.Horizontal
                    ColumnLayout {
                        SplitView.fillWidth: true
                        SplitView.minimumWidth: 420
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: Qt.formatDate(calendarPage.shownMonth, "MMMM yyyy").toUpperCase(); color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2; Layout.fillWidth: true }
                            HudButton { text: "‹"; implicitWidth: 40; onClicked: calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() - 1, 1) }
                            HudButton { text: "TODAY"; onClicked: { calendarPage.shownMonth = new Date(); calendarPage.selectedDate = new Date() } }
                            HudButton { text: "›"; implicitWidth: 40; onClicked: calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() + 1, 1) }
                            HudButton { text: "+ NEW SESSION"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate)) }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Repeater { model: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]; Text { required property string modelData; text: modelData; color: root.accent; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } }
                        }
                        GridLayout {
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
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    color: key === calendarPage.dateKey(calendarPage.selectedDate) ? "#C0123C52" : "#99070D16"
                                    border.color: dropArea.containsDrag ? root.accent : root.outline
                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 3
                                        Text { text: dayCell.cellDate.getDate(); color: dayCell.cellDate.getMonth() === calendarPage.shownMonth.getMonth() ? root.textPrimary : "#3E5A6A"; font.pixelSize: 11 }
                                        Repeater {
                                            model: dayCell.daySessions.slice(0, 3)
                                            delegate: Rectangle {
                                                id: sessionChip
                                                required property var modelData
                                                property string sessionId: modelData.id
                                                width: parent.width
                                                height: 22
                                                color: root.statusFill(modelData.status)
                                                border.color: root.statusColor(modelData.status)
                                                Text { anchors.fill: parent; anchors.margins: 4; text: calendarPage.chipText(modelData); color: root.textPrimary; font.pixelSize: 9; elide: Text.ElideRight }
                                                Drag.active: dragHandler.active
                                                Drag.source: sessionChip
                                                Drag.hotSpot.x: width / 2
                                                Drag.hotSpot.y: height / 2
                                                DragHandler { id: dragHandler }
                                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: sessionMenu.open() }
                                                Menu {
                                                    id: sessionMenu
                                                    palette.window: "#0B1520"
                                                    palette.windowText: root.textPrimary
                                                    palette.highlightedText: root.accent
                                                    MenuItem { text: "Edit"; enabled: sessionChip.modelData.status !== "running"; onTriggered: sessionDialog.openExisting(sessionChip.modelData) }
                                                    MenuItem { text: "Run now"; enabled: sessionChip.modelData.status !== "running"; onTriggered: backend.runNow(sessionChip.sessionId) }
                                                    MenuItem { text: "Skip"; enabled: sessionChip.modelData.status === "planned"; onTriggered: backend.skipSession(sessionChip.sessionId) }
                                                    MenuItem { text: "Duplicate"; onTriggered: backend.duplicateSession(sessionChip.sessionId) }
                                                    MenuSeparator {}
                                                    MenuItem { text: "Delete"; enabled: sessionChip.modelData.status !== "running"; onTriggered: backend.deleteSession(sessionChip.sessionId) }
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
                                    DropArea {
                                        id: dropArea
                                        anchors.fill: parent
                                        onDropped: drop => backend.moveSessionDate(drop.source.sessionId, dayCell.key)
                                    }
                                }
                            }
                        }
                    }
                    HudPanel {
                        title: Qt.formatDate(calendarPage.selectedDate, "ddd d MMM").toUpperCase()
                        SplitView.preferredWidth: 312
                        SplitView.minimumWidth: 220
                        Text {
                            text: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length + " session(s) this night"
                            color: root.textSecondary
                            font.pixelSize: 11
                        }
                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            ListView {
                                anchors.fill: parent
                                clip: true
                                spacing: 6
                                model: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
                                delegate: Rectangle {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 64
                                    color: "#122033"
                                    border.color: root.statusColor(modelData.status)
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 2
                                        Text { text: modelData.start_time + "  " + modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Text { text: modelData.subtitle + " · " + modelData.duration_text; color: root.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                        RowLayout {
                                            HudButton { text: "EDIT"; implicitHeight: 24; enabled: modelData.status !== "running"; onClicked: sessionDialog.openExisting(modelData) }
                                            HudButton { text: "RUN"; implicitHeight: 24; enabled: modelData.status !== "running"; onClicked: backend.runNow(modelData.id) }
                                        }
                                    }
                                }
                            }
                            EmptyHint {
                                anchors.centerIn: parent
                                visible: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length === 0
                                text: "No sessions this observing night"
                            }
                        }
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 10
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "SESSIONS"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                            Text { text: "Templates, scheduled nights, Stellarium and Telescopius import"; color: root.textSecondary }
                        }
                        HudButton { text: "IMPORT STELLARIUM"; onClicked: backend.importStellarium() }
                        HudButton { text: "IMPORT TELESCOPIUS"; onClicked: telescopiusDialog.open() }
                        HudButton { text: "+ MANUAL SESSION"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(Qt.formatDate(new Date(), "yyyy-MM-dd")) }
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
                        Item {
                            EmptyHint { visible: backend.sessions.length === 0; text: "No scheduled sessions yet. Create one or import a target list."; anchors.centerIn: parent }
                            ListView {
                                anchors.fill: parent
                                clip: true
                                spacing: 8
                                model: backend.sessions
                                delegate: HudPanel {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 84
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Rectangle { width: 4; Layout.fillHeight: true; color: modelData.device_color || root.accent }
                                        ColumnLayout {
                                            Layout.preferredWidth: 280
                                            Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Text { text: modelData.subtitle; color: root.textSecondary; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true; visible: modelData.subtitle !== modelData.target_name }
                                        }
                                        Text { text: modelData.start_date + "  " + modelData.start_time; color: root.textPrimary; Layout.preferredWidth: 150 }
                                        Text { text: modelData.device_name; color: root.accent; Layout.preferredWidth: 120; elide: Text.ElideRight }
                                        Text { text: modelData.duration_text; color: root.textSecondary; Layout.preferredWidth: 80 }
                                        Rectangle {
                                            width: 86; height: 24; color: root.statusFill(modelData.status); border.color: root.statusColor(modelData.status)
                                            Text { anchors.centerIn: parent; text: modelData.status.toUpperCase(); color: root.statusColor(modelData.status); font.pixelSize: 9; font.bold: true }
                                        }
                                        HudButton { text: "EDIT"; enabled: modelData.status !== "running"; onClicked: sessionDialog.openExisting(modelData) }
                                        HudButton { text: "RUN"; enabled: modelData.status !== "running"; onClicked: backend.runNow(modelData.id) }
                                    }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: scheduledMenu.popup() }
                                    Menu {
                                        id: scheduledMenu
                                        palette.window: "#0B1520"
                                        palette.windowText: root.textPrimary
                                        MenuItem { text: "Edit"; enabled: modelData.status !== "running"; onTriggered: sessionDialog.openExisting(modelData) }
                                        MenuItem { text: "Run now"; enabled: modelData.status !== "running"; onTriggered: backend.runNow(modelData.id) }
                                        MenuItem { text: "Skip"; enabled: modelData.status === "planned"; onTriggered: backend.skipSession(modelData.id) }
                                        MenuItem { text: "Duplicate"; onTriggered: backend.duplicateSession(modelData.id) }
                                        MenuItem { text: "Delete"; enabled: modelData.status !== "running"; onTriggered: backend.deleteSession(modelData.id) }
                                    }
                                }
                            }
                        }
                        Item {
                            EmptyHint { anchors.centerIn: parent; visible: backend.templates.length === 0; text: "No templates yet. Save a session as a reusable template, or import Stellarium / Telescopius." }
                            GridView {
                                anchors.fill: parent
                                clip: true
                                cellWidth: 340
                                cellHeight: 170
                                model: backend.templates
                                delegate: HudPanel {
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
                                        HudButton { text: "SCHEDULE"; Layout.fillWidth: true; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.scheduleTemplate(modelData.id) }
                                        HudButton { text: "DELETE"; onClicked: backend.deleteTemplate(modelData.id) }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 10
                    Text { text: "HISTORY"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                    Text { text: "Permanent record of planned and actual telescope work"; color: root.textSecondary }
                    RowLayout {
                        Layout.fillWidth: true
                        Repeater {
                            model: [
                                ["SESSIONS", backend.history.length],
                                ["FRAMES", backend.history.reduce((sum, item) => sum + item.frame_count, 0)],
                                ["DEVICES", backend.devices.length]
                            ]
                            delegate: HudPanel {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 90
                                Text { text: modelData[1]; color: root.accent; font.pixelSize: 28; font.bold: true }
                                Text { text: modelData[0]; color: root.textSecondary; font.pixelSize: 11; font.letterSpacing: 1.4 }
                            }
                        }
                    }
                    HudPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        EmptyHint { Layout.alignment: Qt.AlignHCenter; visible: backend.history.length === 0; text: "No completed runs yet. History appears after a session finishes." }
                        ColumnLayout {
                            visible: backend.history.length > 0
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            RowLayout {
                                Layout.fillWidth: true
                                Repeater {
                                    model: [
                                        {label: "DATE", w: 1}, {label: "TARGET", w: 1.4}, {label: "DEVICE", w: 1},
                                        {label: "PLANNED", w: 0.8}, {label: "ACTUAL", w: 0.8}, {label: "OUTCOME", w: 1.2}
                                    ]
                                    Text { required property var modelData; text: modelData.label; color: root.accent; font.pixelSize: 10; font.bold: true; Layout.fillWidth: true; Layout.preferredWidth: 80 * modelData.w }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: root.outline }
                            ListView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                model: backend.history
                                delegate: Rectangle {
                                    required property var modelData
                                    required property int index
                                    width: ListView.view.width
                                    height: 42
                                    color: index % 2 ? "#140A1520" : "transparent"
                                    RowLayout {
                                        anchors.fill: parent
                                        Text { text: modelData.date; color: root.textPrimary; Layout.fillWidth: true }
                                        Text { text: modelData.target_name; color: root.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                                        Text { text: modelData.device_name; color: root.accent; Layout.fillWidth: true; elide: Text.ElideRight }
                                        Text { text: modelData.planned_text; color: root.textSecondary; Layout.fillWidth: true }
                                        Text { text: modelData.actual_text; color: root.textSecondary; Layout.fillWidth: true }
                                        Text { text: modelData.outcome; color: modelData.outcome === "Completed" ? root.success : root.danger; Layout.fillWidth: true; elide: Text.ElideRight }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: settingsPage
                function load() {
                    const d = backend.selectedDevice
                    const hw = d.hardware || {}
                    nameField.text = d.name || ""
                    modelField.currentIndex = Math.max(0, ["Dwarf II", "Dwarf 3", "Dwarf Mini"].indexOf(d.model))
                    ipField.text = d.ip_address || ""
                    cameraField.currentIndex = d.camera === "wide" ? 1 : 0
                    demoField.checked = d.demo_mode === true
                    bleField.checked = d.ble_enabled !== false
                    latField.text = d.latitude
                    lonField.text = d.longitude
                    timezoneField.text = d.timezone_name || "UTC"
                    stellariumField.text = d.stellarium_url || "http://localhost:8090"
                    ssidField.text = d.wifi_ssid || ""
                    wifiField.text = d.wifi_password || ""
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
                }
                Component.onCompleted: load()
                Connections { target: backend; function onSelectedDeviceChanged() { settingsPage.load() } }

                Flickable {
                    id: settingsFlick
                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: settingsColumn.implicitHeight + 24
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    Column {
                        id: settingsColumn
                        width: settingsFlick.width
                        spacing: 12
                        RowLayout {
                            width: parent.width
                            ColumnLayout {
                                Layout.fillWidth: true
                                Text { text: "SETTINGS"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                                Text { text: "Independent connection, camera, Wi‑Fi and timing profiles"; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            DeviceCombo {}
                            HudButton { text: "+ ADD DEVICE"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.addDevice() }
                            HudButton { text: "REMOVE DEVICE"; buttonColor: "#3A1218"; foregroundColor: root.danger; onClicked: backend.deleteDevice(backend.selectedDeviceId) }
                        }
                        HudPanel {
                            title: "DEVICE"
                            width: parent.width
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "NAME" }
                                HudField { id: nameField; Layout.fillWidth: true }
                                FieldLabel { text: "MODEL" }
                                HudCombo { id: modelField; model: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]; Layout.fillWidth: true }
                                FieldLabel { text: "IP ADDRESS" }
                                HudField { id: ipField; Layout.fillWidth: true }
                                FieldLabel { text: "CAMERA" }
                                HudCombo { id: cameraField; model: ["Tele", "Wide"]; Layout.fillWidth: true }
                                FieldLabel { text: "LATITUDE" }
                                HudField { id: latField; Layout.fillWidth: true }
                                FieldLabel { text: "LONGITUDE" }
                                HudField { id: lonField; Layout.fillWidth: true }
                                FieldLabel { text: "TIMEZONE" }
                                HudField { id: timezoneField; Layout.fillWidth: true }
                                FieldLabel { text: "STELLARIUM" }
                                HudField { id: stellariumField; Layout.fillWidth: true }
                                FieldLabel { text: "WIFI SSID" }
                                HudField { id: ssidField; Layout.fillWidth: true }
                                FieldLabel { text: "WIFI PASSWORD" }
                                HudField { id: wifiField; echoMode: TextInput.Password; Layout.fillWidth: true }
                                HudCheck { id: demoField; text: "Demo mode"; Layout.columnSpan: 2 }
                                HudCheck { id: bleField; text: "Bluetooth enabled"; Layout.columnSpan: 1 }
                                RowLayout {
                                    Layout.columnSpan: 1
                                    FieldLabel { text: "NIGHT CUTOFF" }
                                    SpinBox {
                                        id: cutoffField
                                        from: 0
                                        to: 23
                                        value: 12
                                        editable: true
                                        palette.text: root.textPrimary
                                        palette.base: "#0A1524"
                                        palette.button: "#122033"
                                        palette.buttonText: root.accent
                                        palette.highlight: root.accent
                                    }
                                }
                            }
                        }
                        HudPanel {
                            title: "HARDWARE DURATION PROFILE"
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
                            HudButton {
                                text: "SAVE DEVICE"
                                buttonColor: "#0E3A48"
                                foregroundColor: root.accent
                                onClicked: backend.saveDevice(JSON.stringify({
                                    id: backend.selectedDeviceId, name: nameField.text, model: modelField.currentText,
                                    ip_address: ipField.text, camera: cameraField.currentIndex === 1 ? "wide" : "tele",
                                    demo_mode: demoField.checked, ble_enabled: bleField.checked,
                                    latitude: Number(latField.text), longitude: Number(lonField.text),
                                    timezone_name: timezoneField.text, stellarium_url: stellariumField.text,
                                    wifi_ssid: ssidField.text, wifi_password: wifiField.text,
                                    observing_day_cutoff_hour: cutoffField.value, slew_seconds: Number(slewField.text),
                                    settle_seconds: Number(settleField.text), calibration_seconds: Number(calibrationField.text),
                                    autofocus_seconds: Number(autofocusField.text), infinite_focus_seconds: Number(infinityField.text),
                                    polar_seconds: Number(polarField.text), readout_seconds: Number(readoutField.text),
                                    pane_slew_seconds: Number(paneField.text), startup_seconds: Number(startupField.text)
                                }))
                            }
                        }
                        HudPanel {
                            title: "LEGACY IMPORT"
                            width: parent.width
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Import old Astro_Sessions JSON without modifying the old app."; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                }
                                HudButton { text: "CHOOSE FOLDER…"; onClicked: legacyDialog.open() }
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            Layout.maximumHeight: 48
            Layout.fillHeight: false
            Layout.leftMargin: 10
            Layout.rightMargin: 10
            Layout.bottomMargin: 8
            spacing: 8
            Item {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.fillHeight: false
                Image { anchors.fill: parent; source: root.asset("hud-joystick.png"); fillMode: Image.PreserveAspectFit }
            }
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
                    onClicked: root.currentPage = modelData.idx
                }
            }
        }
        }

        EdgeResize {
            edges: Qt.LeftEdge
            cursor: Qt.SizeHorCursor
            width: 6
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 6
            anchors.bottomMargin: 6
        }
        EdgeResize {
            edges: Qt.RightEdge
            cursor: Qt.SizeHorCursor
            width: 6
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.topMargin: 64
            anchors.bottomMargin: 6
        }
        EdgeResize {
            edges: Qt.BottomEdge
            cursor: Qt.SizeVerCursor
            height: 6
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 6
            anchors.rightMargin: 6
        }
        EdgeResize {
            edges: Qt.LeftEdge | Qt.TopEdge
            cursor: Qt.SizeFDiagCursor
            width: 8
            height: 8
            anchors.left: parent.left
            anchors.top: parent.top
        }
        EdgeResize {
            edges: Qt.LeftEdge | Qt.BottomEdge
            cursor: Qt.SizeBDiagCursor
            width: 8
            height: 8
            anchors.left: parent.left
            anchors.bottom: parent.bottom
        }
        EdgeResize {
            edges: Qt.RightEdge | Qt.BottomEdge
            cursor: Qt.SizeFDiagCursor
            width: 8
            height: 8
            anchors.right: parent.right
            anchors.bottom: parent.bottom
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

    Popup {
        id: snackbar
        property alias text: snackbarText.text
        property string level: "info"
        width: Math.min(root.width - 80, 520)
        height: 52
        x: (root.width - width) / 2
        y: root.height - height - 70
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: "#0B1520"
            border.color: snackbar.level === "error" ? root.danger : snackbar.level === "warning" ? root.warning : root.accent
        }
        contentItem: Text { id: snackbarText; color: root.textPrimary; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap; leftPadding: 8 }
        onOpened: snackbarTimer.restart()
        Timer { id: snackbarTimer; interval: 4000; onTriggered: snackbar.close() }
    }

    Connections {
        target: backend
        function onToast(message, level) {
            snackbar.level = level
            snackbar.text = message
            snackbar.open()
        }
    }

    Dialog {
        id: confirmDialog
        property string operation: ""
        property string summary: ""
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 420
        height: 160
        padding: 16
        background: Rectangle { color: "#0B1520"; border.color: root.danger }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "CONFIRM COMMAND"; color: root.danger; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text { text: confirmDialog.summary; color: root.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: confirmDialog.close() }
                HudButton {
                    text: "CONFIRM"
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: {
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
        padding: 0

        function openForDate(day) {
            editingId = ""
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
            sessionName.text = data.name
            targetName.text = data.target_name
            const kind = data.target ? data.target.kind : "equatorial"
            targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
            ra.text = data.target && data.target.ra_hours != null ? data.target.ra_hours : ""
            dec.text = data.target && data.target.dec_degrees != null ? data.target.dec_degrees : ""
            startTime.text = String(data.scheduled_start).substring(0, 16)
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
            open()
        }

        background: Rectangle { color: "#0B1520"; border.color: root.accent }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text { text: sessionDialog.editingId ? "EDIT SESSION" : "NEW SESSION"; color: root.accent; font.pixelSize: 20; font.letterSpacing: 2; Layout.fillWidth: true }
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
                FieldLabel { text: "START" }
                HudField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2 }
                FieldLabel { text: "CAMERA" }
                HudCombo { id: camera; model: ["Tele", "Wide"]; Layout.fillWidth: true }
                HudCombo { id: irFilter; model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]; Layout.fillWidth: true }
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
                HudCheck { id: saveTemplate; text: "Save template" }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: sessionDialog.close() }
                HudButton {
                    text: "SAVE SESSION"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: {
                        backend.saveSession(JSON.stringify({
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
                        }))
                        sessionDialog.close()
                    }
                }
            }
        }
    }
}
