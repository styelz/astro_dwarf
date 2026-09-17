pragma Singleton
import QtQuick
import QtCore

// Single source of truth for the HUD look. Named palette roles can be tinted
// independently; relatives (fills, outlines, glows) follow their parent swatch.
// WINDOW (windowBase) is the seed (Theme.hue / brightness): unedited swatches,
// Theme.hsl() one-offs, and the background wash follow it. Other swatches store overrides.
// Saturation and lightness start from per-token recipes; a role can lock them.
// Named themes (built-in + saved) snapshot the seed and every override.
QtObject {
    id: theme

    readonly property real defaultHue: 0.521
    readonly property int maxSavedThemes: 32

    readonly property Settings store: Settings {
        id: appearanceStore
        category: "appearance"
        property real hue: 0.521
        property real brightness: 0
        property string paletteJson: ""
        property string savedThemesJson: "[]"
        property string activeThemeId: "stock"
        property bool previewChromeHintSeen: false
        property bool enhanceImages: true
        property bool deepCleanImages: false
        property real enhanceDenoise: 1
        property real enhanceSkyCrush: 1
        property bool hudBackground: true
        property real hudBackgroundOpacity: 0.42
    }
    property alias hue: appearanceStore.hue
    // -1 … 1; 0 is the stock look. Negative gives deep, saturated tints; positive lifts them.
    property alias brightness: appearanceStore.brightness
    property alias paletteJson: appearanceStore.paletteJson
    property alias savedThemesJson: appearanceStore.savedThemesJson
    property alias activeThemeId: appearanceStore.activeThemeId
    property alias previewChromeHintSeen: appearanceStore.previewChromeHintSeen
    property alias enhanceImages: appearanceStore.enhanceImages
    property alias deepCleanImages: appearanceStore.deepCleanImages
    property alias enhanceDenoise: appearanceStore.enhanceDenoise
    property alias enhanceSkyCrush: appearanceStore.enhanceSkyCrush
    property alias hudBackground: appearanceStore.hudBackground
    property alias hudBackgroundOpacity: appearanceStore.hudBackgroundOpacity

    readonly property var swatchGroups: [
        { title: "SEED", keys: [
            { key: "windowBase", name: "WINDOW", hint: "Page behind every panel. Unedited colours and the title bar follow this." }
        ]},
        { title: "SURFACES", keys: [
            { key: "surface", name: "CARD", hint: "Solid cards: dialogs, media tiles, idle command pads." },
            { key: "surfaceHigh", name: "BUTTON", hint: "Raised controls: default buttons, hover fills, and menu bars." },
            { key: "panelFill", name: "PANEL", hint: "Translucent wash on setting groups, calendar cells, and Control overlays." },
            { key: "inputBg", name: "FIELD", hint: "Text fields, dropdowns, checkboxes, and inactive tab pills." },
            { key: "popupBg", name: "MENU", hint: "Popup menus, combo lists, and tooltips." },
            { key: "disabledBg", name: "DISABLED", hint: "Fill of greyed-out buttons and fields." },
            { key: "scrim", name: "DIMMER", hint: "Dark overlay that sits over the page behind a dialog." }
        ]},
        { title: "LINES", keys: [
            { key: "outline", name: "BORDER", hint: "Default outlines around panels and controls." },
            { key: "outlineSoft", name: "SOFT LINE", hint: "Quieter edges on media tiles and inactive pills." },
            { key: "outlineStrong", name: "HARD LINE", hint: "Stronger edges on hover, focus, and pad ticks." },
            { key: "disabledOutline", name: "OFF LINE", hint: "Outline of greyed-out controls." }
        ]},
        { title: "TYPE", keys: [
            { key: "textPrimary", name: "TEXT", hint: "Primary labels and typed values." },
            { key: "textSecondary", name: "DIM TEXT", hint: "Secondary labels, column headers, and helper lines." },
            { key: "muted", name: "HINT", hint: "The quietest type: empty states and captions." }
        ]},
        { title: "SIGNAL", keys: [
            { key: "accent", name: "ACCENT", hint: "Highlights: selected items, titles, focus rings, live status." },
            { key: "accentSoft", name: "ACCENT HI", hint: "Brighter accent on the joystick, primed marks, and light ticks." },
            { key: "glowAccent", name: "GLOW", hint: "Soft halo behind accent elements." },
            { key: "fillActive", name: "LIVE FILL", hint: "Fill of a live or selected action button." },
            { key: "fillChecked", name: "CHECKED", hint: "Fill of a ticked box, selected menu row, or on toggle." }
        ]}
    ]

    readonly property var swatches: {
        const out = []
        const groups = theme.swatchGroups
        for (let g = 0; g < groups.length; g++) {
            const keys = groups[g].keys
            for (let i = 0; i < keys.length; i++)
                out.push(keys[i])
        }
        return out
    }

    readonly property var builtinThemes: [
        { id: "stock", name: "Stock cyan", hue: 0.521, brightness: 0, palette: ({}) },
        { id: "ice", name: "Ice", hue: 0.55, brightness: 0.14, palette: ({}) },
        { id: "violet", name: "Violet", hue: 0.76, brightness: 0.02, palette: ({}) },
        { id: "amber", name: "Amber", hue: 0.08, brightness: -0.08, palette: ({}) },
        { id: "forest", name: "Forest", hue: 0.36, brightness: -0.12, palette: ({}) },
        { id: "crimson", name: "Crimson", hue: 0.985, brightness: -0.1, palette: ({}) }
    ]

    // offset/sat/light/weight reproduce the original cyan HUD at hue 0.521, brightness 0.
    // `from` names the editable swatch a relative token follows when that swatch is custom.
    readonly property var recipes: ({
        windowBase: { offset: 0.096, sat: 0.500, light: 0.039, alpha: 1, weight: 0.10, from: "" },
        surface: { offset: 0.066, sat: 0.488, light: 0.084, alpha: 1, weight: 0.20, from: "" },
        surfaceHigh: { offset: 0.075, sat: 0.478, light: 0.135, alpha: 1, weight: 0.25, from: "" },
        outline: { offset: 0.039, sat: 0.535, light: 0.253, alpha: 1, weight: 0.60, from: "" },
        outlineSoft: { offset: 0.047, sat: 0.509, light: 0.208, alpha: 1, weight: 0.60, from: "outline" },
        outlineStrong: { offset: 0.058, sat: 0.402, light: 0.341, alpha: 1, weight: 0.60, from: "outline" },
        textPrimary: { offset: 0.037, sat: 1.000, light: 0.955, alpha: 1, weight: 1.00, from: "" },
        textSecondary: { offset: 0.037, sat: 0.286, light: 0.610, alpha: 1, weight: 0.60, from: "" },
        muted: { offset: 0.046, sat: 0.255, light: 0.400, alpha: 1, weight: 0.50, from: "textSecondary" },
        accent: { offset: 0.000, sat: 1.000, light: 0.651, alpha: 1, weight: 1.00, from: "" },
        accentSoft: { offset: 0.000, sat: 1.000, light: 0.955, alpha: 1, weight: 1.00, from: "accent" },
        glowAccent: { offset: 0.000, sat: 1.000, light: 0.651, alpha: 0.2, weight: 1.00, from: "accent" },
        inputBg: { offset: 0.075, sat: 0.565, light: 0.090, alpha: 1, weight: 0.20, from: "surfaceHigh" },
        popupBg: { offset: 0.079, sat: 0.714, light: 0.027, alpha: 1, weight: 0.10, from: "windowBase" },
        disabledBg: { offset: 0.085, sat: 0.440, light: 0.049, alpha: 1, weight: 0.10, from: "windowBase" },
        disabledOutline: { offset: 0.055, sat: 0.455, light: 0.151, alpha: 1, weight: 0.40, from: "outline" },
        fillActive: { offset: 0.019, sat: 0.674, light: 0.169, alpha: 1, weight: 0.50, from: "accent" },
        fillChecked: { offset: 0.036, sat: 0.640, light: 0.196, alpha: 1, weight: 0.50, from: "accent" },
        panelFill: { offset: 0.079, sat: 0.517, light: 0.057, alpha: 0.702, weight: 0.15, from: "surface" },
        scrim: { offset: 0.095, sat: 0.600, light: 0.020, alpha: 0.80, weight: 0.10, from: "windowBase" }
    })

    readonly property var parsedOverrides: {
        try {
            const raw = JSON.parse(theme.paletteJson || "{}")
            if (raw && typeof raw === "object" && !Array.isArray(raw))
                return raw
        } catch (exc) {
        }
        return ({})
    }

    readonly property var parsedSavedThemes: {
        try {
            const raw = JSON.parse(theme.savedThemesJson || "[]")
            if (!Array.isArray(raw))
                return []
            const out = []
            for (let i = 0; i < raw.length; i++) {
                const item = raw[i]
                if (!item || typeof item !== "object" || Array.isArray(item))
                    continue
                if (!item.id || !item.name)
                    continue
                out.push(item)
            }
            return out
        } catch (exc) {
        }
        return []
    }

    readonly property var listedThemes: {
        void theme.savedThemesJson
        return theme.listThemes()
    }

    readonly property int savedThemeCount: theme.parsedSavedThemes.length

    readonly property var activeTheme: {
        void theme.savedThemesJson
        return theme.themeById(theme.activeThemeId)
    }

    readonly property bool themeEdited: {
        void theme.paletteJson
        void theme.hue
        void theme.brightness
        void theme.savedThemesJson
        void theme.activeThemeId
        const current = theme.activeTheme
        if (!current)
            return theme.paletteCustom
        return theme.fingerprint() !== theme.fingerprintOf(current)
    }

    readonly property bool paletteCustom: {
        if (Math.abs(theme.hue - theme.defaultHue) > 0.002 || Math.abs(theme.brightness) > 0.002)
            return true
        const ov = theme.parsedOverrides
        for (const key in ov) {
            if (!ov[key] || typeof ov[key] !== "object")
                continue
            if (ov[key].hue !== undefined || ov[key].brightness !== undefined
                    || ov[key].sat !== undefined || ov[key].light !== undefined)
                return true
        }
        return false
    }

    // How far the seed hue is from stock (0 … 0.5). The original palette leans its
    // surfaces and outlines ~35° toward blue; the same lean turns a red accent orange,
    // so the offsets shrink as the hue moves away from cyan. At the default hue
    // nothing changes. WINDOW edits the seed; other swatches keep their own overrides.
    readonly property real hueDistance: {
        const d = Math.abs(theme.hue - theme.defaultHue)
        return Math.min(d, 1 - d)
    }
    readonly property real spread: 1 - (theme.hueDistance / 0.5) * 0.7
    readonly property real lift: theme.brightness * 0.25

    function wrapHue(value) {
        let h = Number(value) % 1
        if (h < 0)
            h += 1
        return h
    }

    function clamp(value, lo, hi) {
        return Math.max(lo, Math.min(hi, Number(value)))
    }

    function recipeOf(key) {
        return theme.recipes[key] || ({ offset: 0, sat: 1, light: 0.5, alpha: 1, weight: 0, from: "" })
    }

    function roleOverride(key) {
        const ov = theme.parsedOverrides[key]
        return ov && typeof ov === "object" ? ov : null
    }

    function roleName(key) {
        const list = theme.swatches
        for (let i = 0; i < list.length; i++) {
            if (list[i].key === key)
                return list[i].name
        }
        return String(key || "").toUpperCase()
    }

    function roleHint(key) {
        const list = theme.swatches
        for (let i = 0; i < list.length; i++) {
            if (list[i].key === key)
                return list[i].hint || ""
        }
        return ""
    }

    function parentOf(key) {
        return theme.recipeOf(key).from || ""
    }

    function followersOf(key) {
        const rec = theme.recipes
        const out = []
        for (const k in rec) {
            if (rec[k] && rec[k].from === key)
                out.push(k)
        }
        return out
    }

    function roleCustom(key) {
        if (key === "windowBase") {
            if (Math.abs(theme.hue - theme.defaultHue) > 0.002 || Math.abs(theme.brightness) > 0.002)
                return true
        }
        const ov = theme.roleOverride(key)
        return !!(ov && (ov.hue !== undefined || ov.brightness !== undefined
                         || ov.sat !== undefined || ov.light !== undefined))
    }

    function roleLinked(key) {
        const parent = theme.parentOf(key)
        if (!parent)
            return false
        return !theme.roleOverride(key)
    }

    function copyLeaf(entry) {
        if (!entry || typeof entry !== "object")
            return null
        const e = {}
        if (typeof entry.hue === "number")
            e.hue = entry.hue
        if (typeof entry.brightness === "number")
            e.brightness = entry.brightness
        if (typeof entry.sat === "number")
            e.sat = entry.sat
        if (typeof entry.light === "number")
            e.light = entry.light
        return Object.keys(e).length ? e : null
    }

    function overridesJson(skipKey) {
        const ov = {}
        const src = theme.parsedOverrides
        for (const k in src) {
            if (k === skipKey)
                continue
            const e = theme.copyLeaf(src[k])
            if (e)
                ov[k] = e
        }
        return Object.keys(ov).length ? JSON.stringify(ov) : ""
    }

    function snapshotSpread(hue) {
        const d = Math.abs(theme.wrapHue(hue) - theme.defaultHue)
        return 1 - (Math.min(d, 1 - d) / 0.5) * 0.7
    }

    function paramsFromSnapshot(key, hue, brightness, overrides) {
        const recipe = theme.recipeOf(key)
        const ov = overrides && typeof overrides === "object" && !Array.isArray(overrides) ? overrides : {}
        const own = ov[key] && typeof ov[key] === "object" ? ov[key] : null
        const parentKey = recipe.from || ""
        const parentOv = parentKey && ov[parentKey] && typeof ov[parentKey] === "object" ? ov[parentKey] : null
        const hueSrc = own && (typeof own.hue === "number" || typeof own.brightness === "number")
            ? own
            : (parentOv && (typeof parentOv.hue === "number" || typeof parentOv.brightness === "number") ? parentOv : null)
        const seedH = theme.wrapHue(hue === undefined || hue === null ? theme.defaultHue : hue)
        const seedB = brightness === undefined || brightness === null ? 0 : brightness
        const spread = theme.snapshotSpread(seedH)
        let h
        let b
        if (hueSrc && typeof hueSrc.hue === "number")
            h = theme.wrapHue(hueSrc.hue)
        else
            h = theme.wrapHue(seedH + recipe.offset * spread)
        if (hueSrc && typeof hueSrc.brightness === "number")
            b = hueSrc.brightness
        else
            b = seedB
        let sat = recipe.sat
        if (own && typeof own.sat === "number")
            sat = theme.clamp(own.sat, 0, 1)
        let light = recipe.light
        if (own && typeof own.light === "number")
            light = theme.clamp(own.light, 0.02, 0.97)
        return { h: h, sat: sat, light: light, alpha: recipe.alpha, weight: recipe.weight, brightness: b }
    }

    function paramsFor(key) {
        return theme.paramsFromSnapshot(key, theme.hue, theme.brightness, theme.parsedOverrides)
    }

    function previewColor(entry, key) {
        if (!entry)
            return theme.colorFor(key)
        const p = theme.paramsFromSnapshot(key, entry.hue, entry.brightness, entry.palette)
        return theme.bake(p.h, p.sat, p.light, p.alpha, p.weight, p.brightness)
    }

    function restoreSnapshot(id, hue, brightness, paletteJson) {
        theme.hue = theme.roundHue(hue === undefined || hue === null ? theme.defaultHue : hue)
        theme.brightness = theme.roundBright(brightness === undefined || brightness === null ? 0 : brightness)
        theme.paletteJson = paletteJson === undefined || paletteJson === null ? "" : String(paletteJson)
        theme.activeThemeId = id || "stock"
    }

    function effectiveHue(key) {
        return theme.paramsFor(key).h
    }

    function effectiveSat(key) {
        return theme.paramsFor(key).sat
    }

    function effectiveBrightness(key) {
        return theme.paramsFor(key).brightness
    }

    function effectiveLight(key) {
        const p = theme.paramsFor(key)
        return theme.bakedLight(p.light, p.weight, p.brightness)
    }

    function stockHue(key) {
        return theme.wrapHue(theme.defaultHue + theme.recipeOf(key).offset)
    }

    function stockSat(key) {
        return theme.recipeOf(key).sat
    }

    function stockLight(key) {
        const recipe = theme.recipeOf(key)
        return theme.bakedLight(recipe.light, recipe.weight, 0)
    }

    function bakedLight(light, weight, brightness) {
        const w = weight === undefined ? 0 : weight
        const b = brightness === undefined ? 0 : brightness
        let l = light
        if (b >= 0)
            l = light + b * 0.25 * w
        else
            l = light * (1 + b * 0.75 * w)
        return Math.min(0.97, Math.max(0.02, l))
    }

    function brightnessForLight(light, weight, target) {
        const w = weight || 0
        const t = theme.clamp(target, 0.02, 0.97)
        if (w <= 0.001)
            return 0
        if (t >= light)
            return theme.clamp((t - light) / (0.25 * w), -1, 1)
        if (light <= 0.001)
            return -1
        return theme.clamp((t / light - 1) / (0.75 * w), -1, 1)
    }

    function roundHue(value) {
        return Math.round(theme.wrapHue(value) * 1000) / 1000
    }

    function roundBright(value) {
        return Math.round(theme.clamp(value, -1, 1) * 100) / 100
    }

    function roundUnit(value) {
        return Math.round(theme.clamp(value, 0, 1) * 1000) / 1000
    }

    function resolveSat(key, sat, prev) {
        const recipe = theme.recipeOf(key)
        if (sat === undefined)
            return prev && typeof prev.sat === "number" ? prev.sat : undefined
        if (sat === null)
            return undefined
        const s = theme.roundUnit(sat)
        return Math.abs(s - recipe.sat) > 0.002 ? s : undefined
    }

    function resolveLight(key, light, prev) {
        if (light === undefined)
            return prev && typeof prev.light === "number" ? prev.light : undefined
        if (light === null)
            return undefined
        return Math.round(theme.clamp(light, 0.02, 0.97) * 1000) / 1000
    }

    function writeWindowExtras(satOut, lightOut) {
        const ov = JSON.parse(theme.overridesJson("windowBase") || "{}")
        if (satOut === undefined && lightOut === undefined) {
            theme.paletteJson = Object.keys(ov).length ? JSON.stringify(ov) : ""
            return
        }
        const extra = {}
        if (satOut !== undefined)
            extra.sat = satOut
        if (lightOut !== undefined)
            extra.light = lightOut
        ov.windowBase = extra
        theme.paletteJson = JSON.stringify(ov)
    }

    function setRole(key, hue, brightness, sat, light) {
        if (!theme.recipes[key])
            return
        const h = theme.roundHue(hue)
        const b = theme.roundBright(brightness)
        const prev = theme.roleOverride(key)
        const satOut = theme.resolveSat(key, sat, prev)
        const lightOut = theme.resolveLight(key, light, prev)
        if (key === "windowBase") {
            // BASE is the palette seed. The slider writes Theme.hue / brightness
            // so Theme.hsl() one-offs, the background wash, and unedited swatches follow.
            theme.hue = h
            theme.brightness = b
            theme.writeWindowExtras(satOut, lightOut)
            return
        }
        const ov = JSON.parse(theme.overridesJson("") || "{}")
        const entry = { hue: h, brightness: b }
        if (satOut !== undefined)
            entry.sat = satOut
        if (lightOut !== undefined)
            entry.light = lightOut
        ov[key] = entry
        theme.paletteJson = JSON.stringify(ov)
    }

    function setRoleSat(key, sat) {
        if (key === "windowBase") {
            theme.setRole(key, theme.hue, theme.brightness, sat)
            return
        }
        const p = theme.paramsFor(key)
        theme.setRole(key, p.h, p.brightness, sat)
    }

    function setRoleLight(key, targetLight) {
        const p = theme.paramsFor(key)
        theme.applyHsl(key, p.h, p.sat, targetLight)
    }

    function clearRole(key) {
        if (key === "windowBase") {
            theme.hue = theme.defaultHue
            theme.brightness = 0
            if (theme.roleOverride("windowBase"))
                theme.paletteJson = theme.overridesJson("windowBase")
            return
        }
        theme.paletteJson = theme.overridesJson(key)
    }

    function resetPalette() {
        theme.paletteJson = ""
        theme.hue = theme.defaultHue
        theme.brightness = 0
        theme.activeThemeId = "stock"
    }

    function colorToHex(col) {
        if (col === undefined || col === null)
            return ""
        function hx(n) {
            const v = Math.round(theme.clamp(n, 0, 1) * 255)
            return v.toString(16).padStart(2, "0")
        }
        return ("#" + hx(col.r) + hx(col.g) + hx(col.b)).toUpperCase()
    }

    function parseHex(text) {
        const s = String(text || "").trim().replace(/^#/, "")
        if (!/^([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(s))
            return null
        let hex = s
        if (hex.length === 3)
            hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2]
        const n = parseInt(hex, 16)
        return Qt.rgba(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1)
    }

    function applyHex(key, text) {
        const col = theme.parseHex(text)
        if (!col)
            return false
        return theme.applyColor(key, col)
    }

    function applyColor(key, col) {
        if (col === undefined || col === null || !theme.recipes[key])
            return false
        let h = col.hslHue
        let s = col.hslSaturation
        const l = col.hslLightness
        if (!(h >= 0)) {
            h = theme.effectiveHue(key)
            s = 0
        }
        return theme.applyHsl(key, h, s, l)
    }

    function applyHsl(key, h, s, l) {
        if (!theme.recipes[key])
            return false
        const recipe = theme.recipeOf(key)
        const targetL = theme.clamp(l, 0.02, 0.97)
        let hueOut = h
        if (key === "windowBase") {
            // HEX/PICK target the painted BASE wash, which is seed + recipe offset.
            hueOut = theme.wrapHue(h - recipe.offset)
            theme.hue = theme.roundHue(hueOut)
            hueOut = theme.wrapHue(h - recipe.offset * theme.spread)
        }
        const b = theme.brightnessForLight(recipe.light, recipe.weight, targetL)
        const reached = theme.bakedLight(recipe.light, recipe.weight, b)
        if (Math.abs(reached - targetL) > 0.02)
            theme.setRole(key, hueOut, 0, s, targetL)
        else
            theme.setRole(key, hueOut, b, s, null)
        return true
    }

    function matchRole(targetKey, sourceKey) {
        if (!theme.recipes[targetKey] || !theme.recipes[sourceKey])
            return false
        return theme.applyColor(targetKey, theme.colorFor(sourceKey))
    }

    function matchHue(targetKey, sourceKey) {
        if (!theme.recipes[targetKey] || !theme.recipes[sourceKey])
            return false
        const src = theme.paramsFor(sourceKey)
        const dst = theme.paramsFor(targetKey)
        theme.setRole(targetKey, src.h, dst.brightness)
        return true
    }

    function snapshotPalette() {
        const ov = {}
        const src = theme.parsedOverrides
        const keys = Object.keys(src).sort()
        for (let i = 0; i < keys.length; i++) {
            const e = theme.copyLeaf(src[keys[i]])
            if (e)
                ov[keys[i]] = e
        }
        return ov
    }

    function snapshot() {
        return { hue: theme.roundHue(theme.hue), brightness: theme.roundBright(theme.brightness), palette: theme.snapshotPalette() }
    }

    function fingerprintOf(entry) {
        if (!entry)
            return ""
        const hue = theme.roundHue(entry.hue === undefined ? theme.defaultHue : entry.hue)
        const brightness = theme.roundBright(entry.brightness === undefined ? 0 : entry.brightness)
        const pal = {}
        const src = entry.palette && typeof entry.palette === "object" ? entry.palette : {}
        const keys = Object.keys(src).sort()
        for (let i = 0; i < keys.length; i++) {
            const e = theme.copyLeaf(src[keys[i]])
            if (!e)
                continue
            if (typeof e.hue === "number")
                e.hue = theme.roundHue(e.hue)
            if (typeof e.brightness === "number")
                e.brightness = theme.roundBright(e.brightness)
            if (typeof e.sat === "number")
                e.sat = theme.roundUnit(e.sat)
            if (typeof e.light === "number")
                e.light = Math.round(theme.clamp(e.light, 0.02, 0.97) * 1000) / 1000
            pal[keys[i]] = e
        }
        return JSON.stringify({ hue: hue, brightness: brightness, palette: pal })
    }

    function fingerprint() {
        return theme.fingerprintOf(theme.snapshot())
    }

    function listThemes() {
        const out = []
        const builtins = theme.builtinThemes
        for (let i = 0; i < builtins.length; i++)
            out.push(builtins[i])
        const saved = theme.parsedSavedThemes
        for (let i = 0; i < saved.length; i++)
            out.push(saved[i])
        return out
    }

    function themeById(id) {
        const list = theme.listThemes()
        for (let i = 0; i < list.length; i++) {
            if (list[i].id === id)
                return list[i]
        }
        return null
    }

    function themeIndexOf(id) {
        const list = theme.listThemes()
        for (let i = 0; i < list.length; i++) {
            if (list[i].id === id)
                return i
        }
        return -1
    }

    function isBuiltinId(id) {
        const builtins = theme.builtinThemes
        for (let i = 0; i < builtins.length; i++) {
            if (builtins[i].id === id)
                return true
        }
        return false
    }

    function applyTheme(id) {
        const entry = theme.themeById(id)
        if (!entry)
            return false
        theme.hue = theme.roundHue(entry.hue === undefined ? theme.defaultHue : entry.hue)
        theme.brightness = theme.roundBright(entry.brightness === undefined ? 0 : entry.brightness)
        const pal = entry.palette && typeof entry.palette === "object" && !Array.isArray(entry.palette) ? entry.palette : {}
        const clean = {}
        for (const k in pal) {
            const e = theme.copyLeaf(pal[k])
            if (e)
                clean[k] = e
        }
        theme.paletteJson = Object.keys(clean).length ? JSON.stringify(clean) : ""
        theme.activeThemeId = entry.id
        return true
    }

    function newThemeId() {
        return "t" + Date.now().toString(36) + Math.floor(Math.random() * 1e6).toString(36)
    }

    function saveThemeAs(name) {
        const trimmed = String(name || "").trim().slice(0, 40)
        if (!trimmed)
            return ""
        const saved = theme.parsedSavedThemes.slice()
        if (saved.length >= theme.maxSavedThemes)
            return ""
        const id = theme.newThemeId()
        const snap = theme.snapshot()
        saved.push({ id: id, name: trimmed, hue: snap.hue, brightness: snap.brightness, palette: snap.palette })
        theme.savedThemesJson = JSON.stringify(saved)
        theme.activeThemeId = id
        return id
    }

    function updateTheme(id) {
        if (!id || theme.isBuiltinId(id))
            return false
        const saved = theme.parsedSavedThemes.slice()
        const snap = theme.snapshot()
        let found = false
        for (let i = 0; i < saved.length; i++) {
            if (saved[i].id !== id)
                continue
            saved[i] = { id: id, name: saved[i].name, hue: snap.hue, brightness: snap.brightness, palette: snap.palette }
            found = true
            break
        }
        if (!found)
            return false
        theme.savedThemesJson = JSON.stringify(saved)
        theme.activeThemeId = id
        return true
    }

    function renameTheme(id, name) {
        if (!id || theme.isBuiltinId(id))
            return false
        const trimmed = String(name || "").trim().slice(0, 40)
        if (!trimmed)
            return false
        const saved = theme.parsedSavedThemes.slice()
        let found = false
        for (let i = 0; i < saved.length; i++) {
            if (saved[i].id !== id)
                continue
            saved[i].name = trimmed
            found = true
            break
        }
        if (!found)
            return false
        theme.savedThemesJson = JSON.stringify(saved)
        return true
    }

    function deleteTheme(id) {
        if (!id || theme.isBuiltinId(id))
            return false
        const saved = theme.parsedSavedThemes.filter(item => item.id !== id)
        if (saved.length === theme.parsedSavedThemes.length)
            return false
        theme.savedThemesJson = JSON.stringify(saved)
        if (theme.activeThemeId === id)
            theme.activeThemeId = "stock"
        return true
    }

    // Older builds stored BASE as a leaf override, which left Theme.hsl() and
    // unedited swatches on the old seed. Fold that override back into the seed.
    Component.onCompleted: {
        if (!theme.themeById(theme.activeThemeId))
            theme.activeThemeId = "stock"
        const ov = theme.roleOverride("windowBase")
        if (!ov)
            return
        if (typeof ov.hue === "number")
            theme.hue = Math.round(theme.wrapHue(ov.hue - theme.recipeOf("windowBase").offset * theme.spread) * 1000) / 1000
        if (typeof ov.brightness === "number")
            theme.brightness = ov.brightness
        const sat = typeof ov.sat === "number" ? ov.sat : undefined
        const light = typeof ov.light === "number" ? ov.light : undefined
        const rest = JSON.parse(theme.overridesJson("windowBase") || "{}")
        if (sat !== undefined || light !== undefined) {
            const extra = {}
            if (sat !== undefined)
                extra.sat = sat
            if (light !== undefined)
                extra.light = light
            rest.windowBase = extra
        }
        theme.paletteJson = Object.keys(rest).length ? JSON.stringify(rest) : ""
    }

    // weight: how strongly the brightness slider moves this token (0 = fixed).
    // Positive brightness adds a flat lift so the glow side reads lighter. Negative
    // brightness scales lightness instead (an additive drop leaves near-white text
    // almost untouched). Saturation is never touched: dimming should darken the
    // colour, not grey it out.
    function bake(h, sat, light, alpha, weight, brightness) {
        const w = weight === undefined ? 0 : weight
        const b = brightness === undefined ? theme.brightness : brightness
        const l = theme.bakedLight(light, w, b)
        return Qt.hsla(theme.wrapHue(h), sat, l, alpha === undefined ? 1 : alpha)
    }

    function hsl(offset, sat, light, alpha, weight) {
        return theme.bake(theme.hue + offset * theme.spread, sat, light, alpha, weight, theme.brightness)
    }

    function colorFor(key) {
        const p = theme.paramsFor(key)
        return theme.bake(p.h, p.sat, p.light, p.alpha, p.weight, p.brightness)
    }

    readonly property color windowBase: theme.colorFor("windowBase")
    readonly property color surface: theme.colorFor("surface")
    readonly property color surfaceHigh: theme.colorFor("surfaceHigh")
    readonly property color outline: theme.colorFor("outline")
    readonly property color outlineSoft: theme.colorFor("outlineSoft")
    readonly property color outlineStrong: theme.colorFor("outlineStrong")
    readonly property color textPrimary: theme.colorFor("textPrimary")
    readonly property color textSecondary: theme.colorFor("textSecondary")
    readonly property color muted: theme.colorFor("muted")
    readonly property color accent: theme.colorFor("accent")
    readonly property color accentSoft: theme.colorFor("accentSoft")
    readonly property color glowAccent: theme.colorFor("glowAccent")
    readonly property color inputBg: theme.colorFor("inputBg")
    readonly property color popupBg: theme.colorFor("popupBg")
    readonly property color disabledBg: theme.colorFor("disabledBg")
    readonly property color disabledOutline: theme.colorFor("disabledOutline")
    readonly property color fillActive: theme.colorFor("fillActive")
    readonly property color fillChecked: theme.colorFor("fillChecked")
    readonly property color panelFill: theme.colorFor("panelFill")
    readonly property color scrim: theme.colorFor("scrim")

    // Fixed semantic colours.
    readonly property color success: "#3DFFB0"
    readonly property color danger: "#FF6B7A"
    readonly property color warning: "#F5C542"
    readonly property color notice: "#5EE0D0"
    readonly property color fillDanger: "#3A1218"
    readonly property color fillSuccess: "#143028"
    readonly property color fillWarning: "#3A2410"

    // Type.
    readonly property string fontUi: "Segoe UI"
    readonly property string fontMono: "Cascadia Mono"
    readonly property string fontIcon: "Segoe MDL2 Assets"
    readonly property int fontXs: 8
    readonly property int fontSm: 10
    readonly property int fontMd: 12
    readonly property int fontBase: 13
    readonly property int fontLg: 16
    readonly property int fontXl: 22
    readonly property real tracking1: 0.6
    readonly property real tracking2: 1.2
    readonly property real tracking3: 2.4

    // Spacing and shape.
    readonly property int s1: 4
    readonly property int s2: 8
    readonly property int s3: 12
    readonly property int s4: 16
    readonly property int s5: 20
    readonly property int radius: 3
    readonly property int notch: 11
    readonly property int notchSmall: 5
    readonly property int controlHeight: 34
    readonly property int compactControlHeight: 24
    readonly property real focusStroke: 1.5

    // Largest square pad that keeps ticks, nudges, and inset inside `box`.
    // The inset is a fraction of the box so it still reads as padding when the panel grows.
    function fitPadSize(box) {
        const span = Math.max(0, Number(box) || 0)
        const edge = Math.max(theme.s3, span * 0.125)
        return Math.max(48, Math.min(0.75 * (span - 2 * edge), span - 2 * (theme.s4 + edge)))
    }

    // Motion.
    readonly property int quick: 120
    readonly property int normal: 180
    readonly property int slow: 300
    readonly property int tooltipDelay: 400
}
