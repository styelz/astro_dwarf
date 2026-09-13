import QtQuick
import QtQuick.Controls
import ".."

// Clickable theme-role sample. Hue/brightness sliders edit the selected swatch;
// BASE writes the palette seed so unedited colours follow. Double-click restores
// that role to stock. A hue strip stays readable on near-black fills.
Item {
    id: swatch
    property string roleKey: ""
    property string roleName: ""
    property bool selected: false
    readonly property color tint: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return roleKey ? Theme.colorFor(roleKey) : Theme.surface
    }
    readonly property bool customized: {
        void Theme.paletteJson
        return Theme.roleCustom(roleKey)
    }
    signal clicked()
    signal resetRequested()

    implicitWidth: 40
    implicitHeight: 36
    Accessible.role: Accessible.Button
    Accessible.name: roleName + " colour"
    Accessible.description: selected
        ? "Selected. Hue and brightness sliders edit this colour. Double-click restores it."
        : "Click to edit this colour. Double-click restores it."
    Accessible.checkable: true
    Accessible.checked: selected
    activeFocusOnTab: true
    Keys.onReturnPressed: swatch.clicked()
    Keys.onSpacePressed: swatch.clicked()

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }
    TapHandler {
        id: tap
        onTapped: {
            if (tap.tapCount > 1)
                swatch.resetRequested()
            else
                swatch.clicked()
        }
    }

    Column {
        anchors.fill: parent
        spacing: 3
        Rectangle {
            width: parent.width
            height: 22
            radius: 2
            color: swatch.tint
            border.color: swatch.selected || swatch.activeFocus ? Theme.accent : (hover.hovered ? Theme.outlineStrong : Theme.outline)
            border.width: swatch.selected || swatch.activeFocus ? 2 : 1
            Behavior on border.color { ColorAnimation { duration: Theme.quick } }
            Rectangle {
                // Near-black roles (BASE, PANEL) hide hue in the fill; this strip keeps it readable.
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 1
                height: 3
                radius: 1
                color: {
                    void Theme.paletteJson
                    void Theme.hue
                    void Theme.brightness
                    return Qt.hsla(Theme.effectiveHue(swatch.roleKey), 0.9, 0.55, 1)
                }
            }
            Rectangle {
                visible: swatch.customized
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 2
                width: 5
                height: 5
                radius: 1
                color: Theme.warning
            }
        }
        Text {
            width: parent.width
            text: swatch.roleName
            color: swatch.selected ? Theme.accent : Theme.textSecondary
            font.pixelSize: Theme.fontXs
            font.letterSpacing: 0.6
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
    }

    ToolTip.visible: hover.hovered
    ToolTip.delay: Theme.tooltipDelay
    ToolTip.text: (selected ? "Editing " : "Edit ") + roleName + ". Double-click restores this colour."
}
