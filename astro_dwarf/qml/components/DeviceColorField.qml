pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../dialogs"

// Marker colour for a telescope. Preset dots match the device-bar chips;
// PICK opens the HUD colour modal for a custom hex.
Item {
    id: field
    objectName: "deviceColorField"
    property string colorHex: "#62A0FF"
    property string roleName: "DEVICE DOT"
    property var presets: backend.deviceColorPresets && backend.deviceColorPresets.length
                          ? backend.deviceColorPresets
                          : ["#62A0FF", "#E879F9", "#34D399", "#FBBF24", "#FB7185"]
    readonly property color currentColor: Theme.parseHex(field.colorHex) || Theme.accent

    implicitHeight: Theme.controlHeight
    implicitWidth: row.implicitWidth
    Accessible.role: Accessible.Grouping
    Accessible.name: "Device colour"
    Accessible.description: field.colorHex

    function setHex(value) {
        const parsed = Theme.parseHex(value)
        if (!parsed)
            return
        field.colorHex = Theme.colorToHex(parsed)
    }

    function assignUnused(used) {
        const taken = {}
        const list = used || ((backend.devices || []).map(function (item) { return item.color }))
        for (let i = 0; i < list.length; i++)
            taken[String(list[i] || "").toUpperCase()] = true
        const palette = field.presets || []
        for (let i = 0; i < palette.length; i++) {
            const hex = String(palette[i] || "").toUpperCase()
            if (hex && !taken[hex]) {
                field.colorHex = hex
                return
            }
        }
        if (palette.length)
            field.colorHex = palette[list.length % palette.length]
    }

    function openPicker() {
        colourPick.roleName = field.roleName
        colourPick.selectedColor = field.currentColor
        colourPick.open()
    }

    function dismiss() {
        if (colourPick.visible)
            colourPick.close()
    }

    onVisibleChanged: if (!visible) field.dismiss()

    RowLayout {
        id: row
        anchors.fill: parent
        spacing: Theme.px(6)

        Item {
            id: currentChip
            Layout.preferredWidth: Theme.controlHeight
            Layout.preferredHeight: Theme.controlHeight
            Accessible.role: Accessible.Button
            Accessible.name: "Current device colour " + field.colorHex
            Accessible.description: "Opens the colour picker"
            activeFocusOnTab: true
            Keys.onReturnPressed: field.openPicker()
            Keys.onSpacePressed: field.openPicker()
            HoverHandler { id: currentHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: field.openPicker() }
            Rectangle {
                anchors.centerIn: parent
                width: Theme.px(18)
                height: Theme.px(18)
                radius: Theme.px(9)
                color: field.currentColor
                border.color: currentChip.activeFocus || currentHover.hovered ? Theme.textPrimary : Theme.outlineStrong
                border.width: 2
                Behavior on border.color { ColorAnimation { duration: Theme.quick } }
            }
            ToolTip.visible: currentHover.hovered
            ToolTip.delay: Theme.tooltipDelay
            ToolTip.text: field.colorHex + ". Click to pick a custom colour."
        }

        Repeater {
            model: field.presets
            delegate: Item {
                id: chip
                required property var modelData
                required property int index
                Layout.preferredWidth: Theme.px(26)
                Layout.preferredHeight: Theme.controlHeight
                readonly property string hex: String(modelData || "").toUpperCase()
                readonly property bool chosen: chip.hex === String(field.colorHex).toUpperCase()
                Accessible.role: Accessible.Button
                Accessible.name: "Preset colour " + chip.hex
                Accessible.checkable: true
                Accessible.checked: chip.chosen
                activeFocusOnTab: true
                Keys.onReturnPressed: field.setHex(chip.modelData)
                Keys.onSpacePressed: field.setHex(chip.modelData)
                HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: field.setHex(chip.modelData) }
                Rectangle {
                    anchors.centerIn: parent
                    width: chip.chosen ? Theme.s4 : Theme.s3
                    height: width
                    radius: width / 2
                    color: chip.modelData
                    border.color: chip.chosen || chip.activeFocus ? Theme.textPrimary : (chipHover.hovered ? Theme.outlineStrong : Theme.outline)
                    border.width: chip.chosen || chip.activeFocus ? Theme.px(2) : Theme.px(1)
                    Behavior on width { NumberAnimation { duration: Theme.quick } }
                    Behavior on border.color { ColorAnimation { duration: Theme.quick } }
                }
                ToolTip.visible: chipHover.hovered
                ToolTip.delay: Theme.tooltipDelay
                ToolTip.text: chip.hex
            }
        }

        HudButton {
            text: "PICK"
            implicitHeight: Theme.controlHeight
            accessibleDescription: "Open a colour picker for this telescope's marker"
            onClicked: field.openPicker()
        }
        Text {
            text: field.colorHex
            color: Theme.textSecondary
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontSm
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
    }

    ColorPickDialog {
        id: colourPick
        screenPicker: backend.screenColor
        onAccepted: field.setHex(colourPick.currentHex)
    }
}
