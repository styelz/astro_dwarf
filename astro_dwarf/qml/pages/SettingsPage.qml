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
            if (settingsPage.loadedDeviceId !== backend.selectedDeviceId || !settingsPage.dirty)
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
                HudButton { text: "+ ADD DEVICE"; busyText: "ADDING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: locationDialog.openForAdd() }
                HudButton { text: "REMOVE DEVICE"; busyText: "REMOVING…"; buttonColor: Theme.fillDanger; foregroundColor: Theme.danger; onClicked: root.confirmRemoveDevice(backend.selectedDeviceId) }
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
                                    // marker for the stock cyan
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
                    Item { implicitWidth: 1; implicitHeight: 1 }
                    Item { implicitWidth: 1; implicitHeight: 1 }
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
                                    // dim → stock → bright, in the current hue (ends match Theme.accent at ±1)
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: Qt.hsla(Theme.hue, 1, 0.16, 1) }
                                    GradientStop { position: 0.5; color: Qt.hsla(Theme.hue, 1, 0.651, 1) }
                                    GradientStop { position: 1.0; color: Qt.hsla(Theme.hue, 1, 0.90, 1) }
                                }
                                Rectangle {
                                    // stock mark
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
                }
                Text {
                    text: "Applies immediately. Choose where the page buttons sit, drag the hue slider to re-tint the whole console (the tick marks the stock cyan), and pull brightness down to dim the text, accents and glow for night use, or up for a lighter glow."
                    color: Theme.textSecondary
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
                        tone: backend.selectedDevice.connected ? Theme.success : Theme.textSecondary
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
                        palette.text: Theme.textPrimary
                        palette.base: Theme.inputBg
                        palette.button: Theme.surfaceHigh
                        palette.buttonText: Theme.accent
                        palette.highlight: Theme.accent
                    }
                }
            }
            HudPanel {
                title: "⇌  CONNECTION"
                width: parent.width
                Text {
                    text: "Bluetooth finds the telescope and sets its Wi‑Fi. In AP mode this app then joins the Dwarf hotspot on this computer. Commands and the live stream always use that Wi‑Fi link."
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
                    Text {
                        Layout.fillWidth: true
                        Layout.columnSpan: 4
                        wrapMode: Text.Wrap
                        color: Theme.textSecondary
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
                Text { text: "These overheads size calendar blocks and remaining-time estimates."; color: Theme.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
                        Text { text: "Import old Astro_Sessions JSON without modifying the old app."; color: Theme.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
                    ? "UNSAVED CHANGES · " + (backend.selectedDevice.name || "device").toUpperCase()
                    : "ALL CHANGES SAVED · " + (backend.selectedDevice.name || "device").toUpperCase()
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
