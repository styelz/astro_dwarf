import QtQuick
import QtQuick.Controls
import ".."

ToolTip {
    id: tip
    property int wrapWidth: Theme.px(240)
    delay: Theme.tooltipDelay
    timeout: 8000
    padding: Theme.s2
    contentItem: Text {
        text: tip.text
        color: Theme.textPrimary
        font.pixelSize: Theme.fontSm
        wrapMode: Text.Wrap
        width: Math.min(implicitWidth, tip.wrapWidth)
    }
    background: Rectangle {
        color: Theme.popupBg
        border.color: Theme.outline
        border.width: 1
        radius: Theme.px(3)
    }
}
