pragma Singleton
import QtQuick
import QtQuick.Controls
import QtCore

// Control-page panel drag. Drop on a panel body to swap slots; drop on the
// top or bottom edge to insert beside it. Drop on a column seam or the outer
// left or right edge to open a column. Drop on the very top or bottom of the
// panel area, or on the seam between rows, to open a full-width row. A panel
// alone in a column or row fills that band.
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
    property real columnDockY: 0
    property real columnDockH: 0
    property string columnDockBeforeKey: ""
    property string columnDockBandKey: ""
    property bool columnDockAtEnd: false
    property var columnFactory: null
    property real rowDockY: 0
    property string rowDockBeforeKey: ""
    property bool rowDockAtEnd: false
    property var rowFactory: null

    property Settings store: Settings {
        id: orderStore
        category: "panelLayout"
        property string panelOrderJson: ""
    }

    readonly property var builtinColumnKeys: ["controlLeft", "controlCenter", "controlRight"]
    property var columnKeys: ["controlLeft", "controlCenter", "controlRight"]
    property var rowKeys: []

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
        const beforeKey = mode === "row" ? coord.rowDockBeforeKey : coord.columnDockBeforeKey
        const atEnd = mode === "row" ? coord.rowDockAtEnd : coord.columnDockAtEnd
        const bandKey = coord.columnDockBandKey
        coord.clearHover()
        coord.active = false
        coord.source = null
        coord.dropMode = ""
        if (!a)
            return
        Qt.callLater(function() {
            if (mode === "row")
                coord.dockAsRow(a, beforeKey, atEnd)
            else if (mode === "column")
                coord.dockAsColumn(a, beforeKey, atEnd, bandKey)
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
        const rowDock = coord.rowDockAt(position)
        if (rowDock) {
            if (coord.hover)
                coord.hover.dropMode = ""
            coord.hover = null
            coord.dropMode = "row"
            coord.rowDockBeforeKey = rowDock.beforeKey
            coord.rowDockAtEnd = rowDock.atEnd
            coord.rowDockY = rowDock.y
            coord.columnDockBeforeKey = ""
            coord.columnDockAtEnd = false
            return
        }
        coord.rowDockBeforeKey = ""
        coord.rowDockAtEnd = false
        const dock = coord.columnDockAt(position)
        if (dock) {
            if (coord.hover)
                coord.hover.dropMode = ""
            coord.hover = null
            coord.dropMode = "column"
            coord.columnDockBeforeKey = dock.beforeKey
            coord.columnDockAtEnd = dock.atEnd
            coord.columnDockBandKey = dock.bandKey
            coord.columnDockX = dock.x
            coord.columnDockY = dock.y
            coord.columnDockH = dock.h
            return
        }
        coord.columnDockIndex = -1
        coord.columnDockBeforeKey = ""
        coord.columnDockAtEnd = false
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
        coord.columnDockBeforeKey = ""
        coord.columnDockBandKey = ""
        coord.columnDockAtEnd = false
        coord.rowDockBeforeKey = ""
        coord.rowDockAtEnd = false
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

    function refreshColumnKeys() {
        const keys = coord.builtinColumnKeys.slice()
        const columns = coord.columnsSplit()
        if (columns && columns.itemAt) {
            for (let i = 0; i < columns.count; i++) {
                const item = columns.itemAt(i)
                const key = item && item.settingsKey ? String(item.settingsKey) : ""
                if (key && key !== "controlColumns" && keys.indexOf(key) < 0)
                    keys.push(key)
            }
        }
        coord.columnKeys = keys
    }

    function nextExtraKey() {
        for (let n = 1; n <= 12; n++) {
            const key = "controlExtra" + n
            if (!coord.splits[key])
                return key
        }
        return ""
    }

    function columnCapacity(band) {
        const columns = band || coord.columnsSplit()
        const width = columns ? columns.width : 0
        const minW = Theme.px(196)
        const handle = Theme.s2
        const floor = columns && String(columns.settingsKey || "") === "controlColumns" ? 3 : 1
        if (width < minW * 2)
            return floor
        let count = 1
        let used = minW
        while (count < 8 && used + handle + minW <= width + 1) {
            count += 1
            used += handle + minW
        }
        return Math.max(floor, count)
    }

    function columnBand(split) {
        if (!split)
            return null
        const main = coord.columnsSplit()
        if (coord.indexOfItem(main, split) >= 0)
            return main
        const rows = coord.rowsSplit()
        if (!rows || !rows.itemAt)
            return null
        for (let i = 0; i < rows.count; i++) {
            const row = rows.itemAt(i)
            if (row && coord.indexOfItem(row, split) >= 0)
                return row
        }
        return null
    }

    function bandAt(position) {
        const rows = coord.rowsSplit()
        const host = coord.host
        if (!rows || !host)
            return coord.columnsSplit()
        const local = rows.mapFromItem(host, position.x, position.y)
        if (local.y < -Theme.s2 || local.y > rows.height + Theme.s2)
            return null
        for (let i = 0; i < rows.count; i++) {
            const item = rows.itemAt(i)
            if (!item || !item.visible || item.height < 1 || item.orientation !== Qt.Horizontal)
                continue
            const pt = item.mapToItem(rows, 0, 0)
            if (local.y >= pt.y - Theme.s1 && local.y <= pt.y + item.height + Theme.s1)
                return item
        }
        return null
    }

    function createColumn(key, band) {
        const factory = coord.columnFactory
        const columns = band || coord.columnsSplit()
        if (!factory || !columns || !key)
            return null
        if (coord.splits[key])
            return coord.splits[key]
        const shell = factory.createObject(null, {
            settingsKey: key,
            autoRestore: false,
            orientation: Qt.Vertical
        })
        if (!shell) {
            console.warn("PanelSwap column create failed", factory.errorString())
            return null
        }
        shell.parent = columns
        if (columns.insertItem)
            columns.insertItem(columns.count, shell)
        else if (columns.addItem)
            columns.addItem(shell)
        if (shell.SplitView) {
            shell.SplitView.minimumWidth = Theme.px(196)
            shell.SplitView.preferredWidth = Theme.px(280)
            shell.SplitView.maximumWidth = Number.POSITIVE_INFINITY
            shell.SplitView.fillWidth = false
        }
        coord.registerSplit(shell)
        coord.refreshColumnKeys()
        return shell
    }

    function destroyColumn(split) {
        if (!split || !split.settingsKey)
            return
        const key = String(split.settingsKey)
        if (coord.builtinColumnKeys.indexOf(key) >= 0)
            return
        if (split.clearSaved)
            split.clearSaved()
        const columns = coord.columnBand(split) || coord.columnsSplit()
        const idx = coord.indexOfItem(columns, split)
        if (idx >= 0 && columns && columns.takeItem)
            columns.takeItem(idx)
        const next = Object.assign({}, coord.splits)
        delete next[key]
        coord.splits = next
        split.destroy()
        coord.refreshColumnKeys()
    }

    function destroyExtraColumns() {
        const columns = coord.columnsSplit()
        if (!columns || !columns.itemAt)
            return
        for (let i = columns.count - 1; i >= 0; i--) {
            const item = columns.itemAt(i)
            if (!item || coord.builtinColumnKeys.indexOf(String(item.settingsKey || "")) >= 0)
                continue
            coord.destroyColumn(item)
        }
    }

    function fitColumn(split) {
        const panels = coord.columnPanels(split)
        if (panels.length === 1) {
            const panel = panels[0]
            if (!panel || !panel.SplitView)
                return
            panel.columnStretched = true
            panel.SplitView.fillHeight = true
            panel.SplitView.maximumHeight = Number.POSITIVE_INFINITY
            return
        }
        for (let i = 0; i < panels.length; i++) {
            const panel = panels[i]
            if (!panel || !panel.columnStretched)
                continue
            panel.columnStretched = false
            if (panel.swapDefaultProps)
                coord.applyProps(panel, panel.swapDefaultProps)
        }
    }

    function sameColumnSlot(dest, insertBefore, vis) {
        let idx = -1
        for (let i = 0; i < vis.length; i++) {
            if (vis[i].split === dest) {
                idx = i
                break
            }
        }
        if (idx < 0)
            return false
        if (insertBefore === dest)
            return true
        const next = vis[idx + 1]
        if (!insertBefore && !next)
            return true
        if (next && insertBefore === next.split)
            return true
        return false
    }

    function syncColumns() {
        const keys = coord.columnKeys.slice()
        const occupied = []
        const doomed = []
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (!split)
                continue
            if (coord.columnIsEmpty(split)) {
                if (coord.builtinColumnKeys.indexOf(keys[k]) < 0)
                    doomed.push(split)
                else
                    coord.collapseColumn(split)
            } else {
                if (coord.columnIsCollapsed(split))
                    coord.expandColumn(split)
                else
                    split.visible = true
                occupied.push(split)
                coord.fitColumn(split)
                if (split.width < 8 && split.SplitView) {
                    split.SplitView.minimumWidth = Theme.px(196)
                    split.SplitView.preferredWidth = Theme.px(280)
                    split.SplitView.maximumWidth = Number.POSITIVE_INFINITY
                    split.visible = true
                }
            }
        }
        for (let d = 0; d < doomed.length; d++)
            coord.destroyColumn(doomed[d])
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
        coord.syncRows()
    }

    function findCollapsedShell(excludeSplit, band) {
        const columns = band || coord.columnsSplit()
        if (!columns || !columns.itemAt)
            return null
        for (let i = 0; i < columns.count; i++) {
            const split = columns.itemAt(i)
            if (!split || split === excludeSplit || split.panelId)
                continue
            if (coord.columnIsEmpty(split))
                return split
        }
        return null
    }

    function visibleColumns(band) {
        const columns = band || coord.columnsSplit()
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
        const columns = coord.bandAt(position)
        const host = coord.host
        const panel = coord.source
        if (!columns || !host || !panel)
            return null
        const sourceSplit = coord.ancestorSplit(panel)
        if (!sourceSplit || !columns.moveItem)
            return null
        const local = columns.mapFromItem(host, position.x, position.y)
        if (local.y < -Theme.s2 || local.y > columns.height + Theme.s2)
            return null
        const vis = coord.visibleColumns(columns)
        if (!vis.length)
            return null
        const edge = coord.columnEdgePx
        let insertBefore = undefined
        for (let i = 0; i < vis.length - 1; i++) {
            const leftEnd = vis[i].x + vis[i].width
            const rightStart = vis[i + 1].x
            const mid = (leftEnd + rightStart) / 2
            if (Math.abs(local.x - mid) <= edge || (local.x >= leftEnd && local.x <= rightStart)) {
                insertBefore = vis[i + 1].split
                break
            }
        }
        if (insertBefore === undefined) {
            if (local.x <= vis[0].x + edge)
                insertBefore = vis[0].split
            else if (local.x >= vis[vis.length - 1].x + vis[vis.length - 1].width - edge)
                insertBefore = null
            else
                return null
        }
        const movingSource = coord.columnIsEmpty(sourceSplit, panel)
        const sameBand = coord.columnBand(sourceSplit) === columns
        if (movingSource && sameBand && coord.sameColumnSlot(sourceSplit, insertBefore, vis))
            return null
        const collapsed = movingSource && sameBand ? sourceSplit : coord.findCollapsedShell(sourceSplit, columns)
        if (!collapsed && vis.length >= coord.columnCapacity(columns))
            return null
        if (!collapsed && !coord.columnFactory)
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
        const origin = columns.mapToItem(host, barX, 0)
        return {
            beforeKey: insertBefore && insertBefore.settingsKey ? String(insertBefore.settingsKey) : "",
            atEnd: !insertBefore,
            x: origin.x,
            y: origin.y,
            h: columns.height,
            bandKey: String(columns.settingsKey || "")
        }
    }

    function nextRowColumnKey(rowKey) {
        const prefix = String(rowKey || "")
        for (let n = 1; n <= 8; n++) {
            const key = prefix + "Col" + n
            if (!coord.splits[key])
                return key
        }
        return coord.nextExtraKey()
    }

    function dockAsColumn(panel, beforeKey, atEnd, bandKey) {
        const sourceSplit = coord.ancestorSplit(panel)
        const columns = (bandKey && coord.splits[bandKey]) || coord.columnsSplit()
        if (!panel || !sourceSplit || !columns || !columns.moveItem)
            return
        const lastInSource = coord.columnIsEmpty(sourceSplit, panel)
        const sameBand = coord.columnBand(sourceSplit) === columns
        let dest = lastInSource && sameBand ? sourceSplit : coord.findCollapsedShell(sourceSplit, columns)
        if (!dest) {
            if (coord.visibleColumns(columns).length >= coord.columnCapacity(columns))
                return
            const key = coord.isExtraRow(columns) ? coord.nextRowColumnKey(columns.settingsKey) : coord.nextExtraKey()
            dest = coord.createColumn(key, columns)
            if (!dest)
                return
        }
        coord.takeFrom(sourceSplit, panel)
        const before = !atEnd && beforeKey ? coord.splits[beforeKey] : null
        const current = coord.indexOfItem(columns, dest)
        let destIndex = columns.count - 1
        if (before) {
            destIndex = coord.indexOfItem(columns, before)
            if (current >= 0 && current < destIndex)
                destIndex -= 1
        }
        if (current >= 0 && destIndex >= 0 && current !== destIndex)
            columns.moveItem(current, destIndex)
        coord.insertAt(dest, panel, dest.count)
        if (coord.indexOfItem(dest, panel) < 0 && dest.addItem) {
            panel.parent = dest
            dest.addItem(panel)
        }
        if (coord.columnIsCollapsed(dest))
            coord.expandColumn(dest)
        else
            dest.visible = true
        coord.syncColumns()
        coord.persist()
    }

    function rowsSplit() {
        return coord.splits["controlRows"] || null
    }

    function isExtraRow(split) {
        const key = split && split.settingsKey ? String(split.settingsKey) : ""
        return key.indexOf("controlRow") === 0 && key !== "controlRows" && key.indexOf("Col") < 0
    }

    function bandHasPanels(split, exclude) {
        if (!split)
            return false
        if (String(split.settingsKey || "") === "controlColumns") {
            const keys = coord.columnKeys
            for (let k = 0; k < keys.length; k++) {
                const column = coord.splits[keys[k]]
                if (column && !coord.columnIsEmpty(column, exclude))
                    return true
            }
            return false
        }
        if (coord.isExtraRow(split)) {
            if (!coord.columnIsEmpty(split, exclude))
                return true
            if (!split.itemAt)
                return false
            for (let i = 0; i < split.count; i++) {
                const column = split.itemAt(i)
                if (column && !column.panelId && !coord.columnIsEmpty(column, exclude))
                    return true
            }
            return false
        }
        return !coord.columnIsEmpty(split, exclude)
    }

    function nextRowKey() {
        for (let n = 1; n <= 8; n++) {
            const key = "controlRow" + n
            if (!coord.splits[key])
                return key
        }
        return ""
    }

    function rowCapacity() {
        const rows = coord.rowsSplit()
        const height = rows ? rows.height : 0
        const minH = Theme.px(120)
        const handle = Theme.s2
        if (height < minH * 2)
            return 1
        let count = 1
        let used = minH
        while (count < 6 && used + handle + minH <= height + 1) {
            count += 1
            used += handle + minH
        }
        return count
    }

    function refreshRowKeys() {
        const keys = []
        const rows = coord.rowsSplit()
        if (rows && rows.itemAt) {
            for (let i = 0; i < rows.count; i++) {
                const item = rows.itemAt(i)
                if (coord.isExtraRow(item))
                    keys.push(String(item.settingsKey))
            }
        }
        coord.rowKeys = keys
    }

    function createRow(key) {
        const factory = coord.rowFactory
        const rows = coord.rowsSplit()
        if (!factory || !rows || !key)
            return null
        if (coord.splits[key])
            return coord.splits[key]
        const shell = factory.createObject(null, {
            settingsKey: key,
            autoRestore: false,
            orientation: Qt.Horizontal
        })
        if (!shell) {
            console.warn("PanelSwap row create failed", factory.errorString())
            return null
        }
        shell.parent = rows
        if (rows.insertItem)
            rows.insertItem(rows.count, shell)
        else if (rows.addItem)
            rows.addItem(shell)
        if (shell.SplitView) {
            shell.SplitView.minimumHeight = Theme.px(120)
            shell.SplitView.preferredHeight = Theme.px(220)
            shell.SplitView.maximumHeight = Number.POSITIVE_INFINITY
            shell.SplitView.fillHeight = false
            shell.SplitView.fillWidth = true
        }
        coord.registerSplit(shell)
        coord.refreshRowKeys()
        return shell
    }

    function destroyRow(split) {
        if (!coord.isExtraRow(split))
            return
        const key = String(split.settingsKey)
        if (split.itemAt) {
            for (let i = split.count - 1; i >= 0; i--) {
                const child = split.itemAt(i)
                if (child && child.settingsKey && !child.panelId)
                    coord.destroyColumn(child)
            }
        }
        if (split.clearSaved)
            split.clearSaved()
        const rows = coord.rowsSplit()
        const idx = coord.indexOfItem(rows, split)
        if (idx >= 0 && rows && rows.takeItem)
            rows.takeItem(idx)
        const next = Object.assign({}, coord.splits)
        delete next[key]
        coord.splits = next
        split.destroy()
        coord.refreshRowKeys()
    }

    function destroyExtraRows() {
        const rows = coord.rowsSplit()
        if (!rows || !rows.itemAt)
            return
        for (let i = rows.count - 1; i >= 0; i--) {
            const item = rows.itemAt(i)
            if (coord.isExtraRow(item))
                coord.destroyRow(item)
        }
    }

    function collapseBand(split) {
        if (!split || !split.SplitView)
            return
        split.visible = false
        const attached = split.SplitView
        attached.fillHeight = false
        attached.minimumHeight = 0
        attached.preferredHeight = 0
        attached.maximumHeight = 0
    }

    function expandBand(split) {
        if (!split)
            return
        const saved = coord.defaultSplitStates[split.settingsKey]
        if (saved && saved.attached)
            coord.applyProps(split, saved.attached)
        else if (split.SplitView) {
            split.SplitView.maximumHeight = Number.POSITIVE_INFINITY
            split.SplitView.minimumHeight = Theme.px(120)
            split.SplitView.preferredHeight = Theme.px(220)
            split.SplitView.fillHeight = String(split.settingsKey || "") === "controlColumns"
        }
        split.visible = true
    }

    function visibleRows() {
        const rows = coord.rowsSplit()
        const out = []
        if (!rows || !rows.itemAt)
            return out
        for (let i = 0; i < rows.count; i++) {
            const item = rows.itemAt(i)
            if (!item || !item.visible || item.height < 1)
                continue
            const pt = item.mapToItem(rows, 0, 0)
            out.push({ split: item, index: i, y: pt.y, height: item.height })
        }
        return out
    }

    function sameRowSlot(dest, insertBefore, vis) {
        let idx = -1
        for (let i = 0; i < vis.length; i++) {
            if (vis[i].split === dest) {
                idx = i
                break
            }
        }
        if (idx < 0)
            return false
        if (insertBefore === dest)
            return true
        const next = vis[idx + 1]
        if (!insertBefore && !next)
            return true
        if (next && insertBefore === next.split)
            return true
        return false
    }

    function rowDockAt(position) {
        const rows = coord.rowsSplit()
        const host = coord.host
        const panel = coord.source
        if (!rows || !host || !panel || !rows.moveItem)
            return null
        const local = rows.mapFromItem(host, position.x, position.y)
        if (local.x < -Theme.s2 || local.y < -Theme.s2 || local.x > rows.width + Theme.s2 || local.y > rows.height + Theme.s2)
            return null
        const vis = coord.visibleRows()
        if (!vis.length)
            return null
        const edge = coord.columnEdgePx
        let insertBefore = undefined
        for (let i = 0; i < vis.length - 1; i++) {
            const topEnd = vis[i].y + vis[i].height
            const bottomStart = vis[i + 1].y
            const mid = (topEnd + bottomStart) / 2
            if (Math.abs(local.y - mid) <= edge || (local.y >= topEnd && local.y <= bottomStart)) {
                insertBefore = vis[i + 1].split
                break
            }
        }
        if (insertBefore === undefined) {
            if (local.y <= vis[0].y + edge)
                insertBefore = vis[0].split
            else if (local.y >= vis[vis.length - 1].y + vis[vis.length - 1].height - edge)
                insertBefore = null
            else
                return null
        }
        const sourceSplit = coord.ancestorSplit(panel)
        const movingRow = coord.isExtraRow(sourceSplit) && coord.columnIsEmpty(sourceSplit, panel)
        if (movingRow && coord.sameRowSlot(sourceSplit, insertBefore, vis))
            return null
        if (!movingRow && vis.length >= coord.rowCapacity())
            return null
        if (!movingRow && !coord.rowFactory)
            return null
        let barY = vis[0].y
        if (!insertBefore)
            barY = vis[vis.length - 1].y + vis[vis.length - 1].height
        else {
            for (let i = 0; i < vis.length; i++) {
                if (vis[i].split === insertBefore) {
                    barY = vis[i].y
                    break
                }
            }
        }
        return {
            beforeKey: insertBefore && insertBefore.settingsKey ? String(insertBefore.settingsKey) : "",
            atEnd: !insertBefore,
            y: barY
        }
    }

    function dockAsRow(panel, beforeKey, atEnd) {
        const sourceSplit = coord.ancestorSplit(panel)
        const rows = coord.rowsSplit()
        if (!panel || !sourceSplit || !rows || !rows.moveItem)
            return
        const lastInSource = coord.columnIsEmpty(sourceSplit, panel)
        let dest = lastInSource && coord.isExtraRow(sourceSplit) ? sourceSplit : null
        if (!dest) {
            if (coord.visibleRows().length >= coord.rowCapacity())
                return
            dest = coord.createRow(coord.nextRowKey())
            if (!dest)
                return
        }
        coord.takeFrom(sourceSplit, panel)
        const before = !atEnd && beforeKey ? coord.splits[beforeKey] : null
        const current = coord.indexOfItem(rows, dest)
        let destIndex = rows.count - 1
        if (before) {
            destIndex = coord.indexOfItem(rows, before)
            if (current >= 0 && current < destIndex)
                destIndex -= 1
        }
        if (current >= 0 && destIndex >= 0 && current !== destIndex)
            rows.moveItem(current, destIndex)
        let column = null
        if (coord.columnBand(sourceSplit) === dest)
            column = sourceSplit
        if (!column)
            column = coord.createColumn(coord.nextRowColumnKey(dest.settingsKey), dest)
        if (!column)
            return
        coord.insertAt(column, panel, column.count)
        if (coord.indexOfItem(column, panel) < 0 && column.addItem) {
            panel.parent = column
            column.addItem(panel)
        }
        dest.visible = true
        column.visible = true
        coord.syncColumns()
        coord.persist()
    }

    function fitRow(row) {
        if (!row || !row.itemAt)
            return
        const doomed = []
        const cols = []
        for (let i = 0; i < row.count; i++) {
            const column = row.itemAt(i)
            if (!column || column.panelId)
                continue
            if (coord.columnIsEmpty(column))
                doomed.push(column)
            else {
                column.visible = true
                cols.push(column)
                coord.fitColumn(column)
            }
        }
        for (let d = 0; d < doomed.length; d++)
            coord.destroyColumn(doomed[d])
        const fill = cols.length ? cols[cols.length - 1] : null
        for (let i = 0; i < cols.length; i++) {
            if (!cols[i].SplitView)
                continue
            cols[i].SplitView.fillWidth = cols[i] === fill
            if (cols[i].width < 8) {
                cols[i].SplitView.minimumWidth = Theme.px(196)
                cols[i].SplitView.preferredWidth = cols.length === 1 ? Math.max(Theme.px(280), row.width) : Theme.px(280)
                cols[i].SplitView.maximumWidth = Number.POSITIVE_INFINITY
            }
        }
    }

    function rowOrder() {
        const rows = coord.rowsSplit()
        const order = []
        if (!rows || !rows.itemAt)
            return ["controlColumns"]
        for (let i = 0; i < rows.count; i++) {
            const item = rows.itemAt(i)
            if (item && item.settingsKey)
                order.push(item.settingsKey)
        }
        return order.length ? order : ["controlColumns"]
    }

    function applyRowOrder(order) {
        const rows = coord.rowsSplit()
        if (!rows || !rows.moveItem || !order || !order.length)
            return
        for (let dest = 0; dest < order.length; dest++) {
            const split = coord.splits[order[dest]]
            if (!split)
                continue
            const current = coord.indexOfItem(rows, split)
            if (current < 0 || current === dest)
                continue
            rows.moveItem(current, dest)
        }
    }

    function syncRows() {
        const rows = coord.rowsSplit()
        if (!rows)
            return
        coord.refreshRowKeys()
        const keys = coord.rowKeys.slice()
        const doomed = []
        const occupied = []
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (!split)
                continue
            if (!coord.bandHasPanels(split))
                doomed.push(split)
            else {
                if (!split.visible)
                    coord.expandBand(split)
                split.visible = true
                occupied.push(split)
                coord.fitRow(split)
            }
        }
        for (let d = 0; d < doomed.length; d++)
            coord.destroyRow(doomed[d])
        const columns = coord.columnsSplit()
        const columnsOccupied = columns && coord.bandHasPanels(columns)
        if (columns) {
            if (columnsOccupied) {
                if (!columns.visible || coord.finiteHint(columns.SplitView.maximumHeight) === 0)
                    coord.expandBand(columns)
                columns.visible = true
            } else {
                coord.collapseBand(columns)
            }
        }
        const fill = columnsOccupied ? columns : (occupied.length ? occupied[occupied.length - 1] : null)
        if (columns && columns.SplitView && columns.visible)
            columns.SplitView.fillHeight = columns === fill
        for (let i = 0; i < occupied.length; i++) {
            if (!occupied[i].SplitView)
                continue
            occupied[i].SplitView.fillHeight = occupied[i] === fill
            if (occupied[i].height < 8) {
                occupied[i].SplitView.minimumHeight = Theme.px(120)
                occupied[i].SplitView.preferredHeight = Theme.px(220)
                occupied[i].SplitView.maximumHeight = Number.POSITIVE_INFINITY
            }
        }
        if (rows.relock)
            rows.relock()
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

    function splitItem(item) {
        if (!item)
            return false
        let parent = item.parent
        while (parent) {
            if (parent.itemAt && coord.indexOfItem(parent, item) >= 0)
                return true
            parent = parent.parent
        }
        return false
    }

    function captureProps(item) {
        if (!item || !coord.splitItem(item)) {
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
        const attached = item.SplitView
        const maxW = coord.finiteHint(attached.maximumWidth)
        const maxH = coord.finiteHint(attached.maximumHeight)
        const props = {
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
        if (item.columnStretched && item.swapDefaultProps) {
            const natural = item.swapDefaultProps
            props.preferredHeight = Number(natural.preferredHeight || 0)
            props.minimumHeight = Number(natural.minimumHeight || 0)
            props.maximumHeight = coord.finiteHint(natural.maximumHeight)
            props.fillHeight = !!natural.fillHeight
        }
        return props
    }

    function applyProps(item, props) {
        if (!item || !props || !coord.splitItem(item))
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
        const keys = coord.panelHolderKeys()
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
        out.rowOrder = coord.rowOrder()
        out.rowColumns = coord.rowColumnOrder()
        if (!coord.layoutComplete(out))
            return false
        orderStore.panelOrderJson = JSON.stringify(out)
        coord.persistSplitSizes()
        if (typeof orderStore.sync === "function")
            orderStore.sync()
        return true
    }

    function persistSplitSizes() {
        const keys = coord.layoutSplitKeys()
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (split && split.persist)
                split.persist()
        }
    }

    function savedColumnKeys(saved) {
        const keys = []
        if (!saved)
            return keys
        const names = Object.keys(saved)
        for (let i = 0; i < names.length; i++) {
            if (names[i] === "order" || names[i] === "rowOrder" || names[i] === "rowColumns")
                continue
            keys.push(names[i])
        }
        return keys
    }

    function ensureSavedColumns(saved) {
        const names = coord.savedColumnKeys(saved)
        const order = saved && saved.order ? saved.order : []
        for (let i = 0; i < order.length; i++) {
            if (names.indexOf(order[i]) < 0)
                names.push(order[i])
        }
        for (let i = 0; i < names.length; i++) {
            const key = String(names[i] || "")
            if (!key || key === "controlColumns" || coord.splits[key])
                continue
            if (coord.builtinColumnKeys.indexOf(key) >= 0)
                continue
            if (key.indexOf("controlExtra") !== 0)
                continue
            coord.createColumn(key)
        }
    }

    function panelHolderKeys() {
        const keys = coord.columnKeys.slice()
        for (let r = 0; r < coord.rowKeys.length; r++) {
            const row = coord.splits[coord.rowKeys[r]]
            if (!row || !row.itemAt)
                continue
            for (let i = 0; i < row.count; i++) {
                const item = row.itemAt(i)
                const key = item && item.settingsKey ? String(item.settingsKey) : ""
                if (key && keys.indexOf(key) < 0)
                    keys.push(key)
            }
        }
        return keys
    }

    function rowColumnOrder() {
        const map = {}
        for (let r = 0; r < coord.rowKeys.length; r++) {
            const row = coord.splits[coord.rowKeys[r]]
            if (!row || !row.itemAt)
                continue
            const cols = []
            for (let i = 0; i < row.count; i++) {
                const item = row.itemAt(i)
                if (item && item.settingsKey && !item.panelId)
                    cols.push(String(item.settingsKey))
            }
            if (cols.length)
                map[coord.rowKeys[r]] = cols
        }
        return map
    }

    function ensureSavedRowColumns(saved) {
        const map = saved && saved.rowColumns ? saved.rowColumns : {}
        const names = Object.keys(map)
        for (let i = 0; i < names.length; i++) {
            const rowKey = String(names[i] || "")
            if (!coord.isExtraRow({ settingsKey: rowKey }))
                continue
            if (!coord.splits[rowKey])
                coord.createRow(rowKey)
            const cols = map[rowKey] || []
            for (let c = 0; c < cols.length; c++) {
                if (!coord.splits[cols[c]])
                    coord.createColumn(String(cols[c]), coord.splits[rowKey])
            }
        }
        const keys = coord.savedColumnKeys(saved)
        for (let i = 0; i < keys.length; i++) {
            const key = String(keys[i] || "")
            const cut = key.indexOf("Col")
            if (cut < 1 || key.indexOf("controlRow") !== 0 || coord.splits[key])
                continue
            const rowKey = key.slice(0, cut)
            if (!coord.splits[rowKey])
                coord.createRow(rowKey)
            coord.createColumn(key, coord.splits[rowKey])
        }
    }

    function applyRowColumnOrder(map) {
        if (!map)
            return
        const names = Object.keys(map)
        for (let i = 0; i < names.length; i++) {
            const row = coord.splits[names[i]]
            const order = map[names[i]]
            if (!row || !row.moveItem || !order)
                continue
            for (let dest = 0; dest < order.length; dest++) {
                const split = coord.splits[order[dest]]
                if (!split)
                    continue
                const current = coord.indexOfItem(row, split)
                if (current >= 0 && current !== dest)
                    row.moveItem(current, dest)
            }
        }
    }

    function ensureSavedRows(saved) {
        const names = coord.savedColumnKeys(saved)
        const order = saved && saved.rowOrder ? saved.rowOrder : []
        for (let i = 0; i < order.length; i++) {
            if (names.indexOf(order[i]) < 0)
                names.push(order[i])
        }
        for (let i = 0; i < names.length; i++) {
            const key = String(names[i] || "")
            if (!coord.isExtraRow({ settingsKey: key }) || coord.splits[key])
                continue
            coord.createRow(key)
        }
    }

    function layoutSplitKeys() {
        return coord.panelHolderKeys().concat(coord.rowKeys).concat(["controlColumns", "controlRows"])
    }

    function collectedIds(saved) {
        const ids = []
        const keys = coord.savedColumnKeys(saved)
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
        const keys = coord.layoutSplitKeys()
        const next = {}
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            if (!split)
                continue
            next[key] = {
                attached: coord.captureProps(split),
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
            panel.columnStretched = false
            if (panel.swapDefaultProps)
                coord.applyProps(panel, panel.swapDefaultProps)
        }
        const keys = coord.builtinColumnKeys.concat(["controlColumns", "controlRows"])
        for (let k = 0; k < keys.length; k++) {
            const key = keys[k]
            const split = coord.splits[key]
            const saved = coord.defaultSplitStates[key]
            if (!split || !saved)
                continue
            split.visible = true
            if (saved.attached)
                coord.applyProps(split, saved.attached)
            if (split.relock)
                split.relock()
        }
        coord.destroyExtraColumns()
        coord.destroyExtraRows()
        coord.applyColumnOrder(coord.builtinColumnKeys)
        coord.applyRowOrder(["controlColumns"])
        coord.syncColumns()
        coord.discardSavedLayout()
        coord.persist()
        return true
    }

    function discardSavedLayout() {
        orderStore.panelOrderJson = ""
        const keys = coord.layoutSplitKeys()
        for (let k = 0; k < keys.length; k++) {
            const split = coord.splits[keys[k]]
            if (split && split.clearSaved)
                split.clearSaved()
        }
    }

    function restoreSplitSizes() {
        const keys = coord.layoutSplitKeys()
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
        coord.ensureSavedColumns(saved)
        coord.ensureSavedRows(saved)
        coord.ensureSavedRowColumns(saved)
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
        const keys = coord.savedColumnKeys(saved)
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
        if (saved.rowOrder)
            coord.applyRowOrder(saved.rowOrder)
        if (saved.rowColumns)
            coord.applyRowColumnOrder(saved.rowColumns)
        coord.restoreSplitSizes()
        coord.syncColumns()
        return true
    }
}
