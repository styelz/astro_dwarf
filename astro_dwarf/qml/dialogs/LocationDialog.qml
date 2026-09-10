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
    property bool addingDevice: false
    modal: true
    closePolicy: Popup.NoAutoClose
    anchors.centerIn: Overlay.overlay
    width: 520
    padding: 18
    height: Math.min(root.height - 60, locationColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
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
    readonly property var modelOptions: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]
    onClosed: addingDevice = false
    onOpened: {
        const d = backend.selectedDevice
        locationModel.currentIndex = Math.max(0, locationDialog.modelOptions.indexOf(d.model || "Dwarf 3"))
        const lat = Number(d.latitude || 0)
        const lon = Number(d.longitude || 0)
        const hasCoords = Math.abs(lat) > 1e-9 || Math.abs(lon) > 1e-9
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
    contentItem: ColumnLayout {
        id: locationColumn
        spacing: 12
        Text { text: locationDialog.addingDevice ? "ADD DEVICE" : "OBSERVING LOCATION"; color: Theme.accent; font.pixelSize: 16; font.letterSpacing: 1.4 }
        Text {
            text: locationDialog.addingDevice
                ? "Choose the telescope model and a timezone or city. Nothing is created until you save."
                : "Choose the telescope model and a timezone or city so Astro Dwarf can set longitude and latitude. A location is required before connecting or running sessions."
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        FieldLabel { text: "MODEL" }
        HudCombo {
            id: locationModel
            Layout.fillWidth: true
            model: locationDialog.modelOptions
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
            HudButton { text: "CANCEL"; onClicked: locationDialog.close() }
            HudButton {
                text: locationDialog.addingDevice ? "ADD DEVICE" : "SAVE LOCATION"
                enabled: {
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
                        model: locationModel.currentText,
                        timezone_name: locationTimezone.selectedName || locationTimezone.editText,
                        latitude: Number(locationLat.text),
                        longitude: Number(locationLon.text)
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
