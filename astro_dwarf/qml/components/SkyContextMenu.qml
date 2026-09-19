import QtQuick
import QtQuick.Controls

HudMenu {
    id: skyMenu
    objectName: "skyContextMenu"
    popupType: Popup.Window
    implicitWidth: 300
    property bool overlayEnabled: false
    property real overlayOpacity: 0.65
    readonly property int overlayOpacityPct: Math.round(Math.max(0, Math.min(1, overlayOpacity)) * 100)
    property bool dblclickTrack: false
    property bool trackEnabled: false
    property bool hasTarget: false
    property bool atlasMenuAvailable: false
    property bool clipboardValid: false
    property string clipboardText: ""
    property real clipboardRaHours: 0
    property real clipboardDecDegrees: 0

    signal overlayToggled()
    signal previewToggled()
    signal dblclickTrackToggled()
    signal trackSelected()
    signal atlasMenuRequested()
    signal clipboardGotoRequested()

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
        visible: skyMenu.clipboardValid
        text: "Go to clipboard"
        glyph: "\uE707"
        trailingText: skyMenu.clipboardText
        trailingMaxWidth: 168
        accessibleDescription: "Center the sky map on the clipboard RA and Dec without changing the selected mosaic target, "
                               + skyMenu.clipboardText
        onTriggered: skyMenu.clipboardGotoRequested()
    }
    HudMenuSeparator {
        visible: skyMenu.clipboardValid
        height: visible ? implicitHeight : 0
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
        text: skyMenu.dblclickTrack ? "Double-click only centers" : "Double-click starts tracking"
        glyph: "\uE734"
        trailingText: skyMenu.dblclickTrack ? "ON" : "OFF"
        accessibleDescription: skyMenu.dblclickTrack
                               ? "Turn off slewing the telescope when you double-click a sky-map target"
                               : "Slew to the double-clicked sky-map target and start sidereal tracking"
        onTriggered: skyMenu.dblclickTrackToggled()
    }
    HudMenuItem {
        text: "Track selected target"
        glyph: "\uE1D2"
        enabled: skyMenu.trackEnabled && skyMenu.hasTarget
        accessibleDescription: !skyMenu.hasTarget
                               ? "Select a target in the sky map first"
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
