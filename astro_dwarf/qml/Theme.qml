pragma Singleton
import QtQuick
import QtCore

// Single source of truth for the HUD look. Named palette roles can be tinted
// independently; relatives (fills, outlines, glows) follow their parent swatch.
// Theme.hsl() still uses the seed hue/brightness for one-off tints. Saturation
// and lightness recipes stay fixed per token so contrast remains stable.
QtObject {
    id: theme

    readonly property real defaultHue: 0.521

    readonly property Settings store: Settings {
        id: appearanceStore
        category: "appearance"
        property real hue: 0.521
        property real brightness: 0
        property string paletteJson: ""
        property bool previewChromeHintSeen: false
        property bool enhanceImages: true
        property bool deepCleanImages: false
        property real enhanceDenoise: 1
        property real enhanceSkyCrush: 1
    }
    property alias hue: appearanceStore.hue
    // -1 … 1; 0 is the stock look. Negative gives deep, saturated tints; positive lifts them.
    property alias brightness: appearanceStore.brightness
    property alias paletteJson: appearanceStore.paletteJson
    property alias previewChromeHintSeen: appearanceStore.previewChromeHintSeen
    property alias enhanceImages: appearanceStore.enhanceImages
    property alias deepCleanImages: appearanceStore.deepCleanImages
    property alias enhanceDenoise: appearanceStore.enhanceDenoise
    property alias enhanceSkyCrush: appearanceStore.enhanceSkyCrush

    readonly property var swatches: [
        { key: "windowBase", name: "BASE" },
        { key: "surface", name: "PANEL" },
        { key: "surfaceHigh", name: "RAISED" },
        { key: "outline", name: "LINE" },
        { key: "textSecondary", name: "DIM" },
        { key: "textPrimary", name: "TEXT" },
        { key: "accent", name: "ACCENT" }
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

    readonly property bool paletteCustom: {
        if (Math.abs(theme.hue - theme.defaultHue) > 0.002 || Math.abs(theme.brightness) > 0.002)
            return true
        const ov = theme.parsedOverrides
        for (const key in ov) {
            if (!ov[key] || typeof ov[key] !== "object")
                continue
            if (ov[key].hue !== undefined || ov[key].brightness !== undefined)
                return true
        }
        return false
    }

    // How far the seed hue is from stock (0 … 0.5). The original palette leans its
    // surfaces and outlines ~35° toward blue; the same lean turns a red accent orange,
    // so the offsets shrink as the hue moves away from cyan. At the default hue
    // nothing changes. Seed-based so editing one swatch does not retint the others.
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

    function recipeOf(key) {
        return theme.recipes[key] || ({ offset: 0, sat: 1, light: 0.5, alpha: 1, weight: 0, from: "" })
    }

    function roleOverride(key) {
        const ov = theme.parsedOverrides[key]
        return ov && typeof ov === "object" ? ov : null
    }

    function roleCustom(key) {
        const ov = theme.roleOverride(key)
        return !!(ov && (ov.hue !== undefined || ov.brightness !== undefined))
    }

    function paramsFor(key) {
        const recipe = theme.recipeOf(key)
        const source = recipe.from || key
        const ov = theme.roleOverride(source)
        let h
        let b
        if (ov && typeof ov.hue === "number")
            h = theme.wrapHue(ov.hue)
        else
            h = theme.wrapHue(theme.hue + recipe.offset * theme.spread)
        if (ov && typeof ov.brightness === "number")
            b = ov.brightness
        else
            b = theme.brightness
        return { h: h, sat: recipe.sat, light: recipe.light, alpha: recipe.alpha, weight: recipe.weight, brightness: b }
    }

    function effectiveHue(key) {
        return theme.paramsFor(key).h
    }

    function effectiveBrightness(key) {
        return theme.paramsFor(key).brightness
    }

    function stockHue(key) {
        return theme.wrapHue(theme.defaultHue + theme.recipeOf(key).offset)
    }

    function setRole(key, hue, brightness) {
        if (!theme.recipes[key])
            return
        const ov = {}
        const src = theme.parsedOverrides
        for (const k in src) {
            if (!src[k] || typeof src[k] !== "object")
                continue
            ov[k] = { hue: src[k].hue, brightness: src[k].brightness }
        }
        ov[key] = {
            hue: Math.round(theme.wrapHue(hue) * 1000) / 1000,
            brightness: Math.round(Math.max(-1, Math.min(1, Number(brightness))) * 100) / 100
        }
        theme.paletteJson = JSON.stringify(ov)
    }

    function clearRole(key) {
        const ov = {}
        const src = theme.parsedOverrides
        for (const k in src) {
            if (k === key || !src[k] || typeof src[k] !== "object")
                continue
            ov[k] = { hue: src[k].hue, brightness: src[k].brightness }
        }
        theme.paletteJson = Object.keys(ov).length ? JSON.stringify(ov) : ""
    }

    function resetPalette() {
        theme.paletteJson = ""
        theme.hue = theme.defaultHue
        theme.brightness = 0
    }

    // weight: how strongly the brightness slider moves this token (0 = fixed).
    // Positive brightness adds a flat lift so the glow side reads lighter. Negative
    // brightness scales lightness instead (an additive drop leaves near-white text
    // almost untouched). Saturation is never touched: dimming should darken the
    // colour, not grey it out.
    function bake(h, sat, light, alpha, weight, brightness) {
        const w = weight === undefined ? 0 : weight
        const b = brightness === undefined ? theme.brightness : brightness
        let l = light
        if (b >= 0) {
            l = light + b * 0.25 * w
        } else {
            // 0.75: at -1 a weight-1 token keeps a quarter of its lightness (text ~0.24, accent ~0.16).
            l = light * (1 + b * 0.75 * w)
        }
        l = Math.min(0.97, Math.max(0.02, l))
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

    // Motion.
    readonly property int quick: 120
    readonly property int normal: 180
    readonly property int slow: 300
    readonly property int tooltipDelay: 400
}
