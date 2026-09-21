import QtQuick
import QtQuick.Layouts
import ".."

Rectangle {
    id: chip
    property string label: ""
    property string value: ""
    property color tone: Theme.accent
    property bool glow: false
    property bool dim: false
    implicitHeight: Theme.px(20)
    implicitWidth: chipRowLayout.implicitWidth + Theme.px(14)
    radius: Theme.radius
    color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.05 : 0.14)
    border.color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.25 : 0.55)
    opacity: dim ? 0.6 : 1
    Behavior on color { ColorAnimation { duration: 200 } }
    Rectangle {
        anchors.fill: parent; anchors.margins: Theme.px(-2); radius: Theme.px(5)
        color: "transparent"; border.color: chip.tone; opacity: 0.3
        visible: chip.glow && !chip.dim
    }
    RowLayout {
        id: chipRowLayout
        anchors.centerIn: parent
        spacing: Theme.px(5)
        Text { visible: chip.label !== ""; text: chip.label; color: chip.tone; font.pixelSize: Theme.fontXs; font.bold: true; font.letterSpacing: 1 }
        Text { visible: chip.value !== ""; text: chip.value; color: Theme.textPrimary; font.pixelSize: Theme.fontSm; font.family: Theme.fontMono }
    }
}
