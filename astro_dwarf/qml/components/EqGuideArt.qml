import QtQuick
import QtQuick.Layouts
import ".."

// Drawn EQ setup guide. Residuals are how far the wedge is off the pole.
// Both axes within 2° pass; closer to 0° is the tighter target.
Item {
    id: art
    property string phase: "stars"
    property real aziErr: 0
    property real altErr: 0
    property bool hasResult: false
    property bool aligned: false
    property real tiltDeg: 0
    property string hemisphere: ""
    property bool siteReady: true
    property string aziText: ""
    property string aziAction: ""
    property string altText: ""
    property string altAction: ""

    readonly property bool showMoves: (phase === "result" || phase === "adjust") && hasResult
    readonly property bool aziOk: hasResult && Math.abs(aziErr) <= 2
    readonly property bool altOk: hasResult && Math.abs(altErr) <= 2
    readonly property color ink: Theme.accent
    readonly property string captionText: {
        if (phase === "stars")
            return "Point up at the stars. A roof or a wall will not plate-solve."
        if (phase === "gear")
            return "The head tilts and turns. Leave the tripod legs where they are."
        if (phase === "pose") {
            if (!siteReady)
                return "Set the observing site. The wedge tilt has to match your latitude."
            if (hemisphere === "south")
                return "Back faces south, lens faces north. Tilt about " + tiltDeg.toFixed(1) + "° toward the south celestial pole."
            if (hemisphere === "equator")
                return "Latitude is 0°. Keep the polar axis level and aim the lens at a horizon."
            return "Back faces north, lens faces south. Tilt about " + tiltDeg.toFixed(1) + "° toward Polaris."
        }
        if (phase === "solving")
            return "Short pictures are matched to the star catalog. Both axes must come back within 2°."
        if (phase === "result" || phase === "adjust") {
            if (!hasResult)
                return "The plate-solve finished without an azimuth or altitude error."
            if (aligned)
                return "Pass: both are within 2°. You can image. 0° is tighter for 30–120s exposures and for a mosaic."
            return "Not yet. Both azimuth and altitude must be within 2°. Move only the head, then lock it."
        }
        return ""
    }
    readonly property color captionColor: {
        if ((phase === "result" || phase === "adjust") && hasResult)
            return aligned ? Theme.success : Theme.warning
        return Theme.textSecondary
    }

    implicitHeight: showMoves ? Theme.px(188) : Theme.px(148)
    Accessible.name: "EQ setup guide"
    Accessible.description: captionText

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.s2
        Text {
            Layout.fillWidth: true
            text: art.captionText
            color: art.captionColor
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSm
            font.family: Theme.fontMono
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.s3
            Canvas {
                id: diagram
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: Theme.px(160)
                readonly property string mode: art.phase
                readonly property bool moves: art.showMoves
                readonly property real azimuth: art.aziErr
                readonly property real altitude: art.altErr
                readonly property bool azimuthOk: art.aziOk
                readonly property bool altitudeOk: art.altOk
                readonly property bool solved: art.hasResult
                readonly property real tilt: art.tiltDeg
                readonly property string side: art.hemisphere
                readonly property bool site: art.siteReady
                readonly property color stroke: art.ink
                onModeChanged: requestPaint()
                onMovesChanged: requestPaint()
                onAzimuthChanged: requestPaint()
                onAltitudeChanged: requestPaint()
                onAzimuthOkChanged: requestPaint()
                onAltitudeOkChanged: requestPaint()
                onSolvedChanged: requestPaint()
                onTiltChanged: requestPaint()
                onSideChanged: requestPaint()
                onSiteChanged: requestPaint()
                onStrokeChanged: requestPaint()
                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.reset()
                    const w = width
                    const h = height
                    if (w < 8 || h < 8)
                        return
                    if (art.showMoves)
                        art.paintMoves(ctx, w, h)
                    else if (art.phase === "gear")
                        art.paintGear(ctx, w, h)
                    else if (art.phase === "pose")
                        art.paintPose(ctx, w, h)
                    else if (art.phase === "solving")
                        art.paintSolve(ctx, w, h)
                    else
                        art.paintStars(ctx, w, h)
                }
            }
            ColumnLayout {
                visible: art.showMoves
                Layout.fillWidth: true
                Layout.preferredWidth: Theme.px(220)
                Layout.alignment: Qt.AlignVCenter
                spacing: Theme.s2
                Text {
                    Layout.fillWidth: true
                    text: art.aziText || "AZ"
                    color: art.aziOk ? Theme.success : Theme.warning
                    font.pixelSize: Theme.fontMd
                    font.family: Theme.fontMono
                    font.letterSpacing: Theme.tracking1
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    text: art.aziAction
                    color: Theme.textPrimary
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fontSm
                }
                Text {
                    Layout.fillWidth: true
                    text: art.altText || "ALT"
                    color: art.altOk ? Theme.success : Theme.warning
                    font.pixelSize: Theme.fontMd
                    font.family: Theme.fontMono
                    font.letterSpacing: Theme.tracking1
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    text: art.altAction
                    color: Theme.textPrimary
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fontSm
                }
            }
        }
    }

    function axisColor(ok, solved) {
        if (!solved)
            return Theme.muted
        return ok ? Theme.success : Theme.warning
    }

    function paintStars(ctx, w, h) {
        ctx.fillStyle = Theme.surfaceHigh
        ctx.fillRect(0, 0, w, h * 0.72)
        ctx.strokeStyle = Theme.notice
        ctx.fillStyle = Theme.notice
        const stars = [[0.18, 0.18], [0.42, 0.12], [0.67, 0.22], [0.82, 0.1], [0.3, 0.38], [0.58, 0.34]]
        for (let i = 0; i < stars.length; i++) {
            ctx.beginPath()
            ctx.arc(stars[i][0] * w, stars[i][1] * h, i % 2 ? 2.2 : 1.4, 0, Math.PI * 2)
            ctx.fill()
        }
        ctx.strokeStyle = Theme.outline
        ctx.beginPath()
        ctx.moveTo(0, h * 0.72)
        ctx.lineTo(w, h * 0.72)
        ctx.stroke()
        paintScope(ctx, w * 0.5, h * 0.9, -Math.PI / 2, Theme.accent)
        paintTag(ctx, "STARS", w * 0.08, h * 0.16, Theme.notice)
    }

    function paintGear(ctx, w, h) {
        const hubX = w * 0.42
        const hubY = h * 0.42
        ctx.strokeStyle = Theme.outline
        ctx.lineWidth = 1.5
        const feet = [[w * 0.16, h * 0.88], [w * 0.48, h * 0.9], [w * 0.7, h * 0.86]]
        for (let i = 0; i < feet.length; i++) {
            ctx.beginPath()
            ctx.moveTo(hubX, hubY)
            ctx.lineTo(feet[i][0], feet[i][1])
            ctx.stroke()
        }
        ctx.strokeStyle = Theme.accent
        ctx.strokeRect(hubX - 16, hubY - 22, 32, 28)
        ctx.beginPath()
        ctx.arc(hubX + 28, hubY - 6, 16, -Math.PI * 0.2, Math.PI * 0.85)
        ctx.stroke()
        paintArrowHead(ctx, hubX + 28 + Math.cos(Math.PI * 0.85) * 16, hubY - 6 + Math.sin(Math.PI * 0.85) * 16, Math.PI * 0.85 + Math.PI / 2, Theme.accent)
        ctx.beginPath()
        ctx.moveTo(hubX, hubY - 28)
        ctx.lineTo(hubX, hubY - 46)
        ctx.stroke()
        paintArrowHead(ctx, hubX, hubY - 46, -Math.PI / 2, Theme.accent)
        paintTag(ctx, "TURN", hubX + 36, hubY + 18, Theme.textSecondary)
        paintTag(ctx, "TILT", hubX + 8, hubY - 40, Theme.textSecondary)
        paintTag(ctx, "LEGS STAY", w * 0.08, h * 0.78, Theme.warning)
    }

    function paintPose(ctx, w, h) {
        const groundY = h * 0.78
        ctx.strokeStyle = Theme.outline
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.moveTo(w * 0.08, groundY)
        ctx.lineTo(w * 0.92, groundY)
        ctx.stroke()
        if (!siteReady) {
            paintTag(ctx, "SITE", w * 0.4, h * 0.4, Theme.warning)
            return
        }
        const south = hemisphere === "south"
        const level = hemisphere === "equator" || tiltDeg < 1
        const angle = level ? 0 : Math.min(75, Math.max(8, tiltDeg)) * Math.PI / 180
        const dir = south ? -1 : 1
        const pivotX = south ? w * 0.72 : w * 0.28
        const length = Math.min(w, h) * 0.62
        const endX = pivotX + dir * Math.cos(angle) * length
        const endY = groundY - Math.sin(angle) * length
        ctx.strokeStyle = Theme.accent
        ctx.beginPath()
        ctx.moveTo(pivotX, groundY)
        ctx.lineTo(endX, endY)
        ctx.stroke()
        paintScope(ctx, (pivotX + endX) / 2, (groundY + endY) / 2, Math.atan2(groundY - endY, endX - pivotX), Theme.accent)
        ctx.fillStyle = Theme.notice
        ctx.beginPath()
        ctx.arc(endX, endY, 3, 0, Math.PI * 2)
        ctx.fill()
        paintTag(ctx, south ? "SCP" : (level ? "HORIZON" : "POLARIS"), endX - (south ? 36 : 0), endY - 8, Theme.notice)
        paintTag(ctx, level ? "LEVEL" : (tiltDeg.toFixed(0) + "°"), pivotX + dir * 18, groundY - 16, Theme.textPrimary)
        paintTag(ctx, south ? "LENS NORTH" : (level ? "LENS OUT" : "LENS SOUTH"), w * 0.08, h * 0.16, Theme.textSecondary)
    }

    function paintSolve(ctx, w, h) {
        paintScope(ctx, w * 0.28, h * 0.62, -Math.PI / 3, Theme.accent)
        ctx.strokeStyle = Theme.outline
        ctx.strokeRect(w * 0.48, h * 0.22, w * 0.4, h * 0.5)
        ctx.fillStyle = Theme.notice
        const dots = [[0.58, 0.34], [0.7, 0.42], [0.78, 0.3], [0.64, 0.55], [0.8, 0.58]]
        for (let i = 0; i < dots.length; i++) {
            ctx.beginPath()
            ctx.arc(dots[i][0] * w, dots[i][1] * h, 1.6, 0, Math.PI * 2)
            ctx.fill()
        }
        paintTag(ctx, "CATALOG", w * 0.52, h * 0.18, Theme.notice)
        paintTag(ctx, "WITHIN 2°", w * 0.08, h * 0.16, Theme.textSecondary)
    }

    function paintMoves(ctx, w, h) {
        const aziColor = axisColor(aziOk, hasResult)
        const altColor = axisColor(altOk, hasResult)
        const cx = w * 0.28
        const cy = h * 0.48
        const radius = Math.min(w * 0.18, h * 0.32)
        ctx.strokeStyle = Theme.outline
        ctx.lineWidth = 1.25
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.stroke()
        ctx.strokeStyle = aziColor
        ctx.fillStyle = aziColor
        if (!hasResult || Math.abs(aziErr) < 0.05) {
            ctx.beginPath()
            ctx.arc(cx, cy, 3, 0, Math.PI * 2)
            ctx.fill()
        } else {
            const clockwise = aziErr > 0
            const start = clockwise ? -0.6 : 0.6
            const end = clockwise ? 1.4 : -1.4
            ctx.beginPath()
            ctx.arc(cx, cy, radius * 0.72, start, end, !clockwise)
            ctx.stroke()
            const tip = clockwise ? end : end
            paintArrowHead(ctx, cx + Math.cos(tip) * radius * 0.72, cy + Math.sin(tip) * radius * 0.72, tip + (clockwise ? Math.PI / 2 : -Math.PI / 2), aziColor)
        }
        paintTag(ctx, "AZ", cx - 8, cy + radius + 14, aziColor)
        const sx = w * 0.72
        const sy = h * 0.58
        ctx.strokeStyle = Theme.outline
        ctx.strokeRect(sx - 22, sy - 10, 44, 16)
        ctx.strokeStyle = altColor
        ctx.beginPath()
        const up = altErr >= 0
        const y1 = up ? sy - 14 : sy + 14
        const y2 = up ? sy - 36 : sy + 28
        if (!hasResult || Math.abs(altErr) < 0.05) {
            ctx.fillStyle = altColor
            ctx.beginPath()
            ctx.arc(sx, sy - 2, 3, 0, Math.PI * 2)
            ctx.fill()
        } else {
            ctx.beginPath()
            ctx.moveTo(sx, y1)
            ctx.lineTo(sx, y2)
            ctx.stroke()
            paintArrowHead(ctx, sx, y2, up ? -Math.PI / 2 : Math.PI / 2, altColor)
        }
        paintTag(ctx, "ALT", sx - 10, h * 0.9, altColor)
        paintTag(ctx, "2° PASS", w * 0.06, h * 0.16, Theme.textSecondary)
    }

    function paintScope(ctx, x, y, angle, color) {
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(angle)
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.strokeRect(-18, -5, 28, 10)
        ctx.beginPath()
        ctx.moveTo(10, -5)
        ctx.lineTo(18, -8)
        ctx.lineTo(18, 8)
        ctx.lineTo(10, 5)
        ctx.stroke()
        ctx.restore()
    }

    function paintArrowHead(ctx, x, y, angle, color) {
        ctx.save()
        ctx.translate(x, y)
        ctx.rotate(angle)
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.moveTo(0, 0)
        ctx.lineTo(-7, -3.5)
        ctx.lineTo(-7, 3.5)
        ctx.closePath()
        ctx.fill()
        ctx.restore()
    }

    function paintTag(ctx, text, x, y, color) {
        ctx.fillStyle = color
        ctx.font = Theme.fontPx(10) + "px monospace"
        ctx.textBaseline = "top"
        ctx.fillText(text, x, y)
    }
}
