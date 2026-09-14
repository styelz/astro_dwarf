import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtCore
import ".."

// SplitView that remembers its own sizes. Give it a settingsKey and it restores on
// startup and saves when the window closes; no coordinator needs to know its id.
// Set autoRestore false when a coordinator (PanelSwap) reorders children first —
// restoreState warns and no-ops if the saved blob has more items than exist yet.
SplitView {
    id: splitView
    property string settingsKey: ""
    property bool autoRestore: true

    Settings {
        id: splitStore
        category: "splitLayout"
    }

    readonly property string countKey: splitView.settingsKey === "" ? "" : splitView.settingsKey + "Count"

    function restore() {
        if (splitView.settingsKey === "")
            return
        const savedCount = Number(splitStore.value(splitView.countKey))
        if (isFinite(savedCount) && savedCount > 0 && savedCount !== splitView.count)
            return
        const state = splitStore.value(splitView.settingsKey)
        if (state)
            splitView.restoreState(state)
    }

    function persist() {
        if (splitView.settingsKey === "")
            return
        splitStore.setValue(splitView.settingsKey, splitView.saveState())
        splitStore.setValue(splitView.countKey, splitView.count)
    }

    function clearSaved() {
        if (splitView.settingsKey === "")
            return
        splitStore.setValue(splitView.settingsKey, "")
        splitStore.setValue(splitView.countKey, 0)
    }

    Timer {
        interval: 1
        running: splitView.autoRestore
        repeat: false
        onTriggered: splitView.restore()
    }

    Connections {
        target: splitView.Window.window
        function onClosing() { splitView.persist() }
    }

    handle: Rectangle {
        implicitWidth: 8
        implicitHeight: 8
        color: SplitHandle.pressed ? Theme.glowAccent : (SplitHandle.hovered ? Theme.hsl(0.039, 0.535, 0.253, 0.13) : "transparent")
        Rectangle {
            anchors.centerIn: parent
            width: parent.width >= parent.height ? 22 : 2
            height: parent.width >= parent.height ? 2 : 22
            radius: 1
            color: SplitHandle.pressed ? Theme.accent : (SplitHandle.hovered ? Theme.accent : Theme.outline)
        }
    }
}
