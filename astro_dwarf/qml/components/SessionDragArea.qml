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
    property bool editOnDoubleTap: true
    property bool dragEnabled: true
    signal editRequested(var session)
    readonly property bool canEdit: {
        const item = root.dragItem || {}
        if (item.from_history)
            return false
        if (item.group_collapsed)
            return String(item.group_status || item.status || "") !== "running"
        return String(item.status || "") !== "running"
    }
    Accessible.role: Accessible.Button
    Accessible.name: {
        const item = root.dragItem || {}
        const when = item.start_time || ""
        const label = item.group_collapsed
            ? (item.group_title || item.target_name || "Mosaic")
            : (item.pane_name || item.target_name || "Session")
        return (when ? when + " " : "") + label
    }
    Accessible.description: {
        const item = root.dragItem || {}
        if (item.from_history)
            return "Completed run from history"
        if (!root.canEdit)
            return "Running"
        return root.editOnDoubleTap ? "Drag to reschedule, double-click to edit" : "Drag to reschedule"
    }

    TapHandler {
        parent: root.parent
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        enabled: root.editOnDoubleTap && root.canEdit && !drag.active && !drag.live
        // Approve a drag taking this press. Do not steal the grab back —
        // CanTakeOverFromAnything + ApprovesTakeOverByAnything livelocks
        // against DragHandler on these list rows.
        grabPermissions: PointerHandler.ApprovesTakeOverByAnything
        onDoubleTapped: root.editRequested(root.dragItem)
    }

    DragHandler {
        id: drag
        parent: root.parent
        target: null
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        cursorShape: Qt.ClosedHandCursor
        enabled: root.canEdit && root.dragEnabled
        property bool started: false
        property bool live: false

        function mappedPos() {
            return parent.mapToItem(DragCoordinator.contentItem, centroid.position.x, centroid.position.y)
        }

        onActiveChanged: {
            if (active) {
                started = true
                live = true
                if (root.pressedAction)
                    root.pressedAction()
                DragCoordinator.startDrag(root.dragItem, mappedPos(), centroid.position.y)
            } else if (started) {
                started = false
                const pos = mappedPos()
                Qt.callLater(function() {
                    drag.live = false
                    DragCoordinator.completeDrag(pos)
                })
            }
        }
        onTranslationChanged: {
            if (active)
                DragCoordinator.moveDrag(mappedPos())
        }
        onCanceled: {
            if (started) {
                started = false
                Qt.callLater(function() {
                    drag.live = false
                    DragCoordinator.cancelDrag()
                })
            }
        }
    }
}
