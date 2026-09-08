import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

CheckBox {
    id: box
    font.pixelSize: 13
    contentItem: Text {
        text: box.text
        color: Theme.textPrimary
        font: box.font
        leftPadding: box.indicator.width + 8
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: box.leftPadding
        y: parent.height / 2 - height / 2
        color: box.checked ? Theme.fillChecked : Theme.inputBg
        border.color: Theme.accent
        Text { anchors.centerIn: parent; text: box.checked ? "✓" : ""; color: Theme.accent; font.pixelSize: 12 }
    }
}
