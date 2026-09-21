import QtQuick
import ".."

// Per-frame stack timer that reuses the MOTION pad geometry: ring, ticks,
// and crosshair. Firmware progress packets from the logs:
//   (armed, no packet)  START_CAPTURE accepted → WAIT
//   0/0  first exposure starting → start the ring
//   1/0  subframe captured, still processing → keep counting past exp
//   1/1  stacked caught up, next exposure starting → reset and start
//   N/N  last frame stacked → hold
// Cycle time is exposure plus processing, so elapsed is not clamped to the
// configured shutter. N/M still uses stacked. The ring fills over exposure
// and stays full while the device processes the subframe.
Item {
    id: timer
    property bool active: false
    property bool progressSeen: false
    property real firmwareElapsed: 0
    property real exposureSeconds: 0
    property int current: 0
    property int stacked: 0
    property int total: 0
    property string target: ""
    property real padSize: Theme.fitPadSize(Math.min(width, height))

    readonly property int frameKey: timer.stacked
    readonly property bool processing: timer.progressSeen && timer.current > timer.stacked
    readonly property bool complete: timer.active && timer.progressSeen && timer.total > 0
                                     && timer.stacked >= timer.total
    readonly property bool exposing: timer.active && timer.progressSeen && !timer.complete
    readonly property bool waiting: timer.active && !timer.progressSeen
    readonly property real elapsed: displayedElapsed
    readonly property real progress: {
        if (timer.complete)
            return 1
        if (timer.exposureSeconds > 0)
            return Math.min(1, timer.displayedElapsed / timer.exposureSeconds)
        return 0
    }
    readonly property string secondsText: {
        if (timer.waiting)
            return "WAIT"
        const value = timer.displayedElapsed
        if (timer.exposureSeconds > 0 && timer.exposureSeconds < 1)
            return value.toFixed(2)
        if (timer.exposureSeconds > 0 && timer.exposureSeconds < 3)
            return value.toFixed(1)
        return String(Math.floor(value))
    }
    readonly property string exposureText: {
        const total = timer.exposureSeconds
        if (!(total > 0))
            return timer.waiting ? "FIRST EXP" : "EXP"
        if (total < 1)
            return total.toFixed(2) + "s"
        if (Math.abs(total - Math.round(total)) < 0.05)
            return Math.round(total) + "s"
        return total.toFixed(1) + "s"
    }
    readonly property string framesText: {
        if (timer.total > 0)
            return timer.stacked + " / " + timer.total
        if (timer.stacked > 0)
            return String(timer.stacked)
        if (timer.current > 0)
            return String(timer.current)
        if (timer.waiting)
            return "WAIT"
        return "—"
    }

    property real displayedElapsed: 0
    property real anchorElapsed: 0
    property real anchorMs: 0
    property bool haveFirmware: false
    property int lastFrame: -1

    function reanchor(seconds) {
        const value = Math.max(0, Number(seconds) || 0)
        timer.anchorElapsed = value
        timer.anchorMs = Date.now()
        timer.displayedElapsed = timer.clamped(value)
    }

    function clamped(seconds) {
        return Math.min(999, Math.max(0, Number(seconds) || 0))
    }

    function tick() {
        const now = Date.now()
        const stamp = timer.anchorMs || now
        timer.displayedElapsed = timer.clamped(timer.anchorElapsed + (now - stamp) / 1000)
        ring.requestPaint()
    }

    function freshElapsed() {
        return timer.firmwareElapsed < 0.5 ? Math.max(0, timer.firmwareElapsed) : 0
    }

    onActiveChanged: {
        timer.haveFirmware = false
        timer.lastFrame = -1
        if (timer.active && timer.firmwareElapsed > 0.05)
            timer.haveFirmware = true
        if (timer.active && timer.exposing)
            timer.reanchor(timer.freshElapsed())
        else
            timer.reanchor(timer.complete ? timer.displayedElapsed : 0)
    }
    onProgressSeenChanged: {
        if (!timer.active)
            return
        timer.haveFirmware = timer.firmwareElapsed > 0.05
        timer.lastFrame = timer.frameKey
        if (timer.exposing)
            timer.reanchor(timer.freshElapsed())
        else if (!timer.complete)
            timer.reanchor(0)
    }
    onExposingChanged: {
        if (!timer.active)
            return
        if (timer.exposing)
            timer.reanchor(timer.freshElapsed())
        else if (!timer.complete)
            timer.reanchor(0)
    }
    onFirmwareElapsedChanged: {
        // Long-exp packets are shutter time only. Ignore them while the
        // device is processing a captured subframe so the ring can run past
        // the configured exposure.
        if (!timer.active || !timer.exposing || timer.processing)
            return
        if (timer.firmwareElapsed > 0.05)
            timer.haveFirmware = true
        if (!timer.haveFirmware)
            return
        if (timer.firmwareElapsed + 0.4 < timer.displayedElapsed)
            timer.reanchor(timer.firmwareElapsed)
        else if (timer.firmwareElapsed >= timer.displayedElapsed - 0.02)
            timer.reanchor(timer.firmwareElapsed)
    }
    onFrameKeyChanged: {
        if (!timer.active)
            return
        if (timer.complete) {
            timer.lastFrame = timer.frameKey
            return
        }
        if (timer.lastFrame >= 0 && timer.frameKey > timer.lastFrame)
            timer.reanchor(timer.freshElapsed())
        else if (timer.lastFrame >= 0 && timer.frameKey < timer.lastFrame) {
            timer.haveFirmware = timer.firmwareElapsed > 0.05
            if (timer.exposing)
                timer.reanchor(timer.freshElapsed())
            else
                timer.reanchor(0)
        }
        timer.lastFrame = timer.frameKey
    }
    onExposureSecondsChanged: timer.tick()

    Accessible.role: Accessible.Indicator
    Accessible.name: {
        const target = timer.target ? ", " + timer.target : ""
        if (timer.waiting) {
            const frames = timer.total > 0 ? ", " + timer.total + " frames" : ""
            return "Stacking started, waiting for first exposure" + frames + target
        }
        const frame = timer.total > 0 ? timer.stacked + " of " + timer.total + " stacked" : timer.framesText + " stacked"
        const taken = timer.current > timer.stacked ? ", " + timer.current + " taken" : ""
        if (timer.complete)
            return "Stack complete, " + frame + target
        if (timer.processing)
            return "Processing subframe, " + timer.secondsText + "s, " + frame + taken + target
        return "Exposure " + timer.secondsText + " of " + timer.exposureText + ", " + frame + taken + target
    }

    Timer {
        interval: 50
        running: timer.active && timer.visible && timer.exposing
        repeat: true
        onTriggered: timer.tick()
    }

    Item {
        id: analogPad
        anchors.centerIn: parent
        width: timer.padSize
        height: width
        readonly property real padScale: width / 96
        readonly property real tickMargin: Math.max(Theme.px(6), Math.round(10 * padScale))
        readonly property real hairInset: Math.max(Theme.s3, Math.round(18 * padScale))

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Theme.hsl(0.075, 0.565, 0.090, 0.702)
            border.color: Theme.outline
            border.width: 2
        }
        Canvas {
            id: ring
            anchors.fill: parent
            anchors.margins: -analogPad.tickMargin
            readonly property color majorInk: Theme.accent
            readonly property color minorInk: Theme.outlineStrong
            readonly property color trackInk: Theme.outline
            readonly property color arcInk: Theme.accent
            readonly property real fill: timer.progress
            readonly property real padRadius: analogPad.width / 2 - Math.max(Theme.s1, Math.round(6 * analogPad.padScale))
            onMajorInkChanged: requestPaint()
            onMinorInkChanged: requestPaint()
            onTrackInkChanged: requestPaint()
            onArcInkChanged: requestPaint()
            onFillChanged: requestPaint()
            onPadRadiusChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const cx = width / 2, cy = height / 2
                const rOuter = width / 2 - 1
                const scale = analogPad.padScale
                for (let i = 0; i < 36; i++) {
                    const major = i % 9 === 0
                    const a = i * Math.PI * 2 / 36
                    const len = (major ? 8 : 4) * scale
                    ctx.strokeStyle = major ? majorInk : minorInk
                    ctx.lineWidth = major ? 2 : 1
                    ctx.beginPath()
                    ctx.moveTo(cx + Math.cos(a) * (rOuter - len), cy + Math.sin(a) * (rOuter - len))
                    ctx.lineTo(cx + Math.cos(a) * rOuter, cy + Math.sin(a) * rOuter)
                    ctx.stroke()
                }
                const r = padRadius
                ctx.lineCap = "round"
                ctx.lineWidth = Math.max(Theme.px(3), 4 * scale)
                ctx.strokeStyle = trackInk
                ctx.beginPath()
                ctx.arc(cx, cy, r, 0, Math.PI * 2)
                ctx.stroke()
                if (fill > 0) {
                    ctx.strokeStyle = arcInk
                    ctx.shadowColor = arcInk
                    ctx.shadowBlur = 8 * scale
                    ctx.beginPath()
                    ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * fill)
                    ctx.stroke()
                }
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }
        Rectangle {
            anchors.centerIn: parent
            width: Theme.px(2)
            height: parent.height - analogPad.hairInset
            color: Theme.outlineStrong
            opacity: 0.45
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - analogPad.hairInset
            height: Theme.px(2)
            color: Theme.outlineStrong
            opacity: 0.45
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 0.58
            height: width
            radius: width / 2
            color: Theme.hsl(0.062, 0.488, 0.169)
            border.color: Theme.outlineStrong
        }
        Column {
            anchors.centerIn: parent
            spacing: Theme.px(-1)
            Text {
                id: secondsLabel
                anchors.horizontalCenter: parent.horizontalCenter
                text: timer.secondsText
                color: (timer.waiting || timer.processing) ? Theme.warning : Theme.textPrimary
                font.pixelSize: Math.max(14, Math.round(22 * analogPad.padScale))
                font.family: Theme.fontMono
                font.bold: true
                SequentialAnimation on opacity {
                    running: timer.waiting
                    loops: Animation.Infinite
                    NumberAnimation { from: 1; to: 0.45; duration: 700; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 0.45; to: 1; duration: 700; easing.type: Easing.InOutSine }
                    onRunningChanged: if (!running) secondsLabel.opacity = 1
                }
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: timer.exposureText
                color: Theme.textSecondary
                font.pixelSize: Math.max(8, Math.round(9 * analogPad.padScale))
                font.bold: true
                font.letterSpacing: 0.8
            }
        }
    }
}
