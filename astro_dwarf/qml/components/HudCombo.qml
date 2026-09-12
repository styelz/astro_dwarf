pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

ComboBox {
    id: combo
    // shown instead of a blank box when nothing is selected, e.g. mixed values
    property string emptyText: ""
    property string accessibleName: ""
    property string accessibleDescription: ""
    displayText: combo.currentIndex < 0 && combo.emptyText ? combo.emptyText : combo.currentText
    implicitWidth: 160
    implicitHeight: Theme.controlHeight
    Layout.minimumWidth: 0
    Layout.preferredWidth: implicitWidth
    font.pixelSize: Theme.fontBase
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: accessibleName || displayText
    Accessible.description: accessibleDescription
    palette.window: Theme.popupBg
    palette.windowText: Theme.textPrimary
    palette.base: Theme.popupBg
    palette.text: Theme.textPrimary
    palette.button: Theme.inputBg
    palette.buttonText: Theme.textPrimary
    palette.highlight: Theme.fillChecked
    palette.highlightedText: Theme.accent
    opacity: combo.enabled ? 1 : 0.45
    HoverHandler {
        enabled: combo.enabled
        cursorShape: Qt.PointingHandCursor
    }
    background: Item {
        implicitHeight: Theme.controlHeight
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
            strokeColor: !combo.enabled ? Theme.disabledOutline : combo.hovered || combo.down || combo.popup.visible || combo.visualFocus ? Theme.accent : Theme.outline
            strokeWidth: combo.popup.visible || combo.visualFocus ? Theme.focusStroke : 1
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
        id: optionItem
        required property int index
        width: combo.width
        height: 32
        highlighted: combo.highlightedIndex === index
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.text: Theme.textPrimary
        palette.highlightedText: Theme.accent
        contentItem: Text {
            text: combo.textAt(optionItem.index)
            color: optionItem.highlighted ? Theme.accent : Theme.textPrimary
            font.pixelSize: Theme.fontBase
            verticalAlignment: Text.AlignVCenter
            leftPadding: 10
        }
        background: Rectangle { color: optionItem.highlighted ? Theme.fillChecked : Theme.popupBg }
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
