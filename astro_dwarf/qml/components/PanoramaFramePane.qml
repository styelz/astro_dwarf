import QtQuick
import ".."

// Device framing canvas. The blank area is the mount's reachable panorama.
// The box starts as one wide frame. A resize asks the telescope to scan.
Item {
    id: pane
    property bool active: false
    property bool widePlaying: false

    readonly property var telemetry: (backend.selectedDevice && backend.selectedDevice.telemetry) || ({})
    readonly property bool hasRect: !!telemetry.panorama_has_rect
    readonly property real limitLeft: Number(telemetry.panorama_limit_left || 0)
    readonly property real limitTop: Number(telemetry.panorama_limit_top || 0)
    readonly property real limitRight: Number(telemetry.panorama_limit_right || 1)
    readonly property real limitBottom: Number(telemetry.panorama_limit_bottom || 1)
    readonly property real spanX: Math.max(0.05, limitRight - limitLeft)
    readonly property real spanY: Math.max(0.05, limitBottom - limitTop)
    readonly property real canvasAspect: spanX / spanY
    readonly property real fitW: width > 0 && height > 0
        ? (width / height > canvasAspect ? height * canvasAspect : width)
        : 0
    readonly property real fitH: canvasAspect > 0 ? fitW / canvasAspect : 0
    readonly property real fitX: (width - fitW) / 2
    readonly property real fitY: (height - fitH) / 2
    readonly property real boxX1: Number(telemetry.panorama_x1 || limitLeft)
    readonly property real boxY1: Number(telemetry.panorama_y1 || limitTop)
    readonly property real boxX2: Number(telemetry.panorama_x2 || limitRight)
    readonly property real boxY2: Number(telemetry.panorama_y2 || limitBottom)
    readonly property bool wideSized: {
        const h = Number(telemetry.panorama_rect_fov_h || 0)
        const v = Number(telemetry.panorama_rect_fov_v || 0)
        const wh = Number(telemetry.wide_fov_h || 0)
        const wv = Number(telemetry.wide_fov_v || 0)
        if (!(h > 0 && v > 0 && wh > 0 && wv > 0))
            return !userEnlarged
        return Math.abs(h - wh) / wh < 0.2 && Math.abs(v - wv) / wv < 0.2
    }
    property bool userEnlarged: false
    property bool dragging: false
    property real dragX1: 0
    property real dragY1: 0
    property real dragX2: 0
    property real dragY2: 0

    readonly property real showX1: dragging ? dragX1 : boxX1
    readonly property real showY1: dragging ? dragY1 : boxY1
    readonly property real showX2: dragging ? dragX2 : boxX2
    readonly property real showY2: dragging ? dragY2 : boxY2

    onActiveChanged: if (!active) userEnlarged = false

    function unitToPx(nx, ny) {
        return Qt.point(
            fitX + ((nx - limitLeft) / spanX) * fitW,
            fitY + ((ny - limitTop) / spanY) * fitH
        )
    }

    function pxToUnit(px, py) {
        return Qt.point(
            limitLeft + ((px - fitX) / Math.max(1, fitW)) * spanX,
            limitTop + ((py - fitY) / Math.max(1, fitH)) * spanY
        )
    }

    function clampUnit(nx, ny) {
        return Qt.point(
            Math.max(limitLeft, Math.min(limitRight, nx)),
            Math.max(limitTop, Math.min(limitBottom, ny))
        )
    }

    function commitBox() {
        if (!hasRect || !active)
            return
        const x1 = Math.min(dragX1, dragX2)
        const y1 = Math.min(dragY1, dragY2)
        const x2 = Math.max(dragX1, dragX2)
        const y2 = Math.max(dragY1, dragY2)
        if ((x2 - x1) < 0.02 || (y2 - y1) < 0.02)
            return
        userEnlarged = true
        backend.updatePanoramaFrame(x1, y1, x2, y2)
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.surface
        visible: pane.active
    }

    Image {
        x: pane.fitX
        y: pane.fitY
        width: pane.fitW
        height: pane.fitH
        visible: pane.active && String(pane.telemetry.panorama_scan_url || "") !== ""
        source: pane.telemetry.panorama_scan_url || ""
        fillMode: Image.Stretch
        cache: false
        asynchronous: true
    }

    Rectangle {
        id: canvas
        x: pane.fitX
        y: pane.fitY
        width: pane.fitW
        height: pane.fitH
        visible: pane.active
        color: "transparent"
        border.color: Theme.outline
        border.width: 1

        Text {
            anchors.centerIn: parent
            visible: !pane.hasRect
            text: "WAITING FOR FRAME"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }

    Item {
        id: box
        visible: pane.active && pane.hasRect && pane.fitW > 0
        readonly property point origin: pane.unitToPx(Math.min(pane.showX1, pane.showX2), Math.min(pane.showY1, pane.showY2))
        readonly property point far: pane.unitToPx(Math.max(pane.showX1, pane.showX2), Math.max(pane.showY1, pane.showY2))
        x: origin.x
        y: origin.y
        width: Math.max(Theme.px(28), far.x - origin.x)
        height: Math.max(Theme.px(28), far.y - origin.y)

        LiveViewPane {
            anchors.fill: parent
            visible: pane.wideSized && pane.widePlaying
            playing: pane.widePlaying && pane.wideSized && pane.active
            wideView: true
            camera: "wide"
            inputEnabled: false
            showFootprint: false
            chromeShown: false
        }

        Rectangle {
            anchors.fill: parent
            color: "transparent"
            border.color: Theme.accent
            border.width: 2
        }

        MouseArea {
            anchors.fill: parent
            enabled: pane.hasRect && !pane.dragging
            cursorShape: Qt.SizeAllCursor
            preventStealing: true
            property real startX: 0
            property real startY: 0
            property real originX1: 0
            property real originY1: 0
            property real originX2: 0
            property real originY2: 0
            onPressed: (mouse) => {
                pane.dragging = true
                startX = mouse.x
                startY = mouse.y
                originX1 = pane.boxX1
                originY1 = pane.boxY1
                originX2 = pane.boxX2
                originY2 = pane.boxY2
                pane.dragX1 = originX1
                pane.dragY1 = originY1
                pane.dragX2 = originX2
                pane.dragY2 = originY2
            }
            onPositionChanged: (mouse) => {
                if (!pane.dragging)
                    return
                const du = ((mouse.x - startX) / Math.max(1, pane.fitW)) * pane.spanX
                const dv = ((mouse.y - startY) / Math.max(1, pane.fitH)) * pane.spanY
                const w = originX2 - originX1
                const h = originY2 - originY1
                let x1 = originX1 + du
                let y1 = originY1 + dv
                x1 = Math.max(pane.limitLeft, Math.min(pane.limitRight - w, x1))
                y1 = Math.max(pane.limitTop, Math.min(pane.limitBottom - h, y1))
                pane.dragX1 = x1
                pane.dragY1 = y1
                pane.dragX2 = x1 + w
                pane.dragY2 = y1 + h
            }
            onReleased: {
                pane.commitBox()
                pane.dragging = false
            }
            onCanceled: pane.dragging = false
        }

        Repeater {
            model: [
                {corner: "tl", ax: 0, ay: 0},
                {corner: "tr", ax: 1, ay: 0},
                {corner: "bl", ax: 0, ay: 1},
                {corner: "br", ax: 1, ay: 1}
            ]
            delegate: Rectangle {
                required property var modelData
                width: Theme.px(14)
                height: Theme.px(14)
                x: modelData.ax ? parent.width - width : 0
                y: modelData.ay ? parent.height - height : 0
                color: Theme.accent
                Accessible.name: "Resize panorama " + modelData.corner
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -Theme.px(6)
                    cursorShape: Qt.SizeFDiagCursor
                    preventStealing: true
                    onPressed: pane.dragging = true
                    onPositionChanged: (mouse) => {
                        const local = mapToItem(pane, mouse.x, mouse.y)
                        const unit = pane.clampUnit(pane.pxToUnit(local.x, local.y).x, pane.pxToUnit(local.x, local.y).y)
                        pane.dragX1 = modelData.ax ? pane.boxX1 : unit.x
                        pane.dragY1 = modelData.ay ? pane.boxY1 : unit.y
                        pane.dragX2 = modelData.ax ? unit.x : pane.boxX2
                        pane.dragY2 = modelData.ay ? unit.y : pane.boxY2
                    }
                    onReleased: {
                        pane.commitBox()
                        pane.dragging = false
                    }
                    onCanceled: pane.dragging = false
                }
            }
        }
    }

    Text {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.px(14)
        visible: pane.active && Number(pane.telemetry.panorama_rect_error || 0) !== 0
        text: "FRAME LIMIT " + pane.telemetry.panorama_rect_error
        color: Theme.warning
        font.pixelSize: Theme.fontSm
        font.family: Theme.fontMono
        elide: Text.ElideRight
        z: 6
    }
}
