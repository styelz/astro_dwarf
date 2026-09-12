import QtQuick
import AstroDwarf 1.0
import ".."

// One live camera pane: decoded frames, Dual Lenses Locating on the wide
// view, and the tele footprint overlay. Used for the main preview and PiP.
Item {
    id: pane
    property bool playing: false
    property bool wideView: false
    property string camera: "tele"
    property bool centerEnabled: false
    property bool showFootprint: false
    property bool swallowClicks: false
    property bool inputEnabled: true
    property bool chromeShown: true
    property real fovH: 2.95 / 45.06
    property real fovV: 1.66 / 25.93
    property real footprintNx: 0.5
    property real footprintNy: 0.5
    property real footprintNw: 0
    property real footprintNh: 0
    readonly property real paintedWidth: frame.paintedWidth
    readonly property real paintedHeight: frame.paintedHeight
    // Native decoded frame size. Used for PiP aspect so the box does not
    // resize from the letterboxed fit, which would feed back into painted size.
    readonly property real imageWidth: frame.imageWidth
    readonly property real imageHeight: frame.imageHeight
    readonly property real sourceAspect: (imageWidth > 0 && imageHeight > 0) ? imageHeight / imageWidth : 9 / 16
    // Same fit rect paint() draws with, so overlays and taps track the pixels.
    readonly property real frameX: frame.paintedX
    readonly property real frameY: frame.paintedY
    signal centerRequested(real nx, real ny, string diag)

    LiveFrameItem {
        id: frame
        anchors.fill: parent
        visible: pane.playing
        playing: pane.playing
        camera: pane.camera
    }

    function centerOn(px, py) {
        if (!pane.centerEnabled || !pane.wideView)
            return
        const mapped = tapMouse.mapToItem(frame, px, py)
        const m = frame.mapToFrame(mapped.x, mapped.y)
        if (!m || !m.inside)
            return
        tapMarker.showAt(px, py)
        const diag = "mouse (" + px.toFixed(1) + ", " + py.toFixed(1) + ")"
            + " item " + m.itemW.toFixed(0) + "x" + m.itemH.toFixed(0)
            + " rect (" + m.rectX.toFixed(1) + ", " + m.rectY.toFixed(1) + " "
            + m.rectW.toFixed(1) + "x" + m.rectH.toFixed(1) + ")"
            + " jpeg " + m.imageW + "x" + m.imageH
            + " dpr " + Number(m.dpr).toFixed(2)
        pane.centerRequested(m.nx, m.ny, diag)
    }

    MouseArea {
        id: tapMouse
        // Local mouse coords on the pane (letterbox included), then mapped
        // through LiveFrameItem so taps use the same fit rect as paint().
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: false
        enabled: pane.inputEnabled && (pane.swallowClicks || (pane.centerEnabled && pane.wideView))
        onDoubleClicked: (mouse) => pane.centerOn(mouse.x, mouse.y)
    }

    Item {
        id: tapMarker
        z: 2
        width: 44
        height: 44
        opacity: 0
        visible: opacity > 0
        function showAt(px, py) {
            x = px - width / 2
            y = py - height / 2
            tapMarkerAnim.restart()
        }
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "transparent"
            border.color: Theme.accent
            border.width: 2
        }
        Rectangle { anchors.centerIn: parent; width: 14; height: 1.5; color: Theme.accent }
        Rectangle { anchors.centerIn: parent; width: 1.5; height: 14; color: Theme.accent }
        SequentialAnimation {
            id: tapMarkerAnim
            PropertyAction { target: tapMarker; property: "opacity"; value: 1 }
            PauseAnimation { duration: 350 }
            NumberAnimation { target: tapMarker; property: "opacity"; to: 0; duration: 500 }
        }
    }

    Rectangle {
        id: teleFootprint
        enabled: false
        visible: pane.showFootprint && pane.wideView && paintedWidth > 0
            && pane.footprintNw > 0 && pane.footprintNh > 0
        width: paintedWidth * pane.footprintNw
        height: paintedHeight * pane.footprintNh
        x: pane.frameX + paintedWidth * pane.footprintNx - width / 2
        y: pane.frameY + paintedHeight * pane.footprintNy - height / 2
        color: "transparent"
        border.color: Theme.accent
        border.width: 1
        opacity: pane.chromeShown ? 0.85 : 0.4
        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
    }
}
