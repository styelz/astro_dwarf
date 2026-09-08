import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Rectangle {
    id: statusChip
    property string status: ""
    readonly property color tone: Util.statusColor(status)
    readonly property bool running: String(status || "").toLowerCase() === "running"
    implicitHeight: 18
    implicitWidth: statusChipText.implicitWidth + 16
    radius: 3
    color: Util.statusFill(status)
    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.7)
    Rectangle {
        anchors.fill: parent; anchors.margins: -2; radius: 5
        color: "transparent"; border.color: statusChip.tone
        opacity: 0.3
        visible: statusChip.running
        SequentialAnimation on opacity {
            running: statusChip.running
            loops: Animation.Infinite
            NumberAnimation { to: 0.05; duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { to: 0.45; duration: 900; easing.type: Easing.InOutSine }
        }
    }
    Text {
        id: statusChipText
        anchors.centerIn: parent
        text: String(statusChip.status || "").toUpperCase()
        color: statusChip.tone
        font.pixelSize: 8
        font.bold: true
        font.letterSpacing: 1.2
    }
}
