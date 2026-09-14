pragma Singleton
import QtQuick
import QtQuick.Controls
import QtCore

// Control-page panel drag. Drop on a panel body to swap slots; drop on the
// leading or trailing edge to insert beside it.
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
        coord.clearHover()
        coord.active = false
        coord.source = null
        coord.dropMode = ""
        if (!a || !b || a === b)
            return
        Qt.callLater(function() {
            if (mode === "before")
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
        const edge = Math.max(20, Math.min(56, span * 0.33))
        if (along < edge)
            return "before"
        if (along > span - edge)
            return "after"
        return "swap"
    }

    function refreshHover(position) {
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
            if (key !== "controlColumns" && saved.attached)
                coord.applyProps(split, saved.attached)
            if (saved.state && split.restoreState)
                split.restoreState(saved.state)
        }
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
            return false
        }
        let saved
        try {
            saved = JSON.parse(raw)
        } catch (e) {
            orderStore.panelOrderJson = ""
            coord.restoreSplitSizes()
            return false
        }
        if (!saved || typeof saved !== "object" || !coord.layoutComplete(saved)) {
            coord.restoreSplitSizes()
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
        coord.restoreSplitSizes()
        return true
    }
}
