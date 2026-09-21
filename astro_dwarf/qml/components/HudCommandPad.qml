import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Button {
    id: commandPad
    property string glyph: ""
    property string detail: ""
    property string tooltip: ""
    property string stopTooltip: "Cancel primed command"
    property bool activeState: false
    property bool pending: false
    property bool primed: false
    property bool destructive: false
    property string flash: ""   // "", "success" or "error"
    readonly property color flashColor: flash === "error" ? Theme.danger : Theme.success
    readonly property bool showStop: primed && !activeState && !pending
    property bool stopPressed: false
    signal stopClicked()
    hoverEnabled: enabled
    focusPolicy: Qt.StrongFocus
    implicitHeight: Theme.px(58)
    leftPadding: Theme.s2
    rightPadding: Theme.s2
    Accessible.name: text
    Accessible.description: pending ? "Sending" : (tooltip || detail)
    function showFlash(kind) {
        flash = kind
        flashTimer.restart()
    }
    Timer { id: flashTimer; interval: 900; onTriggered: commandPad.flash = "" }
    HudToolTip {
        visible: commandPad.tooltip !== "" && commandPad.hovered && !stopButton.hovered
        text: commandPad.tooltip
    }
    background: Rectangle {
        id: padBackground
        color: commandPad.flash !== "" ? Qt.rgba(commandPad.flashColor.r, commandPad.flashColor.g, commandPad.flashColor.b, 0.22)
             : commandPad.destructive ? Theme.fillDanger : commandPad.activeState ? Theme.fillSuccess : commandPad.pending ? Theme.fillActive : commandPad.down ? Theme.fillChecked : commandPad.hovered ? Theme.surfaceHigh : Theme.surface
        border.color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.destructive ? Theme.danger : commandPad.activeState ? Theme.success : commandPad.pending || commandPad.hovered ? Theme.accent : commandPad.primed ? Theme.success : Theme.outline
        border.width: commandPad.activeState || commandPad.hovered || commandPad.pending || commandPad.flash !== "" ? Theme.px(2) : Theme.px(1)
        radius: Theme.radius
        Behavior on color { ColorAnimation { duration: Theme.normal } }
        Behavior on border.color { ColorAnimation { duration: Theme.normal } }
        Rectangle { x: Theme.s1; y: Theme.s1; width: parent.width - Theme.s2; height: Theme.px(1); color: commandPad.destructive ? Theme.danger : commandPad.primed && !commandPad.activeState ? Theme.success : Theme.accent; opacity: 0.35 }
        Rectangle {
            visible: commandPad.primed && !commandPad.activeState && !commandPad.pending
            width: Theme.px(2)
            height: parent.height - Theme.s2
            anchors.left: parent.left
            anchors.leftMargin: Theme.px(2)
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.success
            opacity: 0.9
        }
        Rectangle {
            // pulsing ring while the device reports the command running
            anchors.fill: parent
            anchors.margins: Theme.px(-3)
            radius: Theme.px(6)
            color: "transparent"
            border.color: commandPad.activeState ? Theme.success : Theme.accent
            border.width: 1
            visible: commandPad.activeState || commandPad.pending
            opacity: 0
            SequentialAnimation on opacity {
                running: commandPad.activeState || commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 0.7; to: 0; duration: commandPad.pending ? 600 : 1100; easing.type: Easing.OutQuad }
                PauseAnimation { duration: commandPad.pending ? 150 : 400 }
            }
        }
        Rectangle {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(7)
            width: Theme.px(7); height: Theme.px(7); radius: Theme.s1
            visible: !commandPad.showStop
            color: commandPad.activeState || (commandPad.primed && !commandPad.pending) ? Theme.success : commandPad.pending ? Theme.accent : commandPad.enabled ? Theme.muted : Theme.disabledOutline
            border.color: commandPad.activeState || commandPad.primed ? Theme.accentSoft : Theme.outline
            SequentialAnimation on opacity {
                running: commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.2; duration: 320 }
                NumberAnimation { from: 0.2; to: 1; duration: 320 }
            }
        }
    }
    contentItem: RowLayout {
        spacing: Theme.px(7)
        Text { text: commandPad.glyph; color: commandPad.destructive ? Theme.danger : commandPad.activeState || commandPad.primed ? Theme.success : Theme.accent; font.pixelSize: Math.round(Math.min(26, Math.max(16, commandPad.height * 0.32))); Layout.preferredWidth: font.pixelSize + 6; horizontalAlignment: Text.AlignHCenter }
        ColumnLayout {
            Layout.fillWidth: true; spacing: 0
            Text { text: commandPad.text; color: commandPad.enabled || commandPad.activeState ? Theme.textPrimary : Theme.textSecondary; font.pixelSize: Theme.fontSm; font.bold: true; font.letterSpacing: 0.7; elide: Text.ElideRight; Layout.fillWidth: true }
            Text { text: commandPad.flash === "success" ? "DONE" : commandPad.flash === "error" ? "FAILED" : commandPad.pending ? "SENDING…" : commandPad.detail; color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.activeState || (commandPad.primed && !commandPad.pending) ? Theme.success : commandPad.pending ? Theme.accent : Theme.textSecondary; font.pixelSize: Theme.fontXs; font.family: commandPad.activeState || commandPad.primed ? Theme.fontMono : Theme.fontUi; elide: Text.ElideRight; Layout.fillWidth: true }
        }
        Button {
            id: stopButton
            objectName: commandPad.objectName ? commandPad.objectName + "-stop" : "pad-stop"
            visible: commandPad.showStop
            Layout.preferredWidth: Theme.px(22)
            Layout.preferredHeight: Theme.px(22)
            Layout.minimumWidth: Theme.px(22)
            Layout.maximumWidth: Theme.px(22)
            Layout.alignment: Qt.AlignVCenter
            implicitWidth: Theme.px(22)
            implicitHeight: Theme.px(22)
            padding: 0
            hoverEnabled: true
            focusPolicy: Qt.TabFocus
            Accessible.name: "Stop " + commandPad.text
            Accessible.description: commandPad.stopTooltip
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            HudToolTip {
                visible: stopButton.hovered && commandPad.stopTooltip !== ""
                text: commandPad.stopTooltip
            }
            background: Rectangle {
                color: stopButton.down ? Theme.fillDanger : stopButton.hovered || stopButton.visualFocus ? Theme.surfaceHigh : Theme.panelFill
                border.color: stopButton.hovered || stopButton.visualFocus || stopButton.down ? Theme.danger : Theme.outline
                border.width: 1
                radius: Theme.radius
            }
            contentItem: Item {
                Rectangle {
                    width: Theme.s2
                    height: Theme.s2
                    radius: Theme.px(1)
                    color: Theme.danger
                    anchors.centerIn: parent
                }
            }
            onPressed: commandPad.stopPressed = true
            onCanceled: commandPad.stopPressed = false
            onReleased: Qt.callLater(function () { commandPad.stopPressed = false })
            onClicked: commandPad.stopClicked()
        }
    }
}
