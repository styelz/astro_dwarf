import QtQuick
import AstroDwarf 1.0
import ".."

// Device framing canvas. The blank area is the mount's reachable panorama.
// The box starts as one wide frame. A resize asks the telescope to scan.
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
    // Normalized X and Y are not square pixels. Paint the scan at its own
    // aspect, or 32:9 until the first thumbnail has loaded.
    property real lockedAspect: 0
    readonly property real canvasAspect: lockedAspect > 0.2 ? lockedAspect : 32 / 9
    readonly property real fitW: width > 0 && height > 0
        ? (width / height > canvasAspect ? height * canvasAspect : width)
        : 0
    readonly property real fitH: canvasAspect > 0 ? fitW / canvasAspect : 0
    readonly property real fitX: (width - fitW) / 2
    readonly property real fitY: (height - fitH) / 2
    // A reported 0 is a real corner. `||` would treat it as missing and
    // fall through to the full travel limits, which is the 1800-shot grid.
    readonly property real boxX1: isNaN(Number(telemetry.panorama_x1)) ? limitLeft : Number(telemetry.panorama_x1)
    readonly property real boxY1: isNaN(Number(telemetry.panorama_y1)) ? limitTop : Number(telemetry.panorama_y1)
    readonly property real boxX2: isNaN(Number(telemetry.panorama_x2)) ? limitRight : Number(telemetry.panorama_x2)
    readonly property real boxY2: isNaN(Number(telemetry.panorama_y2)) ? limitBottom : Number(telemetry.panorama_y2)
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
    readonly property int tileIndex: tileTotal > 0 ? Math.min(tileTotal - 1, tileDone) : 0
    // Do not name these `rows`/`columns` or return `{rows: …}`. QML treats
    // `.rows` as a recursive lookup of a property named `rows` and blows the
    // JS stack (RangeError, fake line ~8e8).
    // Full travel is 1800 tele fields. On the 32:9 scan that is 60×30.
    // A framed area only chooses which of those cells are shot. The cell
    // itself stays one tele FOV, 2.95°×1.66°.
    readonly property int fullColCount: {
        const total = 1800
        if (fitW < 2 || fitH < 2)
            return 60
        const teleH = Number(telemetry.tele_fov_h || 0)
        const teleV = Number(telemetry.tele_fov_v || 0)
        const teleAspect = (teleH > 0.5 && teleV > 0.3) ? teleH / teleV : 2.95 / 1.66
        const target = (fitW / fitH) / teleAspect
        let count = 60
        let err = 1e9
        for (let c = 1; c <= total; ++c) {
            if (total % c !== 0)
                continue
            const across = total / c
            const delta = Math.abs(c / across - target)
            if (delta < err) {
                err = delta
                count = c
            }
        }
        return count
    }
    readonly property int fullRowCount: Math.max(1, Math.round(1800 / Math.max(1, fullColCount)))
    readonly property real cellNormW: spanX / fullColCount
    readonly property real cellNormH: spanY / fullRowCount
    readonly property int tileColCount: {
        const w = Math.abs(showX2 - showX1)
        if (!(cellNormW > 0))
            return 1
        return Math.max(1, Math.round(w / cellNormW))
    }
    readonly property int tileRowCount: {
        const h = Math.abs(showY2 - showY1)
        if (!(cellNormH > 0))
            return 1
        return Math.max(1, Math.round(h / cellNormH))
    }

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

    // Drop a local drag so the next device rect is the box on screen.
    // Do not send a replacement rectangle here. The telescope opens on its
    // own frame; inventing one from the travel limits is the full 1800-shot grid.
    function releaseFrame() {
        userEnlarged = false
        holding = false
        dragging = false
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

    function snapBox(x1, y1, x2, y2) {
        const cw = cellNormW
        const ch = cellNormH
        const colsMax = fullColCount
        const rowsMax = fullRowCount
        if (!(cw > 0) || !(ch > 0))
            return [x1, y1, x2, y2]
        const left = Math.min(x1, x2)
        const right = Math.max(x1, x2)
        const top = Math.min(y1, y2)
        const bottom = Math.max(y1, y2)
        const cols = Math.max(1, Math.min(colsMax, Math.round((right - left) / cw)))
        const rows = Math.max(1, Math.min(rowsMax, Math.round((bottom - top) / ch)))
        function start(center, origin, cell, count, grid) {
            let s = ((center - origin) / cell) - (count / 2)
            s = Math.round(s * 2) / 2
            s = Math.max(0, Math.min(grid - count, s))
            return origin + s * cell
        }
        const snappedLeft = start((left + right) / 2, limitLeft, cw, cols, colsMax)
        const snappedTop = start((top + bottom) / 2, limitTop, ch, rows, rowsMax)
        return [snappedLeft, snappedTop, snappedLeft + cols * cw, snappedTop + rows * ch]
    }

    function commitBox() {
        if (!hasRect || !active)
            return
        const snapped = snapBox(dragX1, dragY1, dragX2, dragY2)
        const x1 = snapped[0]
        const y1 = snapped[1]
        const x2 = snapped[2]
        const y2 = snapped[3]
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

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.bottom
            anchors.topMargin: Theme.s1
            visible: !pane.shooting
            text: pane.tileColCount + "×" + pane.tileRowCount
            color: Theme.accent
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
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
                const snapped = pane.snapBox(x1, y1, x1 + w, y1 + h)
                pane.dragX1 = snapped[0]
                pane.dragY1 = snapped[1]
                pane.dragX2 = snapped[2]
                pane.dragY2 = snapped[3]
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
                        const snapped = pane.snapBox(
                            modelData.ax ? pane.showX1 : unit.x,
                            modelData.ay ? pane.showY1 : unit.y,
                            modelData.ax ? unit.x : pane.showX2,
                            modelData.ay ? unit.y : pane.showY2
                        )
                        pane.dragX1 = snapped[0]
                        pane.dragY1 = snapped[1]
                        pane.dragX2 = snapped[2]
                        pane.dragY2 = snapped[3]
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
        playing: pane.telePlaying && pane.tileTotal > 1
        tileIndex: pane.tileIndex
        gridColumns: pane.tileColCount
        gridRows: pane.tileRowCount
        fitX: pane.fitX
        fitY: pane.fitY // C++ name; do not bind `.rows` on a JS object
        fitW: pane.fitW
        fitH: pane.fitH
        boxX1: pane.showX1
        boxY1: pane.showY1
        boxX2: pane.showX2
        boxY2: pane.showY2
        limitLeft: pane.limitLeft
        limitTop: pane.limitTop
        spanX: pane.spanX
        spanY: pane.spanY
    }

    Rectangle {
        id: tileBox
        z: 5
        visible: pane.active && pane.shooting && pane.tileTotal > 1 && pane.fitW > 0
        readonly property int shotCols: Math.max(1, pane.tileColCount)
        readonly property real tileLeft: Math.min(pane.showX1, pane.showX2)
        readonly property real tileTop: Math.min(pane.showY1, pane.showY2)
        // Snap onto the full 60×30 grid. Do not divide the frame by the
        // shot count; that resizes the tele field.
        readonly property int originCol: pane.cellNormW > 0
            ? Math.max(0, Math.round((tileLeft - pane.limitLeft) / pane.cellNormW))
            : 0
        readonly property int originRow: pane.cellNormH > 0
            ? Math.max(0, Math.round((tileTop - pane.limitTop) / pane.cellNormH))
            : 0
        readonly property int shotRow: Math.floor(pane.tileIndex / shotCols)
        readonly property int shotCol: {
            const c = pane.tileIndex % shotCols
            return (shotRow % 2) ? (shotCols - 1 - c) : c
        }
        readonly property real shotNw: pane.cellNormW
        readonly property real shotNh: pane.cellNormH
        readonly property real shotNx: pane.limitLeft + (originCol + shotCol + 0.5) * shotNw
        readonly property real shotNy: pane.limitTop + (originRow + shotRow + 0.5) * shotNh
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
