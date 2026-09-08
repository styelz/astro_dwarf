import QtQuick
import ".."

// One live camera pane: decoded frames, Dual Lenses Locating on the wide
// view, and the tele footprint overlay. Used for the main preview and PiP.
Item {
    id: pane
    property bool playing: false
    property bool wideView: false
    property string source: ""
    property bool centerEnabled: false
    property bool showFootprint: false
    property bool swallowClicks: false
    property bool chromeShown: true
    property real fovH: 2.95 / 45.06
    property real fovV: 1.66 / 25.93
    readonly property real paintedWidth: frame.paintedWidth
    readonly property real paintedHeight: frame.paintedHeight
    readonly property real frameX: (width - paintedWidth) / 2
    readonly property real frameY: (height - paintedHeight) / 2
    signal centerRequested(real nx, real ny)

    Image {
        id: frame
        anchors.fill: parent
        visible: pane.playing
        cache: false
        fillMode: Image.PreserveAspectFit
        source: pane.source
    }

    function centerOn(px, py) {
        if (!pane.centerEnabled || !pane.wideView || paintedWidth <= 0 || paintedHeight <= 0)
            return
        const fx = px - pane.frameX
        const fy = py - pane.frameY
        if (fx < 0 || fy < 0 || fx > paintedWidth || fy > paintedHeight)
            return
        tapMarker.showAt(px, py)
        pane.centerRequested(fx / paintedWidth, fy / paintedHeight)
    }

    MouseArea {
        // Local mouse coords on the Image (letterbox included). Scene
        // mapping from TapHandler was treating window X as frame X, so
        // a click on the left of the wide view was sent as the right half.
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        hoverEnabled: false
        enabled: pane.swallowClicks || (pane.centerEnabled && pane.wideView)
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
        width: paintedWidth * pane.fovH
        height: paintedHeight * pane.fovV
        x: pane.frameX + (paintedWidth - width) / 2
        y: pane.frameY + (paintedHeight - height) / 2
        color: "transparent"
        border.color: Theme.accent
        border.width: 1
        opacity: pane.chromeShown ? 0.85 : 0.4
        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
    }
}
