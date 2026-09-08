import QtQuick
import ".."

// Background for dialogs: notched surface with corner ticks in the dialog's tone.
Item {
    id: dialogFrame
    property color tone: Theme.accent
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
    Rectangle { x: Theme.notch; y: 1; width: 16; height: 2; color: dialogFrame.tone }
    Rectangle { x: 1; y: Theme.notch; width: 2; height: 16; color: dialogFrame.tone }
    Rectangle { x: parent.width - Theme.notch - 16; y: parent.height - 3; width: 16; height: 2; color: dialogFrame.tone }
    Rectangle { x: parent.width - 3; y: parent.height - Theme.notch - 16; width: 2; height: 16; color: dialogFrame.tone }
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 2
        height: Math.min(72, parent.height * 0.4)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(dialogFrame.tone.r, dialogFrame.tone.g, dialogFrame.tone.b, 0.08) }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
}
