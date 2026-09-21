import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

TextField {
    id: field
    property bool releaseFocusOnEnter: true
    property string tooltip: ""
    property string accessibleName: ""
    property string accessibleDescription: ""
    property bool passwordRevealed: false
    readonly property bool passwordField: echoMode === TextInput.Password
        || echoMode === TextInput.PasswordEchoOnEdit
        || passwordRevealed
    color: field.enabled ? Theme.textPrimary : Theme.textSecondary
    placeholderTextColor: Theme.textSecondary
    selectedTextColor: Theme.hsl(0.046, 0.714, 0.055)
    selectionColor: Theme.accent
    opacity: field.enabled ? 1 : 0.45
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    font.pixelSize: Theme.fontBase
    Accessible.name: accessibleName || placeholderText || text
    Accessible.description: accessibleDescription || tooltip
    HudToolTip {
        visible: field.tooltip !== "" && field.hovered
        text: field.tooltip
    }
    Keys.priority: Keys.BeforeItem
    Keys.onPressed: function (event) {
        if (!field.releaseFocusOnEnter)
            return
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            event.accepted = true
            field.focus = false
        }
    }
    leftPadding: 10
    rightPadding: passwordField ? 32 : 10
    clip: true
    Binding {
        target: field
        property: "echoMode"
        value: TextInput.Normal
        when: field.passwordRevealed
        restoreMode: Binding.RestoreBindingOrValue
    }
    Item {
        id: revealBtn
        visible: field.passwordField
        width: 28
        height: parent.height
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        z: 2
        enabled: field.enabled
        activeFocusOnTab: visible && enabled
        Accessible.role: Accessible.Button
        Accessible.name: field.passwordRevealed ? "Hide password" : "Show password"
        Accessible.onPressAction: field.passwordRevealed = !field.passwordRevealed
        Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                event.accepted = true
                field.passwordRevealed = !field.passwordRevealed
            }
        }
        MouseArea {
            id: revealClick
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            enabled: field.enabled && revealBtn.visible
            onClicked: {
                field.passwordRevealed = !field.passwordRevealed
                field.forceActiveFocus()
            }
        }
        Text {
            anchors.centerIn: parent
            text: field.passwordRevealed ? "\uE7ED" : "\uE7B3"
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontPx(14)
            color: !field.enabled ? Theme.textSecondary
                 : revealBtn.activeFocus || revealClick.containsMouse ? Theme.accent
                 : Theme.textSecondary
            Behavior on color { ColorAnimation { duration: Theme.quick } }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 4
            radius: 2
            color: "transparent"
            border.color: Theme.accent
            border.width: Theme.focusStroke
            visible: revealBtn.activeFocus
        }
        ToolTip.visible: revealClick.containsMouse
        ToolTip.delay: Theme.tooltipDelay
        ToolTip.text: field.passwordRevealed ? "Hide password" : "Show password"
    }
    implicitWidth: 160
    implicitHeight: Theme.controlHeight
    Layout.minimumWidth: 0
    Layout.preferredWidth: implicitWidth
    background: Item {
        implicitHeight: Theme.controlHeight
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
            strokeWidth: field.activeFocus ? Theme.focusStroke : 1
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
