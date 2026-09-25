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
    property bool seeded: false
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
    readonly property int tileIndex: tileTotal > 0 ? Math.min(tileTotal - 1, tileDone) : 0

    // Same factoring as domain.panorama_shot_grid: tele FOV on the painted
    // canvas, not a 1:1 split of normalized x/y (that overlay is too wide).
    function tileGrid() {
        const total = tileTotal
        if (total < 2 || fitW < 2 || fitH < 2)
            return {cols: 1, rows: 1}
        const teleH = Number(telemetry.tele_fov_h || 0)
        const teleV = Number(telemetry.tele_fov_v || 0)
        const teleAspect = (teleH > 0.5 && teleV > 0.3) ? teleH / teleV : 2.95 / 1.66
        const target = (fitW / fitH) / teleAspect
        let cols = 1
        let err = 1e9
        for (let c = 1; c <= total; ++c) {
            if (total % c !== 0)
                continue
            const rows = total / c
            const delta = Math.abs(c / rows - target)
            if (delta < err) {
                err = delta
                cols = c
            }
        }
        return {cols: cols, rows: total / cols}
    }

    onActiveChanged: {
        if (!active) {
            userEnlarged = false
            seeded = false
            holding = false
            shownScanRev = -1
            lockedAspect = 0
            scanA.source = ""
            scanB.source = ""
            frontScan = scanA
        }
    }
    onHasRectChanged: seedFrame()
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
        if (!url || rev === shownScanRev)
            return
        shownScanRev = rev
        const incoming = frontScan === scanA ? scanB : scanA
        incoming.source = url
    }

    function promoteScan(image) {
        if (image.status !== Image.Ready || String(image.source) === "")
            return
        noteScanAspect(image)
        frontScan = image
        lumaProbe.schedule()
    }

    function holdBox(x1, y1, x2, y2) {
        heldX1 = x1
        heldY1 = y1
        heldX2 = x2
        heldY2 = y2
        holding = true
    }

    // The telescope opens framing on the full reachable area. Start at half
    // that width and keep the box there while the quick scan updates the rect.
    function seedFrame() {
        if (!active || !hasRect || seeded || dragging || userEnlarged)
            return
        seeded = true
        const w = spanX * 0.5
        const h = Math.min(spanY, spanY * w / spanX * canvasAspect / wideAspect)
        const cx = (limitLeft + limitRight) / 2
        const cy = (limitTop + limitBottom) / 2
        const x1 = cx - w / 2
        const y1 = cy - h / 2
        const x2 = cx + w / 2
        const y2 = cy + h / 2
        holdBox(x1, y1, x2, y2)
        backend.updatePanoramaFrame(x1, y1, x2, y2)
    }

    function unitToPx(nx, ny) {
        return Qt.point(
            fitX + ((nx - limitLeft) / spanX) * fitW,
            fitY + ((ny - limitTop) / spanY) * fitH
        )
    }

    function scanPainted(image) {
        if (!image || image.paintedWidth < 2 || image.paintedHeight < 2)
            return Qt.rect(0, 0, 0, 0)
        return Qt.rect(
            image.x + (image.width - image.paintedWidth) / 2,
            image.y + (image.height - image.paintedHeight) / 2,
            image.paintedWidth,
            image.paintedHeight
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
        readonly property point origin: pane.unitToPx(Math.min(pane.showX1, pane.showX2), Math.min(pane.showY1, pane.showY2))
        readonly property point far: pane.unitToPx(Math.max(pane.showX1, pane.showX2), Math.max(pane.showY1, pane.showY2))
        x: origin.x
        y: origin.y
        width: Math.max(Theme.px(28), far.x - origin.x)
        height: Math.max(Theme.px(28), far.y - origin.y)

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

    Rectangle {
        id: tileBox
        z: 5
        visible: pane.active && pane.shooting && pane.tileTotal > 1 && pane.fitW > 0
        readonly property var grid: pane.tileGrid()
        readonly property real tileLeft: Math.min(pane.showX1, pane.showX2)
        readonly property real tileTop: Math.min(pane.showY1, pane.showY2)
        readonly property real spanW: Math.abs(pane.showX2 - pane.showX1)
        readonly property real spanH: Math.abs(pane.showY2 - pane.showY1)
        readonly property int row: Math.floor(pane.tileIndex / Math.max(1, grid.cols))
        readonly property int col: {
            const cols = Math.max(1, grid.cols)
            const c = pane.tileIndex % cols
            return (row % 2) ? (cols - 1 - c) : c
        }
        readonly property real shotNx: tileLeft + (col + 0.5) * spanW / grid.cols
        readonly property real shotNy: tileTop + (row + 0.5) * spanH / grid.rows
        readonly property real shotNw: spanW / grid.cols
        readonly property real shotNh: spanH / grid.rows
        readonly property point origin: pane.unitToPx(shotNx - shotNw / 2, shotNy - shotNh / 2)
        readonly property point far: pane.unitToPx(shotNx + shotNw / 2, shotNy + shotNh / 2)
        readonly property color strokeDark: Theme.hsl(0, 0.25, 0.08)
        readonly property color strokeLight: Theme.hsl(0, 0.12, 0.94)
        property bool overLight: false
        property bool strokeReady: false
        x: origin.x
        y: origin.y
        width: Math.max(1, far.x - origin.x)
        height: Math.max(1, far.y - origin.y)
        color: "transparent"
        border.color: strokeReady ? (overLight ? strokeDark : strokeLight) : Theme.accent
        border.width: 1
        antialiasing: false
        onVisibleChanged: lumaProbe.schedule()
        onXChanged: lumaProbe.schedule()
        onYChanged: lumaProbe.schedule()
        onWidthChanged: lumaProbe.schedule()
        onHeightChanged: lumaProbe.schedule()
    }

    Canvas {
        id: lumaProbe
        x: -64
        y: -64
        width: 32
        height: 18
        opacity: 0
        renderTarget: Canvas.Image
        contextType: "2d"
        property bool scheduled: false
        property bool sampled: false

        function schedule() {
            if (scheduled || !tileBox.visible)
                return
            scheduled = true
            Qt.callLater(kick)
        }

        function kick() {
            scheduled = false
            if (tileBox.visible)
                requestPaint()
        }

        onPaint: {
            sampled = false
            const img = pane.frontScan
            const ctx = getContext("2d")
            if (!ctx)
                return
            ctx.reset()
            if (!img || img.status !== Image.Ready || img.implicitWidth < 2 || img.implicitHeight < 2)
                return
            const painted = pane.scanPainted(img)
            if (painted.width < 2 || painted.height < 2)
                return
            const sx = (tileBox.x - painted.x) / painted.width * img.implicitWidth
            const sy = (tileBox.y - painted.y) / painted.height * img.implicitHeight
            const sw = tileBox.width / painted.width * img.implicitWidth
            const sh = tileBox.height / painted.height * img.implicitHeight
            if (!(sw > 1 && sh > 1))
                return
            try {
                ctx.drawImage(img, sx, sy, sw, sh, 0, 0, width, height)
            } catch (err) {
                try {
                    ctx.drawImage(img.source, sx, sy, sw, sh, 0, 0, width, height)
                } catch (err2) {
                    return
                }
            }
            sampled = true
        }

        onPainted: {
            if (!sampled) {
                tileBox.strokeReady = false
                return
            }
            const ctx = getContext("2d")
            const pix = ctx ? ctx.getImageData(0, 0, width, height) : null
            const data = pix && pix.data
            if (!data || data.length < 16) {
                tileBox.strokeReady = false
                return
            }
            let sum = 0
            let n = 0
            for (let i = 0; i < data.length; i += 4) {
                if (data[i + 3] < 16)
                    continue
                sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]
                n++
            }
            if (n < 4) {
                tileBox.strokeReady = false
                return
            }
            const luma = sum / n / 255
            if (luma > 0.55)
                tileBox.overLight = true
            else if (luma < 0.45)
                tileBox.overLight = false
            tileBox.strokeReady = true
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
