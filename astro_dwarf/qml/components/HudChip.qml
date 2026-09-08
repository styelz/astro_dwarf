import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Rectangle {
    id: chip
    property string label: ""
    property string value: ""
    property color tone: Theme.accent
    property bool glow: false
    property bool dim: false
    implicitHeight: 20
    implicitWidth: chipRowLayout.implicitWidth + 14
    radius: 3
    color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.05 : 0.14)
    border.color: Qt.rgba(tone.r, tone.g, tone.b, dim ? 0.25 : 0.55)
    opacity: dim ? 0.6 : 1
    Behavior on color { ColorAnimation { duration: 200 } }
    Rectangle {
        anchors.fill: parent; anchors.margins: -2; radius: 5
        color: "transparent"; border.color: chip.tone; opacity: 0.3
        visible: chip.glow && !chip.dim
    }
    RowLayout {
        id: chipRowLayout
        anchors.centerIn: parent
        spacing: 5
        Text { visible: chip.label !== ""; text: chip.label; color: chip.tone; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1 }
        Text { visible: chip.value !== ""; text: chip.value; color: Theme.textPrimary; font.pixelSize: 10; font.family: "Cascadia Mono" }
    }
}
