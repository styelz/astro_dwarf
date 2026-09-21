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
    property real headerHeight: 0
    property string observingDate: ""
    keys: ["session"]
    // Written from refreshInsert(). Do not bind these to itemAtIndex / mapToItem:
    // those walk the same ListView that owns the drag and can relayout the
    // delegate mid-gesture, which hangs the GUI thread.
    property int insertIndex: -1
    property real insertLineY: -999
    Component.onCompleted: DragCoordinator.registerDropArea(insertDrop)
    Component.onDestruction: DragCoordinator.unregisterDropArea(insertDrop)

    function pointerLocal() {
        if (!DragCoordinator.active || !DragCoordinator.contentItem || !insertDrop.visible)
            return null
        if (insertDrop.width <= 0 || insertDrop.height <= 0)
            return null
        const pos = insertDrop.mapFromItem(DragCoordinator.contentItem, DragCoordinator.pos.x, DragCoordinator.pos.y)
        if (pos.x < 0 || pos.y < 0 || pos.x > insertDrop.width || pos.y > insertDrop.height)
            return null
        return pos
    }

    function rowAt(list, index) {
        if (!list || index < 0)
            return null
        const model = list.model
        if (model && model[index])
            return model[index]
        if (model && model.get)
            return model.get(index)
        return null
    }

    function rowStrideAt(list, index) {
        const spacing = list ? Number(list.spacing) || 0 : 0
        const base = Math.max(Theme.px(1), insertDrop.rowHeight + spacing)
        if (insertDrop.headerHeight <= 0 || !list)
            return base
        const row = insertDrop.rowAt(list, index)
        if (!row || !row.is_grouped || row.group_collapsed)
            return base
        if (index <= 0)
            return base + insertDrop.headerHeight
        const prev = insertDrop.rowAt(list, index - 1)
        if (!prev || String(prev.group_key || "") !== String(row.group_key || ""))
            return base + insertDrop.headerHeight
        return base
    }

    function indexAtY(y) {
        const list = insertDrop.targetList
        if (!list || list.count <= 0)
            return 0
        const contentY = y + list.contentY
        if (contentY <= 0)
            return 0
        const contentHeight = Number(list.contentHeight)
        if (contentHeight > 0 && contentY >= contentHeight)
            return list.count
        let acc = 0
        for (let i = 0; i < list.count; i++) {
            const stride = insertDrop.rowStrideAt(list, i)
            if (contentY < acc + stride / 2)
                return i
            acc += stride
        }
        return list.count
    }

    function lineYForIndex(idx) {
        const list = insertDrop.targetList
        if (!list || idx < 0)
            return -999
        if (idx === 0)
            return -list.contentY - 1
        if (idx >= list.count)
            return Number(list.contentHeight) - list.contentY - 1
        let acc = 0
        for (let i = 0; i < idx && i < list.count; i++)
            acc += insertDrop.rowStrideAt(list, i)
        return acc - list.contentY - 1
    }

    function refreshInsert() {
        const pos = insertDrop.pointerLocal()
        if (!pos || !insertDrop.targetList) {
            if (insertDrop.insertIndex !== -1)
                insertDrop.insertIndex = -1
            if (Math.abs(insertDrop.insertLineY + 999) > 0.01)
                insertDrop.insertLineY = -999
            return
        }
        const idx = insertDrop.indexAtY(pos.y)
        const lineY = insertDrop.lineYForIndex(idx)
        if (insertDrop.insertIndex !== idx)
            insertDrop.insertIndex = idx
        if (insertDrop.insertLineY !== lineY)
            insertDrop.insertLineY = lineY
    }

    Connections {
        target: DragCoordinator
        function onPosChanged() { insertDrop.refreshInsert() }
        function onActiveChanged() { insertDrop.refreshInsert() }
    }
    Connections {
        target: insertDrop.targetList
        ignoreUnknownSignals: true
        function onContentYChanged() { if (DragCoordinator.active) insertDrop.refreshInsert() }
        function onCountChanged() { if (DragCoordinator.active) insertDrop.refreshInsert() }
        function onContentHeightChanged() { if (DragCoordinator.active) insertDrop.refreshInsert() }
    }

    onDropped: drop => {
        drop.accept()
        DragCoordinator.reorderFromInsert(insertDrop.targetList, insertDrop.insertIndex, DragCoordinator.data, insertDrop.observingDate)
    }

    Rectangle {
        z: 1000
        enabled: false
        width: parent.width
        height: Theme.px(2)
        color: Theme.accent
        visible: insertDrop.insertIndex >= 0 && insertDrop.insertLineY >= -2 && insertDrop.insertLineY <= insertDrop.height
        y: insertDrop.insertLineY
    }
}
