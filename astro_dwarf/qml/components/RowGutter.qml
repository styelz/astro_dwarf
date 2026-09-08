import QtQuick
import ".."

// Left gutter for session rows: a device-colour spine that the row selector floats
// over, so revealing the selector never leaves a dead column beside the text.
Item {
    id: gutter
    property color spineColor: Theme.accent
    property bool checked: false
    property bool revealed: false
    property int spineInset: 6
    signal toggled(bool shiftHeld)
    implicitWidth: 20
    width: 20

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        x: Math.round((parent.width - width) / 2)
        width: 4
        height: Math.max(8, parent.height - gutter.spineInset * 2)
        radius: 2
        color: gutter.spineColor
        opacity: select.shown ? 0.3 : 1
        Behavior on opacity { NumberAnimation { duration: Theme.quick } }
    }
    SelectBox {
        id: select
        anchors.centerIn: parent
        checked: gutter.checked
        revealed: gutter.revealed
        onToggled: shiftHeld => gutter.toggled(shiftHeld)
    }
}
