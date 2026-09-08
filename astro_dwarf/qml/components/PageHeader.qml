import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

RowLayout {
    id: pageHeader
    property string title: ""
    property string subtitle: ""
    property string glyph: ""
    default property alias actions: pageActions.data
    Layout.fillWidth: true
    spacing: 10
    Rectangle { width: 3; Layout.preferredHeight: 34; color: Theme.accent; radius: 1 }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 1
        RowLayout {
            spacing: 8
            Text { visible: pageHeader.glyph !== ""; text: pageHeader.glyph; color: Theme.accent; font.pixelSize: 16 }
            Text { text: pageHeader.title; color: Theme.textPrimary; font.pixelSize: 22; font.letterSpacing: 2.4; font.bold: true }
        }
        Text { visible: pageHeader.subtitle !== ""; text: pageHeader.subtitle; color: Theme.textSecondary; font.pixelSize: 11; font.letterSpacing: 0.4; elide: Text.ElideRight; Layout.fillWidth: true }
    }
    Row {
        id: pageActions
        spacing: 8
        Layout.fillWidth: false
        Layout.preferredWidth: implicitWidth
        Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
    }
}
