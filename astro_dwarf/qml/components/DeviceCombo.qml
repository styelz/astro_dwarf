import QtQuick
import QtQuick.Controls

HudCombo {
    id: deviceCombo
    model: backend.devices
    textRole: "name"
    valueRole: "id"
    implicitWidth: 200
    onActivated: if (currentValue) backend.selectDevice(currentValue)

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

    Component.onCompleted: sync()
    Connections {
        target: backend
        function onSelectedDeviceChanged() { deviceCombo.sync() }
        function onDevicesChanged() { deviceCombo.sync() }
    }
}
