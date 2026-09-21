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
    implicitHeight: Theme.px(46)
    implicitWidth: Theme.px(96)
    readonly property bool compact: height > 0 && height < Theme.px(38)
    readonly property int valuePx: compact
        ? Math.max(Theme.s2, Math.min(Theme.s3, height - Theme.px(10)))
        : Math.max(Theme.px(10), Math.min(Theme.px(14), Math.round(height * 0.30)))
    readonly property int labelPx: compact
        ? Math.max(Theme.px(6), Math.min(Theme.s2, Math.round(height * 0.32)))
        : Math.max(Theme.px(6), Math.min(Theme.s2, Math.round(height * 0.18)))
    readonly property int glyphPx: Math.max(Theme.px(9), Math.min(Theme.px(14), Math.round(height * 0.32)))
    readonly property int unitPx: Math.max(Theme.px(7), Math.min(Theme.px(9), Math.round(height * (compact ? 0.28 : 0.20))))
    radius: Theme.radius
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
        width: Theme.px(2)
        height: parent.height - (tile.compact ? Theme.px(6) : Theme.px(10))
        color: tile.stale && !tile.dimmed ? Theme.warning : tile.dimmed ? Theme.outline : tile.tone
        opacity: tile.dimmed ? 0.5 : 0.9
        Behavior on color { ColorAnimation { duration: Theme.normal } }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: tile.compact ? Theme.px(6) : Theme.px(9)
        anchors.rightMargin: tile.compact ? Theme.px(5) : Theme.s2
        spacing: tile.compact ? Theme.s1 : Theme.px(6)
        Text {
            visible: tile.glyph !== "" && !tile.compact && tile.width >= Theme.px(84)
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
                spacing: Theme.px(3)
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
                    Layout.minimumWidth: Theme.px(18)
                    Behavior on color { ColorAnimation { duration: Theme.normal } }
                }
                Text { visible: tile.unit !== "" && !tile.dimmed; text: tile.unit; color: Theme.textSecondary; font.pixelSize: tile.unitPx; elide: Text.ElideRight; Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: Theme.px(1) }
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
        anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(3)
        visible: tile.stale && !tile.dimmed && tile.height >= Theme.px(34)
        text: "STALE"
        color: Theme.warning
        font.pixelSize: Theme.fontPx(7)
        font.bold: true
        font.letterSpacing: 1
        opacity: 0.85
    }
}
