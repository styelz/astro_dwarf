import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Button {
    id: commandPad
    property string glyph: ""
    property string detail: ""
    property bool activeState: false
    property bool pending: false
    property bool destructive: false
    property string flash: ""   // "", "success" or "error"
    readonly property color flashColor: flash === "error" ? Theme.danger : Theme.success
    hoverEnabled: enabled
    implicitHeight: 58
    leftPadding: 8
    rightPadding: 8
    function showFlash(kind) {
        flash = kind
        flashTimer.restart()
    }
    Timer { id: flashTimer; interval: 900; onTriggered: commandPad.flash = "" }
    background: Rectangle {
        id: padBackground
        color: commandPad.flash !== "" ? Qt.rgba(commandPad.flashColor.r, commandPad.flashColor.g, commandPad.flashColor.b, 0.22)
             : commandPad.destructive ? "#301117" : commandPad.activeState ? Theme.hsl(-0.049, 0.538, 0.153) : commandPad.pending ? Theme.hsl(0.046, 0.600, 0.147) : commandPad.down ? Theme.hsl(0.033, 0.627, 0.116) : commandPad.hovered ? Theme.hsl(0.046, 0.581, 0.169) : Theme.hsl(0.066, 0.532, 0.092)
        border.color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.destructive ? Theme.danger : commandPad.activeState ? Theme.success : commandPad.pending || commandPad.hovered ? Theme.accent : Theme.outline
        border.width: commandPad.activeState || commandPad.hovered || commandPad.pending || commandPad.flash !== "" ? 2 : 1
        radius: 4
        Behavior on color { ColorAnimation { duration: 160 } }
        Behavior on border.color { ColorAnimation { duration: 160 } }
        Rectangle { x: 4; y: 4; width: parent.width - 8; height: 1; color: commandPad.destructive ? Theme.danger : Theme.accent; opacity: 0.35 }
        Rectangle {
            // pulsing ring while the device reports the command running
            anchors.fill: parent
            anchors.margins: -3
            radius: 6
            color: "transparent"
            border.color: commandPad.activeState ? Theme.success : Theme.accent
            border.width: 1
            visible: commandPad.activeState || commandPad.pending
            opacity: 0
            SequentialAnimation on opacity {
                running: commandPad.activeState || commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 0.7; to: 0; duration: commandPad.pending ? 600 : 1100; easing.type: Easing.OutQuad }
                PauseAnimation { duration: commandPad.pending ? 150 : 400 }
            }
        }
        Rectangle {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 7
            width: 7; height: 7; radius: 4
            color: commandPad.activeState ? Theme.success : commandPad.pending ? Theme.accent : commandPad.enabled ? Theme.hsl(0.042, 0.372, 0.306) : Theme.hsl(0.050, 0.361, 0.141)
            border.color: commandPad.activeState ? "#C8FFE9" : Theme.outline
            SequentialAnimation on opacity {
                running: commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.2; duration: 320 }
                NumberAnimation { from: 0.2; to: 1; duration: 320 }
            }
        }
    }
    contentItem: RowLayout {
        spacing: 7
        Text { text: commandPad.glyph; color: commandPad.destructive ? Theme.danger : commandPad.activeState ? Theme.success : Theme.accent; font.pixelSize: Math.round(Math.min(26, Math.max(16, commandPad.height * 0.32))); Layout.preferredWidth: font.pixelSize + 6; horizontalAlignment: Text.AlignHCenter }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 0
            Text { text: commandPad.text; color: commandPad.enabled || commandPad.activeState ? Theme.textPrimary : Theme.textSecondary; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.7; elide: Text.ElideRight; Layout.fillWidth: true }
            Text { text: commandPad.flash === "success" ? "DONE" : commandPad.flash === "error" ? "FAILED" : commandPad.pending ? "SENDING…" : commandPad.detail; color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.activeState ? Theme.success : commandPad.pending ? Theme.accent : Theme.textSecondary; font.pixelSize: 8; font.family: commandPad.activeState ? Theme.fontMono : Theme.fontUi; elide: Text.ElideRight; Layout.fillWidth: true }
        }
    }
}
