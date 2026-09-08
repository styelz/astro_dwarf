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
    background: Item {
        implicitHeight: 34
        implicitWidth: 120
        HudFrame {
            anchors.fill: parent
            anchors.margins: -2
            topLeft: Theme.notchSmall + 1
            bottomRight: Theme.notchSmall + 1
            strokeColor: Theme.accent
            opacity: combo.popup.visible || combo.visualFocus ? 0.35 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        HudFrame {
            anchors.fill: parent
            topLeft: Theme.notchSmall
            bottomRight: Theme.notchSmall
            fillColor: combo.enabled ? (combo.down ? Theme.fillActive : Theme.inputBg) : Theme.disabledBg
            strokeColor: !combo.enabled ? Theme.disabledOutline : combo.hovered || combo.down || combo.popup.visible ? Theme.accent : Theme.outline
            strokeWidth: combo.popup.visible ? 1.5 : 1
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
            Behavior on fillColor { ColorAnimation { duration: Theme.quick } }
        }
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
        rotation: combo.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
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
        height: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 242)
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.base: Theme.popupBg
        palette.text: Theme.textPrimary
        background: HudFrame {
            implicitWidth: combo.width
            implicitHeight: 32
            topLeft: 0
            topRight: 0
            bottomRight: Theme.notchSmall
            bottomLeft: 0
            fillColor: Theme.popupBg
            strokeColor: Theme.accent
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: combo.popup.visible ? combo.delegateModel : null
            currentIndex: combo.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
        }
    }
}
