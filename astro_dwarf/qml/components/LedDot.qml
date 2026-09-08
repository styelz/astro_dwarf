import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Rectangle {
    id: led
    property bool on: false
    property color onColor: Theme.success
    property bool pulse: false
    width: 7; height: 7; radius: 4
    color: on ? onColor : Theme.hsl(0.057, 0.296, 0.212)
    border.color: on ? Theme.hsl(-0.021, 1.000, 0.924) : Theme.outline
    Behavior on color { ColorAnimation { duration: 200 } }
    Rectangle {
        id: ledRing
        anchors.centerIn: parent
        width: led.width; height: led.height; radius: width / 2
        color: "transparent"
        border.color: led.onColor
        visible: led.on && led.pulse
        SequentialAnimation on scale {
            running: ledRing.visible
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 2.2; duration: 1200; easing.type: Easing.OutQuad }
            PauseAnimation { duration: 600 }
        }
        SequentialAnimation on opacity {
            running: ledRing.visible
            loops: Animation.Infinite
            NumberAnimation { from: 0.8; to: 0; duration: 1200 }
            PauseAnimation { duration: 600 }
        }
    }
}
