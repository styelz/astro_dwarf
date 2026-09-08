import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
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
    hoverEnabled: enabled
    opacity: enabled || isBusy ? 1 : 0.42
    font.pixelSize: 12
    font.letterSpacing: 0.6
    leftPadding: 12
    rightPadding: 12
    implicitHeight: 34
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
    background: Rectangle {
        color: !hudBtn.enabled && !hudBtn.isBusy ? Theme.disabledBg : hudBtn.down || hudBtn.isBusy ? Qt.darker(hudBtn.buttonColor, 1.2) : hudBtn.hovered ? Qt.lighter(hudBtn.buttonColor, 1.18) : hudBtn.buttonColor
        border.color: !hudBtn.enabled && !hudBtn.isBusy ? Theme.disabledOutline : hudBtn.hovered || hudBtn.down || hudBtn.isBusy ? Theme.accent : Theme.outline
        border.width: hudBtn.hovered || hudBtn.down || hudBtn.isBusy ? 2 : 1
        radius: 3
        Rectangle { x: 3; y: 3; width: parent.width - 6; height: 1; color: hudBtn.enabled ? Theme.hsl(0.032, 0.358, 0.427) : "transparent"; opacity: 0.55 }
        Rectangle { x: 3; y: parent.height - 4; width: parent.width - 6; height: 1; color: Theme.hsl(0.083, 0.667, 0.024); opacity: 0.9 }
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
