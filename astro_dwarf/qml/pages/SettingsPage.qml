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
    // Width of the control column in every settings grid; the hint column takes the rest.
    readonly property int controlWidth: 320
    // Narrower column for plain numeric entries so the explanation gets the room instead.
    readonly property int numberWidth: 140
    readonly property var categories: [
        { title: "INTERFACE", hint: "Layout · console tint", glyph: "◫", device: false },
        { title: "IMAGE", hint: "Enhance filters", glyph: "▦", device: false },
        { title: "OBSERVING", hint: "Night cutoff · Stellarium", glyph: "◷", device: false },
        { title: "DEVICE", hint: "Identity · site", glyph: "◈", device: true },
        { title: "CAPTURE", hint: "Session defaults", glyph: "▣", device: true },
        { title: "CONNECT", hint: "Wi-Fi · Bluetooth", glyph: "⇌", device: true },
        { title: "TIMING", hint: "Overhead estimates", glyph: "◷", device: true },
        { title: "IMPORT", hint: "Legacy sessions", glyph: "⇩", device: false }
    ]
    readonly property var categoryKeys: [
        [],
        [],
        [],
        ["name", "model", "camera", "timezone_name", "latitude", "longitude"],
        ["capture_defaults"],
        ["ip_address", "ble_enabled", "wifi_mode", "wifi_ssid", "wifi_password", "ble_password"],
        ["slew_seconds", "settle_seconds", "calibration_seconds", "autofocus_seconds", "infinite_focus_seconds", "polar_seconds", "readout_seconds", "pane_slew_seconds", "startup_seconds"],
        []
    ]
    readonly property var currentCategory: settingsPage.categories[settingsPage.categoryIndex] || ({})
    readonly property bool tintCustom: Math.abs(Theme.hue - Theme.defaultHue) > 0.002 || Math.abs(Theme.brightness) > 0.002
    readonly property bool enhanceCustom: Math.abs(Theme.enhanceDenoise - 1) > 0.002 || Math.abs(Theme.enhanceSkyCrush - 1) > 0.002
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

    function formatSeconds(total) {
        const s = Math.max(0, Number(total) || 0)
        if (s < 90)
            return Math.round(s) + " s"
        const minutes = Math.floor(s / 60)
        const rest = Math.round(s - minutes * 60)
        if (minutes >= 60) {
            const hours = Math.floor(minutes / 60)
            return hours + " h " + String(minutes - hours * 60).padStart(2, "0") + " min"
        }
        return rest ? minutes + " min " + String(rest).padStart(2, "0") + " s" : minutes + " min"
    }
    function formatCoordinate(value, positive, negative) {
        const n = Number(value)
        if (String(value).trim() === "" || !isFinite(n))
            return "—"
        return Math.abs(n).toFixed(3) + "°" + (n < 0 ? negative : positive)
    }
    // Setup overhead a full-workflow session pays before the first frame (see services.py).
    readonly property real setupOverhead: (Number(startupField.text) || 0) + (Number(slewField.text) || 0) + (Number(settleField.text) || 0)
                                          + (Number(calibrationField.text) || 0) + (Number(autofocusField.text) || 0)
                                          + (Number(infinityField.text) || 0) + (Number(polarField.text) || 0)
    readonly property real defaultIntegration: (Number(exposureDefaultField.text) || 0) * (Number(framesDefaultField.text) || 0)
    readonly property real defaultWallClock: settingsPage.defaultIntegration + (Number(readoutField.text) || 0) * (Number(framesDefaultField.text) || 0)

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
            subtitle: "Console, image filters, telescope and timing profiles  ·  Astro Dwarf v" + backend.appVersion
            DeviceCombo {}
            HudButton { text: "+ ADD DEVICE"; busyText: "ADDING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: locationDialog.openForAdd() }
            HudButton { text: "REMOVE DEVICE"; busyText: "REMOVING…"; buttonColor: Theme.fillDanger; foregroundColor: Theme.danger; onClicked: root.confirmRemoveDevice(backend.selectedDeviceId) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Rectangle {
                Layout.preferredWidth: 190
                Layout.minimumWidth: 170
                Layout.fillHeight: true
                color: Theme.panelFill
                border.color: Theme.outline
                border.width: 1
                radius: Theme.radius
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 6
                    spacing: 2
                    Repeater {
                        model: settingsPage.categories
                        delegate: Item {
                            id: railRow
                            required property int index
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 38
                            readonly property bool current: settingsPage.categoryIndex === index
                            readonly property bool dirty: settingsPage.sectionDirty(index)
                            Accessible.role: Accessible.Button
                            Accessible.name: modelData.title
                            Accessible.description: (modelData.hint || "") + (dirty ? " · Unsaved changes" : "")
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
                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.margins: 6
                                width: 2
                                radius: 1
                                color: Theme.accent
                                opacity: railRow.current ? 1 : 0
                                Behavior on opacity { NumberAnimation { duration: Theme.quick } }
                            }
                            HoverHandler { id: railHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: settingsPage.categoryIndex = railRow.index }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 8
                                spacing: 8
                                Text {
                                    text: railRow.modelData.glyph
                                    color: railRow.current ? Theme.accent : Theme.textSecondary
                                    font.pixelSize: 13
                                    Layout.preferredWidth: 16
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    Text {
                                        Layout.fillWidth: true
                                        text: railRow.modelData.title
                                        color: railRow.current ? Theme.accent : Theme.textPrimary
                                        font.pixelSize: 11
                                        font.bold: true
                                        font.letterSpacing: 1.1
                                        elide: Text.ElideRight
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: railRow.modelData.hint || ""
                                        color: railRow.current ? Theme.textPrimary : Theme.textSecondary
                                        opacity: railRow.current ? 0.8 : 0.75
                                        font.pixelSize: 9
                                        elide: Text.ElideRight
                                    }
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
                    Item { Layout.fillHeight: true }
                }
            }

            HudPanel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: (settingsPage.currentCategory.glyph || "") + "  " + (settingsPage.currentCategory.title || "")
                headerExtra: [
                    HudChip {
                        label: settingsPage.currentCategory.device ? "PER TELESCOPE" : "APP-WIDE"
                        tone: settingsPage.currentCategory.device ? Theme.accent : Theme.textSecondary
                        dim: !settingsPage.currentCategory.device
                    },
                    HudChip {
                        visible: !!settingsPage.currentCategory.device
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

                    // INTERFACE
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "How the console looks on this computer. Changes apply immediately and are remembered here, not on the telescope."
                        }
                        SettingGroup {
                            title: "LAYOUT"
                            FieldLabel { text: "NAV BUTTONS" }
                            HudCombo {
                                Layout.preferredWidth: settingsPage.controlWidth
                                model: ["Bottom", "Top (below header)"]
                                currentIndex: layoutSettings.navBarOnTop ? 1 : 0
                                onActivated: layoutSettings.navBarOnTop = currentIndex === 1
                                accessibleName: "Navigation button position"
                            }
                            FieldHint { text: "Where the page tabs sit. Top keeps them under the device bar; Bottom leaves the header clear and puts them along the lower edge." }
                        }
                        SettingGroup {
                            title: "CONSOLE TINT"
                            trailing: [
                                HudChip {
                                    label: settingsPage.tintCustom ? "CUSTOM" : "STOCK"
                                    tone: settingsPage.tintCustom ? Theme.warning : Theme.textSecondary
                                    dim: !settingsPage.tintCustom
                                    anchors.verticalCenter: parent.verticalCenter
                                },
                                HudButton {
                                    text: "RESET"
                                    implicitHeight: 28
                                    enabled: settingsPage.tintCustom
                                    Accessible.description: "Return hue and brightness to stock"
                                    onClicked: {
                                        Theme.hue = Theme.defaultHue
                                        Theme.brightness = 0
                                    }
                                }
                            ]
                            FieldLabel { text: "THEME HUE" }
                            HudSlider {
                                id: hueSlider
                                Layout.preferredWidth: settingsPage.controlWidth
                                from: 0
                                to: 1
                                stepSize: 0.001
                                value: Theme.hue
                                onMoved: Theme.hue = value
                                markerPosition: Theme.defaultHue
                                valueText: Math.round(Theme.hue * 360) + "°"
                                accessibleName: "Theme hue"
                                trackGradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.000; color: Qt.hsla(0.000, 0.9, 0.55, 1) }
                                    GradientStop { position: 0.167; color: Qt.hsla(0.167, 0.9, 0.55, 1) }
                                    GradientStop { position: 0.333; color: Qt.hsla(0.333, 0.9, 0.55, 1) }
                                    GradientStop { position: 0.500; color: Qt.hsla(0.500, 0.9, 0.55, 1) }
                                    GradientStop { position: 0.667; color: Qt.hsla(0.667, 0.9, 0.55, 1) }
                                    GradientStop { position: 0.833; color: Qt.hsla(0.833, 0.9, 0.55, 1) }
                                    GradientStop { position: 1.000; color: Qt.hsla(1.000, 0.9, 0.55, 1) }
                                }
                            }
                            FieldHint { text: "Base colour for panels, outlines, text and accent; the whole palette is derived from it. Success, warning and danger colours stay fixed. The tick is stock cyan." }
                            FieldLabel { text: "BRIGHTNESS" }
                            HudSlider {
                                id: brightSlider
                                Layout.preferredWidth: settingsPage.controlWidth
                                from: -1
                                to: 1
                                stepSize: 0.01
                                value: Theme.brightness
                                onMoved: Theme.brightness = value
                                markerPosition: 0.5
                                valueText: (Theme.brightness > 0 ? "+" : "") + Math.round(Theme.brightness * 100)
                                accessibleName: "Theme brightness"
                                trackGradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: Qt.hsla(Theme.hue, 1, 0.16, 1) }
                                    GradientStop { position: 0.5; color: Qt.hsla(Theme.hue, 1, 0.651, 1) }
                                    GradientStop { position: 1.0; color: Qt.hsla(Theme.hue, 1, 0.90, 1) }
                                }
                            }
                            FieldHint { text: "Lifts or deepens the palette. 0 is stock; negative darkens the console for use at the telescope, positive raises contrast on bright monitors." }
                            FieldLabel { text: "PALETTE" }
                            Row {
                                Layout.preferredWidth: settingsPage.controlWidth
                                spacing: 6
                                Repeater {
                                    model: [
                                        { name: "BASE", tint: Theme.windowBase },
                                        { name: "PANEL", tint: Theme.surface },
                                        { name: "RAISED", tint: Theme.surfaceHigh },
                                        { name: "LINE", tint: Theme.outline },
                                        { name: "DIM", tint: Theme.textSecondary },
                                        { name: "TEXT", tint: Theme.textPrimary },
                                        { name: "ACCENT", tint: Theme.accent }
                                    ]
                                    delegate: Column {
                                        required property var modelData
                                        spacing: 3
                                        Rectangle {
                                            width: 40
                                            height: 16
                                            radius: 2
                                            color: modelData.tint
                                            border.color: Theme.outline
                                            border.width: 1
                                        }
                                        Text {
                                            width: 40
                                            text: modelData.name
                                            color: Theme.textSecondary
                                            font.pixelSize: Theme.fontXs
                                            font.letterSpacing: 0.6
                                            horizontalAlignment: Text.AlignHCenter
                                        }
                                    }
                                }
                            }
                            FieldHint { text: "Live sample of the derived palette. The Windows title bar follows the panel and accent colours a moment after the sliders stop." }
                        }
                    }

                    // IMAGE
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Display-only clean-up for stacked frames. Nothing is written back to the telescope or to files on disk."
                        }
                        SettingGroup {
                            title: "ENHANCE"
                            trailing: [
                                HudChip {
                                    label: !Theme.enhanceImages ? "OFF" : (Theme.deepCleanImages ? "ON · DEEP CLEAN" : "ON · STANDARD")
                                    tone: Theme.enhanceImages ? Theme.success : Theme.textSecondary
                                    dim: !Theme.enhanceImages
                                    glow: Theme.enhanceImages
                                }
                            ]
                            FieldLabel { text: "FILTERS" }
                            HudCheck {
                                id: enhanceCheck
                                Layout.preferredWidth: settingsPage.controlWidth
                                text: "Enhance stacked frames"
                                checked: Theme.enhanceImages
                                onToggled: Theme.enhanceImages = checked
                                accessibleName: "Enhance stacked frames"
                            }
                            FieldHint { text: "Master switch for both filters below. It is the same setting as the ENHANCE badge over the live stack and the button in the Media viewer." }
                            FieldLabel { text: "PROFILE" }
                            HudCombo {
                                id: profileCombo
                                Layout.preferredWidth: settingsPage.controlWidth
                                model: ["Standard", "Deep clean"]
                                enabled: Theme.enhanceImages
                                currentIndex: Theme.deepCleanImages ? 1 : 0
                                onActivated: Theme.deepCleanImages = currentIndex === 1
                                accessibleName: "Enhance profile"
                            }
                            FieldHint { text: "Standard protects faint nebulosity and small stars. Deep clean smooths harder and pulls the sky further down; use it on short, very grainy stacks." }
                        }
                        SettingGroup {
                            title: "STRENGTH"
                            trailing: [
                                HudChip {
                                    label: settingsPage.enhanceCustom ? "ADJUSTED" : "FULL"
                                    tone: settingsPage.enhanceCustom ? Theme.warning : Theme.textSecondary
                                    dim: !settingsPage.enhanceCustom
                                    anchors.verticalCenter: parent.verticalCenter
                                },
                                HudButton {
                                    text: "RESET"
                                    implicitHeight: 28
                                    enabled: settingsPage.enhanceCustom
                                    Accessible.description: "Return denoise and sky crush to full strength"
                                    onClicked: {
                                        Theme.enhanceDenoise = 1
                                        Theme.enhanceSkyCrush = 1
                                    }
                                }
                            ]
                            FieldLabel { text: "DENOISE" }
                            HudSlider {
                                id: denoiseSlider
                                Layout.preferredWidth: settingsPage.controlWidth
                                from: 0
                                to: 1
                                stepSize: 0.01
                                enabled: Theme.enhanceImages
                                value: Theme.enhanceDenoise
                                onMoved: Theme.enhanceDenoise = value
                                valueText: Math.round(Theme.enhanceDenoise * 100) + "%"
                                accessibleName: "Enhance denoise"
                            }
                            FieldHint { text: "How hard sensor grain is smoothed. Works on the dark sky and eases off over stars and nebula so detail survives. 0% leaves the grain alone; 100% is the profile's full strength." }
                            FieldLabel { text: "SKY CRUSH" }
                            HudSlider {
                                id: skySlider
                                Layout.preferredWidth: settingsPage.controlWidth
                                from: 0
                                to: 1
                                stepSize: 0.01
                                enabled: Theme.enhanceImages
                                value: Theme.enhanceSkyCrush
                                onMoved: Theme.enhanceSkyCrush = value
                                valueText: Math.round(Theme.enhanceSkyCrush * 100) + "%"
                                accessibleName: "Enhance sky crush"
                            }
                            FieldHint { text: "How far the background is pulled toward black. The black point is measured from the frame's own sky and capped so the target is never clipped. 0% keeps the raw background level." }
                        }
                        FieldHint {
                            visible: !Theme.enhanceImages
                            emphasis: true
                            text: "Enhance is off. Profile and strength are kept but nothing is applied until it is switched back on."
                        }
                        FieldHint {
                            visible: Theme.enhanceImages
                            text: "Strength changes re-render the live stack and any open Media stack a moment after the slider stops."
                        }
                        SettingGroup {
                            title: "WHERE IT APPLIES"
                            FieldLabel { text: "LIVE STACK" }
                            HudChip {
                                label: Theme.enhanceImages ? "FILTERED" : "AS CAPTURED"
                                tone: Theme.enhanceImages ? Theme.success : Theme.textSecondary
                                dim: !Theme.enhanceImages
                                Layout.preferredWidth: settingsPage.numberWidth
                            }
                            FieldHint { text: "Stacked result shown on Control while the telescope is stacking. The plain live view is never filtered." }
                            FieldLabel { text: "MEDIA STACKS" }
                            HudChip {
                                label: Theme.enhanceImages ? "FILTERED" : "AS CAPTURED"
                                tone: Theme.enhanceImages ? Theme.success : Theme.textSecondary
                                dim: !Theme.enhanceImages
                                Layout.preferredWidth: settingsPage.numberWidth
                            }
                            FieldHint { text: "Stacks from the telescope album and local *_stacked files opened in the Media viewer. Grid thumbnails stay raw." }
                            FieldLabel { text: "STILLS · VIDEO" }
                            HudChip {
                                label: "AS CAPTURED"
                                tone: Theme.textSecondary
                                dim: true
                                Layout.preferredWidth: settingsPage.numberWidth
                            }
                            FieldHint { text: "Single photos, bursts and video are never filtered." }
                            FieldLabel { text: "FILES" }
                            HudChip {
                                label: "UNCHANGED"
                                tone: Theme.textSecondary
                                dim: true
                                Layout.preferredWidth: settingsPage.numberWidth
                            }
                            FieldHint { text: "Originals on the telescope and on disk are left as they are; only what is drawn on screen changes." }
                        }
                    }

                    // OBSERVING
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Shared by every telescope in this app and saved as soon as it is changed."
                        }
                        SettingGroup {
                            title: "CALENDAR"
                            FieldLabel { text: "NIGHT CUTOFF" }
                            SpinBox {
                                id: cutoffField
                                Layout.preferredWidth: settingsPage.numberWidth
                                from: 0
                                to: 23
                                value: 12
                                editable: true
                                palette.text: Theme.textPrimary
                                palette.base: Theme.inputBg
                                palette.button: Theme.surfaceHigh
                                palette.buttonText: Theme.accent
                                palette.highlight: Theme.accent
                                textFromValue: (value, locale) => String(value).padStart(2, "0") + ":00"
                                valueFromText: (text, locale) => {
                                    const n = parseInt(String(text).trim(), 10)
                                    return isNaN(n) ? cutoffField.value : Math.max(cutoffField.from, Math.min(cutoffField.to, n))
                                }
                                validator: RegularExpressionValidator { regularExpression: /^\d{1,2}(:\d{0,2})?$/ }
                                Accessible.name: "Observing night cutoff hour"
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
                            FieldHint {
                                text: "Local hour when the calendar rolls to the next observing night. With "
                                      + String(cutoffField.value).padStart(2, "0") + ":00, a session at "
                                      + String((cutoffField.value + 23) % 24).padStart(2, "0") + ":30 still belongs to the previous evening."
                            }
                        }
                        SettingGroup {
                            title: "INTEGRATIONS"
                            FieldLabel { text: "STELLARIUM" }
                            HudField {
                                id: stellariumField
                                Layout.preferredWidth: settingsPage.controlWidth
                                placeholderText: "http://localhost:8090"
                                accessibleName: "Stellarium remote control URL"
                                onEditingFinished: backend.setStellariumUrl(text)
                            }
                            FieldHint { text: "Address of Stellarium's Remote Control plugin. Sessions can pull the object currently selected in Stellarium from here." }
                        }
                    }

                    // DEVICE
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Identity and observing site for the selected telescope. Site coordinates are sent to the mount and drive altitude checks in the calendar."
                        }
                        SettingGroup {
                            title: "IDENTITY"
                            FieldLabel { text: "NAME" }
                            HudField { id: nameField; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Telescope name" }
                            FieldHint { text: "Shown in the device bar, calendar, session lists and logs." }
                            FieldLabel { text: "MODEL" }
                            HudCombo { id: modelField; model: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Telescope model" }
                            FieldHint { text: "Selects the firmware profile and lens set. Dwarf 3 exposes a fixed-focus wide camera alongside the telephoto." }
                            FieldLabel { text: "CAMERA" }
                            HudCombo { id: cameraField; model: ["Tele", "Wide"]; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Default camera" }
                            FieldHint { text: "Default lens for new sessions on this telescope. Focus controls act on Tele only; Wide has no focus motor." }
                        }
                        SettingGroup {
                            title: "SITE"
                            trailing: [
                                HudChip {
                                    value: settingsPage.formatCoordinate(latField.text, "N", "S") + "  " + settingsPage.formatCoordinate(lonField.text, "E", "W")
                                    tone: Theme.textSecondary
                                    dim: true
                                }
                            ]
                            FieldLabel { text: "TIMEZONE" }
                            HudSearchCombo {
                                id: timezoneField
                                Layout.preferredWidth: settingsPage.controlWidth
                                allItems: backend.timezones
                                onItemChosen: (item) => settingsPage.applyLocation(item)
                            }
                            FieldHint { text: "Search a city to fill timezone and coordinates together. Sets local session times and the night cutoff for this telescope." }
                            FieldLabel { text: "LATITUDE" }
                            HudField { id: latField; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Site latitude"; placeholderText: "-37.81" }
                            FieldHint { text: "Decimal degrees; south is negative." }
                            FieldLabel { text: "LONGITUDE" }
                            HudField { id: lonField; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Site longitude"; placeholderText: "144.96" }
                            FieldHint { text: "Decimal degrees; west is negative." }
                        }
                    }

                    // CAPTURE
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Starting values for new sessions and imported targets on this telescope. Each session can still override them."
                        }
                        SettingGroup {
                            title: "DEFAULTS"
                            trailing: [
                                HudChip {
                                    label: "INTEGRATION"
                                    value: settingsPage.formatSeconds(settingsPage.defaultIntegration)
                                    tone: Theme.accent
                                }
                            ]
                            FieldLabel { text: "EXPOSURE S" }
                            HudField {
                                id: exposureDefaultField
                                Layout.preferredWidth: settingsPage.numberWidth
                                placeholderText: String(Util.stockExposureSeconds)
                                accessibleName: "Default exposure seconds"
                            }
                            FieldHint { text: "Seconds per frame. Stock " + Util.stockExposureSeconds + " s; longer frames gather more signal but need clean tracking." }
                            FieldLabel { text: "GAIN" }
                            HudField {
                                id: gainDefaultField
                                Layout.preferredWidth: settingsPage.numberWidth
                                placeholderText: String(Util.stockGain)
                                accessibleName: "Default gain"
                            }
                            FieldHint { text: "Sensor gain per frame. Stock " + Util.stockGain + "; higher lifts faint detail and grain together." }
                            FieldLabel { text: "FRAMES" }
                            HudField {
                                id: framesDefaultField
                                Layout.preferredWidth: settingsPage.numberWidth
                                placeholderText: String(Util.stockFrameCount)
                                accessibleName: "Default frame count"
                            }
                            FieldHint { text: "Frames stacked per session. Stock " + Util.stockFrameCount + ". Total integration is exposure × frames." }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "A default session integrates " + framesDefaultField.text + " × " + exposureDefaultField.text + " s = "
                                  + settingsPage.formatSeconds(settingsPage.defaultIntegration)
                                  + "  ·  about " + settingsPage.formatSeconds(settingsPage.defaultWallClock)
                                  + " of imaging with " + readoutField.text + " s readout per frame (Timing)."
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                    }

                    // CONNECT
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "How this computer reaches the telescope. Commands and the live stream travel over Wi-Fi; Bluetooth is only used to set up that link."
                        }
                        SettingGroup {
                            title: "WI-FI LINK"
                            FieldLabel { text: "IP ADDRESS" }
                            HudField { id: ipField; Layout.preferredWidth: settingsPage.controlWidth; placeholderText: "192.168.88.1 or LAN IP"; accessibleName: "Telescope IP address" }
                            FieldHint { text: "Address the app connects to. Hotspot mode is 192.168.88.1; on a router use the address it leased. Filled in automatically once Bluetooth reports it." }
                            FieldLabel { text: "WIFI MODE" }
                            HudCombo { id: wifiModeField; model: ["Auto", "AP hotspot", "STA station"]; Layout.preferredWidth: settingsPage.controlWidth; accessibleName: "Wi-Fi connection mode" }
                            FieldHint {
                                text: wifiModeField.currentIndex === 1
                                    ? "AP: this computer joins the telescope's own hotspot. Simple, but no internet while connected."
                                    : wifiModeField.currentIndex === 2
                                        ? "STA: Bluetooth tells the telescope to join your router. This computer must already be on that Wi-Fi."
                                        : "Auto keeps whatever mode the telescope is already in and connects to it."
                            }
                            FieldLabel { text: "ROUTER SSID"; visible: wifiModeField.currentIndex === 2 }
                            HudField {
                                id: ssidField
                                Layout.preferredWidth: settingsPage.controlWidth
                                visible: wifiModeField.currentIndex === 2
                                placeholderText: "Router name, not DWARF3_…"
                                accessibleName: "Router Wi-Fi name"
                            }
                            FieldHint { visible: wifiModeField.currentIndex === 2; text: "The router network the telescope should join, exactly as it is broadcast." }
                            FieldLabel { text: wifiModeField.currentIndex === 1 ? "HOTSPOT PASS" : "ROUTER PASS"; visible: wifiModeField.currentIndex !== 0 }
                            HudField {
                                id: wifiField
                                echoMode: TextInput.Password
                                Layout.preferredWidth: settingsPage.controlWidth
                                visible: wifiModeField.currentIndex !== 0
                                placeholderText: wifiModeField.currentIndex === 1 ? "Leave empty to use the Bluetooth password" : ""
                                accessibleName: wifiModeField.currentIndex === 1 ? "Hotspot password" : "Router Wi-Fi password"
                            }
                            FieldHint {
                                visible: wifiModeField.currentIndex !== 0
                                text: wifiModeField.currentIndex === 1
                                    ? "Password for the telescope's hotspot. Empty reuses the Bluetooth password."
                                    : "Password for the router network above; sent to the telescope over Bluetooth."
                            }
                        }
                        SettingGroup {
                            title: "BLUETOOTH"
                            FieldLabel { text: "BLE PASSWORD" }
                            HudField {
                                id: blePasswordField
                                echoMode: TextInput.Password
                                Layout.preferredWidth: settingsPage.controlWidth
                                placeholderText: "Factory default DWARF_12345678"
                                accessibleName: "Bluetooth password"
                            }
                            FieldHint { text: "Pairing password from the DWARF app. Factory default is DWARF_12345678." }
                            FieldLabel { text: "FALLBACK" }
                            HudCheck {
                                id: bleField
                                Layout.preferredWidth: settingsPage.controlWidth
                                text: "Use Bluetooth when Wi-Fi fails"
                                accessibleName: "Use Bluetooth when the IP is empty or unreachable"
                            }
                            FieldHint { text: "When the IP is empty or unreachable, connect over Bluetooth to set the Wi-Fi mode and learn the address before retrying." }
                        }
                    }

                    // TIMING
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Fixed overheads used to size calendar blocks and remaining-time estimates. After a few completed sessions the app measures these and suggests corrections here."
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
                        SettingGroup {
                            title: "SETUP"
                            trailing: [
                                HudChip {
                                    label: "FULL SETUP"
                                    value: settingsPage.formatSeconds(settingsPage.setupOverhead)
                                    tone: Theme.accent
                                }
                            ]
                            FieldLabel { text: "STARTUP S" }
                            HudField { id: startupField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Startup seconds" }
                            FieldHint { text: "Power-on and connect until the telescope accepts commands. Paid once per session." }
                            FieldLabel { text: "SLEW S" }
                            HudField { id: slewField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Slew seconds" }
                            FieldHint { text: "GoTo move to the target." }
                            FieldLabel { text: "SETTLE S" }
                            HudField { id: settleField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Settle seconds" }
                            FieldHint { text: "Pause after the slew before imaging starts." }
                            FieldLabel { text: "CALIBRATE S" }
                            HudField { id: calibrationField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Calibration seconds" }
                            FieldHint { text: "Plate-solve calibration, when the session workflow asks for it." }
                            FieldLabel { text: "AUTOFOCUS S" }
                            HudField { id: autofocusField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Autofocus seconds" }
                            FieldHint { text: "Astronomical autofocus run on the telephoto lens." }
                            FieldLabel { text: "INFINITY S" }
                            HudField { id: infinityField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Infinity focus seconds" }
                            FieldHint { text: "Infinity focus step, when selected instead of or before autofocus." }
                            FieldLabel { text: "POLAR S" }
                            HudField { id: polarField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Polar alignment seconds" }
                            FieldHint { text: "Polar alignment routine, when the workflow includes it." }
                        }
                        SettingGroup {
                            title: "IMAGING"
                            FieldLabel { text: "READOUT S" }
                            HudField { id: readoutField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Readout seconds per frame" }
                            FieldHint { text: "Added to every frame on top of its exposure. Small per frame, but it scales with the frame count." }
                            FieldLabel { text: "PANE SLEW S" }
                            HudField { id: paneField; Layout.preferredWidth: settingsPage.numberWidth; accessibleName: "Pane slew seconds" }
                            FieldHint { text: "Move between mosaic panes; counted once per pane change." }
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "A full-workflow session pays about " + settingsPage.formatSeconds(settingsPage.setupOverhead)
                                  + " before the first frame; each frame then takes exposure + " + readoutField.text + " s."
                            color: Theme.textPrimary
                            font.family: Theme.fontMono
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                    }

                    // IMPORT
                    ColumnLayout {
                        spacing: Theme.s3
                        FieldHint {
                            text: "Bring sessions from the old Astro_Sessions scheduler onto the selected telescope. The old files are only read, never changed."
                        }
                        SettingGroup {
                            title: "LEGACY SESSIONS"
                            FieldLabel { text: "SOURCE" }
                            HudButton {
                                text: "CHOOSE FOLDER…"
                                busyText: "OPENING…"
                                onClicked: legacyDialog.open()
                            }
                            FieldHint { text: "Pick the folder holding the old app's JSON session files. Imported sessions appear on " + (nameField.text || "this telescope") + "'s calendar." }
                        }
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
