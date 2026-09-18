import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import ".."

T.MenuItem {
    id: hudMenuItem
    property string glyph: ""
    property string trailingText: ""
    property bool destructive: false
    property bool info: false
    property string accessibleDescription: ""
    implicitWidth: 220
    implicitHeight: visible ? (info ? Math.max(Theme.compactControlHeight, (contentItem ? contentItem.implicitHeight : 0) + topPadding + bottomPadding) : 34) : 0
    height: visible ? implicitHeight : 0
    leftPadding: 8
    rightPadding: 10
    topPadding: visible && info ? 4 : 0
    bottomPadding: visible && info ? 4 : 0
    hoverEnabled: !info
    focusPolicy: info ? Qt.NoFocus : Qt.StrongFocus
    Accessible.name: text
    Accessible.description: accessibleDescription || trailingText
    Accessible.role: info ? Accessible.StaticText : Accessible.MenuItem
    opacity: info ? 1 : (enabled ? 1 : 0.4)
    font.pixelSize: info ? Theme.fontMd : Theme.fontBase
    HoverHandler {
        enabled: hudMenuItem.enabled && !hudMenuItem.info
        cursorShape: Qt.PointingHandCursor
    }
    background: Rectangle {
        color: !hudMenuItem.info && (hudMenuItem.highlighted || hudMenuItem.down) ? Theme.fillChecked : "transparent"
        radius: 4
    }
    contentItem: RowLayout {
        spacing: 10
        Text {
            visible: !hudMenuItem.info || hudMenuItem.glyph !== ""
            Layout.preferredWidth: visible ? 18 : 0
            text: hudMenuItem.glyph
            color: hudMenuItem.info ? Theme.muted : (hudMenuItem.destructive ? Theme.danger : Theme.textSecondary)
            font.family: Theme.fontIcon
            font.pixelSize: 14
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        Text {
            Layout.fillWidth: true
            text: hudMenuItem.text
            color: hudMenuItem.info ? Theme.muted : (hudMenuItem.destructive ? Theme.danger : Theme.textPrimary)
            font: hudMenuItem.font
            wrapMode: hudMenuItem.info ? Text.Wrap : Text.NoWrap
            elide: hudMenuItem.info ? Text.ElideNone : Text.ElideRight
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
