pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtCore
import ".."

// SplitView that remembers its own sizes. Give it a settingsKey and it restores on
// startup and saves when the window closes; no coordinator needs to know its id.
// Set autoRestore false when a coordinator (PanelSwap) reorders children first —
// restoreState warns and no-ops if the saved blob has more items than exist yet.
//
// Visible panes keep their share of the split across window maximize/restore.
// Qt SplitView otherwise rewrites preferred sizes while the window is large, so
// proportions drift. Fill panes still absorb leftover pixels after rounding.
// While a handle is dragged, fill is pinned to the pane after that bar so the
// two joined panels resize together instead of dumping leftover onto CAMERA / LOG.
SplitView {
    id: splitView
    property string settingsKey: ""
    property bool autoRestore: true
    readonly property bool controlLayoutSplit: splitView.settingsKey === "controlColumns"
        || PanelSwap.columnKeys.indexOf(splitView.settingsKey) >= 0
    property var lockedRatios: []
    property int handleDragCount: 0
    property bool applyingLocks: false
    property bool neighborResizeActive: false
    property int pinnedFillIndex: -1
    property real lastAlong: -1
    readonly property bool handleDragging: splitView.handleDragCount > 0
    readonly property bool verticalSplit: splitView.orientation === Qt.Vertical

    Settings {
        id: splitStore
        category: "splitLayout"
    }

    readonly property string countKey: splitView.settingsKey === "" ? "" : splitView.settingsKey + "Count"
    readonly property string ratiosKey: splitView.settingsKey === "" ? "" : splitView.settingsKey + "Ratios"

    function viewAlong() {
        return splitView.verticalSplit ? splitView.height : splitView.width
    }

    function itemAlong(item) {
        return splitView.verticalSplit ? item.height : item.width
    }

    function itemMinimum(item) {
        if (!item || !item.SplitView)
            return 0
        const n = splitView.verticalSplit
            ? Number(item.SplitView.minimumHeight)
            : Number(item.SplitView.minimumWidth)
        return isFinite(n) && n > 0 ? n : 0
    }

    function itemIsFill(item) {
        if (!item || !item.SplitView)
            return false
        return splitView.verticalSplit ? !!item.SplitView.fillHeight : !!item.SplitView.fillWidth
    }

    function setItemPreferred(item, size) {
        if (!item || !item.SplitView)
            return
        if (splitView.verticalSplit)
            item.SplitView.preferredHeight = size
        else
            item.SplitView.preferredWidth = size
    }

    function itemPreferred(item) {
        if (!item || !item.SplitView)
            return -1
        const n = splitView.verticalSplit
            ? Number(item.SplitView.preferredHeight)
            : Number(item.SplitView.preferredWidth)
        if (isFinite(n) && n >= 8)
            return n
        return -1
    }

    function isLaidOut(item) {
        if (!item || !item.visible)
            return false
        return splitView.itemAlong(item) > 0.5
    }

    function snapshotPreferred() {
        for (let i = 0; i < splitView.count; i++) {
            const item = splitView.itemAt(i)
            if (!item || !item.SplitView)
                continue
            item.SplitView.preferredWidth = item.width
            item.SplitView.preferredHeight = item.height
        }
    }

    function clearFills() {
        for (let i = 0; i < splitView.count; i++) {
            const item = splitView.itemAt(i)
            if (!item || !item.SplitView)
                continue
            if (splitView.verticalSplit)
                item.SplitView.fillHeight = false
            else
                item.SplitView.fillWidth = false
        }
    }

    function setFillAt(index) {
        const item = splitView.itemAt(index)
        if (!item || !item.SplitView)
            return
        if (splitView.verticalSplit)
            item.SplitView.fillHeight = true
        else
            item.SplitView.fillWidth = true
    }

    function captureFillIndex() {
        for (let i = 0; i < splitView.count; i++) {
            if (splitView.itemIsFill(splitView.itemAt(i)))
                return i
        }
        for (let i = splitView.count - 1; i >= 0; i--) {
            if (splitView.isLaidOut(splitView.itemAt(i)))
                return i
        }
        return -1
    }

    function neighborAfter(handleItem) {
        if (!handleItem)
            return -1
        const mid = handleItem.mapToItem(splitView, handleItem.width / 2, handleItem.height / 2)
        const along = splitView.verticalSplit ? mid.y : mid.x
        for (let i = 0; i < splitView.count; i++) {
            const item = splitView.itemAt(i)
            if (!splitView.isLaidOut(item))
                continue
            const startPt = item.mapToItem(splitView, 0, 0)
            const start = splitView.verticalSplit ? startPt.y : startPt.x
            if (along < start)
                return i
        }
        return -1
    }

    function beginNeighborResize(handleItem) {
        if (splitView.neighborResizeActive)
            return
        const next = splitView.neighborAfter(handleItem)
        if (next < 0)
            return
        splitView.pinnedFillIndex = splitView.captureFillIndex()
        splitView.snapshotPreferred()
        splitView.clearFills()
        splitView.setFillAt(next)
        splitView.neighborResizeActive = true
    }

    function endNeighborResize() {
        if (!splitView.neighborResizeActive)
            return
        const restore = splitView.pinnedFillIndex
        splitView.snapshotPreferred()
        splitView.clearFills()
        splitView.neighborResizeActive = false
        splitView.pinnedFillIndex = -1
        if (restore >= 0 && restore < splitView.count)
            splitView.setFillAt(restore)
    }

    function paneUsable() {
        let sum = 0
        for (let i = 0; i < splitView.count; i++) {
            const it = splitView.itemAt(i)
            if (it && it.visible)
                sum += splitView.itemAlong(it)
        }
        if (sum >= 8)
            return sum
        return splitView.viewAlong()
    }

    function parseRatios(raw) {
        if (raw === undefined || raw === null || raw === "")
            return null
        try {
            const parsed = typeof raw === "string" ? JSON.parse(raw) : raw
            if (!parsed || parsed.length === undefined)
                return null
            const out = []
            for (let i = 0; i < parsed.length; i++) {
                const n = Number(parsed[i])
                if (!isFinite(n))
                    return null
                out.push(n)
            }
            return out
        } catch (e) {
            return null
        }
    }

    function ratiosValid(ratios) {
        if (!ratios || ratios.length !== splitView.count)
            return false
        let sum = 0
        let any = false
        for (let i = 0; i < ratios.length; i++) {
            const r = Number(ratios[i])
            if (!isFinite(r) || r < 0)
                continue
            if (r > 0)
                any = true
            sum += r
        }
        return any && sum > 0.5 && sum < 1.5
    }

    function captureLocked() {
        if (splitView.handleDragging || splitView.applyingLocks)
            return
        if (splitView.viewAlong() < 64)
            return
        const usable = splitView.paneUsable()
        if (usable < 8)
            return
        const sizes = []
        const fillIdx = []
        let reserved = 0
        let fillLaid = 0
        for (let i = 0; i < splitView.count; i++) {
            const it = splitView.itemAt(i)
            if (!it || !it.visible) {
                sizes.push(-1)
                continue
            }
            if (splitView.itemIsFill(it)) {
                sizes.push(0)
                fillIdx.push(i)
                const laid = splitView.itemAlong(it)
                fillLaid += laid >= 0 ? laid : 0
                continue
            }
            const pref = splitView.itemPreferred(it)
            const laid = splitView.itemAlong(it)
            const size = pref >= 8 ? pref : laid
            if (size < 8) {
                sizes.push(-1)
                continue
            }
            sizes.push(size)
            reserved += size
        }
        let fillSpace = Math.max(0, usable - reserved)
        if (fillIdx.length === 0) {
            if (reserved < 8)
                return
            fillSpace = reserved
        }
        for (let f = 0; f < fillIdx.length; f++) {
            const i = fillIdx[f]
            const it = splitView.itemAt(i)
            const laid = it ? splitView.itemAlong(it) : 0
            sizes[i] = fillLaid > 0 ? fillSpace * laid / fillLaid : fillSpace / fillIdx.length
        }
        const total = fillIdx.length === 0 ? reserved : reserved + fillSpace
        if (total < 8)
            return
        const next = []
        let any = false
        for (let i = 0; i < sizes.length; i++) {
            if (sizes[i] < 0) {
                next.push(-1)
                continue
            }
            next.push(sizes[i] / total)
            any = true
        }
        if (any)
            splitView.lockedRatios = next
    }

    function applyLocked() {
        if (splitView.handleDragging || splitView.applyingLocks)
            return
        if (splitView.viewAlong() < 64)
            return
        const ratios = splitView.lockedRatios
        if (!splitView.ratiosValid(ratios)) {
            splitView.captureLocked()
            return
        }
        const usable = splitView.paneUsable()
        if (usable < 8)
            return
        splitView.applyingLocks = true
        for (let i = 0; i < splitView.count; i++) {
            const it = splitView.itemAt(i)
            if (!it || !it.visible)
                continue
            const ratio = Number(ratios[i])
            if (!isFinite(ratio) || ratio < 0)
                continue
            const size = Math.max(splitView.itemMinimum(it), Math.round(ratio * usable))
            if (size >= 8)
                splitView.setItemPreferred(it, size)
        }
        splitView.applyingLocks = false
    }

    function relock() {
        splitView.captureLocked()
        splitView.applyLocked()
    }

    function scheduleApply() {
        const along = splitView.viewAlong()
        if (along < 64)
            return
        const changed = splitView.lastAlong >= 0 && Math.abs(along - splitView.lastAlong) >= 1
        splitView.lastAlong = along
        if (changed)
            Qt.callLater(splitView.applyLocked)
    }

    function restore() {
        if (splitView.settingsKey === "")
            return
        const savedCount = Number(splitStore.value(splitView.countKey))
        if (isFinite(savedCount) && savedCount > 0 && savedCount !== splitView.count)
            return
        const ratios = splitView.parseRatios(splitStore.value(splitView.ratiosKey))
        if (splitView.ratiosValid(ratios)) {
            splitView.lockedRatios = ratios
            splitView.applyLocked()
            return
        }
        const state = splitStore.value(splitView.settingsKey)
        if (state)
            splitView.restoreState(state)
        splitView.captureLocked()
    }

    function persist() {
        if (splitView.neighborResizeActive)
            splitView.endNeighborResize()
        if (splitView.settingsKey === "")
            return
        if (splitView.viewAlong() < 64)
            return
        splitView.captureLocked()
        splitStore.setValue(splitView.settingsKey, splitView.saveState())
        splitStore.setValue(splitView.countKey, splitView.count)
        splitStore.setValue(splitView.ratiosKey, JSON.stringify(splitView.lockedRatios || []))
    }

    function clearSaved() {
        if (splitView.settingsKey === "")
            return
        splitStore.setValue(splitView.settingsKey, "")
        splitStore.setValue(splitView.countKey, 0)
        splitStore.setValue(splitView.ratiosKey, "")
        splitView.lockedRatios = []
    }

    onWidthChanged: if (!splitView.verticalSplit)
        splitView.scheduleApply()
    onHeightChanged: if (splitView.verticalSplit)
        splitView.scheduleApply()
    onCountChanged: Qt.callLater(function() {
        if (!splitView.handleDragging)
            splitView.captureLocked()
    })

    Timer {
        interval: 1
        running: true
        repeat: false
        onTriggered: {
            if (splitView.autoRestore)
                splitView.restore()
            else
                splitView.captureLocked()
        }
    }

    Connections {
        target: splitView.Window.window
        function onClosing() { splitView.persist() }
    }

    handle: Rectangle {
        id: grip
        objectName: "splitHandle"
        implicitWidth: 8
        implicitHeight: 8
        color: SplitHandle.pressed ? Theme.glowAccent : (SplitHandle.hovered ? Theme.hsl(0.039, 0.535, 0.253, 0.13) : "transparent")
        property bool dragging: SplitHandle.pressed
        onDraggingChanged: {
            if (dragging) {
                splitView.handleDragCount += 1
                splitView.beginNeighborResize(grip)
                return
            }
            splitView.endNeighborResize()
            splitView.handleDragCount = Math.max(0, splitView.handleDragCount - 1)
            Qt.callLater(splitView.captureLocked)
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: splitView.controlLayoutSplit
            onTapped: layoutMenu.popup()
        }
        LayoutContextMenu {
            id: layoutMenu
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width >= parent.height ? 22 : 2
            height: parent.width >= parent.height ? 2 : 22
            radius: 1
            color: SplitHandle.pressed ? Theme.accent : (SplitHandle.hovered ? Theme.accent : Theme.outline)
        }
    }
}
