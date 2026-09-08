import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

DragHandler {
    id: drag
    required property var dragItem
    property var pressedAction: null
    signal editRequested(var session)
    target: null
    acceptedButtons: Qt.LeftButton
    acceptedModifiers: Qt.NoModifier
    cursorShape: Qt.ClosedHandCursor
    enabled: String((dragItem && dragItem.status) || "") !== "running"
    property bool started: false

    TapHandler {
        id: editTap
        parent: drag.parent
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        enabled: drag.enabled
        grabPermissions: PointerHandler.CanTakeOverFromAnything | PointerHandler.ApprovesTakeOverByAnything
        onDoubleTapped: drag.editRequested(drag.dragItem)
    }

    function mappedPos() {
        return parent.mapToItem(DragCoordinator.contentItem, centroid.position.x, centroid.position.y)
    }

    onActiveChanged: {
        if (active) {
            started = true
            if (pressedAction)
                pressedAction()
            DragCoordinator.startDrag(dragItem, mappedPos(), centroid.position.y)
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
