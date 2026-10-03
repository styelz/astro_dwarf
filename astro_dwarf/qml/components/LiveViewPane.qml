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
    // Tele stream only. Wide double-click still centres.
    property bool feedDoubleClick: false
    // Drag a rectangle on this frame to lock object tracking. Clicks that
    // do not move still double-click (wide centre, tele full screen).
    property bool boxLockEnabled: false
    property bool boxLockShown: false
    property real boxNx: 0
    property real boxNy: 0
    property real boxNw: 0
    property real boxNh: 0
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
    signal feedDoubleClicked()
    signal boxLockRequested(real nx, real ny, real nw, real nh)

    function commitBox(x0, y0, x1, y1) {
        const aLocal = tapMouse.mapToItem(frame, x0, y0)
        const bLocal = tapMouse.mapToItem(frame, x1, y1)
        const a = frame.mapToFrame(aLocal.x, aLocal.y)
        const b = frame.mapToFrame(bLocal.x, bLocal.y)
        if (!a || !b || (!a.inside && !b.inside))
            return
        const nx = Math.max(0, Math.min(a.nx, b.nx))
        const ny = Math.max(0, Math.min(a.ny, b.ny))
        const farX = Math.min(1, Math.max(a.nx, b.nx))
        const farY = Math.min(1, Math.max(a.ny, b.ny))
        const nw = farX - nx
        const nh = farY - ny
        if (nw < 0.03 || nh < 0.03)
            return
        pane.boxLockRequested(nx, ny, nw, nh)
    }

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
        cursorShape: pane.boxLockEnabled ? Qt.CrossCursor : Qt.ArrowCursor
        enabled: pane.inputEnabled && (pane.boxLockEnabled || pane.swallowClicks || pane.feedDoubleClick || (pane.centerEnabled && pane.wideView))
        property real dragX: 0
        property real dragY: 0
        property bool dragArmed: false
        property bool dragMoved: false
        function cancelDrag() {
            dragArmed = false
            dragMoved = false
            dragRubber.visible = false
        }
        onPressed: (mouse) => {
            if (!pane.boxLockEnabled || mouse.button !== Qt.LeftButton)
                return
            dragArmed = true
            dragMoved = false
            dragX = mouse.x
            dragY = mouse.y
            dragRubber.visible = false
        }
        onPositionChanged: (mouse) => {
            if (!dragArmed)
                return
            const dx = mouse.x - dragX
            const dy = mouse.y - dragY
            if (!dragMoved && Math.abs(dx) < Theme.px(12) && Math.abs(dy) < Theme.px(12))
                return
            dragMoved = true
            dragRubber.x = Math.min(dragX, mouse.x)
            dragRubber.y = Math.min(dragY, mouse.y)
            dragRubber.width = Math.abs(dx)
            dragRubber.height = Math.abs(dy)
            dragRubber.visible = dragRubber.width > 2 && dragRubber.height > 2
        }
        onReleased: (mouse) => {
            if (!dragArmed)
                return
            const moved = dragMoved
            const x0 = dragX
            const y0 = dragY
            cancelDrag()
            if (moved && pane.boxLockEnabled)
                pane.commitBox(x0, y0, mouse.x, mouse.y)
        }
        onCanceled: cancelDrag()
        onDoubleClicked: (mouse) => {
            cancelDrag()
            if (!pane.wideView && pane.feedDoubleClick) {
                pane.feedDoubleClicked()
                return
            }
            pane.centerOn(mouse.x, mouse.y)
        }
    }

    Rectangle {
        id: dragRubber
        z: 4
        visible: false
        color: "transparent"
        border.color: Theme.accent
        border.width: 1
    }

    Rectangle {
        id: lockBox
        z: 2
        visible: pane.boxLockShown && pane.playing && pane.paintedWidth > 0 && pane.boxNw > 0.02 && pane.boxNh > 0.02
        x: pane.frameX + pane.paintedWidth * pane.boxNx
        y: pane.frameY + pane.paintedHeight * pane.boxNy
        width: pane.paintedWidth * pane.boxNw
        height: pane.paintedHeight * pane.boxNh
        color: "transparent"
        border.color: Theme.accent
        border.width: 2
    }

    Item {
        id: tapMarker
        z: 2
        width: Theme.px(44)
        height: Theme.px(44)
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
        Rectangle { anchors.centerIn: parent; width: Theme.px(14); height: 1.5; color: Theme.accent }
        Rectangle { anchors.centerIn: parent; width: 1.5; height: Theme.px(14); color: Theme.accent }
        SequentialAnimation {
            id: tapMarkerAnim
            PropertyAction { target: tapMarker; property: "opacity"; value: 1 }
            PauseAnimation { duration: 350 }
            NumberAnimation { target: tapMarker; property: "opacity"; to: 0; duration: 500 }
        }
    }

    Rectangle {
        id: teleFootprint
        z: 1
        enabled: false
        visible: pane.showFootprint && pane.wideView && pane.playing && pane.paintedWidth > 0
            && pane.footprintNw > 0 && pane.footprintNh > 0
        width: pane.paintedWidth * pane.footprintNw
        height: pane.paintedHeight * pane.footprintNh
        x: pane.frameX + pane.paintedWidth * pane.footprintNx - width / 2
        y: pane.frameY + pane.paintedHeight * pane.footprintNy - height / 2
        color: "transparent"
        border.color: Theme.fov
        border.width: 1
        opacity: pane.chromeShown ? 0.85 : 0.4
        Behavior on opacity { NumberAnimation { duration: Theme.slow } }
    }
}
