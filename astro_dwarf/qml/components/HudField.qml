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
    font.pixelSize: 13
    leftPadding: 10
    rightPadding: 10
    implicitHeight: 34
    background: Rectangle {
        color: field.enabled ? Theme.inputBg : Theme.disabledBg
        border.color: !field.enabled ? Theme.disabledOutline : field.activeFocus ? Theme.accent : Theme.outline
        border.width: 1
        radius: 2
    }
}
