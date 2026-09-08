pragma Singleton
import QtQuick
import QtCore

// Single source of truth for the HUD look. Every tinted colour is derived from one
// hue so the whole app re-skins live when Theme.hue changes. Saturation and
// lightness are fixed per token, which keeps contrast stable at any hue.
QtObject {
    id: theme

    readonly property real defaultHue: 0.521

    readonly property Settings store: Settings {
        id: appearanceStore
        category: "appearance"
        property real hue: 0.521
        property real brightness: 0
        property bool previewChromeHintSeen: false
    }
    property alias hue: appearanceStore.hue
    // -1 … 1; 0 is the stock look. Negative gives deep, saturated tints; positive lifts them.
    property alias brightness: appearanceStore.brightness
    property alias previewChromeHintSeen: appearanceStore.previewChromeHintSeen

    // How far the hue is from stock (0 … 0.5). The original palette leans its surfaces
    // and outlines ~35° toward blue; the same lean turns a red accent orange, so the
    // offsets shrink as the hue moves away from cyan. At the default hue nothing changes.
    readonly property real hueDistance: {
        const d = Math.abs(theme.hue - theme.defaultHue)
        return Math.min(d, 1 - d)
    }
    readonly property real spread: 1 - (theme.hueDistance / 0.5) * 0.7
    readonly property real lift: theme.brightness * 0.25

    // weight: how strongly the brightness slider moves this token's lightness (0 = fixed).
    function hsl(offset, sat, light, alpha, weight) {
        let h = (theme.hue + offset * theme.spread) % 1
        if (h < 0)
            h += 1
        const w = weight === undefined ? 0 : weight
        const l = Math.min(0.97, Math.max(0.02, light + theme.lift * w))
        return Qt.hsla(h, sat, l, alpha === undefined ? 1 : alpha)
    }

    // Tinted palette (offsets reproduce the original cyan HUD at hue 0.521, brightness 0).
    readonly property color windowBase: hsl(0.096, 0.500, 0.039, 1, 0.10)
    readonly property color surface: hsl(0.066, 0.488, 0.084, 1, 0.20)
    readonly property color surfaceHigh: hsl(0.075, 0.478, 0.135, 1, 0.25)
    readonly property color outline: hsl(0.039, 0.535, 0.253, 1, 0.60)
    readonly property color outlineSoft: hsl(0.047, 0.509, 0.208, 1, 0.60)
    readonly property color outlineStrong: hsl(0.058, 0.402, 0.341, 1, 0.60)
    readonly property color textPrimary: hsl(0.037, 1.000, 0.955)
    readonly property color textSecondary: hsl(0.037, 0.286, 0.610, 1, 0.25)
    readonly property color muted: hsl(0.046, 0.255, 0.400, 1, 0.30)
    readonly property color accent: hsl(0.000, 1.000, 0.651, 1, 1.00)
    readonly property color accentSoft: hsl(0.000, 1.000, 0.955)
    readonly property color glowAccent: hsl(0.000, 1.000, 0.651, 0.2, 1.00)
    readonly property color inputBg: hsl(0.075, 0.565, 0.090, 1, 0.20)
    readonly property color popupBg: hsl(0.079, 0.714, 0.027, 1, 0.10)
    readonly property color disabledBg: hsl(0.085, 0.440, 0.049, 1, 0.10)
    readonly property color disabledOutline: hsl(0.055, 0.455, 0.151, 1, 0.40)
    readonly property color fillActive: hsl(0.019, 0.674, 0.169, 1, 0.50)
    readonly property color fillChecked: hsl(0.036, 0.640, 0.196, 1, 0.50)
    readonly property color panelFill: hsl(0.079, 0.517, 0.057, 0.702, 0.15)
    readonly property color scrim: hsl(0.095, 0.600, 0.020, 0.80, 0.10)

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

    // Motion.
    readonly property int quick: 120
    readonly property int normal: 180
    readonly property int slow: 300
}
