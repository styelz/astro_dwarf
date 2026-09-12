import QtQuick
import ".."

Rectangle {
    id: statusChip
    property string status: ""
    readonly property string normalizedStatus: String(status || "").toLowerCase()
    readonly property bool running: normalizedStatus === "running"
    readonly property bool pending: ["pending", "stopping", "connecting", "disconnecting", "cancelling"].indexOf(normalizedStatus) >= 0
    readonly property color tone: pending ? Theme.warning : Util.statusColor(status)
    implicitHeight: 18
    implicitWidth: statusChipText.implicitWidth + 16
    radius: 3
    color: pending ? Qt.rgba(tone.r, tone.g, tone.b, 0.12) : Util.statusFill(status)
    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.7)
    Accessible.name: normalizedStatus || "Unknown status"
    Rectangle {
        anchors.fill: parent; anchors.margins: -2; radius: 5
        color: "transparent"; border.color: statusChip.tone
        opacity: 0.3
        visible: statusChip.running || statusChip.pending
        SequentialAnimation on opacity {
            running: statusChip.running || statusChip.pending
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
