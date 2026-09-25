import QtQuick
import AstroDwarf 1.0
import ".."

// Device mosaics paint the live camera inside the full field the telescope
// is building. Custom mosaics stay a gapped contact sheet.
Item {
    id: pane
    property bool playing: false
    property string camera: "tele"
    property color accent: Theme.fov
    readonly property var preview: backend.mosaicPreview || ({})
    readonly property int livePane: {
        const n = Number(preview.live_pane || 0)
        return isFinite(n) && n >= 1 ? n : 0
    }
    readonly property bool liveActive: pane.livePane >= 1
    readonly property bool deviceMosaic: !!preview.device

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
        composed: pane.deviceMosaic
        horizontalScale: Number(preview.horizontal_scale) || 100
        verticalScale: Number(preview.vertical_scale) || 100
    }
}
