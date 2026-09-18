import QtQuick
import ".."

Item {
    id: meter
    property real progress: -1
    property string text: "LOADING"
    property bool running: true
    property bool compact: false
    readonly property bool determinate: running && progress >= 0.02 && progress < 0.995
    readonly property string labelText: determinate
        ? text + "  " + Math.round(progress * 100) + "%"
        : text
    implicitWidth: compact ? 96 : 176
    implicitHeight: label.implicitHeight + Theme.s1 + (compact ? 3 : 4)
    Accessible.role: Accessible.Indicator
    Accessible.name: labelText
    Accessible.description: running ? "Loading" : ""

    Text {
        id: label
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        text: meter.labelText
        color: Theme.accent
        font.pixelSize: meter.compact ? Theme.fontXs : Theme.fontSm
        font.bold: true
        font.letterSpacing: Theme.tracking2
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }

    Rectangle {
        id: track
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: meter.compact ? 3 : 4
        color: Theme.inputBg
        border.color: Theme.outlineSoft
        radius: Theme.radius
        Rectangle {
            id: fill
            y: 1
            height: parent.height - 2
            radius: 1
            color: Theme.accent
            opacity: meter.running ? 0.92 : 0.35
            visible: meter.running
            width: meter.determinate
                ? Math.max(0, (track.width - 2) * Math.min(1, meter.progress))
                : Math.max(Theme.s4, (track.width - 2) * 0.32)
            x: meter.determinate ? 1 : 1 + Math.max(0, track.width - 2 - width) * scan
            property real scan: 0
            SequentialAnimation on scan {
                running: meter.visible && meter.running && !meter.determinate
                loops: Animation.Infinite
                NumberAnimation {
                    from: 0
                    to: 1
                    duration: Theme.slow * 5
                    easing.type: Easing.InOutSine
                }
                NumberAnimation {
                    from: 1
                    to: 0
                    duration: Theme.slow * 5
                    easing.type: Easing.InOutSine
                }
            }
        }
    }
}
