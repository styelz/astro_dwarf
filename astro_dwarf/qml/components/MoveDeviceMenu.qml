import QtQuick
import QtQuick.Controls
import QtQml
import ".."

HudMenu {
    id: moveMenu
    title: "Move to"
    property var sessionIds: []
    enabled: (backend.devices || []).length > 1 && (moveMenu.sessionIds || []).length > 0

    Instantiator {
        model: backend.devices
        delegate: HudMenuItem {
            required property var modelData
            text: modelData.name
            enabled: (moveMenu.sessionIds || []).length > 0
            onTriggered: backend.assignSessionsDevice(moveMenu.sessionIds, modelData.id)
        }
        onObjectAdded: (index, object) => moveMenu.insertItem(index, object)
        onObjectRemoved: (_, object) => moveMenu.removeItem(object)
    }
}
