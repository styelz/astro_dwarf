import QtQuick
import AstroDwarf 1.0
import ".."

// Contact-sheet mosaic preview: live frame in the current pane, last live
// frame held until stacking JPEG starts, completed stacks in the others.
// Painted on the GUI thread like LiveViewPane.
Item {
    id: pane
    property bool playing: false
    property string camera: "tele"
    property color accent: Theme.fov
    readonly property int livePane: {
        const n = Number((backend.mosaicPreview && backend.mosaicPreview.live_pane) || 0)
        return isFinite(n) && n >= 1 ? n : 0
    }
    readonly property bool liveActive: pane.livePane >= 1

    MosaicLiveItem {
        anchors.fill: pane
        playing: pane.playing
        liveActive: pane.liveActive
        livePane: pane.livePane
        camera: pane.camera
        accent: pane.accent
        southUp: backend.mosaicSouthUp
        positionAngle: backend.mosaicPa
        zenithCamera: backend.mosaicPaSource === "parallactic"
        fontPixelSize: Theme.fontPx(11)
    }
}
