import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import ".."
import "../components"

Dialog {
    id: locationDialog
    objectName: "locationDialog"
    property bool addingDevice: false
    property var foundDevices: []
    property var foundLabels: []
    property string foundSsid: ""
    property string discoveryStatus: ""
    property color discoveryTone: Theme.textSecondary
    readonly property var wifiModeOptions: ["Auto", "AP hotspot", "STA station"]
    readonly property var wifiModeValues: ["auto", "ap", "sta"]
    readonly property bool locationRequired: !addingDevice && !backend.selectedDevice.location_configured
    readonly property var modelOptions: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]
    modal: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: 560
    padding: Theme.s4
    height: Math.min(root.height - 60, locationColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
    function wifiModeIndex(mode) {
        return Math.max(0, locationDialog.wifiModeValues.indexOf(String(mode || "auto").toLowerCase()))
    }
    function wifiModeValue() {
        return locationDialog.wifiModeValues[addWifiMode.currentIndex] || "auto"
    }
    function foundLabel(item) {
        if (!item)
            return "Telescope"
        const parts = [item.name || "Telescope"]
        if (item.ip_address)
            parts.push(item.ip_address)
        if (item.wifi_mode && item.wifi_mode !== "auto")
            parts.push(String(item.wifi_mode).toUpperCase())
        return parts.join("  ·  ")
    }
    function discoverySummary(item) {
        if (!item)
            return ""
        if (item.error)
            return item.error
        const mode = item.wifi_mode === "ap" ? "AP hotspot" : item.wifi_mode === "sta" ? "STA station" : "Auto"
        const parts = []
        if (item.name)
            parts.push(item.name)
        parts.push(mode)
        if (item.ip_address)
            parts.push(item.ip_address)
        else
            parts.push("IP not reported")
        if (item.wifi_ssid)
            parts.push(item.wifi_ssid)
        return parts.join("  ·  ")
    }
    function applyFoundDevice(item) {
        if (!item)
            return
        if (!String(addName.text).trim() && item.name)
            addName.text = item.name
        if (item.model) {
            const idx = locationDialog.modelOptions.indexOf(item.model)
            if (idx >= 0)
                locationModel.currentIndex = idx
        }
        if (item.ip_address)
            addIp.text = item.ip_address
        addWifiMode.currentIndex = locationDialog.wifiModeIndex(item.wifi_mode)
        locationDialog.foundSsid = item.wifi_ssid || ""
        locationDialog.discoveryStatus = locationDialog.discoverySummary(item)
        locationDialog.discoveryTone = item.error ? Theme.warning : item.ip_address ? Theme.success : Theme.warning
    }
    function applyDiscovery(items) {
        const list = items || []
        const labels = []
        for (let i = 0; i < list.length; i++)
            labels.push(locationDialog.foundLabel(list[i]))
        locationDialog.foundDevices = list
        locationDialog.foundLabels = labels
        if (!list.length) {
            locationDialog.discoveryStatus = "No Dwarf found over Bluetooth."
            locationDialog.discoveryTone = Theme.warning
            return
        }
        let chosen = 0
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].ip_address) {
                chosen = i
                break
            }
        }
        foundCombo.currentIndex = chosen
        locationDialog.applyFoundDevice(list[chosen])
    }
    function resetAddFields() {
        addName.text = ""
        addIp.text = ""
        addWifiMode.currentIndex = 0
        addBlePassword.text = "DWARF_12345678"
        addColor.assignUnused()
        locationDialog.foundDevices = []
        locationDialog.foundLabels = []
        locationDialog.foundSsid = ""
        locationDialog.discoveryStatus = ""
        locationDialog.discoveryTone = Theme.textSecondary
        foundCombo.currentIndex = 0
    }
    function openForAdd() {
        addingDevice = true
        open()
    }
    function applyLocation(item) {
        if (!item)
            return
        locationTimezone.setFromName(item.name)
        if (item.latitude !== undefined && item.latitude !== null)
            locationLat.text = Number(item.latitude).toFixed(5)
        if (item.longitude !== undefined && item.longitude !== null)
            locationLon.text = Number(item.longitude).toFixed(5)
    }
    onClosed: {
        addingDevice = false
        addColor.dismiss()
        backend.cancelNearbyDiscovery()
        Qt.callLater(root.maybeAskLocation)
    }
    onOpened: {
        const d = backend.selectedDevice
        locationModel.currentIndex = Math.max(0, locationDialog.modelOptions.indexOf(d.model || "Dwarf 3"))
        const lat = Number(d.latitude || 0)
        const lon = Number(d.longitude || 0)
        const hasCoords = Math.abs(lat) > 1e-9 || Math.abs(lon) > 1e-9
        if (locationDialog.addingDevice)
            locationDialog.resetAddFields()
        if (!addingDevice && hasCoords) {
            locationTimezone.setFromName(d.timezone_name || "")
            locationLat.text = d.latitude
            locationLon.text = d.longitude
        } else {
            const suggestion = backend.suggestedLocation
            if (suggestion && suggestion.name) {
                locationDialog.applyLocation(suggestion)
            } else {
                locationTimezone.setFromName("")
                locationLat.text = ""
                locationLon.text = ""
            }
        }
    }
    Connections {
        target: backend
        function onDeviceDiscoveryReady(items) {
            if (locationDialog.addingDevice && locationDialog.visible)
                locationDialog.applyDiscovery(items)
        }
    }
    contentItem: Flickable {
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: locationColumn.implicitHeight
        interactive: contentHeight > height + 1
        ColumnLayout {
            id: locationColumn
            width: parent.width
            spacing: Theme.s3
            Accessible.name: locationDialog.addingDevice ? "Add device" : "Observing location"

            Text {
                text: locationDialog.addingDevice ? "ADD DEVICE" : "OBSERVING LOCATION"
                color: Theme.accent
                font.pixelSize: Theme.fontLg
                font.letterSpacing: Theme.tracking2
            }
            Text {
                text: locationDialog.addingDevice
                    ? "Name the telescope, pick a marker colour, then scan Bluetooth to fill IP and Wi-Fi mode. Choose a timezone or city. Nothing is created until you save."
                    : "Choose the telescope model and a timezone or city so Astro Dwarf can set longitude and latitude. A location is required before connecting or running sessions."
                color: Theme.textPrimary
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: Theme.s3
                rowSpacing: Theme.s2

                FieldLabel { visible: locationDialog.addingDevice; text: "NAME" }
                HudField {
                    id: addName
                    visible: locationDialog.addingDevice
                    Layout.fillWidth: true
                    placeholderText: "Optional — used in the device list"
                    accessibleName: "Telescope name"
                }

                FieldLabel { visible: locationDialog.addingDevice; text: "COLOUR" }
                DeviceColorField {
                    id: addColor
                    visible: locationDialog.addingDevice
                    Layout.fillWidth: true
                    roleName: String(addName.text).trim() ? String(addName.text).trim().toUpperCase() : "DEVICE DOT"
                }
                FieldHint {
                    visible: locationDialog.addingDevice
                    Layout.columnSpan: 2
                    Layout.minimumWidth: 0
                    text: "Dot on this telescope in the device bar, calendar and session lists."
                }

                FieldLabel { text: "MODEL" }
                HudCombo {
                    id: locationModel
                    Layout.fillWidth: true
                    model: locationDialog.modelOptions
                    accessibleName: "Telescope model"
                }

                FieldLabel { visible: locationDialog.addingDevice; text: "BLE PASS" }
                RowLayout {
                    visible: locationDialog.addingDevice
                    Layout.fillWidth: true
                    spacing: Theme.s2
                    HudField {
                        id: addBlePassword
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        placeholderText: "DWARF_12345678"
                        accessibleName: "Bluetooth password"
                    }
                    HudButton {
                        text: "DISCOVER"
                        busy: backend.deviceDiscoveryBusy
                        busyText: "SCANNING…"
                        busyMs: 0
                        enabled: !backend.deviceDiscoveryBusy
                        buttonColor: Theme.fillActive
                        foregroundColor: Theme.accent
                        accessibleDescription: "Scan Bluetooth to learn this telescope's IP and Wi-Fi mode"
                        onClicked: backend.discoverNearbyDevice(JSON.stringify({
                            model: locationModel.currentText,
                            ble_password: addBlePassword.text
                        }))
                    }
                }
                FieldHint {
                    visible: locationDialog.addingDevice
                    Layout.columnSpan: 2
                    Layout.minimumWidth: 0
                    text: "Power the telescope on and keep it near this computer. Discovery reads the current Wi-Fi mode and address; it does not change them."
                }

                HudCombo {
                    id: foundCombo
                    visible: locationDialog.addingDevice && locationDialog.foundDevices.length > 1
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                    model: locationDialog.foundLabels
                    accessibleName: "Discovered telescope"
                    onActivated: locationDialog.applyFoundDevice(locationDialog.foundDevices[currentIndex])
                }
                Text {
                    visible: locationDialog.addingDevice && locationDialog.discoveryStatus.length > 0
                    text: locationDialog.discoveryStatus
                    color: locationDialog.discoveryTone
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fontSm
                    font.family: Theme.fontMono
                    Layout.fillWidth: true
                    Layout.columnSpan: 2
                }

                FieldLabel { visible: locationDialog.addingDevice; text: "IP" }
                HudField {
                    id: addIp
                    visible: locationDialog.addingDevice
                    Layout.fillWidth: true
                    placeholderText: "192.168.88.1 or LAN IP"
                    accessibleName: "Telescope IP address"
                }

                FieldLabel { visible: locationDialog.addingDevice; text: "MODE" }
                HudCombo {
                    id: addWifiMode
                    visible: locationDialog.addingDevice
                    Layout.fillWidth: true
                    model: locationDialog.wifiModeOptions
                    accessibleName: "Wi-Fi connection mode"
                }
                FieldHint {
                    visible: locationDialog.addingDevice
                    Layout.columnSpan: 2
                    Layout.minimumWidth: 0
                    text: addWifiMode.currentIndex === 1
                        ? "AP: this computer joins the telescope's own hotspot."
                        : addWifiMode.currentIndex === 2
                            ? "STA: the telescope is on your router. This computer must be on that same Wi-Fi."
                            : "Auto keeps whatever mode the telescope is already in."
                }

                FieldLabel { text: "TIMEZONE" }
                HudSearchCombo {
                    id: locationTimezone
                    Layout.fillWidth: true
                    accessibleName: "Timezone or city"
                    allItems: backend.timezones
                    onItemChosen: (item) => locationDialog.applyLocation(item)
                }

                FieldLabel { text: "LAT / LON" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.s2
                    HudField { id: locationLat; Layout.fillWidth: true; readOnly: true; accessibleName: "Site latitude" }
                    HudField { id: locationLon; Layout.fillWidth: true; readOnly: true; accessibleName: "Site longitude" }
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignRight
                Layout.topMargin: Theme.s1
                spacing: Theme.s2
                HudButton {
                    text: "CANCEL"
                    visible: !locationDialog.locationRequired
                    onClicked: locationDialog.close()
                }
                HudButton {
                    text: locationDialog.addingDevice ? "ADD DEVICE" : "SAVE LOCATION"
                    enabled: {
                        if (locationDialog.addingDevice && backend.deviceDiscoveryBusy)
                            return false
                        const lat = Number(locationLat.text)
                        const lon = Number(locationLon.text)
                        const named = locationTimezone.selectedName.length > 0 || locationTimezone.editText.length > 0
                        return named && (Math.abs(lat) > 1e-9 || Math.abs(lon) > 1e-9)
                    }
                    busyText: locationDialog.addingDevice ? "ADDING…" : "SAVING…"
                    buttonColor: Theme.fillActive
                    foregroundColor: Theme.accent
                    onClicked: {
                        const payload = JSON.stringify({
                            id: locationDialog.addingDevice ? "" : backend.selectedDeviceId,
                            name: addName.text,
                            model: locationModel.currentText,
                            timezone_name: locationTimezone.selectedName || locationTimezone.editText,
                            latitude: Number(locationLat.text),
                            longitude: Number(locationLon.text),
                            ip_address: addIp.text,
                            wifi_mode: locationDialog.wifiModeValue(),
                            wifi_ssid: locationDialog.foundSsid,
                            ble_password: addBlePassword.text,
                            color: addColor.colorHex
                        })
                        if (locationDialog.addingDevice) {
                            if (backend.addDevice(payload))
                                locationDialog.close()
                        } else if (backend.saveObservingLocation(payload)) {
                            locationDialog.close()
                        }
                    }
                }
            }
        }
    }
}
