import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Column {
    id: hint
    property string text: ""
    property string glyph: "◇"
    property alias font: hintText.font
    property alias color: hintText.color
    spacing: 12
    width: Math.min(360, parent ? parent.width - 24 : 320)
    // when placed inside a Layout the width binding is overridden, so size via Layout hints too
    Layout.preferredWidth: 360
    Layout.minimumWidth: 160
    Layout.fillWidth: false
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        visible: hint.glyph !== ""
        width: glyphText.implicitHeight + 18
        height: width
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.color: Theme.accent
            opacity: 0.35
        }
        Text {
            id: glyphText
            anchors.centerIn: parent
            text: hint.glyph
            color: Theme.accent
            opacity: 0.55
            font.pixelSize: 22
        }
    }
    Text {
        id: hintText
        width: hint.width
        text: hint.text
        color: Theme.textSecondary
        font.pixelSize: 12
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
    }
}
