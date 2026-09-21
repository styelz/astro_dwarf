import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

RowLayout {
    id: pageHeader
    property string title: ""
    property string subtitle: ""
    property string glyph: ""
    default property alias actions: pageActions.data
    Layout.fillWidth: true
    spacing: Theme.px(10)
    Rectangle { width: Theme.px(3); Layout.preferredHeight: Theme.controlHeight; color: Theme.accent; radius: Theme.px(1) }
    ColumnLayout {
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredWidth: 0
        spacing: Theme.px(1)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            Text { visible: pageHeader.glyph !== ""; text: pageHeader.glyph; color: Theme.accent; font.pixelSize: Theme.fontLg }
            Text {
                text: pageHeader.title
                color: Theme.textPrimary
                font.pixelSize: Theme.fontXl
                font.letterSpacing: Theme.tracking3
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.minimumWidth: 0
            }
        }
        Text {
            visible: pageHeader.subtitle !== ""
            text: pageHeader.subtitle
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
            font.letterSpacing: 0.4
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.minimumWidth: 0
        }
    }
    Row {
        id: pageActions
        spacing: Theme.s2
        Layout.fillWidth: false
        Layout.preferredWidth: implicitWidth
        Layout.minimumWidth: 0
        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
    }
}
