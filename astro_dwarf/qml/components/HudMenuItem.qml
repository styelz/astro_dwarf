import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import ".."

T.MenuItem {
    id: hudMenuItem
    property string glyph: ""
    property string trailingText: ""
    property bool destructive: false
    implicitWidth: 220
    implicitHeight: 34
    leftPadding: 8
    rightPadding: 10
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    opacity: enabled ? 1 : 0.4
    font.pixelSize: 13
    background: Rectangle {
        color: hudMenuItem.highlighted || hudMenuItem.down ? Theme.fillChecked : "transparent"
        radius: 4
    }
    contentItem: RowLayout {
        spacing: 10
        Text {
            Layout.preferredWidth: 18
            text: hudMenuItem.glyph
            color: hudMenuItem.destructive ? Theme.danger : Theme.textSecondary
            font.family: Theme.fontIcon
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Text {
            Layout.fillWidth: true
            text: hudMenuItem.text
            color: hudMenuItem.destructive ? Theme.danger : Theme.textPrimary
            font: hudMenuItem.font
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }
        Text {
            visible: text.length > 0
            text: hudMenuItem.subMenu ? "\uE76C" : hudMenuItem.trailingText
            color: Theme.textSecondary
            font.family: hudMenuItem.subMenu ? Theme.fontIcon : Theme.fontUi
            font.pixelSize: hudMenuItem.subMenu ? 12 : 11
            elide: Text.ElideMiddle
            Layout.maximumWidth: 92
            verticalAlignment: Text.AlignVCenter
        }
    }
}
