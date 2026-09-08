pragma Singleton
import QtQuick

// Cross-page session drag state. Drop areas register themselves so nothing here
// needs to know page internals; Main.qml supplies the proxy, content item and the
// calendar page (for timeline previews).
QtObject {
    id: coord

    property bool active: false
    property point pos: Qt.point(0, 0)
    property var data: ({})
    property real grabOffsetY: 0
    property int previewMinutes: -1
    property string previewTime: ""

    property Item contentItem: null
    property var proxy: null
    property var timeline: null
    property var dropAreas: []

    function registerDropArea(area) {
        if (!area || coord.dropAreas.indexOf(area) >= 0)
            return
        const next = coord.dropAreas.slice()
        next.push(area)
        coord.dropAreas = next
    }

    function unregisterDropArea(area) {
        const idx = coord.dropAreas.indexOf(area)
        if (idx < 0)
            return
        const next = coord.dropAreas.slice()
        next.splice(idx, 1)
        coord.dropAreas = next
    }

    function begin(item, position) {
        coord.data = item
        coord.pos = position
        coord.active = true
        coord.refreshPreview(position)
    }
    function update(position) {
        coord.pos = position
        coord.refreshPreview(position)
    }
    function end() {
        coord.active = false
        coord.data = ({})
        coord.grabOffsetY = 0
        coord.previewMinutes = -1
        coord.previewTime = ""
    }
    function refreshPreview(position) {
        const timeline = coord.timeline
        const minutes = timeline && timeline.timelineMinutesFromPos ? timeline.timelineMinutesFromPos(position) : -1
        coord.previewMinutes = minutes
        coord.previewTime = minutes < 0 || !timeline ? "" : timeline.timelineClock(minutes)
    }
    function startDrag(item, position, grabY) {
        coord.grabOffsetY = coord.timeline && coord.timeline.viewMode === 1 ? Number(grabY || 0) : 0
        if (coord.proxy)
            coord.proxy.startDrag(item, position)
    }
    function moveDrag(position) {
        if (coord.proxy)
            coord.proxy.moveDrag(position)
    }
    function finishDrag() {
        if (coord.proxy)
            coord.proxy.finishDrag()
    }
    function cancelDrag() {
        if (coord.proxy)
            coord.proxy.cancelDrag()
    }
    function dragSessionId(drop) {
        return String((coord.data && coord.data.id) || (drop && drop.source && drop.source.sessionId) || "")
    }
    function listRowAt(list, index) {
        if (!list || index < 0 || index >= list.count)
            return null
        const row = list.itemAtIndex(index)
        if (row && row.modelData)
            return row.modelData
        const model = list.model
        if (model && model[index])
            return model[index]
        return null
    }
    function reorderFromInsert(list, insertIndex, source) {
        if (!list || !source || !source.id || insertIndex < 0)
            return
        if (String(source.status || "").toLowerCase() !== "planned")
            return
        const count = list.count
        let from = -1
        for (let i = 0; i < count; i++) {
            const row = coord.listRowAt(list, i)
            if (row && String(row.id) === String(source.id)) {
                from = i
                break
            }
        }
        if (from >= 0 && (insertIndex === from || insertIndex === from + 1))
            return
        let beforeId = ""
        for (let i = Math.max(0, insertIndex); i < count; i++) {
            const target = coord.listRowAt(list, i)
            if (!target || String(target.id) === String(source.id))
                continue
            if (String(target.device_id) !== String(source.device_id))
                continue
            if (String(target.status || "").toLowerCase() !== "planned")
                continue
            beforeId = String(target.id)
            break
        }
        backend.reorderPlanned(String(source.id), beforeId)
    }
    function dropAreaShown(item) {
        for (let node = item; node; node = node.parent) {
            if (node.visible === false)
                return false
        }
        return !!(item && item.width > 0 && item.height > 0)
    }
    function listDropTarget(position) {
        const areas = coord.dropAreas
        for (let i = 0; i < areas.length; i++) {
            const area = areas[i]
            if (!coord.dropAreaShown(area))
                continue
            const local = area.mapFromItem(coord.contentItem, position.x, position.y)
            if (local.x < 0 || local.y < 0 || local.x > area.width || local.y > area.height)
                continue
            return { list: area.targetList, index: area.indexAtY(local.y) }
        }
        return null
    }
    function completeDrag(position) {
        coord.moveDrag(position)
        const source = coord.data
        const target = coord.listDropTarget(position)
        if (target) {
            coord.cancelDrag()
            Qt.callLater(function() {
                coord.reorderFromInsert(target.list, target.index, source)
            })
            return
        }
        coord.finishDrag()
    }
}
