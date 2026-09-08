import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Rectangle {
    id: tile
    property string label: ""
    property string value: "—"
    property string unit: ""
    property string glyph: ""
    property color tone: Theme.accent
    property bool stale: false
    property bool live: false
    property bool dimmed: value === "—" || value === ""
    implicitHeight: 46
    radius: 3
    color: Theme.hsl(0.072, 0.581, 0.084, 0.400)
    border.color: live ? Qt.rgba(tone.r, tone.g, tone.b, 0.6) : Theme.outlineSoft
    border.width: 1
    Behavior on border.color { ColorAnimation { duration: 200 } }
    Rectangle { x: 0; y: 5; width: 2; height: parent.height - 10; color: tile.dimmed ? Theme.outline : tile.tone; opacity: tile.dimmed ? 0.5 : 0.9 }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 9
        anchors.rightMargin: 8
        spacing: 6
        Text { visible: tile.glyph !== ""; text: tile.glyph; color: tile.dimmed ? Theme.muted : tile.tone; font.pixelSize: 14; Layout.preferredWidth: 16; horizontalAlignment: Text.AlignHCenter }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text { text: tile.label; color: Theme.textSecondary; font.pixelSize: 8; font.bold: true; font.letterSpacing: 1.1; elide: Text.ElideRight; Layout.fillWidth: true }
            RowLayout {
                spacing: 3
                Layout.fillWidth: true
                Text {
                    text: tile.value
                    color: tile.dimmed ? Theme.muted : Theme.textPrimary
                    font.pixelSize: 14
                    font.family: "Cascadia Mono"
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.maximumWidth: tile.width - 60
                    Behavior on color { ColorAnimation { duration: 200 } }
                }
                Text { visible: tile.unit !== "" && !tile.dimmed; text: tile.unit; color: Theme.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 2 }
                Item { Layout.fillWidth: true }
            }
        }
    }
    Text {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 4
        visible: tile.stale && !tile.dimmed
        text: "STALE"
        color: Theme.warning
        font.pixelSize: 7
        font.bold: true
        font.letterSpacing: 1
        opacity: 0.85
    }
}
