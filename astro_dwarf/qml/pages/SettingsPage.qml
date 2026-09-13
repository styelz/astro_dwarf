import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: settingsPage
    property string loadedDeviceId: ""
    property string loadedSnapshot: ""
    property bool applyingDeviceSelect: false
    property int categoryIndex: 0
    readonly property var categories: [
        { title: "INTERFACE", glyph: "◫", device: false },
        { title: "OBSERVING", glyph: "◷", device: false },
        { title: "DEVICE", glyph: "◈", device: true },
        { title: "CAPTURE", glyph: "▣", device: true },
        { title: "CONNECT", glyph: "⇌", device: true },
        { title: "TIMING", glyph: "◷", device: true },
        { title: "IMPORT", glyph: "⇩", device: false }
    ]
    readonly property var categoryKeys: [
        [],
        [],
        ["name", "model", "camera", "timezone_name", "latitude", "longitude"],
        ["capture_defaults"],
        ["ip_address", "ble_enabled", "wifi_mode", "wifi_ssid", "wifi_password", "ble_password"],
        ["slew_seconds", "settle_seconds", "calibration_seconds", "autofocus_seconds", "infinite_focus_seconds", "polar_seconds", "readout_seconds", "pane_slew_seconds", "startup_seconds"],
        []
    ]
    function currentPayload() {
        return {
            id: settingsPage.loadedDeviceId || backend.selectedDeviceId, name: nameField.text, model: modelField.currentText,
            ip_address: ipField.text, camera: cameraField.currentIndex === 1 ? "wide" : "tele",
            ble_enabled: bleField.checked,
            latitude: Number(latField.text), longitude: Number(lonField.text),
            timezone_name: timezoneField.selectedName || timezoneField.editText,
            wifi_mode: ["auto", "ap", "sta"][wifiModeField.currentIndex],
            wifi_ssid: ssidField.text, wifi_password: wifiField.text,
            ble_password: blePasswordField.text,
            slew_seconds: Number(slewField.text),
            settle_seconds: Number(settleField.text), calibration_seconds: Number(calibrationField.text),
            autofocus_seconds: Number(autofocusField.text), infinite_focus_seconds: Number(infinityField.text),
            polar_seconds: Number(polarField.text), readout_seconds: Number(readoutField.text),
            pane_slew_seconds: Number(paneField.text), startup_seconds: Number(startupField.text),
            capture_defaults: {
                exposure_seconds: Number(exposureDefaultField.text),
                gain: Number(gainDefaultField.text),
                frame_count: Number(framesDefaultField.text)
            }
        }
    }
    readonly property bool dirty: JSON.stringify(currentPayload()) !== loadedSnapshot
    readonly property var durationHint: backend.durationSuggestion || ({})
    readonly property bool durationHintPending: {
        const hint = settingsPage.durationHint
        if (!hint || !hint.available || !hint.changes || !hint.changes.length)
            return false
        const fields = {
            slew_seconds: slewField.text, settle_seconds: settleField.text,
            calibration_seconds: calibrationField.text, autofocus_seconds: autofocusField.text,
            infinite_focus_seconds: infinityField.text, polar_seconds: polarField.text,
            readout_seconds: readoutField.text, pane_slew_seconds: paneField.text,
            startup_seconds: startupField.text
        }
        for (let i = 0; i < hint.changes.length; i++) {
            const change = hint.changes[i]
            if (Math.abs(Number(fields[change.key]) - Number(change.suggested)) > 0.05)
                return true
        }
        return false
    }
    function sectionDirty(index) {
        const keys = settingsPage.categoryKeys[index] || []
        if (!keys.length || !settingsPage.dirty)
            return false
        try {
            const now = currentPayload()
            const prev = JSON.parse(loadedSnapshot || "{}")
            for (let i = 0; i < keys.length; i++) {
                const key = keys[i]
                if (JSON.stringify(now[key]) !== JSON.stringify(prev[key]))
                    return true
            }
        } catch (exc) {
            return settingsPage.dirty
        }
        return false
    }
    function applyDurationHint() {
        const hint = settingsPage.durationHint
        if (!hint || !hint.changes)
            return
        const fields = {
            slew_seconds: slewField, settle_seconds: settleField,
            calibration_seconds: calibrationField, autofocus_seconds: autofocusField,
            infinite_focus_seconds: infinityField, polar_seconds: polarField,
            readout_seconds: readoutField, pane_slew_seconds: paneField,
            startup_seconds: startupField
        }
        for (let i = 0; i < hint.changes.length; i++) {
            const change = hint.changes[i]
            const field = fields[change.key]
            if (!field)
                continue
            field.text = change.key === "readout_seconds"
                ? Number(change.suggested).toFixed(1)
                : String(change.suggested)
        }
    }
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
        stellariumField.text = backend.stellariumUrl || "http://localhost:8090"
        wifiModeField.currentIndex = Math.max(0, ["auto", "ap", "sta"].indexOf(d.wifi_mode || "auto"))
        ssidField.text = d.wifi_ssid || ""
        wifiField.text = d.wifi_password || ""
        blePasswordField.text = d.ble_password || "DWARF_12345678"
        cutoffField.value = backend.observingDayCutoffHour
        slewField.text = hw.slew_seconds || 20
        settleField.text = hw.settle_seconds || 10
        calibrationField.text = hw.calibration_seconds || 90
        autofocusField.text = hw.autofocus_seconds || 45
        infinityField.text = hw.infinite_focus_seconds || 15
        polarField.text = hw.polar_seconds || 180
        readoutField.text = hw.readout_seconds || 1.2
        paneField.text = hw.pane_slew_seconds || 12
        startupField.text = hw.startup_seconds || 8
        const capture = Util.captureDefaults(d)
        exposureDefaultField.text = String(capture.exposure_seconds)
        gainDefaultField.text = String(capture.gain)
        framesDefaultField.text = String(capture.frame_count)
        loadedSnapshot = JSON.stringify(currentPayload())
    }
    Component.onCompleted: load()
    Connections {
        target: backend
        function onSelectedDeviceChanged() {
            if (settingsPage.applyingDeviceSelect)
                return
            if (settingsPage.loadedDeviceId === backend.selectedDeviceId) {
                if (!settingsPage.dirty)
                    settingsPage.load()
                else if (!ipField.text && backend.selectedDevice.ip_address)
                    ipField.text = backend.selectedDevice.ip_address
                return
            }
            if (!settingsPage.dirty) {
                settingsPage.load()
                return
            }
            const wanted = backend.selectedDeviceId
            settingsPage.applyingDeviceSelect = true
            backend.selectDevice(settingsPage.loadedDeviceId)
            settingsPage.applyingDeviceSelect = false
            root.askLeaveSettings(-1, wanted)
        }
        function onAppSettingsChanged() {
            if (!settingsPage.dirty) {
                stellariumField.text = backend.stellariumUrl || "http://localhost:8090"
                cutoffField.value = backend.observingDayCutoffHour
            }
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

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: settingsFooter.top
        anchors.bottomMargin: 8
        spacing: 8

        PageHeader {
            Layout.fillWidth: true
            title: "SETTINGS"
            subtitle: "Device, connection and timing profiles  ·  Astro Dwarf v" + backend.appVersion
            DeviceCombo {}
            HudButton { text: "+ ADD DEVICE"; busyText: "ADDING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: locationDialog.openForAdd() }
            HudButton { text: "REMOVE DEVICE"; busyText: "REMOVING…"; buttonColor: Theme.fillDanger; foregroundColor: Theme.danger; onClicked: root.confirmRemoveDevice(backend.selectedDeviceId) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Rectangle {
                Layout.preferredWidth: 180
                Layout.minimumWidth: 160
                Layout.fillHeight: true
                color: Theme.panelFill
                border.color: Theme.outline
                border.width: 1
                radius: Theme.radius
                Column {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 2
                    Repeater {
                        model: settingsPage.categories
                        delegate: Item {
                            id: railRow
                            required property int index
                            required property var modelData
                            width: parent.width
                            height: Theme.controlHeight
                            readonly property bool current: settingsPage.categoryIndex === index
                            readonly property bool dirty: settingsPage.sectionDirty(index)
                            Accessible.role: Accessible.Button
                            Accessible.name: modelData.title
                            Accessible.description: dirty ? "Unsaved changes" : ""
                            Keys.onReturnPressed: settingsPage.categoryIndex = index
                            Keys.onSpacePressed: settingsPage.categoryIndex = index
                            activeFocusOnTab: true
                            Rectangle {
                                anchors.fill: parent
                                radius: 2
                                color: railRow.current ? Theme.fillActive : (railHover.hovered || railRow.activeFocus ? Theme.hsl(0.039, 0.535, 0.253, 0.13) : "transparent")
                                border.color: railRow.activeFocus ? Theme.accent : "transparent"
                                border.width: railRow.activeFocus ? 1 : 0
                            }
                            HoverHandler { id: railHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: settingsPage.categoryIndex = railRow.index }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 8
                                spacing: 8
                                Text {
                                    text: railRow.modelData.glyph
                                    color: railRow.current ? Theme.accent : Theme.textSecondary
                                    font.pixelSize: 13
                                    Layout.preferredWidth: 16
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: railRow.modelData.title
                                    color: railRow.current ? Theme.accent : Theme.textPrimary
                                    font.pixelSize: 11
                                    font.bold: true
                                    font.letterSpacing: 1.1
                                    elide: Text.ElideRight
                                }
                                LedDot {
                                    visible: railRow.dirty
                                    on: true
                                    onColor: Theme.warning
                                    pulse: true
                                }
                            }
                        }
                    }
                }
            }

            HudPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: {
                    const item = settingsPage.categories[settingsPage.categoryIndex] || ({})
                    return (item.glyph || "") + "  " + (item.title || "")
                }
                headerExtra: [
                    HudChip {
                        visible: settingsPage.categoryIndex === 2
                        label: backend.selectedDevice.connected ? "ONLINE" : "OFFLINE"
                        tone: backend.selectedDevice.connected ? Theme.success : Theme.textSecondary
                        dim: !backend.selectedDevice.connected
                        glow: !!backend.selectedDevice.connected
                    }
                ]

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: settingsPage.categoryIndex

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "Applies immediately. Hue and brightness tint the console; denoise and sky crush scale the live and media filters."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
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
                            FieldLabel { text: "THEME HUE" }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Slider {
                                    id: hueSlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: 1
                                    stepSize: 0.001
                                    value: Theme.hue
                                    onMoved: Theme.hue = value
                                    implicitHeight: 28
                                    background: Rectangle {
                                        x: hueSlider.leftPadding
                                        y: hueSlider.topPadding + hueSlider.availableHeight / 2 - height / 2
                                        width: hueSlider.availableWidth
                                        height: 10
                                        radius: 5
                                        border.color: Theme.outline
                                        border.width: 1
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.000; color: Qt.hsla(0.000, 0.9, 0.55, 1) }
                                            GradientStop { position: 0.167; color: Qt.hsla(0.167, 0.9, 0.55, 1) }
                                            GradientStop { position: 0.333; color: Qt.hsla(0.333, 0.9, 0.55, 1) }
                                            GradientStop { position: 0.500; color: Qt.hsla(0.500, 0.9, 0.55, 1) }
                                            GradientStop { position: 0.667; color: Qt.hsla(0.667, 0.9, 0.55, 1) }
                                            GradientStop { position: 0.833; color: Qt.hsla(0.833, 0.9, 0.55, 1) }
                                            GradientStop { position: 1.000; color: Qt.hsla(1.000, 0.9, 0.55, 1) }
                                        }
                                        Rectangle {
                                            x: Theme.defaultHue * parent.width - 1
                                            y: -3
                                            width: 2
                                            height: parent.height + 6
                                            color: Theme.textPrimary
                                            opacity: 0.5
                                        }
                                    }
                                    handle: Rectangle {
                                        x: hueSlider.leftPadding + hueSlider.visualPosition * (hueSlider.availableWidth - width)
                                        y: hueSlider.topPadding + hueSlider.availableHeight / 2 - height / 2
                                        width: 20
                                        height: 20
                                        radius: 10
                                        color: Theme.accent
                                        border.color: hueSlider.pressed || hueSlider.hovered ? Theme.textPrimary : Theme.surface
                                        border.width: 2
                                        Rectangle { anchors.fill: parent; anchors.margins: -4; radius: width / 2; color: "transparent"; border.color: Theme.accent; opacity: hueSlider.pressed ? 0.6 : 0 ; Behavior on opacity { NumberAnimation { duration: Theme.quick } } }
                                    }
                                }
                                Text {
                                    text: Math.round(Theme.hue * 360) + "°"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontMono
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 36
                                    horizontalAlignment: Text.AlignRight
                                }
                                HudButton {
                                    text: "RESET"
                                    implicitHeight: 28
                                    enabled: Math.abs(Theme.hue - Theme.defaultHue) > 0.002 || Math.abs(Theme.brightness) > 0.002
                                    onClicked: {
                                        Theme.hue = Theme.defaultHue
                                        Theme.brightness = 0
                                    }
                                }
                            }
                            FieldLabel { text: "BRIGHTNESS" }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Slider {
                                    id: brightSlider
                                    Layout.fillWidth: true
                                    from: -1
                                    to: 1
                                    stepSize: 0.01
                                    value: Theme.brightness
                                    onMoved: Theme.brightness = value
                                    implicitHeight: 28
                                    background: Rectangle {
                                        x: brightSlider.leftPadding
                                        y: brightSlider.topPadding + brightSlider.availableHeight / 2 - height / 2
                                        width: brightSlider.availableWidth
                                        height: 10
                                        radius: 5
                                        border.color: Theme.outline
                                        border.width: 1
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0.0; color: Qt.hsla(Theme.hue, 1, 0.16, 1) }
                                            GradientStop { position: 0.5; color: Qt.hsla(Theme.hue, 1, 0.651, 1) }
                                            GradientStop { position: 1.0; color: Qt.hsla(Theme.hue, 1, 0.90, 1) }
                                        }
                                        Rectangle {
                                            x: parent.width / 2 - 1
                                            y: -3
                                            width: 2
                                            height: parent.height + 6
                                            color: Theme.textPrimary
                                            opacity: 0.5
                                        }
                                    }
                                    handle: Rectangle {
                                        x: brightSlider.leftPadding + brightSlider.visualPosition * (brightSlider.availableWidth - width)
                                        y: brightSlider.topPadding + brightSlider.availableHeight / 2 - height / 2
                                        width: 20
                                        height: 20
                                        radius: 10
                                        color: Theme.accent
                                        border.color: brightSlider.pressed || brightSlider.hovered ? Theme.textPrimary : Theme.surface
                                        border.width: 2
                                    }
                                }
                                Text {
                                    text: (Theme.brightness > 0 ? "+" : "") + Math.round(Theme.brightness * 100)
                                    color: Theme.textSecondary
                                    font.family: Theme.fontMono
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 36
                                    horizontalAlignment: Text.AlignRight
                                }
                                Item { implicitWidth: 60; implicitHeight: 1 }
                            }
                            FieldLabel { text: "DENOISE" }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Slider {
                                    id: denoiseSlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: 1
                                    stepSize: 0.01
                                    value: Theme.enhanceDenoise
                                    onMoved: Theme.enhanceDenoise = value
                                    implicitHeight: 28
                                    Accessible.name: "Enhance denoise"
                                    background: Rectangle {
                                        x: denoiseSlider.leftPadding
                                        y: denoiseSlider.topPadding + denoiseSlider.availableHeight / 2 - height / 2
                                        width: denoiseSlider.availableWidth
                                        height: 10
                                        radius: 5
                                        color: Theme.inputBg
                                        border.color: Theme.outline
                                        Rectangle {
                                            width: denoiseSlider.visualPosition * parent.width
                                            height: parent.height
                                            radius: 5
                                            color: Theme.accent
                                            opacity: 0.45
                                        }
                                    }
                                    handle: Rectangle {
                                        x: denoiseSlider.leftPadding + denoiseSlider.visualPosition * (denoiseSlider.availableWidth - width)
                                        y: denoiseSlider.topPadding + denoiseSlider.availableHeight / 2 - height / 2
                                        width: 20
                                        height: 20
                                        radius: 10
                                        color: Theme.accent
                                        border.color: denoiseSlider.pressed || denoiseSlider.hovered ? Theme.textPrimary : Theme.surface
                                        border.width: 2
                                    }
                                }
                                Text {
                                    text: Math.round(Theme.enhanceDenoise * 100) + "%"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontMono
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 36
                                    horizontalAlignment: Text.AlignRight
                                }
                                Item { implicitWidth: 60; implicitHeight: 1 }
                            }
                            FieldLabel { text: "SKY CRUSH" }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Slider {
                                    id: skySlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: 1
                                    stepSize: 0.01
                                    value: Theme.enhanceSkyCrush
                                    onMoved: Theme.enhanceSkyCrush = value
                                    implicitHeight: 28
                                    Accessible.name: "Enhance sky crush"
                                    background: Rectangle {
                                        x: skySlider.leftPadding
                                        y: skySlider.topPadding + skySlider.availableHeight / 2 - height / 2
                                        width: skySlider.availableWidth
                                        height: 10
                                        radius: 5
                                        color: Theme.inputBg
                                        border.color: Theme.outline
                                        Rectangle {
                                            width: skySlider.visualPosition * parent.width
                                            height: parent.height
                                            radius: 5
                                            color: Theme.accent
                                            opacity: 0.45
                                        }
                                    }
                                    handle: Rectangle {
                                        x: skySlider.leftPadding + skySlider.visualPosition * (skySlider.availableWidth - width)
                                        y: skySlider.topPadding + skySlider.availableHeight / 2 - height / 2
                                        width: 20
                                        height: 20
                                        radius: 10
                                        color: Theme.accent
                                        border.color: skySlider.pressed || skySlider.hovered ? Theme.textPrimary : Theme.surface
                                        border.width: 2
                                    }
                                }
                                Text {
                                    text: Math.round(Theme.enhanceSkyCrush * 100) + "%"
                                    color: Theme.textSecondary
                                    font.family: Theme.fontMono
                                    font.pixelSize: 11
                                    Layout.preferredWidth: 36
                                    horizontalAlignment: Text.AlignRight
                                }
                                Item { implicitWidth: 60; implicitHeight: 1 }
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "Applies to every telescope immediately. Night cutoff is when the calendar rolls to the next observing night."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 4
                            columnSpacing: 10
                            rowSpacing: 8
                            FieldLabel { text: "NIGHT CUTOFF" }
                            SpinBox {
                                id: cutoffField
                                from: 0
                                to: 23
                                value: 12
                                editable: true
                                Layout.fillWidth: true
                                palette.text: Theme.textPrimary
                                palette.base: Theme.inputBg
                                palette.button: Theme.surfaceHigh
                                palette.buttonText: Theme.accent
                                palette.highlight: Theme.accent
                                onValueModified: backend.setObservingDayCutoffHour(value)
                                WheelHandler {
                                    enabled: cutoffField.enabled
                                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                    acceptedModifiers: Qt.NoModifier
                                    blocking: true
                                    onWheel: event => {
                                        const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
                                        if (!delta)
                                            return
                                        const next = Math.max(cutoffField.from, Math.min(cutoffField.to, cutoffField.value + (delta > 0 ? 1 : -1)))
                                        if (next !== cutoffField.value) {
                                            cutoffField.value = next
                                            cutoffField.valueModified()
                                        }
                                        event.accepted = true
                                    }
                                }
                            }
                            FieldLabel { text: "STELLARIUM" }
                            HudField {
                                id: stellariumField
                                Layout.fillWidth: true
                                placeholderText: "http://localhost:8090"
                                onEditingFinished: backend.setStellariumUrl(text)
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "Identity and site for the selected telescope. Save to keep these on this device."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
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
                        }
                    }

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "New sessions and imported targets on this telescope start with these capture settings."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 6
                            columnSpacing: 8
                            rowSpacing: 6
                            FieldLabel { text: "EXPOSURE S" }
                            HudField {
                                id: exposureDefaultField
                                Layout.fillWidth: true
                                placeholderText: String(Util.stockExposureSeconds)
                                accessibleName: "Default exposure seconds"
                            }
                            FieldLabel { text: "GAIN" }
                            HudField {
                                id: gainDefaultField
                                Layout.fillWidth: true
                                placeholderText: String(Util.stockGain)
                                accessibleName: "Default gain"
                            }
                            FieldLabel { text: "FRAMES" }
                            HudField {
                                id: framesDefaultField
                                Layout.fillWidth: true
                                placeholderText: String(Util.stockFrameCount)
                                accessibleName: "Default frame count"
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: wifiModeField.currentIndex === 1
                                ? "AP: this app joins the Dwarf hotspot. IP is usually 192.168.88.1."
                                : wifiModeField.currentIndex === 2
                                    ? "STA: Bluetooth tells the telescope to join your router. This computer must already be on that Wi-Fi."
                                    : "Auto keeps the mode already set on the telescope. Commands and live stream use that Wi-Fi link."
                            color: Theme.textSecondary
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

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "These overheads size calendar blocks and remaining-time estimates."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        ColumnLayout {
                            visible: settingsPage.durationHintPending
                            Layout.fillWidth: true
                            spacing: 6
                            Text {
                                Layout.fillWidth: true
                                text: settingsPage.durationHint.summary || ""
                                color: Theme.warning
                                wrapMode: Text.Wrap
                                font.pixelSize: 12
                            }
                            Text {
                                visible: !!(settingsPage.durationHint.note)
                                Layout.fillWidth: true
                                text: settingsPage.durationHint.note || ""
                                color: Theme.textSecondary
                                wrapMode: Text.Wrap
                                font.pixelSize: 11
                            }
                            Text {
                                Layout.fillWidth: true
                                text: settingsPage.durationHint.change_text || ""
                                color: Theme.textPrimary
                                wrapMode: Text.Wrap
                                font.pixelSize: 12
                                font.family: Theme.fontMono
                            }
                            RowLayout {
                                HudButton {
                                    text: "APPLY SUGGESTIONS"
                                    busyText: "APPLYING…"
                                    buttonColor: Theme.fillActive
                                    foregroundColor: Theme.accent
                                    onClicked: settingsPage.applyDurationHint()
                                }
                                Item { Layout.fillWidth: true }
                            }
                        }
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

                    ColumnLayout {
                        spacing: 8
                        Text {
                            text: "Import old Astro_Sessions JSON without modifying the old app."
                            color: Theme.textSecondary
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                        HudButton { text: "CHOOSE FOLDER…"; busyText: "OPENING…"; onClicked: legacyDialog.open() }
                        Item { Layout.fillHeight: true }
                    }
                }
            }
        }
    }
    Rectangle {
        id: settingsFooter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 46
        radius: 3
        color: settingsPage.dirty ? Theme.hsl(0.040, 0.611, 0.141, 0.753) : Theme.panelFill
        border.color: settingsPage.dirty ? Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.6) : Theme.outline
        Behavior on color { ColorAnimation { duration: 180 } }
        Behavior on border.color { ColorAnimation { duration: 180 } }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 14
            anchors.rightMargin: 10
            spacing: 10
            LedDot { on: true; onColor: settingsPage.dirty ? Theme.warning : Theme.success; pulse: settingsPage.dirty }
            Text {
                Layout.fillWidth: true
                text: settingsPage.dirty
                    ? "UNSAVED CHANGES · " + (nameField.text || "device").toUpperCase()
                    : "ALL CHANGES SAVED · " + (nameField.text || "device").toUpperCase()
                color: settingsPage.dirty ? Theme.warning : Theme.textSecondary
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
                buttonColor: settingsPage.dirty ? Theme.fillActive : Theme.surfaceHigh
                foregroundColor: settingsPage.dirty ? Theme.accent : Theme.textSecondary
                onClicked: settingsPage.saveCurrent()
            }
        }
    }
}
