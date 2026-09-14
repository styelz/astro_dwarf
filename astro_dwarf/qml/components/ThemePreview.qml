import QtQuick
import QtQuick.Layouts
import ".."

// Live HUD fragment so palette edits can be judged against buttons, type,
// inputs and the fixed semantic colours without leaving Settings.
Rectangle {
    id: preview
    implicitHeight: 44
    color: Theme.panelFill
    border.color: Theme.outline
    border.width: 1
    radius: Theme.radius
    clip: true
    Layout.minimumWidth: 0
    Accessible.role: Accessible.StaticText
    Accessible.name: "Theme preview"
    Accessible.description: "Live sample of panel, type, accent, input and status colours"

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 8

        Text {
            text: "PREVIEW"
            color: Theme.accent
            font.pixelSize: Theme.fontXs
            font.bold: true
            font.letterSpacing: Theme.tracking2
        }
        HudButton {
            text: "ACTION"
            implicitHeight: Theme.compactControlHeight
            Layout.alignment: Qt.AlignVCenter
            Accessible.name: "Preview action button"
        }
        HudButton {
            text: "LIVE"
            implicitHeight: Theme.compactControlHeight
            Layout.alignment: Qt.AlignVCenter
            buttonColor: Theme.fillActive
            foregroundColor: Theme.accent
            Accessible.name: "Preview accent button"
        }
        HudChip {
            label: "CHIP"
            tone: Theme.accent
        }
        Rectangle {
            Layout.preferredWidth: 88
            Layout.preferredHeight: Theme.compactControlHeight
            color: Theme.inputBg
            border.color: Theme.outline
            border.width: 1
            radius: 2
            Text {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                text: "FIELD"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSm
                font.family: Theme.fontMono
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
        }
        Text {
            text: "DIM TYPE"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
        }
        Item { Layout.fillWidth: true }
        HudChip { label: "OK"; tone: Theme.success }
        HudChip { label: "WARN"; tone: Theme.warning }
        HudChip { label: "ERR"; tone: Theme.danger }
    }
}
