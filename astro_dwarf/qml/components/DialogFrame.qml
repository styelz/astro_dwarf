import QtQuick
import ".."

// Background for dialogs: notched surface with corner ticks in the dialog's tone.
Item {
    id: dialogFrame
    property color tone: Theme.accent
    MouseArea {
        anchors.fill: parent
        z: -1
        acceptedButtons: Qt.LeftButton
        onPressed: (mouse) => {
            const focused = dialogFrame.Window.window ? dialogFrame.Window.window.activeFocusItem : null
            if (focused)
                focused.focus = false
            mouse.accepted = false
        }
    }
    HudFrame {
        anchors.fill: parent
        topLeft: Theme.notch
        topRight: Theme.notch
        bottomRight: Theme.notch
        bottomLeft: Theme.notch
        fillColor: Theme.surface
        strokeColor: dialogFrame.tone
        strokeWidth: 1.25
    }
    Rectangle { x: Theme.notch; y: Theme.px(1); width: Theme.s4; height: Theme.px(2); color: dialogFrame.tone }
    Rectangle { x: Theme.px(1); y: Theme.notch; width: Theme.px(2); height: Theme.s4; color: dialogFrame.tone }
    Rectangle { x: parent.width - Theme.notch - 16; y: parent.height - Theme.px(3); width: Theme.s4; height: Theme.px(2); color: dialogFrame.tone }
    Rectangle { x: parent.width - Theme.px(3); y: parent.height - Theme.notch - 16; width: Theme.px(2); height: Theme.s4; color: dialogFrame.tone }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Theme.px(2)
        height: Math.min(Theme.px(72), parent.height * 0.4)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(dialogFrame.tone.r, dialogFrame.tone.g, dialogFrame.tone.b, 0.08) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
}
