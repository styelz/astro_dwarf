import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

SpinBox {
    id: box
    property string tooltip: ""
    property string accessibleName: ""
    property string accessibleDescription: ""
    editable: true
    implicitHeight: Theme.controlHeight
    implicitWidth: 140
    Layout.minimumWidth: 0
    Layout.preferredWidth: implicitWidth
    font.pixelSize: Theme.fontBase
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    palette.text: Theme.textPrimary
    palette.base: Theme.inputBg
    palette.button: Theme.surfaceHigh
    palette.buttonText: Theme.accent
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.textPrimary
    opacity: box.enabled ? 1 : 0.45
    Accessible.name: accessibleName
    Accessible.description: accessibleDescription || tooltip
    HudToolTip {
        visible: box.tooltip !== "" && box.hovered
        text: box.tooltip
    }
    WheelHandler {
        enabled: box.enabled
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        acceptedModifiers: Qt.NoModifier
        blocking: true
        onWheel: event => {
            const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
            if (!delta)
                return
            const next = Math.max(box.from, Math.min(box.to, box.value + (delta > 0 ? box.stepSize : -box.stepSize)))
            if (next !== box.value) {
                box.value = next
                box.valueModified()
            }
            event.accepted = true
        }
    }
    contentItem: TextInput {
        id: spinText
        z: 2
        font: box.font
        color: box.enabled ? Theme.textPrimary : Theme.textSecondary
        selectionColor: Theme.accent
        selectedTextColor: Theme.hsl(0.046, 0.714, 0.055)
        horizontalAlignment: Qt.AlignHCenter
        verticalAlignment: Qt.AlignVCenter
        readOnly: !box.editable
        validator: box.validator
        inputMethodHints: box.inputMethodHints
        leftPadding: 22
        rightPadding: 22
        Binding {
            target: spinText
            property: "text"
            value: box.textFromValue(box.value, box.locale)
            when: !spinText.activeFocus
        }
        onEditingFinished: {
            const next = box.valueFromText(text, box.locale)
            box.value = Math.max(box.from, Math.min(box.to, isNaN(next) ? box.value : next))
            box.valueModified()
        }
    }
    up.indicator: Item {
        x: box.width - width - 2
        y: 2
        height: box.height / 2 - 2
        width: 20
        implicitWidth: 20
        implicitHeight: 14
        HoverHandler { id: upHover }
        Text {
            anchors.centerIn: parent
            text: "\uE70E"
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontSm
            color: box.up.pressed || upHover.hovered ? Theme.accent : Theme.textSecondary
        }
    }
    down.indicator: Item {
        x: box.width - width - 2
        y: box.height / 2
        height: box.height / 2 - 2
        width: 20
        implicitWidth: 20
        implicitHeight: 14
        HoverHandler { id: downHover }
        Text {
            anchors.centerIn: parent
            text: "\uE70D"
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontSm
            color: box.down.pressed || downHover.hovered ? Theme.accent : Theme.textSecondary
        }
    }
    background: Item {
        implicitHeight: Theme.controlHeight
        HudFrame {
            anchors.fill: parent
            anchors.margins: -2
            topLeft: Theme.notchSmall + 1
            bottomRight: Theme.notchSmall + 1
            strokeColor: Theme.accent
            opacity: box.activeFocus ? 0.35 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        HudFrame {
            anchors.fill: parent
            topLeft: Theme.notchSmall
            bottomRight: Theme.notchSmall
            fillColor: box.enabled ? Theme.inputBg : Theme.disabledBg
            strokeColor: !box.enabled ? Theme.disabledOutline : box.activeFocus ? Theme.accent : box.hovered ? Theme.outlineStrong : Theme.outline
            strokeWidth: box.activeFocus ? Theme.focusStroke : 1
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
        }
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            height: 2
            width: box.activeFocus ? parent.width - Theme.notchSmall * 2 - 6 : 0
            color: Theme.accent
            opacity: 0.8
            Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        }
    }
}
