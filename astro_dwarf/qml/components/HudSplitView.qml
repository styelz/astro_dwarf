import QtQuick
import QtQuick.Controls
import QtQuick.Window
import QtCore
import ".."

// SplitView that remembers its own sizes. Give it a settingsKey and it restores on
// startup and saves when the window closes; no coordinator needs to know its id.
SplitView {
    id: splitView
    property string settingsKey: ""

    Settings {
        id: splitStore
        category: "splitLayout"
    }

    function restore() {
        if (splitView.settingsKey === "")
            return
        const state = splitStore.value(splitView.settingsKey)
        if (state)
            splitView.restoreState(state)
    }

    function persist() {
        if (splitView.settingsKey !== "")
            splitStore.setValue(splitView.settingsKey, splitView.saveState())
    }

    Timer {
        interval: 1
        running: true
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
