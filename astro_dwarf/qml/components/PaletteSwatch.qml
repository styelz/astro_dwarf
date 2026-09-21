import QtQuick
import ".."

// Clickable theme-role sample. Hue/saturation/lightness sliders edit the
// selected swatch; WINDOW writes the palette seed so unedited colours follow.
// Double-click restores that role to stock. A hue strip stays readable on
// near-black fills. Tooltip names the on-screen use so the chip is not a code token.
Item {
    id: swatch
    property string roleKey: ""
    property string roleName: ""
    property bool selected: false
    readonly property string roleHint: {
        void Theme.paletteJson
        return roleKey ? Theme.roleHint(roleKey) : ""
    }
    readonly property color tint: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return roleKey ? Theme.colorFor(roleKey) : Theme.surface
    }
    readonly property bool customized: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.roleCustom(roleKey)
    }
    readonly property bool linked: {
        void Theme.paletteJson
        return Theme.roleLinked(roleKey)
    }
    readonly property string hex: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.colorToHex(swatch.tint)
    }
    signal clicked()
    signal resetRequested()

    implicitWidth: Theme.px(72)
    implicitHeight: Theme.px(48)
    Accessible.role: Accessible.Button
    Accessible.name: roleName + " colour"
    Accessible.description: {
        const hex = swatch.hex
        const use = swatch.roleHint ? " " + swatch.roleHint : ""
        if (selected)
            return "Selected " + hex + "." + use + " Sliders edit this colour. Double-click restores it."
        if (linked)
            return hex + "." + use + " Follows " + Theme.roleName(Theme.parentOf(roleKey)) + ". Click to edit. Double-click restores it."
        return hex + "." + use + " Click to edit this colour. Double-click restores it."
    }
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
        spacing: Theme.px(3)
        Rectangle {
            width: parent.width
            height: Theme.px(22)
            radius: Theme.px(2)
            color: swatch.tint
            border.color: swatch.selected || swatch.activeFocus ? Theme.accent : (hover.hovered ? Theme.outlineStrong : Theme.outline)
            border.width: swatch.selected || swatch.activeFocus ? Theme.px(2) : Theme.px(1)
            Behavior on border.color { ColorAnimation { duration: Theme.quick } }
            Rectangle {
                // Near-black roles (WINDOW, CARD) hide hue in the fill; this strip keeps it readable.
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: Theme.px(1)
                height: Theme.px(3)
                radius: Theme.px(1)
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
                anchors.margins: Theme.px(2)
                width: Theme.px(5)
                height: Theme.px(5)
                radius: Theme.px(1)
                color: Theme.warning
            }
            Rectangle {
                visible: swatch.linked && !swatch.customized
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.px(2)
                width: Theme.px(5)
                height: Theme.px(5)
                radius: Theme.px(1)
                color: Theme.accent
                opacity: 0.7
            }
        }
        Text {
            width: parent.width
            height: Theme.s5
            text: swatch.roleName
            color: swatch.selected ? Theme.accent : Theme.textSecondary
            font.pixelSize: Theme.fontXs
            font.letterSpacing: 0.4
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }
    }

    HudToolTip {
        visible: hover.hovered
        wrapWidth: Theme.px(280)
        text: {
            const parentName = Theme.parentOf(swatch.roleKey) ? Theme.roleName(Theme.parentOf(swatch.roleKey)) : ""
            let line = (selected ? "Editing " : "Edit ") + roleName + "  " + swatch.hex + "."
            if (swatch.roleHint)
                line += " " + swatch.roleHint
            if (parentName)
                line += linked ? " Follows " + parentName + "." : " Unlocked from " + parentName + "."
            line += " Double-click restores this colour."
            return line
        }
    }
}
