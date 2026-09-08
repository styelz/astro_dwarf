import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

DropArea {
    id: insertDrop
    required property var targetList
    required property real rowHeight
    keys: ["session"]
    Component.onCompleted: DragCoordinator.registerDropArea(insertDrop)
    Component.onDestruction: DragCoordinator.unregisterDropArea(insertDrop)
    readonly property int insertIndex: {
        if (!DragCoordinator.active || !insertDrop.targetList)
            return -1
        const pos = insertDrop.mapFromItem(DragCoordinator.contentItem, DragCoordinator.pos.x, DragCoordinator.pos.y)
        if (pos.x < 0 || pos.y < 0 || pos.x > insertDrop.width || pos.y > insertDrop.height)
            return -1
        return insertDrop.indexAtY(pos.y)
    }
    readonly property real insertLineY: {
        const list = insertDrop.targetList
        if (!list)
            return -999
        return insertDrop.insertIndex * (insertDrop.rowHeight + list.spacing) - list.contentY - 1
    }

    function indexAtY(y) {
        const list = insertDrop.targetList
        if (!list)
            return 0
        const stride = Math.max(1, insertDrop.rowHeight + list.spacing)
        let idx = Math.round((y + list.contentY) / stride)
        if (idx < 0)
            return 0
        if (idx > list.count)
            return list.count
        return idx
    }

    onDropped: drop => {
        drop.accept()
        DragCoordinator.reorderFromInsert(insertDrop.targetList, insertDrop.insertIndex, DragCoordinator.data)
    }

    Rectangle {
        z: 1000
        enabled: false
        width: parent.width
        height: 2
        color: Theme.accent
        visible: insertDrop.insertIndex >= 0 && insertDrop.insertLineY >= -2 && insertDrop.insertLineY <= insertDrop.height
        y: insertDrop.insertLineY
    }
}
