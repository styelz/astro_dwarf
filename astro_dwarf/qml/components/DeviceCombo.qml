pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

HudCombo {
    id: deviceCombo
    // Telemetry flushes re-emit devicesChanged. A new array resets the model,
    // so keep the last list until an id, name, or colour changes.
    property var deviceList: []
    property string deviceListKey: ""
    model: deviceCombo.deviceList
    textRole: "name"
    valueRole: "id"
    implicitWidth: Theme.px(200)
    onActivated: if (currentValue) backend.selectDevice(currentValue)

    function refreshDevices() {
        const source = backend.devices
        const devices = source ? source.map(item => ({ id: item.id, name: item.name, color: item.color })) : []
        const key = JSON.stringify(devices)
        if (key === deviceCombo.deviceListKey)
            return
        deviceCombo.deviceListKey = key
        deviceCombo.deviceList = devices
    }

    function colorAt(index) {
        const devices = deviceCombo.deviceList
        if (index < 0 || index >= deviceCombo.count)
            return Theme.muted
        const id = deviceCombo.valueAt(index)
        for (let i = 0; i < devices.length; i++) {
            if (String(devices[i].id || "") === String(id || ""))
                return devices[i].color || Theme.muted
        }
        return Theme.muted
    }

    function sync() {
        if (deviceCombo.count === 0)
            return
        for (let i = 0; i < deviceCombo.count; i++) {
            if (deviceCombo.valueAt(i) === backend.selectedDeviceId) {
                deviceCombo.currentIndex = i
                return
            }
        }
    }

    Component.onCompleted: {
        deviceCombo.refreshDevices()
        deviceCombo.sync()
    }
    Connections {
        target: backend
        function onSelectedDeviceChanged() { deviceCombo.sync() }
        function onDevicesChanged() {
            deviceCombo.refreshDevices()
            deviceCombo.sync()
        }
    }

    contentItem: RowLayout {
        spacing: Theme.px(7)
        Rectangle {
            Layout.alignment: Qt.AlignVCenter
            Layout.leftMargin: Theme.px(10)
            Layout.preferredWidth: Theme.s2
            Layout.preferredHeight: Theme.s2
            visible: deviceCombo.currentIndex >= 0
            radius: width / 2
            color: deviceCombo.colorAt(deviceCombo.currentIndex)
        }
        Text {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            Layout.rightMargin: Theme.px(22)
            text: deviceCombo.displayText
            color: deviceCombo.enabled ? Theme.textPrimary : Theme.textSecondary
            font: deviceCombo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    delegate: ItemDelegate {
        id: optionItem
        required property int index
        width: deviceCombo.width
        height: Theme.px(32)
        leftPadding: Theme.px(10)
        rightPadding: Theme.px(8)
        highlighted: deviceCombo.highlightedIndex === index
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.text: Theme.textPrimary
        palette.highlightedText: Theme.accent
        contentItem: RowLayout {
            spacing: Theme.px(7)
            Rectangle {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: Theme.s2
                Layout.preferredHeight: Theme.s2
                radius: width / 2
                color: deviceCombo.colorAt(optionItem.index)
            }
            Text {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                text: deviceCombo.textAt(optionItem.index)
                color: optionItem.highlighted ? Theme.accent : Theme.textPrimary
                font.pixelSize: Theme.fontBase
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }
        background: Rectangle { color: optionItem.highlighted ? Theme.fillChecked : Theme.popupBg }
    }
}
