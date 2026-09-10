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
        const idx = insertDrop.insertIndex
        if (!list || idx < 0)
            return -999
        if (idx === 0)
            return -list.contentY - 1
        if (idx >= list.count) {
            const last = list.itemAtIndex(list.count - 1)
            if (last)
                return last.mapToItem(insertDrop, 0, last.height).y - 1
            return list.contentHeight - list.contentY - 1
        }
        const row = list.itemAtIndex(idx)
        if (row)
            return row.mapToItem(insertDrop, 0, 0).y - 1
        const stride = Math.max(1, insertDrop.rowHeight + list.spacing)
        return idx * stride - list.contentY - 1
    }

    function indexAtY(y) {
        const list = insertDrop.targetList
        if (!list || list.count <= 0)
            return 0
        const contentY = y + list.contentY
        if (contentY <= 0)
            return 0
        if (contentY >= list.contentHeight)
            return list.count
        const x = Math.max(1, list.width / 2)
        let idx = list.indexAt(x, contentY)
        if (idx < 0) {
            const step = Math.max(4, insertDrop.rowHeight / 4)
            const reach = insertDrop.rowHeight + list.spacing
            for (let d = step; d <= reach; d += step) {
                const down = list.indexAt(x, contentY + d)
                if (down >= 0)
                    return down
                const up = list.indexAt(x, contentY - d)
                if (up >= 0)
                    return up + 1
            }
            const stride = Math.max(1, insertDrop.rowHeight + list.spacing)
            idx = Math.round(contentY / stride)
            if (idx < 0)
                return 0
            if (idx > list.count)
                return list.count
            return idx
        }
        const row = list.itemAtIndex(idx)
        if (row) {
            const top = row.mapToItem(insertDrop, 0, 0).y
            if (y > top + row.height / 2)
                return idx + 1
        }
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
