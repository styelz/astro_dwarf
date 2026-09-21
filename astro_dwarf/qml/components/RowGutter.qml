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
    implicitWidth: Theme.s5
    width: Theme.s5

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        x: Math.round((parent.width - width) / 2)
        width: Theme.s1
        height: Math.max(Theme.s2, parent.height - gutter.spineInset * 2)
        radius: Theme.px(2)
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
