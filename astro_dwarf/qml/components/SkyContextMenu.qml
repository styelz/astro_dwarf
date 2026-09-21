import QtQuick
import QtQuick.Controls
import ".."

HudMenu {
    id: skyMenu
    objectName: "skyContextMenu"
    popupType: Popup.Window
    implicitWidth: Theme.px(360)
    property bool overlayEnabled: false
    property real overlayOpacity: 0.65
    readonly property int overlayOpacityPct: Math.round(Math.max(0, Math.min(1, overlayOpacity)) * 100)
    property bool dblclickTrack: false
    property bool trackEnabled: false
    property bool hasTarget: false
    property bool hasFovCenter: false
    property string fovCenterText: ""
    property bool atlasMenuAvailable: false
    property bool clipboardValid: false
    property string clipboardText: ""
    property real clipboardRaHours: 0
    property real clipboardDecDegrees: 0

    signal overlayToggled()
    signal previewToggled()
    signal dblclickTrackToggled()
    signal trackSelected()
    signal fovTargetRequested()
    signal atlasMenuRequested()
    signal clipboardGotoRequested()
    signal enterRaDecRequested()

    function refreshClipboard() {
        const coords = backend.clipboardCoordinates() || ({})
        skyMenu.clipboardValid = !!coords.valid
        skyMenu.clipboardText = String(coords.text || "")
        skyMenu.clipboardRaHours = Number(coords.ra_hours)
        skyMenu.clipboardDecDegrees = Number(coords.dec_degrees)
    }

    onAboutToShow: skyMenu.refreshClipboard()

    HudMenuItem {
        objectName: "clipboardGotoMenuItem"
        text: "Go to clipboard"
        glyph: "\uE707"
        enabled: skyMenu.clipboardValid
        trailingText: skyMenu.clipboardValid ? skyMenu.clipboardText : ""
        trailingMaxWidth: Theme.px(168)
        accessibleDescription: skyMenu.clipboardValid
                               ? "Center the sky map on the clipboard RA and Dec without changing the selected mosaic target, "
                                 + skyMenu.clipboardText
                               : "Copy RA and Dec from a session or template first"
        onTriggered: skyMenu.clipboardGotoRequested()
    }
    HudMenuItem {
        objectName: "enterRaDecMenuItem"
        text: "Enter RA / Dec"
        glyph: "\uE70F"
        accessibleDescription: "Open a dialog to type right ascension and declination and center the sky map"
        onTriggered: skyMenu.enterRaDecRequested()
    }
    HudMenuSeparator {
    }
    HudMenuItem {
        text: skyMenu.overlayEnabled ? "Hide live stream on FOV" : "Overlay live stream on FOV"
        glyph: "\uE8B9"
        trailingText: skyMenu.overlayOpacityPct + "%"
        accessibleDescription: "Paint the live camera stream inside the sky-map field of view. Hold Ctrl and scroll to change opacity, currently "
                               + skyMenu.overlayOpacityPct + " percent"
        onTriggered: skyMenu.overlayToggled()
    }
    HudMenuItem {
        text: "Ctrl + mouse wheel adjusts overlay opacity"
        info: true
        enabled: false
        accessibleDescription: "Hold Ctrl and scroll the mouse wheel to change live stream overlay opacity"
    }
    HudMenuItem {
        text: backend.previewActive ? "Stop live view" : "Start live view"
        glyph: backend.previewActive ? "\uE71A" : "\uE768"
        enabled: backend.previewActive || !!(backend.selectedDevice && backend.selectedDevice.connected)
        accessibleDescription: backend.previewActive
                               ? "Stop the telescope live preview used by the FOV overlay"
                               : "Start the telescope live preview so it can be overlaid on the FOV"
        onTriggered: skyMenu.previewToggled()
    }
    HudMenuItem {
        text: skyMenu.dblclickTrack ? "Double-click starts tracking" : "Double-click only centers"
        glyph: "\uE734"
        trailingText: skyMenu.dblclickTrack ? "ON" : "OFF"
        accessibleDescription: skyMenu.dblclickTrack
                               ? "Turn off slewing the telescope when you double-click a sky-map target"
                               : "Slew to the double-clicked sky-map target and start sidereal tracking"
        onTriggered: skyMenu.dblclickTrackToggled()
    }
    HudMenuItem {
        objectName: "fovTargetMenuItem"
        text: "Set target to FOV centre"
        glyph: "\uE1D2"
        enabled: skyMenu.hasFovCenter
        trailingText: skyMenu.hasFovCenter ? skyMenu.fovCenterText : ""
        trailingMaxWidth: Theme.px(120)
        accessibleDescription: skyMenu.hasFovCenter
                               ? "Use the sky-map field centre as the target without picking a catalog object, "
                                 + skyMenu.fovCenterText
                               : "Pan the sky map until the field centre is known"
        onTriggered: skyMenu.fovTargetRequested()
    }
    HudMenuItem {
        text: "Track selected target"
        glyph: "\uE1D2"
        enabled: skyMenu.trackEnabled && skyMenu.hasTarget
        accessibleDescription: !skyMenu.hasTarget
                               ? "Select a sky-map object, or set the FOV centre as the target"
                               : !skyMenu.trackEnabled
                                 ? "Connect the telescope and wait until it is idle"
                                 : "Slew the telescope to the selected sky-map target and start tracking"
        onTriggered: skyMenu.trackSelected()
    }
    HudMenuSeparator {
        visible: skyMenu.atlasMenuAvailable
        height: visible ? implicitHeight : 0
    }
    HudMenuItem {
        objectName: "openAtlasMenuItem"
        visible: skyMenu.atlasMenuAvailable
        text: "Open atlas menu"
        glyph: "\uE8EC"
        accessibleDescription: "Open the Aladin Lite atlas tools at the clicked sky position"
        onTriggered: skyMenu.atlasMenuRequested()
    }
}
