import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: hudBtn
    property color buttonColor: Theme.surfaceHigh
    property color foregroundColor: Theme.textPrimary
    property string busyText: ""
    property string tooltip: ""
    property string accessibleName: ""
    property string accessibleDescription: ""
    property bool busy: false
    property int busyMs: 1400
    property bool iconButton: false
    property bool _clickBusy: false
    readonly property bool isBusy: busy || _clickBusy
    // iconButton only — using width here loops with Button.implicitWidth.
    readonly property bool tightChrome: iconButton
    // state model: disabled < idle < hover < down/busy
    readonly property bool inactive: !enabled && !isBusy
    readonly property bool lit: hovered || down || isBusy || visualFocus
    readonly property color fillColor: inactive ? Theme.disabledBg
                                     : down || isBusy ? Qt.darker(buttonColor, 1.25)
                                     : hovered ? Qt.lighter(buttonColor, 1.18) : buttonColor
    readonly property color lineColor: inactive ? Theme.disabledOutline : lit ? Theme.accent : Theme.outline
    hoverEnabled: enabled
    focusPolicy: Qt.StrongFocus
    Accessible.name: accessibleName !== "" ? accessibleName : text
    Accessible.description: isBusy && busyText !== "" ? busyText : (accessibleDescription || tooltip)
    HudToolTip {
        visible: hudBtn.tooltip !== "" && hudBtn.hovered
        text: hudBtn.tooltip
    }
    opacity: inactive ? 0.45 : 1
    font.pixelSize: Theme.fontMd
    font.letterSpacing: tightChrome ? 0 : Theme.tracking1
    font.preferShaping: hudBtn.iconButton
    leftPadding: tightChrome ? 0 : Theme.s3
    rightPadding: tightChrome ? 0 : Theme.s3
    implicitHeight: Theme.controlHeight
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }

    HoverHandler {
        enabled: hudBtn.enabled
        cursorShape: Qt.PointingHandCursor
    }

    Timer {
        id: clickBusyTimer
        interval: Math.max(1, hudBtn.busyMs)
        repeat: false
        onTriggered: hudBtn._clickBusy = false
    }
    onClicked: {
        if (hudBtn.busyText === "" || hudBtn.busy || hudBtn.busyMs <= 0)
            return
        hudBtn._clickBusy = true
        clickBusyTimer.restart()
    }

    background: Item {
        implicitWidth: 0
        implicitHeight: Theme.controlHeight
        // outer glow on hover / busy
        HudFrame {
            anchors.fill: parent
            anchors.margins: Theme.px(-2)
            topLeft: Theme.notchSmall + 2
            bottomRight: Theme.notchSmall + 2
            strokeColor: Theme.accent
            strokeWidth: 1
            opacity: hudBtn.isBusy ? 0.55 : hudBtn.hovered && !hudBtn.inactive ? 0.28 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
            SequentialAnimation on opacity {
                running: hudBtn.isBusy
                loops: Animation.Infinite
                NumberAnimation { to: 0.15; duration: 500; easing.type: Easing.InOutSine }
                NumberAnimation { to: 0.6; duration: 500; easing.type: Easing.InOutSine }
            }
        }
        HudFrame {
            anchors.fill: parent
            topLeft: Theme.notchSmall
            bottomRight: Theme.notchSmall
            fillColor: hudBtn.fillColor
            strokeColor: hudBtn.lineColor
            strokeWidth: hudBtn.lit ? Theme.focusStroke : 1
            Behavior on fillColor { ColorAnimation { duration: Theme.quick } }
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
        }
        // top highlight line, like a lit bezel edge
        Rectangle {
            x: Theme.notchSmall + 2
            y: Theme.px(2)
            width: parent.width - Theme.notchSmall - 6
            height: Theme.px(1)
            color: Theme.accent
            opacity: hudBtn.inactive ? 0 : hudBtn.lit ? 0.45 : 0.18
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        // active indicator bar along the bottom that grows on hover
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: Theme.px(1)
            anchors.horizontalCenter: parent.horizontalCenter
            height: Theme.px(2)
            width: hudBtn.lit && !hudBtn.inactive ? parent.width - Theme.notchSmall * 2 - 8 : 0
            color: Theme.accent
            opacity: 0.85
            Behavior on width { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
        }
    }

    contentItem: Text {
        text: (hudBtn.isBusy && hudBtn.busyText !== "") ? hudBtn.busyText : hudBtn.text
        color: hudBtn.enabled || hudBtn.isBusy ? hudBtn.foregroundColor : Theme.textSecondary
        font: hudBtn.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: hudBtn.tightChrome ? Text.ElideNone : Text.ElideRight
    }
}
