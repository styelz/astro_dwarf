import QtQuick
import QtQuick.Controls
import ".."

// Themed horizontal slider. The track fills with accent up to the handle unless a
// `trackGradient` is supplied (hue and brightness pickers paint their own scale).
// `markerPosition` draws a stock/default tick along the track; `valueText` shows the
// current value in a fixed mono column so the track does not jitter as it changes.
Slider {
    id: control
    property string accessibleName: ""
    property string tooltip: ""
    property var trackGradient: null
    property real markerPosition: -1
    property string valueText: ""
    property int trackHeight: Theme.px(10)
    readonly property bool fillTrack: !trackGradient

    implicitHeight: Theme.px(28)
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    rightPadding: valueText.length ? Theme.px(46) : 0
    opacity: enabled ? 1 : 0.55
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }
    Accessible.name: accessibleName
    Accessible.description: tooltip || valueText
    HudToolTip {
        visible: control.tooltip !== "" && control.hovered && !control.pressed
        text: control.tooltip
    }

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: control.trackHeight
        radius: height / 2
        color: Theme.inputBg
        border.color: control.visualFocus ? Theme.accent : Theme.outline
        border.width: 1
        gradient: control.trackGradient
        Rectangle {
            visible: control.fillTrack
            width: Math.max(0, control.visualPosition * parent.width)
            height: parent.height
            radius: parent.radius
            color: Theme.accent
            opacity: control.enabled ? 0.45 : 0.25
        }
        Rectangle {
            visible: control.markerPosition >= 0 && control.markerPosition <= 1
            x: Math.round(control.markerPosition * parent.width) - 1
            y: Theme.px(-3)
            width: Theme.px(2)
            height: parent.height + Theme.px(6)
            color: Theme.textPrimary
            opacity: 0.5
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: Theme.px(20)
        height: Theme.px(20)
        radius: Theme.px(10)
        color: control.enabled ? Theme.accent : Theme.textSecondary
        border.color: control.pressed || control.hovered || control.visualFocus ? Theme.textPrimary : Theme.surface
        border.width: 2
        Behavior on border.color { ColorAnimation { duration: Theme.quick } }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -Theme.s1
            radius: width / 2
            color: "transparent"
            border.color: Theme.accent
            opacity: control.pressed || control.visualFocus ? 0.6 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
        }
    }

    Text {
        visible: control.valueText.length
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.px(40)
        horizontalAlignment: Text.AlignRight
        text: control.valueText
        color: control.enabled ? Theme.textPrimary : Theme.textSecondary
        font.family: Theme.fontMono
        font.pixelSize: Theme.fontPx(11)
    }
}
