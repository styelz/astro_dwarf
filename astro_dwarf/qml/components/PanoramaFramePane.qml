import QtQuick
import AstroDwarf 1.0
import ".."

// Device framing canvas. The blank area is the mount's reachable panorama.
// Firmware draws the first yellow box (usually one wide frame). A resize
// asks the telescope to scan that crop. Tele stamps stay the full-canvas
// cell size; they only walk the yellow box.
Item {
    id: pane
    property bool active: false
    property bool widePlaying: false
    property bool telePlaying: false

    readonly property var telemetry: (backend.selectedDevice && backend.selectedDevice.telemetry) || ({})
    readonly property bool hasRect: !!telemetry.panorama_has_rect
    readonly property real limitLeft: Number(telemetry.panorama_limit_left || 0)
    readonly property real limitTop: Number(telemetry.panorama_limit_top || 0)
    readonly property real limitRight: Number(telemetry.panorama_limit_right || 1)
    readonly property real limitBottom: Number(telemetry.panorama_limit_bottom || 1)
    readonly property real spanX: Math.max(0.05, limitRight - limitLeft)
    readonly property real spanY: Math.max(0.05, limitBottom - limitTop)
    readonly property real boxNormW: Math.max(0.02, Math.abs(boxX2 - boxX1))
    readonly property real boxNormH: Math.max(0.02, Math.abs(boxY2 - boxY1))
    // Wide frame is about 16:9. Size the canvas so that normalized box
    // lands on screen at the wide camera's aspect, instead of treating
    // normalized X and Y as square pixels (that squashes the scan into a
    // strip and letterboxes the live frame).
    readonly property real wideAspect: {
        const wh = Number(telemetry.wide_fov_h || 0)
        const wv = Number(telemetry.wide_fov_v || 0)
        if (wh > 1 && wv > 1)
            return wh / wv
        const rh = Number(telemetry.panorama_rect_fov_h || 0)
        const rv = Number(telemetry.panorama_rect_fov_v || 0)
        if (rh > 1 && rv > 1 && wideSized)
            return rh / rv
        return 16 / 9
    }
    property real lockedAspect: 0
    readonly property real canvasAspect: lockedAspect > 0.2 ? lockedAspect : 32 / 9
    readonly property real fitW: width > 0 && height > 0
        ? (width / height > canvasAspect ? height * canvasAspect : width)
        : 0
    readonly property real fitH: canvasAspect > 0 ? fitW / canvasAspect : 0
    readonly property real fitX: (width - fitW) / 2
    readonly property real fitY: (height - fitH) / 2
    function numOr(value, fallback) {
        const n = Number(value)
        return isFinite(n) ? n : fallback
    }
    readonly property real boxX1: numOr(telemetry.panorama_x1, limitLeft)
    readonly property real boxY1: numOr(telemetry.panorama_y1, limitTop)
    readonly property real boxX2: numOr(telemetry.panorama_x2, limitRight)
    readonly property real boxY2: numOr(telemetry.panorama_y2, limitBottom)
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
    property bool holding: false
    property real heldX1: 0
    property real heldY1: 0
    property real heldX2: 0
    property real heldY2: 0
    property int shownScanRev: -1
    property Item frontScan: null
    property bool dragging: false
    property real dragX1: 0
    property real dragY1: 0
    property real dragX2: 0
    property real dragY2: 0

    readonly property real showX1: dragging ? dragX1 : (holding ? heldX1 : boxX1)
    readonly property real showY1: dragging ? dragY1 : (holding ? heldY1 : boxY1)
    readonly property real showX2: dragging ? dragX2 : (holding ? heldX2 : boxX2)
    readonly property real showY2: dragging ? dragY2 : (holding ? heldY2 : boxY2)
    readonly property bool shooting: String(telemetry.panorama_state || "") === "running"
    readonly property int tileDone: Math.max(0, Number(telemetry.panorama_completed || 0))
    readonly property int tileTotal: Math.max(0, Number(telemetry.panorama_total || 0))
    // Same 1800-on-canvas factoring as before the FOV-fill change. Cell size
    // is span/fullGrid, never the yellow box divided by that grid.
    readonly property int fullColCount: {
        const total = 1800
        const teleH = Number(telemetry.tele_fov_h || 0)
        const teleV = Number(telemetry.tele_fov_v || 0)
        const teleAspect = (teleH > 0.5 && teleV > 0.3) ? teleH / teleV : 2.95 / 1.66
        const view = (fitW > 2 && fitH > 2) ? (fitW / fitH) : canvasAspect
        const target = (view > 0.2 ? view : 32 / 9) / teleAspect
        let bestCols = 1
        let bestErr = 1e9
        for (let cols = 1; cols <= total; cols++) {
            if (total % cols)
                continue
            const rowCount = total / cols
            const err = Math.abs(cols / rowCount - target)
            if (err < bestErr) {
                bestErr = err
                bestCols = cols
            }
        }
        return Math.max(1, bestCols)
    }
    readonly property int fullRowCount: Math.max(1, Math.round(1800 / Math.max(1, fullColCount)))
    readonly property real stampNw: spanX / Math.max(1, fullColCount)
    readonly property real stampNh: spanY / Math.max(1, fullRowCount)
    readonly property real frameLeft: Math.min(showX1, showX2)
    readonly property real frameTop: Math.min(showY1, showY2)
    // Do not name these `rows`/`columns` or return `{rows: …}`. QML treats
    // `.rows` as a recursive lookup of a property named `rows` and blows the
    // JS stack (RangeError, fake line ~8e8).
    readonly property int tileColCount: {
        const bw = Math.abs(showX2 - showX1)
        if (!(stampNw > 0.001) || !(bw > 0.001) || fitW < 2)
            return 1
        return Math.max(1, Math.round(bw / stampNw))
    }
    readonly property int tileRowCount: {
        const bh = Math.abs(showY2 - showY1)
        if (!(stampNh > 0.001) || !(bh > 0.001) || fitH < 2)
            return 1
        return Math.max(1, Math.round(bh / stampNh))
    }
    readonly property int tileCap: Math.max(1, tileColCount * tileRowCount)
    readonly property int tileIndex: Math.max(0, Math.min(tileCap - 1, tileDone))

    onActiveChanged: {
        if (!active && !shooting) {
            userEnlarged = false
            holding = false
            shownScanRev = -1
            lockedAspect = 0
            scanA.source = ""
            scanB.source = ""
            frontScan = scanA
        }
    }
    onTelemetryChanged: reloadScan()

    function noteScanAspect(image) {
        if (lockedAspect > 0.2 || image.status !== Image.Ready)
            return
        if (image.implicitWidth > 0 && image.implicitHeight > 0)
            lockedAspect = image.implicitWidth / image.implicitHeight
    }

    function reloadScan() {
        const url = String(telemetry.panorama_scan_url || "")
        const rev = Number(telemetry.panorama_scan_rev || 0)
        if (!active || !url) {
            shownScanRev = -1
            if (scanA.source !== "")
                scanA.source = ""
            if (scanB.source !== "")
                scanB.source = ""
            frontScan = scanA
            return
        }
        if (rev === shownScanRev)
            return
        if (scanA.status === Image.Loading || scanB.status === Image.Loading)
            return
        shownScanRev = rev
        const incoming = frontScan === scanA ? scanB : scanA
        incoming.source = url
    }

    function promoteScan(image) {
        if (image.status === Image.Error) {
            image.source = ""
            reloadScan()
            return
        }
        if (image.status !== Image.Ready || String(image.source) === "")
            return
        noteScanAspect(image)
        frontScan = image
        reloadScan()
    }

    function holdBox(x1, y1, x2, y2) {
        heldX1 = x1
        heldY1 = y1
        heldX2 = x2
        heldY2 = y2
        holding = true
    }

    function releaseFrame() {
        userEnlarged = false
        holding = false
    }

    function unitPxX(nx) {
        return fitX + ((nx - limitLeft) / spanX) * fitW
    }

    function unitPxY(ny) {
        return fitY + ((ny - limitTop) / spanY) * fitH
    }

    function unitToPx(nx, ny) {
        return Qt.point(unitPxX(nx), unitPxY(ny))
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
        holdBox(x1, y1, x2, y2)
        backend.updatePanoramaFrame(x1, y1, x2, y2)
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.surface
        visible: pane.active
    }

    Image {
        id: scanA
        x: pane.fitX
        y: pane.fitY
        width: pane.fitW
        height: pane.fitH
        visible: pane.active && pane.frontScan === scanA
        fillMode: Image.PreserveAspectFit
        cache: false
        asynchronous: true
        onStatusChanged: pane.promoteScan(scanA)
    }
    Image {
        id: scanB
        x: pane.fitX
        y: pane.fitY
        width: pane.fitW
        height: pane.fitH
        visible: pane.active && pane.frontScan === scanB
        fillMode: Image.PreserveAspectFit
        cache: false
        asynchronous: true
        onStatusChanged: pane.promoteScan(scanB)
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
            visible: !pane.hasRect && !pane.holding && !pane.shooting
            text: "WAITING FOR FRAME"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
    }

    Item {
        id: box
        visible: pane.active && pane.fitW > 0 && (pane.hasRect || pane.holding)
        readonly property real minNX: Math.min(pane.showX1, pane.showX2)
        readonly property real minNY: Math.min(pane.showY1, pane.showY2)
        readonly property real maxNX: Math.max(pane.showX1, pane.showX2)
        readonly property real maxNY: Math.max(pane.showY1, pane.showY2)
        x: pane.unitPxX(minNX)
        y: pane.unitPxY(minNY)
        width: Math.max(Theme.px(28), pane.unitPxX(maxNX) - pane.unitPxX(minNX))
        height: Math.max(Theme.px(28), pane.unitPxY(maxNY) - pane.unitPxY(minNY))

        Rectangle {
            anchors.fill: parent
            visible: !pane.shooting
            color: "transparent"
            border.color: Theme.accent
            border.width: 2
        }

        MouseArea {
            anchors.fill: parent
            enabled: pane.hasRect && !pane.shooting
            cursorShape: Qt.SizeAllCursor
            preventStealing: true
            property real startX: 0
            property real startY: 0
            property real originX1: 0
            property real originY1: 0
            property real originX2: 0
            property real originY2: 0
            onPressed: (mouse) => {
                const local = mapToItem(pane, mouse.x, mouse.y)
                pane.dragging = true
                startX = local.x
                startY = local.y
                originX1 = pane.showX1
                originY1 = pane.showY1
                originX2 = pane.showX2
                originY2 = pane.showY2
                pane.dragX1 = originX1
                pane.dragY1 = originY1
                pane.dragX2 = originX2
                pane.dragY2 = originY2
            }
            onPositionChanged: (mouse) => {
                if (!pane.dragging)
                    return
                const local = mapToItem(pane, mouse.x, mouse.y)
                const du = ((local.x - startX) / Math.max(1, pane.fitW)) * pane.spanX
                const dv = ((local.y - startY) / Math.max(1, pane.fitH)) * pane.spanY
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
                visible: !pane.shooting
                color: Theme.accent
                Accessible.name: "Resize panorama " + modelData.corner
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -Theme.px(6)
                    enabled: !pane.shooting
                    cursorShape: Qt.SizeFDiagCursor
                    preventStealing: true
                    onPressed: {
                        pane.dragX1 = pane.showX1
                        pane.dragY1 = pane.showY1
                        pane.dragX2 = pane.showX2
                        pane.dragY2 = pane.showY2
                        pane.dragging = true
                    }
                    onPositionChanged: (mouse) => {
                        const local = mapToItem(pane, mouse.x, mouse.y)
                        const unit = pane.clampUnit(pane.pxToUnit(local.x, local.y).x, pane.pxToUnit(local.x, local.y).y)
                        pane.dragX1 = modelData.ax ? pane.showX1 : unit.x
                        pane.dragY1 = modelData.ay ? pane.showY1 : unit.y
                        pane.dragX2 = modelData.ax ? unit.x : pane.showX2
                        pane.dragY2 = modelData.ay ? unit.y : pane.showY2
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

    PanoramaStampItem {
        id: stampLayer
        anchors.fill: parent
        z: 4
        enabled: false
        visible: pane.active
        active: pane.active
        shooting: pane.shooting
        playing: pane.telePlaying && pane.shooting && pane.tileCap > 1
        tileIndex: pane.tileIndex
        gridColumns: pane.tileColCount
        gridRows: pane.tileRowCount
        fitX: pane.fitX
        fitY: pane.fitY // C++ name; do not bind `.rows` on a JS object
        fitW: pane.fitW
        fitH: pane.fitH
        boxX1: pane.frameLeft
        boxY1: pane.frameTop
        boxX2: pane.frameLeft + pane.tileColCount * pane.stampNw
        boxY2: pane.frameTop + pane.tileRowCount * pane.stampNh
        limitLeft: pane.limitLeft
        limitTop: pane.limitTop
        spanX: pane.spanX
        spanY: pane.spanY
    }

    Rectangle {
        id: tileBox
        z: 5
        visible: pane.active && pane.shooting && pane.tileCap > 1 && pane.fitW > 0
        readonly property int shotCols: Math.max(1, pane.tileColCount)
        readonly property int shotRowCount: Math.max(1, pane.tileRowCount)
        readonly property real tileLeft: pane.frameLeft
        readonly property real tileTop: pane.frameTop
        readonly property int shotRow: Math.floor(pane.tileIndex / shotCols)
        readonly property int shotCol: {
            const c = pane.tileIndex % shotCols
            return (shotRow % 2) ? (shotCols - 1 - c) : c
        }
        readonly property real shotNw: pane.stampNw
        readonly property real shotNh: pane.stampNh
        readonly property real shotNx: tileLeft + (shotCol + 0.5) * shotNw
        readonly property real shotNy: tileTop + (shotRow + 0.5) * shotNh
        x: pane.unitPxX(shotNx - shotNw / 2)
        y: pane.unitPxY(shotNy - shotNh / 2)
        width: Math.max(1, pane.unitPxX(shotNx + shotNw / 2) - pane.unitPxX(shotNx - shotNw / 2))
        height: Math.max(1, pane.unitPxY(shotNy + shotNh / 2) - pane.unitPxY(shotNy - shotNh / 2))
        color: "transparent"
        border.color: Theme.hsl(0, 0.12, 0.94)
        border.width: 1
        antialiasing: false

        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            color: "transparent"
            border.color: Theme.hsl(0, 0.25, 0.08)
            border.width: 1
            antialiasing: false
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
