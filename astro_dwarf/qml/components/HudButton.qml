import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: hudBtn
    property color buttonColor: Theme.surfaceHigh
    property color foregroundColor: Theme.textPrimary
    property string busyText: ""
    property bool busy: false
    property int busyMs: 1400
    property bool _clickBusy: false
    readonly property bool isBusy: busy || _clickBusy
    // state model: disabled < idle < hover < down/busy
    readonly property bool inactive: !enabled && !isBusy
    readonly property bool lit: hovered || down || isBusy || visualFocus
    readonly property color fillColor: inactive ? Theme.disabledBg
                                     : down || isBusy ? Qt.darker(buttonColor, 1.25)
                                     : hovered ? Qt.lighter(buttonColor, 1.18) : buttonColor
    readonly property color lineColor: inactive ? Theme.disabledOutline : lit ? Theme.accent : Theme.outline
    hoverEnabled: enabled
    opacity: inactive ? 0.45 : 1
    font.pixelSize: Theme.fontMd
    font.letterSpacing: Theme.tracking1
    leftPadding: Theme.s3
    rightPadding: Theme.s3
    implicitHeight: 34
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }

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
        implicitHeight: 34
        // outer glow on hover / busy
        HudFrame {
            anchors.fill: parent
            anchors.margins: -2
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
            strokeWidth: hudBtn.lit ? 1.5 : 1
            Behavior on fillColor { ColorAnimation { duration: Theme.quick } }
            Behavior on strokeColor { ColorAnimation { duration: Theme.quick } }
        }
        // top highlight line, like a lit bezel edge
        Rectangle {
            x: Theme.notchSmall + 2
            y: 2
            width: parent.width - Theme.notchSmall - 6
            height: 1
            color: Theme.accent
            opacity: hudBtn.inactive ? 0 : hudBtn.lit ? 0.45 : 0.18
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
        // active indicator bar along the bottom that grows on hover
        Rectangle {
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            height: 2
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
        elide: Text.ElideRight
    }
}
