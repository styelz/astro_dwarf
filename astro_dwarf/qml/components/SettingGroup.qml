import QtQuick
import QtQuick.Layouts
import ".."

// A titled block of settings rows. The default grid is label | control | hint so
// every value carries a short note on what it does; set `columns` to change it.
ColumnLayout {
    id: group
    property string title: ""
    property alias trailing: trailingRow.data
    property alias columns: body.columns
    default property alias contents: body.data
    spacing: Theme.s2
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.s2
        Text {
            text: group.title
            visible: text.length
            color: Theme.accent
            font.pixelSize: Theme.fontSm
            font.bold: true
            font.letterSpacing: Theme.tracking2
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Theme.px(1)
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35) }
                GradientStop { position: 1.0; color: Theme.hsl(0.039, 0.535, 0.253, 0.15) }
            }
        }
        Row {
            id: trailingRow
            spacing: Theme.px(6)
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
        }
    }
    GridLayout {
        id: body
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignLeft | Qt.AlignTop
        Layout.leftMargin: Theme.s1
        columns: 3
        columnSpacing: Theme.s3
        rowSpacing: Theme.s2
    }
}
