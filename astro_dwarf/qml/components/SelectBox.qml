import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: selectBox
    property bool checked: false
    property bool revealed: false
    readonly property bool shown: revealed || checked
    signal toggled(bool shiftHeld)
    z: 30
    implicitWidth: 13
    implicitHeight: 13
    width: 13
    height: 13
    opacity: shown ? 1 : 0
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: 90 } }
    Rectangle {
        anchors.fill: parent
        color: selectBox.checked ? Theme.hsl(0.036, 0.640, 0.196, 0.941) : Theme.hsl(0.083, 0.571, 0.055, 0.878)
        border.color: Theme.accent
        border.width: 1
        radius: 2
        Text {
            anchors.centerIn: parent
            text: selectBox.checked ? "✓" : ""
            color: Theme.accent
            font.pixelSize: 9
            font.bold: true
        }
    }
    MouseArea {
        anchors.fill: parent
        anchors.margins: -4
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        propagateComposedEvents: false
        cursorShape: Qt.PointingHandCursor
        onClicked: mouse => {
            mouse.accepted = true
            selectBox.toggled(!!(mouse.modifiers & Qt.ShiftModifier))
        }
    }
}
