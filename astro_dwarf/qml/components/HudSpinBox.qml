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
    implicitWidth: Theme.px(140)
    Layout.minimumWidth: 0
    Layout.preferredWidth: implicitWidth
    font.pixelSize: Theme.fontBase
    font.preferShaping: true
    hoverEnabled: true
    wheelEnabled: true
    focusPolicy: Qt.StrongFocus
    validator: RegularExpressionValidator { regularExpression: /^-?\d{0,6}.*$/ }
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
    function nudge(direction) {
        const step = box.stepSize === 0 ? 1 : box.stepSize
        let next = box.value + (direction > 0 ? step : -step)
        if (box.wrap) {
            const span = box.to - box.from + step
            if (span <= 0)
                return
            next = box.from + ((((next - box.from) % span) + span) % span)
        } else {
            next = Math.max(box.from, Math.min(box.to, next))
        }
        if (next === box.value)
            return
        box.value = next
        if (spinText.activeFocus)
            spinText.text = String(box.value)
        box.valueModified()
    }
    onValueChanged: {
        if (spinText.activeFocus)
            spinText.text = String(box.value)
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
            box.nudge(delta > 0 ? 1 : -1)
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
        leftPadding: Theme.px(22)
        rightPadding: Theme.px(22)
        text: box.textFromValue(box.value, box.locale)
        Binding {
            target: spinText
            property: "text"
            value: box.textFromValue(box.value, box.locale)
            when: !spinText.activeFocus
            restoreMode: Binding.RestoreNone
        }
        onActiveFocusChanged: {
            if (!spinText.activeFocus)
                return
            spinText.text = String(box.value)
            spinText.selectAll()
        }
        Keys.onPressed: event => {
            if (event.key === Qt.Key_Up) {
                box.nudge(1)
                event.accepted = true
            } else if (event.key === Qt.Key_Down) {
                box.nudge(-1)
                event.accepted = true
            }
        }
        onEditingFinished: {
            const parsed = box.valueFromText(text, box.locale)
            let next = isNaN(parsed) ? box.value : parsed
            if (box.wrap) {
                const span = box.to - box.from + (box.stepSize === 0 ? 1 : box.stepSize)
                next = box.from + ((((next - box.from) % span) + span) % span)
            } else {
                next = Math.max(box.from, Math.min(box.to, next))
            }
            box.value = next
            spinText.text = box.textFromValue(box.value, box.locale)
            box.valueModified()
        }
    }
    up.indicator: Item {
        x: box.width - width - Theme.px(2)
        y: Theme.px(2)
        height: box.height / 2 - 2
        width: Theme.s5
        implicitWidth: Theme.s5
        implicitHeight: Theme.px(14)
        HoverHandler { id: upHover }
        Text {
            anchors.centerIn: parent
            text: "\uE70E"
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontSm
            font.preferShaping: true
            color: box.up.pressed || upHover.hovered ? Theme.accent : Theme.textSecondary
        }
    }
    down.indicator: Item {
        x: box.width - width - Theme.px(2)
        y: box.height / 2
        height: box.height / 2 - 2
        width: Theme.s5
        implicitWidth: Theme.s5
        implicitHeight: Theme.px(14)
        HoverHandler { id: downHover }
        Text {
            anchors.centerIn: parent
            text: "\uE70D"
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontSm
            font.preferShaping: true
            color: box.down.pressed || downHover.hovered ? Theme.accent : Theme.textSecondary
        }
    }
    background: Item {
        implicitHeight: Theme.controlHeight
        HudFrame {
            anchors.fill: parent
            anchors.margins: Theme.px(-2)
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
            anchors.bottomMargin: Theme.px(1)
            anchors.horizontalCenter: parent.horizontalCenter
            height: Theme.px(2)
            width: box.activeFocus ? parent.width - Theme.notchSmall * 2 - 6 : 0
            color: Theme.accent
            opacity: 0.8
            Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        }
    }
}
