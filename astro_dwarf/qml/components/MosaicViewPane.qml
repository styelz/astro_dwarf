import QtQuick
import AstroDwarf 1.0
import ".."

// Contact-sheet mosaic preview: live frame in the current pane, completed
// stacks in the others. Painted on the GUI thread like LiveViewPane.
Item {
    id: pane
    property bool playing: false
    property string camera: "tele"
    property color accent: Theme.accent

    MosaicLiveItem {
        anchors.fill: pane
        playing: pane.playing
        camera: pane.camera
        accent: pane.accent
        southUp: backend.mosaicSouthUp
        positionAngle: backend.mosaicPa
    }
}
