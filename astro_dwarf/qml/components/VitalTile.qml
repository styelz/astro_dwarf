import QtQuick
import QtQuick.Layouts
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
    implicitWidth: 96
    readonly property bool compact: height > 0 && height < 38
    readonly property int valuePx: compact
        ? Math.max(8, Math.min(12, height - 10))
        : Math.max(10, Math.min(14, Math.round(height * 0.30)))
    readonly property int labelPx: compact
        ? Math.max(6, Math.min(8, Math.round(height * 0.32)))
        : Math.max(6, Math.min(8, Math.round(height * 0.18)))
    readonly property int glyphPx: Math.max(9, Math.min(14, Math.round(height * 0.32)))
    readonly property int unitPx: Math.max(7, Math.min(9, Math.round(height * (compact ? 0.28 : 0.20))))
    radius: 3
    color: Theme.hsl(0.072, 0.581, 0.084, 0.400)
    border.color: stale && !dimmed ? Qt.rgba(Theme.warning.r, Theme.warning.g, Theme.warning.b, 0.75)
                                      : live ? Qt.rgba(tone.r, tone.g, tone.b, 0.6) : Theme.outlineSoft
    border.width: 1
    clip: true
    Accessible.name: label + ": " + value + (unit ? " " + unit : "")
    Accessible.description: stale && !dimmed ? "Last reported value; telemetry is stale" : live ? "Live telemetry" : "Telemetry"
    Behavior on border.color { ColorAnimation { duration: Theme.normal } }
    Rectangle {
        x: 0
        y: tile.compact ? 3 : 5
        width: 2
        height: parent.height - (tile.compact ? 6 : 10)
        color: tile.stale && !tile.dimmed ? Theme.warning : tile.dimmed ? Theme.outline : tile.tone
        opacity: tile.dimmed ? 0.5 : 0.9
        Behavior on color { ColorAnimation { duration: Theme.normal } }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: tile.compact ? 6 : 9
        anchors.rightMargin: tile.compact ? 5 : 8
        spacing: tile.compact ? 4 : 6
        Text {
            visible: tile.glyph !== "" && !tile.compact && tile.width >= 84
            text: tile.glyph
            color: tile.dimmed ? Theme.muted : tile.tone
            font.pixelSize: tile.glyphPx
            Layout.preferredWidth: font.pixelSize + 2
            horizontalAlignment: Text.AlignHCenter
        }
        ColumnLayout {
            visible: !tile.compact
            Layout.fillWidth: true
            spacing: 0
            Text { text: tile.label; color: Theme.textSecondary; font.pixelSize: tile.labelPx; font.bold: true; font.letterSpacing: 1.1; elide: Text.ElideRight; Layout.fillWidth: true }
            RowLayout {
                spacing: 3
                Layout.fillWidth: true
                Text {
                    text: tile.value
                    color: tile.dimmed ? Theme.muted : Theme.textPrimary
                    font.pixelSize: tile.valuePx
                    font.family: Theme.fontMono
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                    Layout.preferredWidth: implicitWidth
                    Layout.minimumWidth: 18
                    Behavior on color { ColorAnimation { duration: Theme.normal } }
                }
                Text { visible: tile.unit !== "" && !tile.dimmed; text: tile.unit; color: Theme.textSecondary; font.pixelSize: tile.unitPx; elide: Text.ElideRight; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 1 }
            }
        }
        Text {
            visible: tile.compact
            text: tile.label
            color: Theme.textSecondary
            font.pixelSize: tile.labelPx
            font.bold: true
            font.letterSpacing: 0.8
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text {
            visible: tile.compact
            text: tile.value
            color: tile.dimmed ? Theme.muted : Theme.textPrimary
            font.pixelSize: tile.valuePx
            font.family: Theme.fontMono
            font.bold: true
            elide: Text.ElideRight
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        }
        Text {
            visible: tile.compact && tile.unit !== "" && !tile.dimmed
            text: tile.unit
            color: Theme.textSecondary
            font.pixelSize: tile.unitPx
            elide: Text.ElideRight
        }
    }
    Text {
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 3
        visible: tile.stale && !tile.dimmed && tile.height >= 34
        text: "STALE"
        color: Theme.warning
        font.pixelSize: 7
        font.bold: true
        font.letterSpacing: 1
        opacity: 0.85
    }
}
