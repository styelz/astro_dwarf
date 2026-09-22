pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."
import "../components"
import "../dialogs"

// Console appearance: layout, named themes, and per-token colour matching.
ColumnLayout {
    id: iface
    objectName: "interfaceSettings"
    property int controlWidth: Theme.px(320)
    property string tintRole: "accent"
    property string matchSourceKey: "surface"
    property bool naming: false
    property string testApplyId: ""
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
    readonly property string tintRoleHint: Theme.roleHint(iface.tintRole)
    readonly property string tintParentKey: Theme.parentOf(iface.tintRole)
    readonly property bool tintLinked: Theme.roleLinked(iface.tintRole)
    readonly property string themeStatus: {
        void Theme.savedThemesJson
        void Theme.themeNamesJson
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
    readonly property bool tintFixed: Theme.roleFixed(iface.tintRole)
    readonly property bool savedSlot: !Theme.isBuiltinId(Theme.activeThemeId)
    readonly property bool exampleSlot: Theme.isShippedCustomId(Theme.activeThemeId) && !Theme.hasSavedCopy(Theme.activeThemeId)
    readonly property bool builtinDefault: {
        void Theme.savedThemesJson
        void Theme.activeThemeId
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        if (!Theme.isBuiltinId(Theme.activeThemeId))
            return false
        return Theme.hasSavedCopy(Theme.activeThemeId) || Theme.themeEdited
    }
    readonly property bool renameable: Theme.canRenameTheme(Theme.activeThemeId)
    readonly property bool colourSplit: iface.width >= Theme.px(620)
    readonly property string probeThemeId: Theme.activeThemeId
    readonly property string probeTintRole: iface.tintRole
    readonly property string probeAccentHex: {
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return Theme.colorToHex(Theme.accent)
    }
    readonly property string probeSnapshot: {
        void Theme.savedThemesJson
        void Theme.activeThemeId
        void Theme.paletteJson
        void Theme.hue
        void Theme.brightness
        return JSON.stringify({
            id: Theme.activeThemeId,
            hue: Theme.hue,
            brightness: Theme.brightness,
            paletteJson: Theme.paletteJson
        })
    }

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

    function applyListedTheme(id) {
        Theme.applyTheme(id)
        iface.naming = false
    }

    function restoreThemeSnapshot(json) {
        try {
            const snap = JSON.parse(json)
            Theme.restoreSnapshot(snap.id, snap.hue, snap.brightness, snap.paletteJson)
        } catch (exc) {
        }
        iface.naming = false
    }

    onTintRoleChanged: {
        if (iface.matchSourceKey === iface.tintRole)
            iface.matchSourceKey = iface.tintRole === "accent" ? "surface" : "accent"
    }

    onTestApplyIdChanged: {
        if (iface.testApplyId)
            iface.applyListedTheme(iface.testApplyId)
    }

    FieldHint {
        text: "Console look on this computer. Changes apply immediately and stay here, not on the telescope."
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
        FieldHint { text: "Top sits under the device bar. Bottom keeps the header clear." }
        FieldLabel { text: "UI SCALE" }
        HudCombo {
            Layout.preferredWidth: iface.controlWidth
            model: Theme.uiScalePrefLabels
            currentIndex: {
                const i = Theme.uiScalePrefKeys.indexOf(Theme.uiScalePref)
                return i >= 0 ? i : 0
            }
            onActivated: Theme.uiScalePref = Theme.uiScalePrefKeys[currentIndex] || "auto"
            accessibleName: "UI scale"
        }
        FieldHint { text: "Auto follows this monitor so 2K and 4K chrome grow. 100% is the current laptop look." }
        FieldLabel { text: "FONT SIZE" }
        HudCombo {
            Layout.preferredWidth: iface.controlWidth
            model: Theme.fontSizePrefLabels
            currentIndex: {
                const i = Theme.fontSizePrefKeys.indexOf(Theme.fontSizePref)
                return i >= 0 ? i : 1
            }
            onActivated: Theme.fontSizePref = Theme.fontSizePrefKeys[currentIndex] || "default"
            accessibleName: "Font size"
        }
        FieldHint { text: "Type only. Default matches the current HUD. Large and extra large also grow controls that have to fit a line of text." }
        FieldLabel { text: "ZOOM" }
        HudSlider {
            id: zoomSlider
            objectName: "appZoom"
            Layout.preferredWidth: iface.controlWidth
            from: Theme.zoomMin
            to: Theme.zoomMax
            stepSize: 0.1
            markerPosition: (1 - Theme.zoomMin) / (Theme.zoomMax - Theme.zoomMin)
            valueText: Math.round(Theme.snapZoom(value) * 100) + "%"
            accessibleName: "App zoom"
            tooltip: "Whole-app zoom. The console resizes when you release so the slider stays under the pointer. Ctrl + and − step 10%. Ctrl+0 resets to 100%."
            // Applying zoom live rescales Theme.px() and this panel, which drops
            // mouse grab / hover after a single step. Keep the layout still until
            // the drag ends or wheel / key input settles.
            property bool editing: false
            function commitZoom() {
                zoomCommitTimer.stop()
                Theme.zoom = Theme.snapZoom(value)
                editing = false
            }
            onMoved: {
                editing = true
                if (pressed)
                    return
                zoomCommitTimer.restart()
            }
            onPressedChanged: {
                if (pressed) {
                    editing = true
                    zoomCommitTimer.stop()
                    return
                }
                commitZoom()
            }
            Component.onCompleted: value = Theme.zoomClamped
            Component.onDestruction: {
                if (editing)
                    commitZoom()
            }
            Timer {
                id: zoomCommitTimer
                interval: Theme.slow
                onTriggered: zoomSlider.commitZoom()
            }
            Connections {
                target: Theme
                function onZoomChanged() {
                    if (zoomSlider.pressed || zoomSlider.editing)
                        return
                    zoomSlider.value = Theme.zoomClamped
                }
            }
        }
        FieldHint { text: "Ctrl + / − zoom the whole console. Ctrl+0 resets to 100%. Calendar Ctrl+wheel still zooms the night timeline." }
        FieldLabel { text: "SKY TOOLS" }
        HudCheck {
            Layout.preferredWidth: iface.controlWidth
            text: "Show SKY tab"
            checked: layoutSettings.skyToolsEnabled
            onToggled: layoutSettings.skyToolsEnabled = checked
            accessibleName: "Show sky tools tab"
        }
        FieldHint { text: "Adds a SKY page that uses Stellarium Web to find a target and generate an X-by-Y mosaic plan. Off by default. Unofficial; not affiliated with Stellarium Labs or DwarfLab." }
    }

    SettingGroup {
        title: "BACKGROUND"
        trailing: [
            HudChip {
                label: !Theme.hudBackground ? "OFF" : (Math.round(Theme.hudBackgroundOpacity * 100) + "%")
                tone: Theme.hudBackground ? Theme.success : Theme.textSecondary
                dim: !Theme.hudBackground
                glow: Theme.hudBackground
                anchors.verticalCenter: parent.verticalCenter
            }
        ]
        FieldLabel { text: "ART" }
        HudCheck {
            Layout.preferredWidth: iface.controlWidth
            text: "Show HUD background art"
            checked: Theme.hudBackground
            onToggled: Theme.hudBackground = checked
            accessibleName: "Show HUD background art"
        }
        FieldHint { text: "The decorative wash behind the console. Off leaves the solid HUD fill and hue tint." }
        FieldLabel { text: "OPACITY" }
        HudSlider {
            Layout.preferredWidth: iface.controlWidth
            from: 0
            to: 1
            stepSize: 0.01
            enabled: Theme.hudBackground
            value: Theme.hudBackgroundOpacity
            onMoved: Theme.hudBackgroundOpacity = value
            markerPosition: 0.42
            valueText: Math.round(Theme.hudBackgroundOpacity * 100) + "%"
            accessibleName: "HUD background opacity"
            tooltip: "How strong the background art is on Control. Other pages stay dimmer. The tick is the stock look."
        }
        FieldHint { text: "Stock is 42% on Control. Calendar, sessions, media, and settings keep a dimmer wash so lists stay readable." }
    }

    SettingGroup {
        title: "THEME"
        trailing: [
            HudChip {
                label: iface.themeStatus
                tone: Theme.themeEdited ? Theme.warning : Theme.accent
                dim: !Theme.themeEdited && Theme.isBuiltinId(Theme.activeThemeId)
                anchors.verticalCenter: parent.verticalCenter
            },
            HudChip {
                label: iface.exampleSlot ? "EXAMPLE" : (iface.savedSlot ? "SAVED" : "BUILT-IN")
                tone: iface.exampleSlot || iface.savedSlot ? Theme.success : Theme.textSecondary
                dim: !iface.exampleSlot && !iface.savedSlot
                anchors.verticalCenter: parent.verticalCenter
            }
        ]
        FieldLabel { text: "PRESETS" }
        Flow {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            Layout.minimumWidth: Theme.px(240)
            spacing: Theme.px(6)
            Repeater {
                model: Theme.listedThemes
                delegate: ThemePresetChip {
                    required property var modelData
                    themeEntry: modelData
                    selected: Theme.activeThemeId === modelData.id
                    onClicked: iface.applyListedTheme(modelData.id)
                }
            }
            HudButton {
                text: iface.naming ? "CANCEL" : "SAVE AS"
                implicitHeight: Theme.px(40)
                enabled: iface.naming || Theme.savedThemeCount < Theme.maxSavedThemes
                accessibleDescription: iface.naming ? "Cancel saving a new theme" : "Save the current palette as a new theme"
                onClicked: iface.naming ? iface.naming = false : iface.startSaveAs()
            }
        }
        FieldLabel {
            visible: iface.naming || iface.renameable
            text: iface.naming ? "SAVE AS" : "NAME"
        }
        HudField {
            id: themeNameField
            visible: iface.naming || iface.renameable
            Layout.preferredWidth: iface.controlWidth
            enabled: iface.naming || iface.renameable
            placeholderText: iface.naming ? "Theme name" : "Theme name"
            accessibleName: iface.naming ? "New theme name" : "Theme name"
            maximumLength: 40
            onEditingFinished: {
                if (iface.naming)
                    return
                if (iface.renameable)
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
            visible: iface.naming || iface.renameable
            text: iface.naming
                ? "Name this look, then confirm. " + Theme.savedThemeCount + "/" + Theme.maxSavedThemes + " saved."
                : "Rename this theme."
        }
        FieldLabel {
            visible: iface.naming || (Theme.themeEdited && !!Theme.activeTheme) || iface.savedSlot || iface.builtinDefault
            text: "ACTIONS"
        }
        RowLayout {
            visible: iface.naming || (Theme.themeEdited && !!Theme.activeTheme) || iface.savedSlot || iface.builtinDefault
            Layout.fillWidth: true
            Layout.minimumWidth: Theme.px(240)
            spacing: Theme.px(6)
            HudButton {
                text: "CONFIRM"
                implicitHeight: Theme.px(28)
                visible: iface.naming
                enabled: themeNameField.text.trim().length > 0
                accessibleDescription: "Save the current palette under this name"
                onClicked: iface.confirmSaveAs()
            }
            HudButton {
                text: "REVERT"
                implicitHeight: Theme.px(28)
                visible: Theme.themeEdited && !!Theme.activeTheme && !iface.naming
                        && (!Theme.isBuiltinId(Theme.activeThemeId) || Theme.hasSavedCopy(Theme.activeThemeId))
                accessibleDescription: "Reload the selected theme and discard edits"
                onClicked: {
                    Theme.applyTheme(Theme.activeThemeId)
                    iface.naming = false
                }
            }
            HudButton {
                objectName: "themeDefaultButton"
                text: "DEFAULT"
                implicitHeight: Theme.px(28)
                visible: iface.builtinDefault && !iface.naming
                accessibleDescription: "Restore this theme to its shipped colours"
                onClicked: {
                    Theme.revertBuiltinTheme(Theme.activeThemeId)
                    iface.naming = false
                }
            }
            HudButton {
                objectName: "themeUpdateButton"
                text: "UPDATE"
                implicitHeight: Theme.px(28)
                visible: Theme.themeEdited && !!Theme.activeTheme && !iface.naming
                accessibleDescription: "Store the current palette on the selected theme"
                onClicked: Theme.updateTheme(Theme.activeThemeId)
            }
            HudButton {
                text: "DELETE"
                implicitHeight: Theme.px(28)
                visible: iface.savedSlot && !iface.naming
                accessibleDescription: "Delete the selected theme"
                onClicked: Theme.deleteTheme(Theme.activeThemeId)
            }
            Item { Layout.fillWidth: true }
        }
        FieldHint {
            visible: iface.naming || Theme.themeEdited || iface.savedSlot || iface.builtinDefault
            text: iface.naming
                ? "Confirm writes a new saved look. Cancel drops the name field."
                : Theme.themeEdited && iface.builtinDefault && Theme.hasSavedCopy(Theme.activeThemeId)
                    ? "Edits are live. Revert reloads your saved colours. Update stores this look. Default restores the shipped theme."
                    : Theme.themeEdited && Theme.isBuiltinId(Theme.activeThemeId)
                        ? "Edits are live. Default restores the shipped colours. Update stores this look on the theme."
                        : Theme.themeEdited
                            ? "Edits are live. Revert reloads this look. Update stores it on the selected theme."
                            : iface.builtinDefault
                                ? "Default restores this theme's shipped colours."
                                : iface.exampleSlot
                                    ? "Delete removes this example theme."
                                    : "Delete removes this saved look."
        }
        ThemePreview {
            Layout.columnSpan: 3
            Layout.fillWidth: true
            highlightRole: iface.tintRole
            onRolePicked: function (key) { iface.tintRole = key }
        }
    }

    SettingGroup {
        title: "COLOURS"
        trailing: [
            HudChip {
                label: iface.tintRoleName
                tone: Theme.accent
                anchors.verticalCenter: parent.verticalCenter
            },
            HudChip {
                label: iface.tintFixed ? "FIXED" : (iface.tintLinked ? "FOLLOWS" : (Theme.roleCustom(iface.tintRole) ? "UNLOCKED" : "STOCK"))
                tone: iface.tintFixed ? Theme.textSecondary : (iface.tintLinked ? Theme.accent : (Theme.roleCustom(iface.tintRole) ? Theme.warning : Theme.textSecondary))
                dim: iface.tintFixed || (!iface.tintLinked && !Theme.roleCustom(iface.tintRole))
                anchors.verticalCenter: parent.verticalCenter
            }
        ]
        GridLayout {
            Layout.columnSpan: 3
            Layout.fillWidth: true
            columns: iface.colourSplit ? 2 : 1
            columnSpacing: Theme.s4
            rowSpacing: Theme.s3

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                Layout.minimumWidth: Theme.px(260)
                spacing: Theme.s2
                Repeater {
                    model: Theme.swatchGroups
                    delegate: ColumnLayout {
                        id: groupBlock
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.s1
                        Text {
                            text: groupBlock.modelData.title
                            color: Theme.muted
                            font.pixelSize: Theme.fontXs
                            font.bold: true
                            font.letterSpacing: Theme.tracking2
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: Theme.px(6)
                            Repeater {
                                model: groupBlock.modelData.keys
                                delegate: PaletteSwatch {
                                    required property var modelData
                                    width: Theme.px(76)
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
                FieldHint {
                    text: iface.tintFixed
                        ? iface.tintRoleName + " — " + iface.tintRoleHint + " Click the preview or a swatch to inspect it. Status colours stay fixed."
                        : iface.tintRoleHint
                            ? iface.tintRoleName + " — " + iface.tintRoleHint + " Click the preview or a swatch. WINDOW tints unedited colours. Double-click restores one colour."
                            : "Click a swatch or the preview to edit that colour. WINDOW tints unedited colours. Double-click restores one colour."
                }
            }

            GridLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: iface.colourSplit ? Theme.px(420) : -1
                Layout.minimumWidth: Theme.px(240)
                Layout.alignment: Qt.AlignTop
                enabled: !iface.tintFixed
                columns: 2
                columnSpacing: Theme.s3
                rowSpacing: Theme.s2

                FieldLabel { text: "HEX" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(6)
                    HudField {
                        id: hexField
                        Layout.preferredWidth: Theme.px(120)
                        Layout.maximumWidth: Theme.px(140)
                        font.family: Theme.fontMono
                        maximumLength: 7
                        accessibleName: iface.tintRoleName + " hex colour"
                        tooltip: "Paste #RRGGBB or pick a colour. Hue, saturation and lightness are solved to land on it."
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
                            colourPick.roleName = iface.tintRoleName
                            colourPick.selectedColor = Theme.colorFor(iface.tintRole)
                            colourPick.open()
                        }
                    }
                    HudButton {
                        text: "\uEF3C"
                        iconButton: true
                        font.family: Theme.fontIcon
                        font.pixelSize: Theme.fontPx(15)
                        implicitWidth: Theme.controlHeight
                        implicitHeight: Theme.controlHeight
                        tooltip: "Eyedropper. Sample a pixel on screen, then APPLY."
                        accessibleDescription: "Eyedropper. Sample a colour from the screen."
                        onClicked: {
                            colourPick.roleName = iface.tintRoleName
                            colourPick.selectedColor = Theme.colorFor(iface.tintRole)
                            colourPick.open()
                            Qt.callLater(colourPick.beginDrop)
                        }
                    }
                    Item { Layout.fillWidth: true }
                }
                FieldLabel { text: "HUE" }
                HudSlider {
                    id: hueSlider
                    Layout.fillWidth: true
                    Layout.minimumWidth: Theme.px(160)
                    from: 0
                    to: 1
                    stepSize: 0.001
                    onMoved: Theme.setRole(iface.tintRole, value, iface.tintBrightness)
                    markerPosition: iface.seedRole ? Theme.defaultHue : Theme.stockHue(iface.tintRole)
                    valueText: Math.round(iface.tintHue * 360) + "°"
                    accessibleName: iface.tintRoleName + " hue"
                    tooltip: iface.seedRole
                        ? "Seed hue. Unedited swatches, washes and the title bar follow this. The tick is cyan."
                        : "Hue of the selected swatch. The tick is its stock position. Locked swatches stay put when WINDOW moves."
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
                FieldLabel { text: "SAT" }
                HudSlider {
                    id: satSlider
                    Layout.fillWidth: true
                    Layout.minimumWidth: Theme.px(160)
                    from: 0
                    to: 1
                    stepSize: 0.01
                    onMoved: Theme.setRoleSat(iface.tintRole, value)
                    markerPosition: Theme.stockSat(iface.tintRole)
                    valueText: Math.round(iface.tintSat * 100) + "%"
                    accessibleName: iface.tintRoleName + " saturation"
                    tooltip: "How strong the selected colour is. 0% is grey at the same lightness; 100% is full tint."
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
                FieldLabel { text: iface.seedRole ? "LIFT" : "LIGHT" }
                HudSlider {
                    id: lightSlider
                    Layout.fillWidth: true
                    Layout.minimumWidth: Theme.px(160)
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
                    tooltip: iface.seedRole
                        ? "Seed lift for unedited swatches. 0 is stock; negative deepens the HUD, positive raises it."
                        : "Lightness of the selected swatch. The tick is stock."
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
                FieldLabel { text: "MATCH" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.px(6)
                    HudCombo {
                        id: matchCombo
                        Layout.fillWidth: true
                        Layout.minimumWidth: Theme.px(100)
                        model: iface.matchNames
                        accessibleName: "Colour to match from"
                        tooltip: "Copy hue or the full colour from another swatch onto the selected one."
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
                    HudButton {
                        text: "HUE"
                        implicitHeight: Theme.controlHeight
                        enabled: iface.matchSourceKey !== iface.tintRole && iface.matchSourceKey !== ""
                        accessibleDescription: "Copy hue from the match source onto the selected swatch"
                        onClicked: Theme.matchHue(iface.tintRole, iface.matchSourceKey)
                    }
                    HudButton {
                        text: "COLOUR"
                        implicitHeight: Theme.controlHeight
                        enabled: iface.matchSourceKey !== iface.tintRole && iface.matchSourceKey !== ""
                        accessibleDescription: "Copy the full colour from the match source onto the selected swatch"
                        onClicked: Theme.matchRole(iface.tintRole, iface.matchSourceKey)
                    }
                }
                FieldLabel {
                    visible: iface.tintParentKey !== "" || Theme.roleCustom(iface.tintRole)
                    text: "LINK"
                }
                RowLayout {
                    visible: iface.tintParentKey !== "" || Theme.roleCustom(iface.tintRole)
                    Layout.fillWidth: true
                    spacing: Theme.px(6)
                    HudButton {
                        text: "FOLLOW PARENT"
                        implicitHeight: Theme.px(28)
                        visible: iface.tintParentKey !== ""
                        enabled: !iface.tintLinked
                        accessibleDescription: "Let this colour follow " + Theme.roleName(iface.tintParentKey) + " again"
                        onClicked: Theme.clearRole(iface.tintRole)
                    }
                    HudButton {
                        text: "RESET SWATCH"
                        implicitHeight: Theme.px(28)
                        visible: iface.tintParentKey === ""
                        enabled: Theme.roleCustom(iface.tintRole)
                        accessibleDescription: "Restore the selected colour to stock"
                        onClicked: Theme.clearRole(iface.tintRole)
                    }
                    Text {
                        visible: iface.tintParentKey !== ""
                        Layout.fillWidth: true
                        text: iface.tintLinked
                            ? iface.tintRoleName + " follows " + Theme.roleName(iface.tintParentKey) + "."
                            : iface.tintRoleName + " is unlocked from " + Theme.roleName(iface.tintParentKey) + "."
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSm
                        elide: Text.ElideRight
                    }
                }
                FieldLabel { text: "RELATED"; visible: iface.relatedKeys.length > 0 }
                RowLayout {
                    visible: iface.relatedKeys.length > 0
                    Layout.fillWidth: true
                    spacing: Theme.px(6)
                    Repeater {
                        model: iface.relatedKeys
                        delegate: PaletteSwatch {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredWidth: Theme.px(40)
                            roleKey: modelData
                            roleName: Theme.roleName(modelData)
                            selected: iface.tintRole === modelData
                            onClicked: iface.tintRole = modelData
                            onResetRequested: Theme.clearRole(modelData)
                        }
                    }
                }
            }
        }
    }

    ColorPickDialog {
        id: colourPick
        screenPicker: backend.screenColor
        onAccepted: Theme.applyColor(iface.tintRole, selectedColor)
    }
}
