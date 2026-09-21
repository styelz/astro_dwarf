pragma Singleton
import QtQuick
import QtQuick.Controls
import QtCore

// Control-page panel drag. Drop on a panel body to swap slots; drop on the
// leading or trailing edge to insert beside it. Drop on a column edge or
// between columns to dock the panel as a column.
QtObject {
    id: coord

    property Item host: null
    property var source: null
    property var hover: null
    property string dropMode: ""
    property bool active: false
    property point pos: Qt.point(0, 0)

    property var panels: []
    property var splits: ({})
    property var defaultSplitStates: ({})
    property bool defaultsCaptured: false
    readonly property int columnEdgePx: 28
    property int columnDockIndex: -1
    property real columnDockX: 0

    property Settings store: Settings {
        id: orderStore
        category: "panelLayout"
        property string panelOrderJson: ""
    }

    readonly property var columnKeys: ["controlLeft", "controlCenter", "controlRight"]

    function ancestorWith(item, predicate) {
        for (let n = item; n; n = n.parent) {
            if (predicate(n))
                return n
        }
        return null
    }

    function ancestorSplit(item) {
        const registered = coord.ancestorWith(item, function(n) {
            return !!(n && n.settingsKey && coord.splits[n.settingsKey])
        })
        if (registered)
            return coord.splits[registered.settingsKey] || registered
        return coord.ancestorWith(item, function(n) {
            return !!(n && n.addItem && n.removeItem && n.itemAt && n.orientation !== undefined)
        })
    }

    function register(panel) {
        if (!panel || panel.panelId === "")
            return
        if (coord.panels.indexOf(panel) >= 0)
            return
        const home = coord.ancestorWith(panel, function(n) { return !!(n && n.settingsKey) })
        if (home && home.settingsKey)
            panel.swapHome = home.settingsKey
        if (panel.swapHomeIndex < 0) {
            const split = coord.ancestorSplit(panel)
            panel.swapHomeIndex = coord.indexOfItem(split, panel)
            panel.swapDefaultProps = coord.captureProps(panel)
        }
        const next = coord.panels.slice()
        next.push(panel)
        coord.panels = next
    }

    function unregister(panel) {
        const idx = coord.panels.indexOf(panel)
        if (idx < 0)
            return
        const next = coord.panels.slice()
        next.splice(idx, 1)
        coord.panels = next
        if (coord.source === panel || coord.hover === panel)
            coord.cancel()
    }

    function registerSplit(split) {
        if (!split || !split.settingsKey)
            return
        const next = Object.assign({}, coord.splits)
        next[split.settingsKey] = split
        coord.splits = next
    }

    function begin(panel, position) {
        if (!panel || !panel.movable)
            return
        coord.source = panel
        coord.hover = null
        coord.pos = position
        coord.active = true
        coord.refreshHover(position)
    }

    function update(position) {
        coord.pos = position
        if (coord.active)
            coord.refreshHover(position)
    }

    function finish(position) {
        coord.update(position)
        const a = coord.source
        const b = coord.hover
        const mode = coord.dropMode
        const dockIndex = coord.columnDockIndex
        coord.clearHover()
        coord.active = false
        coord.source = null
        coord.dropMode = ""
        coord.columnDockIndex = -1
        if (!a)
            return
        Qt.callLater(function() {
            if (mode === "column")
                coord.dockAsColumnAt(a, dockIndex)
            else if (!b || a === b)
                return
            else if (mode === "before")
                coord.insertPanel(a, b, false)
            else if (mode === "after")
                coord.insertPanel(a, b, true)
            else
                coord.swapPanels(a, b)
        })
    }

    function cancel() {
        coord.clearHover()
        coord.active = false
        coord.source = null
        coord.dropMode = ""
        coord.pos = Qt.point(0, 0)
    }

    function dropKind(panel, position) {
        if (!panel || !coord.host)
            return ""
        const split = coord.ancestorSplit(panel)
        const local = panel.mapFromItem(coord.host, position.x, position.y)
        const vertical = !split || split.orientation === Qt.Vertical
        const span = vertical ? panel.height : panel.width
        const along = vertical ? local.y : local.x
        const edge = Math.max(Theme.s5, Math.min(Theme.px(56), span * 0.33))
        if (along < edge)
            return "before"
        if (along > span - edge)
            return "after"
        return "swap"
    }

    function refreshHover(position) {
        const dock = coord.columnDockAt(position)
        if (dock) {
            if (coord.hover)
                coord.hover.dropMode = ""
            coord.hover = null
            coord.dropMode = "column"
            coord.columnDockIndex = dock.destIndex
            coord.columnDockX = dock.x
            return
        }
        coord.columnDockIndex = -1
        const next = coord.panelAt(position)
        const mode = next ? coord.dropKind(next, position) : ""
        if (coord.hover === next && coord.dropMode === mode)
            return
        if (coord.hover && coord.hover !== next)
            coord.hover.dropMode = ""
        coord.hover = next
        coord.dropMode = mode
        if (coord.hover)
            coord.hover.dropMode = mode
    }

    function clearHover() {
        if (coord.hover)
            coord.hover.dropMode = ""
        coord.hover = null
        coord.dropMode = ""
        coord.columnDockIndex = -1
    }

    function panelAt(position) {
        const host = coord.host
        const list = coord.panels
        if (!host || !list || !list.length)
            return null
        let best = null
        let bestArea = Infinity
        for (let i = 0; i < list.length; i++) {
            const panel = list[i]
            if (!panel || !panel.movable || panel === coord.source || !panel.visible)
                continue
            if (panel.width <= 0 || panel.height <= 0)
                continue
            const local = panel.mapFromItem(host, position.x, position.y)
            if (local.x < 0 || local.y < 0 || local.x > panel.width || local.y > panel.height)
                continue
            const area = panel.width * panel.height
            if (area < bestArea) {
                best = panel
                bestArea = area
            }
        }
        return best
    }

    function indexOfItem(split, item) {
        if (!split || !item || !split.itemAt)
            return -1
        const n = split.count
        for (let i = 0; i < n; i++) {
            if (split.itemAt(i) === item)
                return i
        }
        return -1
    }

    function columnsSplit() {
        return coord.splits["controlColumns"] || null
    }

    function columnPanels(split, exclude) {
        const out = []
        if (!split || !split.itemAt)
            return out
        for (let i = 0; i < split.count; i++) {
            const item = split.itemAt(i)
            if (!item || !item.panelId || !item.movable)
                continue
            if (exclude && item === exclude)
                continue
            out.push(item)
        }
        return out
    }

    function columnIsEmpty(split, exclude) {
        return coord.columnPanels(split, exclude).length === 0
    }

    function columnIsCollapsed(split) {
        if (!split)
            return true
        if (!split.visible)
            return true
        if (!split.SplitView)
            return false
        const maxW = coord.finiteHint(split.SplitView.maximumWidth)
        return maxW === 0
    }

    function collapseColumn(split) {
        if (!split || !split.SplitView)
            return
        split.visible = false
        const attached = split.SplitView
        attached.fillWidth = false
        attached.minimumWidth = 0
        attached.preferredWidth = 0
        attached.maximumWidth = 0
    }

    function expandColumn(split) {
        if (!split)
            return
        const saved = coord.defaultSplitStates[split.settingsKey]
        if (saved && saved.attached)
            coord.applyProps(split, saved.attached)
        else if (split.SplitView) {
            split.SplitView.maximumWidth = Number.POSITIVE_INFINITY
            split.SplitView.minimumWidth = Theme.px(196)
            split.SplitView.preferredWidth = Theme.px(280)
            split.SplitView.fillWidth = false
        }
        split.visible = true
    }

    function syncColumns() {
        const keys = coord.columnKeys
        const occupied = []
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (!split)
                continue
            if (coord.columnIsEmpty(split))
                coord.collapseColumn(split)
            else {
                if (coord.columnIsCollapsed(split))
                    coord.expandColumn(split)
                else
                    split.visible = true
                occupied.push(split)
            }
        }
        let fill = null
        for (let i = 0; i < occupied.length; i++) {
            if (occupied[i].settingsKey === "controlCenter") {
                fill = occupied[i]
                break
            }
        }
        if (!fill) {
            const columns = coord.columnsSplit()
            if (columns && columns.itemAt) {
                for (let i = columns.count - 1; i >= 0; i--) {
                    const item = columns.itemAt(i)
                    if (occupied.indexOf(item) >= 0) {
                        fill = item
                        break
                    }
                }
            }
        }
        if (!fill && occupied.length)
            fill = occupied[occupied.length - 1]
        for (let i = 0; i < occupied.length; i++) {
            if (!occupied[i].SplitView)
                continue
            occupied[i].SplitView.fillWidth = occupied[i] === fill
        }
        const columns = coord.columnsSplit()
        if (columns && columns.relock)
            columns.relock()
    }

    function findCollapsedShell(excludeSplit) {
        const keys = coord.columnKeys
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (!split || split === excludeSplit)
                continue
            if (coord.columnIsEmpty(split))
                return split
        }
        return null
    }

    function dockTargetAt(panel, destIndex) {
        const sourceSplit = coord.ancestorSplit(panel)
        const columns = coord.columnsSplit()
        if (!panel || !sourceSplit || !columns || !columns.moveItem)
            return null
        const lastInSource = coord.columnIsEmpty(sourceSplit, panel)
        const dest = lastInSource ? sourceSplit : coord.findCollapsedShell(sourceSplit)
        if (!dest)
            return null
        const currentIndex = coord.indexOfItem(columns, dest)
        if (currentIndex < 0)
            return null
        const destClamped = Math.max(0, Math.min(Number(destIndex), columns.count - 1))
        if (!isFinite(destClamped))
            return null
        if (dest === sourceSplit && currentIndex === destClamped && lastInSource)
            return null
        return { dest: dest, destIndex: destClamped, currentIndex: currentIndex, sourceSplit: sourceSplit }
    }

    function visibleColumns() {
        const columns = coord.columnsSplit()
        const out = []
        if (!columns || !columns.itemAt)
            return out
        for (let i = 0; i < columns.count; i++) {
            const item = columns.itemAt(i)
            if (!item || !item.visible || item.width < 1)
                continue
            const pt = item.mapToItem(columns, 0, 0)
            out.push({ split: item, index: i, x: pt.x, width: item.width })
        }
        return out
    }

    function columnDockAt(position) {
        const columns = coord.columnsSplit()
        const host = coord.host
        const panel = coord.source
        if (!columns || !host || !panel)
            return null
        const sourceSplit = coord.ancestorSplit(panel)
        if (!sourceSplit || !columns.moveItem)
            return null
        const lastInSource = coord.columnIsEmpty(sourceSplit, panel)
        const dest = lastInSource ? sourceSplit : coord.findCollapsedShell(sourceSplit)
        if (!dest)
            return null
        const local = columns.mapFromItem(host, position.x, position.y)
        if (local.y < -Theme.s2 || local.y > columns.height + Theme.s2)
            return null
        const vis = coord.visibleColumns()
        if (!vis.length)
            return null
        const edge = coord.columnEdgePx
        const gapEdge = Math.max(edge, 72)
        let insertBefore = undefined
        for (let i = 0; i < vis.length - 1; i++) {
            const leftEnd = vis[i].x + vis[i].width
            const rightStart = vis[i + 1].x
            if (local.x > leftEnd - gapEdge && local.x < rightStart + gapEdge) {
                insertBefore = vis[i + 1].split
                break
            }
        }
        if (insertBefore === undefined) {
            if (local.x < vis[0].x + edge && local.x > vis[0].x - edge)
                insertBefore = vis[0].split
            else if (local.x > vis[vis.length - 1].x + vis[vis.length - 1].width - edge
                     && local.x < vis[vis.length - 1].x + vis[vis.length - 1].width + edge)
                insertBefore = null
            else
                return null
        }
        const order = []
        for (let i = 0; i < columns.count; i++) {
            const item = columns.itemAt(i)
            if (!item || item === dest)
                continue
            if (insertBefore && item === insertBefore)
                order.push(dest)
            order.push(item)
        }
        if (!insertBefore)
            order.push(dest)
        const destIndex = order.indexOf(dest)
        if (destIndex < 0)
            return null
        const currentIndex = coord.indexOfItem(columns, dest)
        if (currentIndex === destIndex && lastInSource && dest === sourceSplit)
            return null
        let barX = vis[0].x
        if (!insertBefore)
            barX = vis[vis.length - 1].x + vis[vis.length - 1].width
        else {
            for (let i = 0; i < vis.length; i++) {
                if (vis[i].split === insertBefore) {
                    barX = vis[i].x
                    break
                }
            }
        }
        return { destIndex: destIndex, x: barX }
    }

    function dockAsColumnAt(panel, destIndex) {
        const target = coord.dockTargetAt(panel, destIndex)
        if (!target)
            return
        const columns = coord.columnsSplit()
        coord.takeFrom(target.sourceSplit, panel)
        if (target.currentIndex !== target.destIndex)
            columns.moveItem(target.currentIndex, target.destIndex)
        coord.insertAt(target.dest, panel, target.dest.count)
        if (coord.columnIsCollapsed(target.dest))
            coord.expandColumn(target.dest)
        coord.syncColumns()
        coord.persist()
    }

    function columnOrder() {
        const columns = coord.columnsSplit()
        const order = []
        if (!columns || !columns.itemAt)
            return coord.columnKeys.slice()
        for (let i = 0; i < columns.count; i++) {
            const item = columns.itemAt(i)
            if (item && item.settingsKey)
                order.push(item.settingsKey)
        }
        return order.length ? order : coord.columnKeys.slice()
    }

    function applyColumnOrder(order) {
        const columns = coord.columnsSplit()
        if (!columns || !columns.moveItem || !order || !order.length)
            return
        for (let dest = 0; dest < order.length; dest++) {
            const split = coord.splits[order[dest]]
            if (!split)
                continue
            const current = coord.indexOfItem(columns, split)
            if (current < 0 || current === dest)
                continue
            columns.moveItem(current, dest)
        }
    }

    function finiteHint(value) {
        const n = Number(value)
        return isFinite(n) && n >= 0 && n < 1000000 ? n : -1
    }

    function captureProps(item) {
        const attached = item && item.SplitView
        if (!attached) {
            return {
                id: item ? item.panelId : "",
                preferredWidth: Number(item && item.width || 0),
                preferredHeight: Number(item && item.height || 0),
                minimumWidth: 0,
                minimumHeight: 0,
                maximumWidth: -1,
                maximumHeight: -1,
                fillWidth: false,
                fillHeight: false
            }
        }
        const maxW = coord.finiteHint(attached.maximumWidth)
        const maxH = coord.finiteHint(attached.maximumHeight)
        return {
            id: item.panelId,
            preferredWidth: Number(attached.preferredWidth || 0),
            preferredHeight: Number(attached.preferredHeight || 0),
            minimumWidth: Number(attached.minimumWidth || 0),
            minimumHeight: Number(attached.minimumHeight || 0),
            maximumWidth: maxW,
            maximumHeight: maxH,
            fillWidth: !!attached.fillWidth,
            fillHeight: !!attached.fillHeight
        }
    }

    function applyProps(item, props) {
        if (!item || !props || !item.SplitView)
            return
        const attached = item.SplitView
        attached.preferredWidth = Number(props.preferredWidth || 0)
        attached.preferredHeight = Number(props.preferredHeight || 0)
        attached.minimumWidth = Number(props.minimumWidth || 0)
        attached.minimumHeight = Number(props.minimumHeight || 0)
        attached.fillWidth = !!props.fillWidth
        attached.fillHeight = !!props.fillHeight
        const maxW = coord.finiteHint(props.maximumWidth)
        const maxH = coord.finiteHint(props.maximumHeight)
        attached.maximumWidth = maxW >= 0 ? maxW : Number.POSITIVE_INFINITY
        attached.maximumHeight = maxH >= 0 ? maxH : Number.POSITIVE_INFINITY
    }

    function place(split, item, index) {
        if (!split || !item || !split.addItem)
            return
        split.addItem(item)
        const last = split.count - 1
        if (index >= 0 && index < last && split.moveItem)
            split.moveItem(last, index)
    }

    function takeFrom(split, item) {
        const idx = coord.indexOfItem(split, item)
        if (idx < 0)
            return
        if (split.takeItem)
            split.takeItem(idx)
    }

    function insertAt(split, item, index) {
        if (!split || !item)
            return
        if (split.insertItem) {
            split.insertItem(Math.max(0, Math.min(index, split.count)), item)
            return
        }
        coord.place(split, item, index)
    }

    function insertPanel(source, target, after) {
        if (!source || !target || source === target)
            return
        const splitA = coord.ancestorSplit(source)
        const splitB = coord.ancestorSplit(target)
        if (!splitA || !splitB || !splitA.moveItem)
            return
        const indexA = coord.indexOfItem(splitA, source)
        const indexB = coord.indexOfItem(splitB, target)
        if (indexA < 0 || indexB < 0)
            return
        if (splitA === splitB) {
            let dest = after ? indexB + 1 : indexB
            if (indexA < dest)
                dest -= 1
            if (dest === indexA)
                return
            splitA.moveItem(indexA, dest)
        } else {
            let dest = after ? indexB + 1 : indexB
            coord.takeFrom(splitA, source)
            coord.insertAt(splitB, source, dest)
        }
        coord.syncColumns()
        coord.persist()
    }

    function swapPanels(a, b) {
        if (!a || !b || a === b)
            return
        const splitA = coord.ancestorSplit(a)
        const splitB = coord.ancestorSplit(b)
        if (!splitA || !splitB || !splitA.moveItem || !splitB.addItem)
            return
        const indexA = coord.indexOfItem(splitA, a)
        const indexB = coord.indexOfItem(splitB, b)
        if (indexA < 0 || indexB < 0)
            return
        const propsA = coord.captureProps(a)
        const propsB = coord.captureProps(b)
        const stateA = splitA.saveState ? splitA.saveState() : null
        const stateB = splitA === splitB ? null : (splitB.saveState ? splitB.saveState() : null)
        if (splitA === splitB) {
            splitA.moveItem(indexA, indexB)
            if (indexA < indexB)
                splitA.moveItem(indexB - 1, indexA)
            else if (indexA > indexB)
                splitA.moveItem(indexB + 1, indexA)
        } else {
            coord.takeFrom(splitA, a)
            coord.takeFrom(splitB, b)
            coord.insertAt(splitA, b, indexA)
            coord.insertAt(splitB, a, indexB)
        }
        coord.applyProps(a, propsB)
        coord.applyProps(b, propsA)
        if (stateA)
            splitA.restoreState(stateA)
        if (stateB)
            splitB.restoreState(stateB)
        coord.syncColumns()
        coord.persist()
    }

    function persist() {
        const out = {}
        const seen = {}
        const keys = coord.columnKeys
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            const entries = []
            if (split && split.itemAt) {
                for (let i = 0; i < split.count; i++) {
                    const item = split.itemAt(i)
                    if (!item || !item.panelId || !item.movable || seen[item.panelId])
                        continue
                    seen[item.panelId] = true
                    entries.push(coord.captureProps(item))
                }
            }
            out[key] = entries
        }
        out.order = coord.columnOrder()
        if (!coord.layoutComplete(out))
            return false
        orderStore.panelOrderJson = JSON.stringify(out)
        coord.persistSplitSizes()
        return true
    }

    function persistSplitSizes() {
        const keys = coord.columnKeys.concat(["controlColumns"])
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (split && split.persist)
                split.persist()
        }
    }

    function collectedIds(saved) {
        const ids = []
        const keys = coord.columnKeys
        for (let k = 0; k < keys.length; k++) {
            const entries = saved[keys[k]]
            if (!entries)
                continue
            for (let i = 0; i < entries.length; i++) {
                const entry = typeof entries[i] === "string" ? { id: entries[i] } : entries[i]
                const id = entry && entry.id ? String(entry.id) : ""
                if (id)
                    ids.push(id)
            }
        }
        return ids
    }

    function layoutComplete(saved) {
        const list = coord.panels
        const seen = {}
        const ids = coord.collectedIds(saved)
        for (let i = 0; i < ids.length; i++) {
            if (seen[ids[i]])
                return false
            seen[ids[i]] = true
        }
        for (let i = 0; i < list.length; i++) {
            const panel = list[i]
            if (!panel || !panel.movable || !panel.panelId)
                continue
            if (!seen[panel.panelId])
                return false
        }
        return ids.length > 0
    }

    function captureDefaults() {
        if (coord.defaultsCaptured)
            return
        const keys = coord.columnKeys.concat(["controlColumns"])
        const next = {}
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            if (!split)
                continue
            next[key] = {
                attached: key === "controlColumns" ? null : coord.captureProps(split),
                state: split.saveState ? split.saveState() : null
            }
        }
        coord.defaultSplitStates = next
        coord.defaultsCaptured = true
    }

    function resetToDefault() {
        coord.cancel()
        const list = coord.panels.slice()
        const movable = []
        for (let i = 0; i < list.length; i++) {
            const panel = list[i]
            if (!panel || !panel.movable || !panel.panelId)
                continue
            movable.push(panel)
            const current = coord.ancestorSplit(panel)
            if (current)
                coord.takeFrom(current, panel)
        }
        movable.sort(function (a, b) {
            const ha = String(a.swapHome || "")
            const hb = String(b.swapHome || "")
            if (ha !== hb)
                return ha < hb ? -1 : 1
            return Number(a.swapHomeIndex) - Number(b.swapHomeIndex)
        })
        for (let i = 0; i < movable.length; i++) {
            const panel = movable[i]
            const split = coord.splits[panel.swapHome]
            if (!split)
                continue
            coord.insertAt(split, panel, split.count)
            if (panel.swapDefaultProps)
                coord.applyProps(panel, panel.swapDefaultProps)
        }
        const keys = coord.columnKeys.concat(["controlColumns"])
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            const saved = coord.defaultSplitStates[key]
            if (!split || !saved)
                continue
            split.visible = true
            if (key !== "controlColumns" && saved.attached)
                coord.applyProps(split, saved.attached)
            if (split.relock)
                split.relock()
        }
        coord.applyColumnOrder(coord.columnKeys)
        coord.syncColumns()
        coord.discardSavedLayout()
        coord.persist()
        return true
    }

    function discardSavedLayout() {
        orderStore.panelOrderJson = ""
        const keys = coord.columnKeys.concat(["controlColumns"])
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (split && split.clearSaved)
                split.clearSaved()
        }
    }

    function restoreSplitSizes() {
        const keys = coord.columnKeys.concat(["controlColumns"])
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (split && split.restore)
                split.restore()
        }
    }

    function restore() {
        const raw = String(orderStore.panelOrderJson || "")
        if (!raw) {
            coord.restoreSplitSizes()
            coord.syncColumns()
            return false
        }
        let saved
        try {
            saved = JSON.parse(raw)
        } catch (e) {
            orderStore.panelOrderJson = ""
            coord.restoreSplitSizes()
            coord.syncColumns()
            return false
        }
        if (!saved || typeof saved !== "object" || !coord.layoutComplete(saved)) {
            coord.restoreSplitSizes()
            coord.syncColumns()
            return false
        }
        const byId = {}
        const list = coord.panels
        for (let i = 0; i < list.length; i++) {
            const panel = list[i]
            if (panel && panel.panelId)
                byId[panel.panelId] = panel
        }
        for (let i = 0; i < list.length; i++) {
            const panel = list[i]
            if (!panel || !panel.movable || !panel.panelId)
                continue
            const current = coord.ancestorSplit(panel)
            if (current)
                coord.takeFrom(current, panel)
        }
        const keys = coord.columnKeys
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            const entries = saved[key]
            if (!split || !entries || !entries.length)
                continue
            for (let i = 0; i < entries.length; i++) {
                const entry = typeof entries[i] === "string" ? { id: entries[i] } : entries[i]
                const id = entry && entry.id ? String(entry.id) : ""
                const panel = byId[id]
                if (!panel)
                    continue
                coord.insertAt(split, panel, split.count)
                coord.applyProps(panel, entry)
            }
        }
        if (saved.order)
            coord.applyColumnOrder(saved.order)
        coord.restoreSplitSizes()
        coord.syncColumns()
        return true
    }
}
