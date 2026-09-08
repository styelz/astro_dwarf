import QtQuick
import ".."

// Floating row selector. Floats above a row instead of taking layout space, so
// revealing it never shifts content. Same silhouette as HudCheck so selection reads
// as one system.
Item {
    id: selectBox
    property bool checked: false
    property bool revealed: false
    readonly property bool shown: revealed || checked
    signal toggled(bool shiftHeld)
    z: 30
    implicitWidth: 14
    implicitHeight: 14
    width: 14
    height: 14
    opacity: shown ? 1 : 0
    scale: shown ? 1 : 0.7
    enabled: shown
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }
    Behavior on scale { NumberAnimation { duration: Theme.quick; easing.type: Easing.OutCubic } }

    // scrim so the box stays legible over text or colour bars
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: 3
        color: Theme.popupBg
        opacity: 0.85
    }
    HudFrame {
        anchors.fill: parent
        topLeft: 4
        bottomRight: 4
        strokeWidth: 1
        strokeColor: selectBox.checked || hoverArea.containsMouse ? Theme.accent : Theme.outlineStrong
        fillColor: selectBox.checked ? Theme.fillChecked : Theme.inputBg
        Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
        Behavior on fillColor { ColorAnimation { duration: Theme.quick } }
    }
    HudCheckMark {
        anchors.fill: parent
        anchors.margins: 2
        on: selectBox.checked
        strokeWidth: 1.6
    }
    MouseArea {
        id: hoverArea
        anchors.fill: parent
        anchors.margins: -5
        hoverEnabled: true
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
