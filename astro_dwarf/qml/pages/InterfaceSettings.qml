pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

// Console appearance: layout, named themes, and per-token colour matching.
ColumnLayout {
    id: iface
    property int controlWidth: 320
    property string tintRole: "accent"
    property string matchSourceKey: "surface"
    property bool naming: false
    spacing: Theme.s3
    Layout.fillWidth: true
    Layout.alignment: Qt.AlignTop | Qt.AlignLeft

    readonly property bool tintCustom: Theme.paletteCustom
    readonly property real tintHue: {
        void Theme.paletteJson
        void Theme.hue
        if (iface.tintRole === "windowBase")
            return Theme.wrapHue(Theme.hue)
        return Theme.effectiveHue(iface.tintRole)
    }
    readonly property real tintSat: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.effectiveSat(iface.tintRole)
    }
    readonly property real tintBrightness: {
        void Theme.paletteJson
        void Theme.brightness
        if (iface.tintRole === "windowBase")
            return Theme.brightness
        return Theme.effectiveBrightness(iface.tintRole)
    }
    readonly property real tintLight: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.effectiveLight(iface.tintRole)
    }
    readonly property string tintHex: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.colorToHex(Theme.colorFor(iface.tintRole))
    }
    readonly property string tintRoleName: Theme.roleName(iface.tintRole)
    readonly property string tintParentKey: Theme.parentOf(iface.tintRole)
    readonly property bool tintLinked: Theme.roleLinked(iface.tintRole)
    readonly property var themeNames: {
        void Theme.savedThemesJson
        const list = Theme.listedThemes
        const names = []
        for (let i = 0; i < list.length; i++)
            names.push(list[i].name)
        return names
    }
    readonly property int themeIndex: {
        void Theme.savedThemesJson
        void Theme.activeThemeId
        return Theme.themeIndexOf(Theme.activeThemeId)
    }
    readonly property string themeStatus: {
        void Theme.savedThemesJson
        void Theme.activeThemeId
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        const item = Theme.activeTheme
        const name = item && item.name ? String(item.name).toUpperCase() : "CUSTOM"
        return Theme.themeEdited ? name + " · EDITED" : name
    }
    readonly property var matchNames: {
        const list = Theme.swatches
        const names = []
        for (let i = 0; i < list.length; i++) {
            if (list[i].key !== iface.tintRole)
                names.push(list[i].name)
        }
        return names
    }
    readonly property var matchKeys: {
        const list = Theme.swatches
        const keys = []
        for (let i = 0; i < list.length; i++) {
            if (list[i].key !== iface.tintRole)
                keys.push(list[i].key)
        }
        return keys
    }
    readonly property int matchIndex: {
        const keys = iface.matchKeys
        const idx = keys.indexOf(iface.matchSourceKey)
        return idx
    }
    readonly property var relatedKeys: {
        const keys = []
        const parent = iface.tintParentKey
        if (parent)
            keys.push(parent)
        const fol = Theme.followersOf(iface.tintRole)
        for (let i = 0; i < fol.length; i++)
            keys.push(fol[i])
        return keys
    }
    readonly property bool seedRole: iface.tintRole === "windowBase"
    readonly property bool savedSlot: !Theme.isBuiltinId(Theme.activeThemeId)

    function confirmSaveAs() {
        const id = Theme.saveThemeAs(themeNameField.text)
        if (!id)
            return
        iface.naming = false
    }

    function startSaveAs() {
        iface.naming = true
        const item = Theme.activeTheme
        const base = item && item.name ? item.name : "Custom"
        themeNameField.text = Theme.themeEdited || Theme.isBuiltinId(Theme.activeThemeId) ? base + " copy" : base
        themeNameField.forceActiveFocus()
        themeNameField.selectAll()
    }

    onTintRoleChanged: {
        if (iface.matchSourceKey === iface.tintRole)
            iface.matchSourceKey = iface.tintRole === "accent" ? "surface" : "accent"
    }

    FieldHint {
        text: "How the console looks on this computer. Changes apply immediately and are remembered here, not on the telescope. Saved themes stay on this machine."
    }

    SettingGroup {
        title: "LAYOUT"
        FieldLabel { text: "NAV BUTTONS" }
        HudCombo {
            Layout.preferredWidth: iface.controlWidth
            model: ["Bottom", "Top (below header)"]
            currentIndex: layoutSettings.navBarOnTop ? 1 : 0
            onActivated: layoutSettings.navBarOnTop = currentIndex === 1
            accessibleName: "Navigation button position"
        }
        FieldHint { text: "Where the page tabs sit. Top keeps them under the device bar; Bottom leaves the header clear and puts them along the lower edge." }
    }

    SettingGroup {
        title: "THEMES"
        trailing: [
            HudChip {
                label: iface.themeStatus
                tone: Theme.themeEdited ? Theme.warning : Theme.accent
                dim: !Theme.themeEdited && Theme.isBuiltinId(Theme.activeThemeId)
                anchors.verticalCenter: parent.verticalCenter
            },
            HudChip {
                label: iface.savedSlot ? "SAVED" : "BUILT-IN"
                tone: iface.savedSlot ? Theme.success : Theme.textSecondary
                dim: !iface.savedSlot
                anchors.verticalCenter: parent.verticalCenter
            }
        ]
        FieldLabel { text: "PRESET" }
        HudCombo {
            id: themeCombo
            Layout.preferredWidth: iface.controlWidth
            model: iface.themeNames
            accessibleName: "Saved theme"
            accessibleDescription: "Apply a built-in or saved console theme"
            onActivated: {
                const list = Theme.listedThemes
                if (currentIndex >= 0 && currentIndex < list.length)
                    Theme.applyTheme(list[currentIndex].id)
                iface.naming = false
            }
            Binding {
                target: themeCombo
                property: "currentIndex"
                value: iface.themeIndex
                when: !themeCombo.popup.visible && iface.themeIndex >= 0
            }
        }
        FieldHint { text: "Built-in starting points, then themes you have saved. Switching applies immediately. Edits stay on the selected slot until you update it, save a copy, or reset." }
        FieldLabel { text: iface.naming ? "SAVE AS" : "NAME" }
        HudField {
            id: themeNameField
            Layout.preferredWidth: iface.controlWidth
            enabled: iface.naming || iface.savedSlot
            placeholderText: iface.naming ? "Theme name" : "Built-in"
            accessibleName: iface.naming ? "New theme name" : "Theme name"
            maximumLength: 40
            onEditingFinished: {
                if (iface.naming)
                    return
                if (iface.savedSlot)
                    Theme.renameTheme(Theme.activeThemeId, text)
            }
            Binding {
                target: themeNameField
                property: "text"
                value: Theme.activeTheme ? Theme.activeTheme.name : ""
                when: !themeNameField.activeFocus && !iface.naming
            }
        }
        FieldHint {
            text: iface.naming
                ? "Name this palette and confirm. Up to " + Theme.maxSavedThemes + " saved themes on this computer (" + Theme.savedThemeCount + " used)."
                : iface.savedSlot
                    ? "Rename the selected saved theme. Built-in presets keep their names."
                    : "Built-in presets cannot be renamed. Save a copy to keep your edits."
        }
        RowLayout {
            Layout.columnSpan: 3
            Layout.fillWidth: true
            spacing: 6
            HudButton {
                text: "REVERT"
                implicitHeight: 28
                enabled: Theme.themeEdited && !!Theme.activeTheme
                accessibleDescription: "Reload the selected theme and discard edits"
                onClicked: {
                    Theme.applyTheme(Theme.activeThemeId)
                    iface.naming = false
                }
            }
            HudButton {
                text: "UPDATE"
                implicitHeight: 28
                enabled: iface.savedSlot && Theme.themeEdited && !iface.naming
                accessibleDescription: "Overwrite the selected saved theme with the current palette"
                onClicked: Theme.updateTheme(Theme.activeThemeId)
            }
            HudButton {
                text: iface.naming ? "CONFIRM" : "SAVE AS"
                implicitHeight: 28
                enabled: iface.naming ? themeNameField.text.trim().length > 0 : Theme.savedThemeCount < Theme.maxSavedThemes
                accessibleDescription: iface.naming ? "Save the current palette under this name" : "Save the current palette as a new theme"
                onClicked: iface.naming ? iface.confirmSaveAs() : iface.startSaveAs()
            }
            HudButton {
                text: iface.naming ? "CANCEL" : "DELETE"
                implicitHeight: 28
                enabled: iface.naming || iface.savedSlot
                accessibleDescription: iface.naming ? "Cancel saving a new theme" : "Delete the selected saved theme"
                onClicked: {
                    if (iface.naming) {
                        iface.naming = false
                        return
                    }
                    Theme.deleteTheme(Theme.activeThemeId)
                }
            }
            HudButton {
                text: "RESET"
                implicitHeight: 28
                enabled: iface.tintCustom || Theme.activeThemeId !== "stock"
                accessibleDescription: "Return every palette colour to stock cyan"
                onClicked: {
                    Theme.resetPalette()
                    iface.naming = false
                }
            }
            Item { Layout.fillWidth: true }
        }
        FieldHint {
            Layout.columnSpan: 3
            text: Theme.savedThemeCount >= Theme.maxSavedThemes
                ? "Saved theme list is full. Delete one before saving another."
                : "Update writes over a saved theme. Save as keeps a copy. Reset returns to stock cyan."
        }
    }

    SettingGroup {
        title: "PALETTE"
        trailing: [
            HudChip {
                label: iface.tintRoleName
                tone: Theme.accent
                anchors.verticalCenter: parent.verticalCenter
            },
            HudChip {
                label: iface.tintLinked ? "FOLLOWS" : (Theme.roleCustom(iface.tintRole) ? "UNLOCKED" : "STOCK")
                tone: iface.tintLinked ? Theme.accent : (Theme.roleCustom(iface.tintRole) ? Theme.warning : Theme.textSecondary)
                dim: !iface.tintLinked && !Theme.roleCustom(iface.tintRole)
                anchors.verticalCenter: parent.verticalCenter
            }
        ]
        ColumnLayout {
            Layout.columnSpan: 3
            Layout.fillWidth: true
            spacing: Theme.s2
            Repeater {
                model: Theme.swatchGroups
                delegate: ColumnLayout {
                    id: groupBlock
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: groupBlock.modelData.title
                        color: Theme.muted
                        font.pixelSize: Theme.fontXs
                        font.bold: true
                        font.letterSpacing: Theme.tracking2
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: groupBlock.modelData.keys
                            delegate: PaletteSwatch {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredWidth: 40
                                Layout.minimumWidth: 36
                                roleKey: modelData.key
                                roleName: modelData.name
                                selected: iface.tintRole === modelData.key
                                onClicked: iface.tintRole = modelData.key
                                onResetRequested: Theme.clearRole(modelData.key)
                            }
                        }
                    }
                }
            }
        }
        FieldHint {
            Layout.columnSpan: 3
            text: "Click a swatch to edit it. BASE is the console seed: unedited colours, fills and the background art follow it. Amber dots are unlocked. Accent dots follow a parent. Double-click restores one colour. Success, warning and danger stay fixed so status still reads."
        }
    }

    SettingGroup {
        title: "COLOUR"
        FieldLabel { text: "HEX" }
        RowLayout {
            Layout.preferredWidth: iface.controlWidth
            Layout.fillWidth: true
            Layout.minimumWidth: 240
            spacing: 6
            HudField {
                id: hexField
                Layout.fillWidth: true
                Layout.preferredWidth: 120
                Layout.maximumWidth: 140
                font.family: Theme.fontMono
                maximumLength: 7
                accessibleName: iface.tintRoleName + " hex colour"
                validator: RegularExpressionValidator { regularExpression: /^#?[0-9A-Fa-f]{0,6}$/ }
                onEditingFinished: {
                    if (!Theme.applyHex(iface.tintRole, text))
                        text = iface.tintHex
                }
                Binding {
                    target: hexField
                    property: "text"
                    value: iface.tintHex
                    when: !hexField.activeFocus
                }
            }
            HudButton {
                text: "PICK"
                implicitHeight: Theme.controlHeight
                accessibleDescription: "Open a colour picker for the selected swatch"
                onClicked: {
                    colourPick.selectedColor = Theme.colorFor(iface.tintRole)
                    colourPick.open()
                }
            }
        }
        FieldHint { text: "Paste a #RRGGBB value or pick a colour to match an element. Hue, saturation and lightness are solved so this swatch lands on that colour." }
        FieldLabel { text: "MATCH" }
        RowLayout {
            Layout.preferredWidth: iface.controlWidth
            Layout.fillWidth: true
            Layout.minimumWidth: 240
            spacing: 6
            HudCombo {
                id: matchCombo
                Layout.fillWidth: true
                model: iface.matchNames
                accessibleName: "Colour to match from"
                onActivated: {
                    if (currentIndex >= 0 && currentIndex < iface.matchKeys.length)
                        iface.matchSourceKey = iface.matchKeys[currentIndex]
                }
                Binding {
                    target: matchCombo
                    property: "currentIndex"
                    value: Math.max(0, iface.matchIndex)
                    when: !matchCombo.popup.visible
                }
            }
        }
        FieldHint { text: "Choose another swatch, then copy only its hue (same family, keep this lightness) or the full colour." }
        RowLayout {
            Layout.columnSpan: 3
            Layout.fillWidth: true
            spacing: 6
            HudButton {
                text: "MATCH HUE"
                implicitHeight: 28
                enabled: iface.matchSourceKey !== iface.tintRole && iface.matchSourceKey !== ""
                accessibleDescription: "Copy hue from the match source onto the selected swatch"
                onClicked: Theme.matchHue(iface.tintRole, iface.matchSourceKey)
            }
            HudButton {
                text: "MATCH COLOUR"
                implicitHeight: 28
                enabled: iface.matchSourceKey !== iface.tintRole && iface.matchSourceKey !== ""
                accessibleDescription: "Copy the full colour from the match source onto the selected swatch"
                onClicked: Theme.matchRole(iface.tintRole, iface.matchSourceKey)
            }
            HudButton {
                text: "FOLLOW PARENT"
                implicitHeight: 28
                visible: iface.tintParentKey !== ""
                enabled: !iface.tintLinked
                accessibleDescription: "Let this colour follow " + Theme.roleName(iface.tintParentKey) + " again"
                onClicked: Theme.clearRole(iface.tintRole)
            }
            HudButton {
                text: "RESET SWATCH"
                implicitHeight: 28
                visible: iface.tintParentKey === ""
                enabled: Theme.roleCustom(iface.tintRole)
                accessibleDescription: "Restore the selected colour to stock"
                onClicked: Theme.clearRole(iface.tintRole)
            }
            Item { Layout.fillWidth: true }
        }
        FieldHint {
            Layout.columnSpan: 3
            visible: iface.tintParentKey !== ""
            text: iface.tintLinked
                ? iface.tintRoleName + " follows " + Theme.roleName(iface.tintParentKey) + ". Editing hue, saturation or lightness unlocks it."
                : iface.tintRoleName + " is unlocked from " + Theme.roleName(iface.tintParentKey) + ". Follow parent to hitch it again."
        }
        FieldLabel { text: "HUE" }
        HudSlider {
            id: hueSlider
            Layout.fillWidth: true
            Layout.preferredWidth: iface.controlWidth
            Layout.minimumWidth: 240
            from: 0
            to: 1
            stepSize: 0.001
            onMoved: Theme.setRole(iface.tintRole, value, iface.tintBrightness)
            markerPosition: iface.seedRole ? Theme.defaultHue : Theme.stockHue(iface.tintRole)
            valueText: Math.round(iface.tintHue * 360) + "°"
            accessibleName: iface.tintRoleName + " hue"
            trackGradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.000; color: Qt.hsla(0.000, 0.9, 0.55, 1) }
                GradientStop { position: 0.167; color: Qt.hsla(0.167, 0.9, 0.55, 1) }
                GradientStop { position: 0.333; color: Qt.hsla(0.333, 0.9, 0.55, 1) }
                GradientStop { position: 0.500; color: Qt.hsla(0.500, 0.9, 0.55, 1) }
                GradientStop { position: 0.667; color: Qt.hsla(0.667, 0.9, 0.55, 1) }
                GradientStop { position: 0.833; color: Qt.hsla(0.833, 0.9, 0.55, 1) }
                GradientStop { position: 1.000; color: Qt.hsla(1.000, 0.9, 0.55, 1) }
            }
            Binding {
                target: hueSlider
                property: "value"
                value: iface.tintHue
                when: !hueSlider.pressed
            }
        }
        FieldHint { text: iface.seedRole ? "Seed hue. Unedited swatches, Theme washes and the title bar follow this. The tick is stock cyan." : "Hue of the selected swatch. The tick is its stock position on the cyan HUD. Locked swatches stay put when BASE moves." }
        FieldLabel { text: "SAT" }
        HudSlider {
            id: satSlider
            Layout.fillWidth: true
            Layout.preferredWidth: iface.controlWidth
            Layout.minimumWidth: 240
            from: 0
            to: 1
            stepSize: 0.01
            onMoved: Theme.setRoleSat(iface.tintRole, value)
            markerPosition: Theme.stockSat(iface.tintRole)
            valueText: Math.round(iface.tintSat * 100) + "%"
            accessibleName: iface.tintRoleName + " saturation"
            trackGradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.hsla(iface.tintHue, 0, iface.tintLight, 1) }
                GradientStop { position: 1.0; color: Qt.hsla(iface.tintHue, 1, iface.tintLight, 1) }
            }
            Binding {
                target: satSlider
                property: "value"
                value: iface.tintSat
                when: !satSlider.pressed
            }
        }
        FieldHint { text: "How strong the selected colour is. 0% is grey at the same lightness; 100% is full tint. The tick is stock saturation for this swatch." }
        FieldLabel { text: iface.seedRole ? "LIFT" : "LIGHT" }
        HudSlider {
            id: lightSlider
            Layout.fillWidth: true
            Layout.preferredWidth: iface.controlWidth
            Layout.minimumWidth: 240
            from: iface.seedRole ? -1 : 0.02
            to: iface.seedRole ? 1 : 0.97
            stepSize: iface.seedRole ? 0.01 : 0.005
            onMoved: {
                if (iface.seedRole)
                    Theme.setRole(iface.tintRole, iface.tintHue, value)
                else
                    Theme.setRoleLight(iface.tintRole, value)
            }
            markerPosition: iface.seedRole ? 0.5 : (Theme.stockLight(iface.tintRole) - 0.02) / 0.95
            valueText: iface.seedRole
                ? ((iface.tintBrightness > 0 ? "+" : "") + Math.round(iface.tintBrightness * 100))
                : Math.round(iface.tintLight * 100) + "%"
            accessibleName: iface.seedRole ? "Palette brightness lift" : iface.tintRoleName + " lightness"
            trackGradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.hsla(iface.tintHue, iface.tintSat, 0.10, 1) }
                GradientStop { position: 0.5; color: Qt.hsla(iface.tintHue, iface.tintSat, 0.50, 1) }
                GradientStop { position: 1.0; color: Qt.hsla(iface.tintHue, iface.tintSat, 0.90, 1) }
            }
            Binding {
                target: lightSlider
                property: "value"
                value: iface.seedRole ? iface.tintBrightness : iface.tintLight
                when: !lightSlider.pressed
            }
        }
        FieldHint {
            text: iface.seedRole
                ? "Seed lift for unedited swatches. 0 is stock; negative deepens the HUD, positive raises it. Locked swatches keep their own lightness."
                : "Lightness of the selected swatch. The tick is stock. Use this with hex matching to land a colour without guessing the old brightness slider."
        }
        FieldLabel { text: "RELATED"; visible: iface.relatedKeys.length > 0 }
        RowLayout {
            visible: iface.relatedKeys.length > 0
            Layout.preferredWidth: iface.controlWidth
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: iface.relatedKeys
                delegate: PaletteSwatch {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredWidth: 40
                    roleKey: modelData
                    roleName: Theme.roleName(modelData)
                    selected: iface.tintRole === modelData
                    onClicked: iface.tintRole = modelData
                    onResetRequested: Theme.clearRole(modelData)
                }
            }
        }
        FieldHint {
            visible: iface.relatedKeys.length > 0
            text: iface.tintParentKey
                ? "Parent and followers of " + iface.tintRoleName + ". Match hue across this family so panels, lines and accents stay in the same tint."
                : "Tokens that follow " + iface.tintRoleName + ". They hitch to this colour until you unlock one and give it its own hex."
        }
    }

    SettingGroup {
        title: "SAMPLE"
        ThemePreview {
            Layout.columnSpan: 3
            Layout.fillWidth: true
        }
        FieldHint {
            Layout.columnSpan: 3
            text: "Live chrome using the current palette. OK / WARN / ERR stay on the fixed status colours so they still contrast. The Windows title bar follows panel, line and accent a moment after the sliders stop."
        }
    }

    ColorDialog {
        id: colourPick
        title: "Pick " + iface.tintRoleName
        onAccepted: Theme.applyColor(iface.tintRole, selectedColor)
    }
}
