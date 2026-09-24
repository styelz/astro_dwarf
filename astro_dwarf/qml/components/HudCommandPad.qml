import QtQuick
import QtQuick.Controls
import ".."

Control {
    id: commandPad
    property string text: ""
    property string glyph: ""
    property string detail: ""
    property string tooltip: ""
    property string stopTooltip: "Stop"
    property bool activeState: false
    property bool pending: false
    property bool primed: false
    property bool canStop: false
    property bool destructive: false
    property bool stopsOnClick: false
    readonly property bool padHovered: padMouse.containsMouse
    readonly property bool hoverStops: stopsOnClick && padHovered && !stopHot && flash === ""
    property string flash: ""   // "", "success" or "error"
    readonly property color flashColor: flash === "error" ? Theme.danger : Theme.success
    readonly property bool showStop: canStop && !pending
    readonly property bool shownActive: activeState && enabled
    property bool stopPressed: false
    property bool stopHandled: false
    property bool stopHot: false
    property bool stopDown: false
    readonly property bool stopHovered: stopHot
    readonly property bool padDown: padMouse.pressed && !stopDown
    readonly property real stopLead: showStop ? stopButton.x - labels.x - titleText.width : 0
    signal clicked()
    signal stopClicked()
    hoverEnabled: enabled
    focusPolicy: Qt.StrongFocus
    opacity: enabled || pending || activeState ? 1 : 0.45
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }
    implicitWidth: Theme.px(120)
    implicitHeight: Theme.px(58)
    leftPadding: Theme.s2
    rightPadding: Theme.s2
    topPadding: Theme.s1
    bottomPadding: Theme.s1
    Accessible.name: text
    Accessible.role: Accessible.Button
    Accessible.description: pending ? "Sending" : (tooltip || detail)
    Accessible.onPressAction: commandPad.clicked()

    function showFlash(kind) {
        flash = kind
        flashTimer.restart()
    }
    function _overStop(pos) {
        if (!showStop || !stopButton.visible || !pos)
            return false
        const local = stopButton.mapFromItem(commandPad, pos.x, pos.y)
        return local.x >= 0 && local.y >= 0 && local.x < stopButton.width && local.y < stopButton.height
    }
    function _activateStop() {
        if (!enabled || !showStop || stopHandled)
            return
        stopHandled = true
        stopPressed = true
        stopClicked()
        stopReleaseTimer.restart()
    }

    Timer { id: flashTimer; interval: 900; onTriggered: commandPad.flash = "" }
    Timer {
        id: stopReleaseTimer
        interval: 80
        onTriggered: {
            commandPad.stopPressed = false
            commandPad.stopHandled = false
        }
    }
    Keys.onReleased: (event) => {
        if (event.isAutoRepeat || stopButton.activeFocus)
            return
        if (event.key !== Qt.Key_Space && event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter)
            return
        if (!commandPad.enabled)
            return
        commandPad.clicked()
        event.accepted = true
    }
    MouseArea {
        id: padMouse
        anchors.fill: parent
        z: 10
        enabled: commandPad.enabled
        hoverEnabled: true
        preventStealing: true
        acceptedButtons: Qt.LeftButton
        cursorShape: commandPad.stopHot ? Qt.PointingHandCursor : Qt.ArrowCursor
        function atStop(mouse) {
            return commandPad._overStop(Qt.point(mouse.x, mouse.y))
        }
        onPositionChanged: function(mouse) { commandPad.stopHot = atStop(mouse) }
        onEntered: commandPad.stopHot = commandPad._overStop(Qt.point(padMouse.mouseX, padMouse.mouseY))
        onExited: commandPad.stopHot = false
        onPressed: function(mouse) {
            commandPad.stopDown = atStop(mouse)
            if (commandPad.stopDown)
                commandPad.stopPressed = true
            mouse.accepted = true
        }
        onReleased: commandPad.stopDown = false
        onCanceled: {
            commandPad.stopDown = false
            commandPad.stopHot = false
            stopReleaseTimer.restart()
        }
        onClicked: function(mouse) {
            if (atStop(mouse)) {
                commandPad._activateStop()
                return
            }
            commandPad.stopPressed = false
            commandPad.stopHandled = false
            commandPad.clicked()
        }
    }
    HudToolTip {
        visible: commandPad.tooltip !== "" && commandPad.padHovered && !commandPad.stopHovered
        text: commandPad.tooltip
    }
    background: Rectangle {
        id: padBackground
        color: commandPad.flash !== "" ? Qt.rgba(commandPad.flashColor.r, commandPad.flashColor.g, commandPad.flashColor.b, 0.22)
             : commandPad.hoverStops || commandPad.destructive ? Theme.fillDanger : commandPad.shownActive ? Theme.fillSuccess : commandPad.pending ? Theme.fillActive : commandPad.padDown ? Theme.fillChecked : commandPad.padHovered ? Theme.surfaceHigh : Theme.surface
        border.color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.hoverStops || commandPad.destructive ? Theme.danger : commandPad.shownActive ? Theme.success : commandPad.pending || commandPad.padHovered || commandPad.visualFocus ? Theme.accent : commandPad.primed ? Theme.success : Theme.outline
        border.width: commandPad.shownActive || commandPad.padHovered || commandPad.visualFocus || commandPad.pending || commandPad.flash !== "" ? Theme.px(2) : Theme.px(1)
        radius: Theme.radius
        Behavior on color { ColorAnimation { duration: Theme.normal } }
        Behavior on border.color { ColorAnimation { duration: Theme.normal } }
        Rectangle { x: Theme.s1; y: Theme.s1; width: parent.width - Theme.s2; height: Theme.px(1); color: commandPad.hoverStops || commandPad.destructive ? Theme.danger : commandPad.primed && !commandPad.activeState ? Theme.success : Theme.accent; opacity: 0.35 }
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
            anchors.fill: parent
            anchors.margins: Theme.px(-3)
            radius: Theme.px(6)
            color: "transparent"
            border.color: commandPad.hoverStops ? Theme.danger : commandPad.shownActive ? Theme.success : Theme.accent
            border.width: 1
            visible: commandPad.shownActive || commandPad.pending
            opacity: 0
            SequentialAnimation on opacity {
                running: commandPad.shownActive || commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 0.7; to: 0; duration: commandPad.pending ? 600 : 1100; easing.type: Easing.OutQuad }
                PauseAnimation { duration: commandPad.pending ? 150 : 400 }
            }
        }
        Rectangle {
            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(7)
            width: Theme.px(7); height: Theme.px(7); radius: Theme.s1
            visible: !commandPad.showStop
            color: commandPad.hoverStops ? Theme.danger : commandPad.shownActive || (commandPad.primed && !commandPad.pending) ? Theme.success : commandPad.pending ? Theme.accent : commandPad.enabled ? Theme.muted : Theme.disabledOutline
            border.color: commandPad.shownActive || commandPad.primed ? Theme.accentSoft : Theme.outline
            SequentialAnimation on opacity {
                running: commandPad.pending
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.2; duration: 320 }
                NumberAnimation { from: 0.2; to: 1; duration: 320 }
            }
        }
    }
    contentItem: Item {
        id: face
        implicitWidth: Theme.px(96)
        implicitHeight: Theme.px(36)
        readonly property int glyphSize: Math.round(Math.min(26, Math.max(16, commandPad.height * 0.32)))

        Text {
            id: glyphText
            anchors.verticalCenter: parent.verticalCenter
            width: face.glyphSize + 6
            horizontalAlignment: Text.AlignHCenter
            text: commandPad.glyph
            color: commandPad.hoverStops || commandPad.destructive ? Theme.danger : commandPad.shownActive || commandPad.primed ? Theme.success : commandPad.enabled ? Theme.accent : Theme.textSecondary
            font.pixelSize: face.glyphSize
        }
        Column {
            id: labels
            anchors.left: glyphText.right
            anchors.leftMargin: Theme.s1
            anchors.right: commandPad.showStop ? stopButton.left : parent.right
            anchors.rightMargin: commandPad.showStop ? Theme.s1 : 0
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0

            Item {
                id: titleRow
                width: labels.width
                height: titleText.implicitHeight

                Text {
                    id: titleText
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, titleRow.width)
                    text: commandPad.text
                    color: commandPad.enabled ? Theme.textPrimary : Theme.textSecondary
                    font.pixelSize: Theme.fontSm
                    font.bold: true
                    font.letterSpacing: 0.7
                    elide: Text.ElideRight
                }
            }
            Text {
                id: detailText
                width: labels.width
                text: commandPad.flash === "success" ? "DONE" : commandPad.flash === "error" ? "FAILED" : commandPad.pending ? "SENDING…" : commandPad.detail
                color: commandPad.flash !== "" ? commandPad.flashColor : commandPad.hoverStops ? Theme.danger : commandPad.shownActive || (commandPad.primed && !commandPad.pending) ? Theme.success : commandPad.pending ? Theme.accent : Theme.textSecondary
                font.pixelSize: Theme.fontXs
                font.family: commandPad.shownActive || commandPad.primed ? Theme.fontMono : Theme.fontUi
                elide: Text.ElideRight
            }
        }
        Item {
            id: stopButton
            objectName: commandPad.objectName ? commandPad.objectName + "-stop" : "pad-stop"
            visible: commandPad.showStop
            enabled: commandPad.showStop && commandPad.enabled
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: Theme.s1 + Theme.px(10)
            width: Theme.px(22)
            height: Theme.px(22)
            z: 2
            activeFocusOnTab: visible && enabled
            Accessible.role: Accessible.Button
            Accessible.name: "Stop " + commandPad.text
            Accessible.description: commandPad.stopTooltip
            Accessible.onPressAction: commandPad._activateStop()
            Keys.onReleased: (event) => {
                if (event.isAutoRepeat)
                    return
                if (event.key !== Qt.Key_Space && event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter)
                    return
                commandPad._activateStop()
                event.accepted = true
            }
            HudToolTip {
                visible: commandPad.stopHovered && commandPad.stopTooltip !== ""
                text: commandPad.stopTooltip
            }
            Rectangle {
                anchors.fill: parent
                color: commandPad.stopDown ? Theme.fillDanger : commandPad.stopHovered || stopButton.activeFocus ? Theme.surfaceHigh : Theme.panelFill
                border.color: commandPad.stopHovered || stopButton.activeFocus || commandPad.stopDown ? Theme.danger : Theme.outline
                border.width: stopButton.activeFocus ? Theme.focusStroke : 1
                radius: Theme.radius
            }
            Rectangle {
                width: Theme.s2
                height: Theme.s2
                radius: Theme.px(1)
                color: Theme.danger
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
