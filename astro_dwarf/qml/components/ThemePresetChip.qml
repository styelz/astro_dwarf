import QtQuick
import ".."

// Named-theme picker. Paints that theme's panel, line and accent so looks
// can be compared before they are applied.
Item {
    id: chip
    property var themeEntry: ({})
    property bool selected: false
    readonly property string themeId: chip.themeEntry && chip.themeEntry.id ? String(chip.themeEntry.id) : ""
    readonly property string themeLabel: chip.themeEntry && chip.themeEntry.name ? String(chip.themeEntry.name) : ""
    readonly property color panelTint: Theme.previewColor(chip.themeEntry, "surface")
    readonly property color accentTint: Theme.previewColor(chip.themeEntry, "accent")
    readonly property color lineTint: Theme.previewColor(chip.themeEntry, "outline")
    readonly property color typeTint: Theme.previewColor(chip.themeEntry, "textPrimary")
    signal clicked()

    implicitWidth: Theme.px(100)
    implicitHeight: Theme.px(40)
    Accessible.role: Accessible.Button
    Accessible.name: chip.themeLabel
    Accessible.description: chip.selected ? "Current theme" : "Apply " + chip.themeLabel
    Accessible.checkable: true
    Accessible.checked: chip.selected
    activeFocusOnTab: true
    Keys.onReturnPressed: chip.clicked()
    Keys.onSpacePressed: chip.clicked()

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        onTapped: chip.clicked()
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: chip.panelTint
        border.width: chip.selected || chip.activeFocus ? Theme.px(2) : Theme.px(1)
        border.color: chip.selected || chip.activeFocus ? chip.accentTint : (hover.hovered ? chip.accentTint : chip.lineTint)
        Behavior on border.color { ColorAnimation { duration: Theme.quick } }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.px(1)
            height: Theme.px(7)
            radius: Theme.px(1)
            color: chip.accentTint
        }
        Text {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: Theme.s1
            anchors.rightMargin: Theme.s1
            anchors.bottomMargin: Theme.px(5)
            text: chip.themeLabel.toUpperCase()
            color: chip.typeTint
            font.pixelSize: Theme.fontXs
            font.bold: true
            font.letterSpacing: 0.6
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
        }
    }

    HudToolTip {
        visible: hover.hovered
        text: chip.selected ? chip.themeLabel + " is active." : "Apply " + chip.themeLabel + "."
    }
}
