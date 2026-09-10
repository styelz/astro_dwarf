import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

TextField {
    id: field
    color: field.enabled ? Theme.textPrimary : Theme.textSecondary
    placeholderTextColor: Theme.textSecondary
    selectedTextColor: Theme.hsl(0.046, 0.714, 0.055)
    selectionColor: Theme.accent
    opacity: field.enabled ? 1 : 0.45
    hoverEnabled: true
    font.pixelSize: 13
    leftPadding: 10
    rightPadding: 10
    clip: true
    implicitWidth: 160
    implicitHeight: 34
    Layout.minimumWidth: 0
    Layout.preferredWidth: implicitWidth
    background: Item {
        implicitHeight: 34
        HudFrame {
            anchors.fill: parent
            anchors.margins: -2
            topLeft: Theme.notchSmall + 1
            bottomRight: Theme.notchSmall + 1
            strokeColor: Theme.accent
            opacity: field.activeFocus ? 0.35 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        HudFrame {
            anchors.fill: parent
            topLeft: Theme.notchSmall
            bottomRight: Theme.notchSmall
            fillColor: field.enabled ? Theme.inputBg : Theme.disabledBg
            strokeColor: !field.enabled ? Theme.disabledOutline : field.activeFocus ? Theme.accent : field.hovered ? Theme.outlineStrong : Theme.outline
            strokeWidth: field.activeFocus ? 1.5 : 1
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
        }
        // bottom "active" rail that fills while focused
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            height: 2
            width: field.activeFocus ? parent.width - Theme.notchSmall * 2 - 6 : 0
            color: Theme.accent
            opacity: 0.8
            Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        }
    }
}
