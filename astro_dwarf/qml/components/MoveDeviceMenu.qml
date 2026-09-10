import QtQuick
import QtQuick.Controls
import QtQml
import ".."

HudMenu {
    id: moveMenu
    title: "Move to"
    property var sessionIds: []
    enabled: !!(backend && (backend.devices || []).length > 1 && (moveMenu.sessionIds || []).length > 0)

    Instantiator {
        model: (backend && backend.devices) || []
        delegate: Action {
            required property var modelData
            text: modelData.name
            enabled: (moveMenu.sessionIds || []).length > 0
            onTriggered: backend.assignSessionsDevice(moveMenu.sessionIds, modelData.id)
        }
        onObjectAdded: (index, object) => moveMenu.insertAction(index, object)
        onObjectRemoved: (_, object) => moveMenu.removeAction(object)
    }
}
