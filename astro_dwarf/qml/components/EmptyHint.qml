import QtQuick
import QtQuick.Layouts
import ".."

Column {
    id: hint
    property string text: ""
    property string glyph: "◇"
    property string mode: "empty"
    property alias font: hintText.font
    property alias color: hintText.color
    readonly property bool loading: mode === "loading"
    readonly property bool unavailable: mode === "unavailable"
    readonly property color tone: unavailable ? Theme.warning : Theme.accent
    spacing: 12
    width: Math.min(360, parent ? parent.width - 24 : 320)
    // when placed inside a Layout the width binding is overridden, so size via Layout hints too
    Layout.preferredWidth: 360
    Layout.minimumWidth: 160
    Layout.fillWidth: false
    Accessible.name: hint.text
    Accessible.description: hint.loading ? "Loading" : hint.unavailable ? "Unavailable" : "Empty"
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        visible: hint.loading || hint.glyph !== ""
        width: glyphText.implicitHeight + 18
        height: width
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.color: hint.tone
            opacity: hint.loading ? 0.6 : 0.35
        }
        Text {
            id: glyphText
            anchors.centerIn: parent
            text: hint.loading ? "↻" : hint.glyph
            color: hint.tone
            opacity: hint.loading ? 0.9 : 0.55
            font.pixelSize: 22
            RotationAnimator on rotation {
                running: hint.loading
                from: 0
                to: 360
                duration: Theme.slow * 3
                loops: Animation.Infinite
            }
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
