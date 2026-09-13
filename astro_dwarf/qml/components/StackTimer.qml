import QtQuick
import ".."

// Per-frame exposure timer that reuses the MOTION pad geometry: ring, ticks,
// and crosshair. Firmware long-exp progress is interpolated between packets;
// if those packets never arrive, the ring still counts from the configured
// exposure and resets when the stacked/taken count advances.
Item {
    id: timer
    property bool active: false
    property real firmwareElapsed: 0
    property real exposureSeconds: 0
    property int current: 0
    property int stacked: 0
    property int total: 0
    property string target: ""

    readonly property int frameKey: Math.max(timer.current, timer.stacked)
    readonly property real elapsed: displayedElapsed
    readonly property real progress: timer.exposureSeconds > 0
        ? Math.min(1, timer.displayedElapsed / timer.exposureSeconds)
        : 0
    readonly property string secondsText: {
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
            return "EXP"
        if (total < 1)
            return total.toFixed(2) + "s"
        if (Math.abs(total - Math.round(total)) < 0.05)
            return Math.round(total) + "s"
        return total.toFixed(1) + "s"
    }
    readonly property string framesText: {
        if (timer.total > 0)
            return timer.current + " / " + timer.total
        if (timer.current > 0)
            return String(timer.current)
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
        const value = Math.max(0, Number(seconds) || 0)
        if (timer.exposureSeconds > 0)
            return Math.min(timer.exposureSeconds, value)
        return Math.min(999, value)
    }

    function tick() {
        const now = Date.now()
        const stamp = timer.anchorMs || now
        timer.displayedElapsed = timer.clamped(timer.anchorElapsed + (now - stamp) / 1000)
        ring.requestPaint()
    }

    onActiveChanged: {
        timer.haveFirmware = false
        timer.lastFrame = -1
        timer.reanchor(timer.active ? Math.max(0, timer.firmwareElapsed) : 0)
    }
    onFirmwareElapsedChanged: {
        if (!timer.active)
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
        if (timer.lastFrame >= 0 && timer.frameKey !== timer.lastFrame) {
            if (!timer.haveFirmware || timer.firmwareElapsed < 0.5)
                timer.reanchor(timer.firmwareElapsed)
        }
        timer.lastFrame = timer.frameKey
    }
    onExposureSecondsChanged: timer.tick()

    Accessible.role: Accessible.Indicator
    Accessible.name: {
        const frame = timer.total > 0 ? timer.current + " of " + timer.total + " frames" : timer.framesText + " frames"
        const stacked = timer.stacked > 0 ? ", " + timer.stacked + " stacked" : ""
        const target = timer.target ? ", " + timer.target : ""
        return "Exposure " + timer.secondsText + " of " + timer.exposureText + ", " + frame + stacked + target
    }

    Timer {
        interval: 50
        running: timer.active && timer.visible
        repeat: true
        onTriggered: timer.tick()
    }

    Item {
        id: analogPad
        anchors.centerIn: parent
        width: Math.min(108, parent.width - 8, parent.height - 8)
        height: width

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
            anchors.margins: -10
            readonly property color majorInk: Theme.accent
            readonly property color minorInk: Theme.outlineStrong
            readonly property color trackInk: Theme.outline
            readonly property color arcInk: Theme.accent
            readonly property real fill: timer.progress
            readonly property real padRadius: analogPad.width / 2 - 6
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
                for (let i = 0; i < 36; i++) {
                    const major = i % 9 === 0
                    const a = i * Math.PI * 2 / 36
                    const len = major ? 8 : 4
                    ctx.strokeStyle = major ? majorInk : minorInk
                    ctx.lineWidth = major ? 2 : 1
                    ctx.beginPath()
                    ctx.moveTo(cx + Math.cos(a) * (rOuter - len), cy + Math.sin(a) * (rOuter - len))
                    ctx.lineTo(cx + Math.cos(a) * rOuter, cy + Math.sin(a) * rOuter)
                    ctx.stroke()
                }
                const r = padRadius
                ctx.lineCap = "round"
                ctx.lineWidth = 4
                ctx.strokeStyle = trackInk
                ctx.beginPath()
                ctx.arc(cx, cy, r, 0, Math.PI * 2)
                ctx.stroke()
                if (fill > 0) {
                    ctx.strokeStyle = arcInk
                    ctx.shadowColor = arcInk
                    ctx.shadowBlur = 8
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
            width: 2
            height: parent.height - 18
            color: Theme.outlineStrong
            opacity: 0.45
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - 18
            height: 2
            color: Theme.outlineStrong
            opacity: 0.45
        }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(64, parent.width * 0.58)
            height: width
            radius: width / 2
            color: Theme.hsl(0.062, 0.488, 0.169)
            border.color: Theme.outlineStrong
        }
        Column {
            anchors.centerIn: parent
            spacing: -1
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: timer.secondsText
                color: Theme.textPrimary
                font.pixelSize: analogPad.width >= 96 ? 22 : 16
                font.family: Theme.fontMono
                font.bold: true
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: timer.exposureText
                color: Theme.textSecondary
                font.pixelSize: analogPad.width >= 96 ? 9 : 8
                font.bold: true
                font.letterSpacing: 0.8
            }
        }
    }
}
