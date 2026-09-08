import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

DragHandler {
    required property var dragItem
    property var pressedAction: null
    target: null
    acceptedButtons: Qt.LeftButton
    acceptedModifiers: Qt.NoModifier
    cursorShape: Qt.ClosedHandCursor
    enabled: String((dragItem && dragItem.status) || "") !== "running"
    property bool started: false

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
