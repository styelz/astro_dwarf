import QtQuick
import QtQuick.Controls
import ".."

CheckBox {
    id: box
    property string accessibleName: ""
    property string accessibleDescription: ""
    font.pixelSize: Theme.fontBase
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: accessibleName || text
    Accessible.description: accessibleDescription
    spacing: 10
    padding: 0
    opacity: enabled ? 1 : 0.5
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }

    readonly property bool ticked: checkState === Qt.Checked
    readonly property bool lit: ticked || checkState === Qt.PartiallyChecked
    readonly property color lineColor: !box.enabled ? Theme.disabledOutline
                                     : box.lit || box.hovered || box.visualFocus ? Theme.accent : Theme.outline

    function setOn(value) {
        const on = !!value
        checked = on
        checkState = on ? Qt.Checked : Qt.Unchecked
    }

    indicator: Item {
        implicitWidth: 20
        implicitHeight: 20
        x: box.leftPadding
        y: box.height / 2 - height / 2

        // soft glow that breathes in on hover / focus
        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: 4
            color: "transparent"
            border.color: Theme.accent
            border.width: 1
            opacity: box.visualFocus ? 0.9 : box.hovered && box.enabled ? 0.35 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        HudFrame {
            anchors.fill: parent
            topLeft: 5
            bottomRight: 5
            strokeWidth: box.lit || box.visualFocus ? Theme.focusStroke : 1
            strokeColor: box.lineColor
            fillColor: !box.enabled ? Theme.disabledBg : box.lit ? Theme.fillChecked : box.down ? Theme.fillActive : Theme.inputBg
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
            Behavior on fillColor { ColorAnimation { duration: Theme.quick } }
        }
        // inner lit fill pulse when checked
        Rectangle {
            anchors.fill: parent
            anchors.margins: 3
            color: Theme.accent
            opacity: box.ticked ? 0.10 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        }
        HudCheckMark {
            anchors.fill: parent
            anchors.margins: 3
            on: box.ticked
            color: box.enabled ? Theme.accent : Theme.textSecondary
        }
        Rectangle {
            // partial state dash
            anchors.centerIn: parent
            width: parent.width - 10
            height: 2
            color: Theme.accent
            visible: box.checkState === Qt.PartiallyChecked
        }
    }

    contentItem: Text {
        text: box.text
        color: box.enabled ? Theme.textPrimary : Theme.textSecondary
        font: box.font
        leftPadding: box.indicator.width + box.spacing
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
        wrapMode: Text.NoWrap
    }
}
