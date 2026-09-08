import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

ComboBox {
    id: combo
    implicitHeight: 34
    font.pixelSize: 13
    palette.window: Theme.popupBg
    palette.windowText: Theme.textPrimary
    palette.base: Theme.popupBg
    palette.text: Theme.textPrimary
    palette.button: Theme.inputBg
    palette.buttonText: Theme.textPrimary
    palette.highlight: Theme.fillChecked
    palette.highlightedText: Theme.accent
    opacity: combo.enabled ? 1 : 0.45
    background: Rectangle {
        color: combo.enabled ? Theme.inputBg : Theme.disabledBg
        border.color: !combo.enabled ? Theme.disabledOutline : combo.hovered || combo.down ? Theme.accent : Theme.outline
        border.width: 1
        radius: 2
    }
    contentItem: Text {
        leftPadding: 10
        rightPadding: 22
        text: combo.displayText
        color: combo.enabled ? Theme.textPrimary : Theme.textSecondary
        font: combo.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        text: "▾"
        color: combo.enabled ? Theme.accent : Theme.textSecondary
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
    }
    delegate: ItemDelegate {
        width: combo.width
        height: 32
        highlighted: combo.highlightedIndex === index
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.text: Theme.textPrimary
        palette.highlightedText: Theme.accent
        contentItem: Text {
            text: combo.textAt(index)
            color: highlighted ? Theme.accent : Theme.textPrimary
            font.pixelSize: 13
            verticalAlignment: Text.AlignVCenter
            leftPadding: 10
        }
        background: Rectangle { color: highlighted ? Theme.fillChecked : Theme.popupBg }
    }
    popup: Popup {
        y: combo.height + 3
        width: combo.width
        padding: 1
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.base: Theme.popupBg
        palette.text: Theme.textPrimary
        background: Rectangle { color: Theme.popupBg; border.color: Theme.accent }
        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, 240)
            model: combo.popup.visible ? combo.delegateModel : null
            currentIndex: combo.highlightedIndex
        }
    }
}
