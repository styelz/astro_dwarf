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
        property bool previewChromeHintSeen: false
    }
    property alias hue: appearanceStore.hue
    property alias previewChromeHintSeen: appearanceStore.previewChromeHintSeen

    function hsl(offset, sat, light, alpha) {
        let h = (theme.hue + offset) % 1
        if (h < 0)
            h += 1
        return Qt.hsla(h, sat, light, alpha === undefined ? 1 : alpha)
    }

    // Tinted palette (offsets reproduce the original cyan HUD at hue 0.521).
    readonly property color windowBase: hsl(0.096, 0.500, 0.039)
    readonly property color surface: hsl(0.066, 0.488, 0.084)
    readonly property color surfaceHigh: hsl(0.075, 0.478, 0.135)
    readonly property color outline: hsl(0.039, 0.535, 0.253)
    readonly property color outlineSoft: hsl(0.047, 0.509, 0.208)
    readonly property color outlineStrong: hsl(0.058, 0.402, 0.341)
    readonly property color textPrimary: hsl(0.037, 1.000, 0.955)
    readonly property color textSecondary: hsl(0.037, 0.286, 0.610)
    readonly property color muted: hsl(0.046, 0.255, 0.400)
    readonly property color accent: hsl(0.000, 1.000, 0.651)
    readonly property color accentSoft: hsl(0.000, 1.000, 0.955)
    readonly property color glowAccent: hsl(0.000, 1.000, 0.651, 0.2)
    readonly property color inputBg: hsl(0.075, 0.565, 0.090)
    readonly property color popupBg: hsl(0.079, 0.714, 0.027)
    readonly property color disabledBg: hsl(0.085, 0.440, 0.049)
    readonly property color disabledOutline: hsl(0.055, 0.455, 0.151)
    readonly property color fillActive: hsl(0.019, 0.674, 0.169)
    readonly property color fillChecked: hsl(0.036, 0.640, 0.196)
    readonly property color panelFill: hsl(0.079, 0.517, 0.057, 0.702)
    readonly property color scrim: hsl(0.095, 0.600, 0.020, 0.80)

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
