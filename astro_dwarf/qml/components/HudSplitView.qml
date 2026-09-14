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
// Non-fill panes keep their pixel size across window maximize/restore. Qt SplitView
// otherwise rewrites preferred sizes while the window is large, so unmaximize does
// not put the layout back. Fill panes still absorb leftover space.
SplitView {
    id: splitView
    property string settingsKey: ""
    property bool autoRestore: true
    readonly property bool controlLayoutSplit: splitView.settingsKey === "controlColumns"
        || PanelSwap.columnKeys.indexOf(splitView.settingsKey) >= 0
    property var lockedSizes: []
    property int handleDragCount: 0
    property bool applyingLocks: false
    property real lastAlong: -1
    readonly property bool handleDragging: splitView.handleDragCount > 0
    readonly property bool verticalSplit: splitView.orientation === Qt.Vertical

    Settings {
        id: splitStore
        category: "splitLayout"
    }

    readonly property string countKey: splitView.settingsKey === "" ? "" : splitView.settingsKey + "Count"

    function viewAlong() {
        return splitView.verticalSplit ? splitView.height : splitView.width
    }

    function itemAlong(item) {
        return splitView.verticalSplit ? item.height : item.width
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

    function clearFillPreferred(item) {
        if (!item || !item.SplitView)
            return
        if (splitView.verticalSplit)
            item.SplitView.preferredHeight = undefined
        else
            item.SplitView.preferredWidth = undefined
    }

    function itemPreferred(item) {
        if (!item || !item.SplitView)
            return -1
        const n = splitView.verticalSplit
            ? Number(item.SplitView.preferredHeight)
            : Number(item.SplitView.preferredWidth)
        if (isFinite(n) && n >= 8)
            return n
        const laidOut = splitView.itemAlong(item)
        return laidOut >= 8 ? laidOut : -1
    }

    function captureLocked() {
        if (splitView.handleDragging || splitView.applyingLocks)
            return
        if (splitView.viewAlong() < 64)
            return
        const next = []
        let usable = false
        for (let i = 0; i < splitView.count; i++) {
            const it = splitView.itemAt(i)
            if (!it || !it.visible || splitView.itemIsFill(it)) {
                next.push(-1)
                continue
            }
            const size = splitView.itemPreferred(it)
            next.push(size)
            if (size >= 8)
                usable = true
        }
        if (usable)
            splitView.lockedSizes = next
    }

    function applyLocked() {
        if (splitView.handleDragging || splitView.applyingLocks)
            return
        if (splitView.viewAlong() < 64)
            return
        const sizes = splitView.lockedSizes
        if (!sizes || sizes.length !== splitView.count) {
            splitView.captureLocked()
            return
        }
        splitView.applyingLocks = true
        for (let i = 0; i < splitView.count; i++) {
            const it = splitView.itemAt(i)
            if (!it || !it.visible)
                continue
            if (splitView.itemIsFill(it)) {
                splitView.clearFillPreferred(it)
                continue
            }
            const size = Number(sizes[i])
            if (size >= 8)
                splitView.setItemPreferred(it, size)
        }
        splitView.applyingLocks = false
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
        const state = splitStore.value(splitView.settingsKey)
        if (state)
            splitView.restoreState(state)
        Qt.callLater(splitView.captureLocked)
    }

    function persist() {
        if (splitView.settingsKey === "")
            return
        if (splitView.viewAlong() < 64)
            return
        splitView.captureLocked()
        splitStore.setValue(splitView.settingsKey, splitView.saveState())
        splitStore.setValue(splitView.countKey, splitView.count)
    }

    function clearSaved() {
        if (splitView.settingsKey === "")
            return
        splitStore.setValue(splitView.settingsKey, "")
        splitStore.setValue(splitView.countKey, 0)
        splitView.lockedSizes = []
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
        implicitWidth: 8
        implicitHeight: 8
        color: SplitHandle.pressed ? Theme.glowAccent : (SplitHandle.hovered ? Theme.hsl(0.039, 0.535, 0.253, 0.13) : "transparent")
        property bool dragging: SplitHandle.pressed
        onDraggingChanged: {
            if (dragging) {
                splitView.handleDragCount += 1
                return
            }
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
