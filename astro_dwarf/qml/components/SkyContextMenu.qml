import QtQuick
import QtQuick.Controls

HudMenu {
    id: skyMenu
    objectName: "skyContextMenu"
    popupType: Popup.Window
    implicitWidth: 280
    property bool overlayEnabled: false
    property real overlayOpacity: 0.65
    readonly property int overlayOpacityPct: Math.round(Math.max(0, Math.min(1, overlayOpacity)) * 100)
    property bool dblclickTrack: false
    property bool trackEnabled: false
    property bool hasTarget: false

    signal overlayToggled()
    signal previewToggled()
    signal dblclickTrackToggled()
    signal trackSelected()

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
}
