import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: root
    required property var dragItem
    property var pressedAction: null
    signal editRequested(var session)
    readonly property bool canEdit: String((dragItem && dragItem.status) || "") !== "running"
    Accessible.role: Accessible.Button
    Accessible.name: {
        const item = root.dragItem || {}
        const when = item.start_time || ""
        const label = item.pane_name || item.target_name || "Session"
        return (when ? when + " " : "") + label
    }
    Accessible.description: root.canEdit ? "Drag to reschedule, double-click to edit" : "Running"

    TapHandler {
        parent: root.parent
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        enabled: root.canEdit
        grabPermissions: PointerHandler.CanTakeOverFromAnything | PointerHandler.ApprovesTakeOverByAnything
        onDoubleTapped: root.editRequested(root.dragItem)
    }

    DragHandler {
        id: drag
        parent: root.parent
        target: null
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        cursorShape: Qt.ClosedHandCursor
        enabled: root.canEdit
        property bool started: false

        function mappedPos() {
            return parent.mapToItem(DragCoordinator.contentItem, centroid.position.x, centroid.position.y)
        }

        onActiveChanged: {
            if (active) {
                started = true
                if (root.pressedAction)
                    root.pressedAction()
                DragCoordinator.startDrag(root.dragItem, mappedPos(), centroid.position.y)
            } else if (started) {
                started = false
                DragCoordinator.completeDrag(mappedPos())
            }
        }
        onTranslationChanged: {
            if (active)
                DragCoordinator.moveDrag(mappedPos())
        }
        onCanceled: {
            if (started) {
                started = false
                DragCoordinator.cancelDrag()
            }
        }
    }
}
