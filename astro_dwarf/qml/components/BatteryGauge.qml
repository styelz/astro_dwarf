import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: gauge
    property int percent: -1
    property bool charging: false
    property string tone: Util.batteryTone(percent)
    readonly property color toneColor: percent < 0 ? Theme.muted : Util.toneColor(tone)
    property real shown: Math.max(0, percent)
    Behavior on shown { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
    implicitWidth: 72
    implicitHeight: 72
    Canvas {
        anchors.fill: parent
        readonly property real value: gauge.shown
        readonly property color ring: gauge.toneColor
        onValueChanged: requestPaint()
        onRingChanged: requestPaint()
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const cx = width / 2, cy = height / 2, r = Math.min(width, height) / 2 - 5
            const start = Math.PI * 0.75, span = Math.PI * 1.5
            ctx.lineCap = "round"
            ctx.lineWidth = 5
            ctx.strokeStyle = Theme.hsl(0.062, 0.450, 0.157)
            ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span); ctx.stroke()
            // tick marks
            ctx.lineWidth = 1
            ctx.strokeStyle = Theme.hsl(0.050, 0.400, 0.275)
            for (let i = 0; i <= 10; i++) {
                const a = start + span * i / 10
                ctx.beginPath()
                ctx.moveTo(cx + Math.cos(a) * (r - 8), cy + Math.sin(a) * (r - 8))
                ctx.lineTo(cx + Math.cos(a) * (r - 11), cy + Math.sin(a) * (r - 11))
                ctx.stroke()
            }
            if (gauge.percent >= 0) {
                ctx.lineWidth = 5
                ctx.strokeStyle = ring
                ctx.shadowColor = ring
                ctx.shadowBlur = 8
                ctx.beginPath(); ctx.arc(cx, cy, r, start, start + span * Math.min(1, value / 100)); ctx.stroke()
            }
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
    }
    Column {
        anchors.centerIn: parent
        anchors.verticalCenterOffset: 2
        spacing: -2
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: gauge.percent >= 0 ? gauge.percent + "%" : "—"
            color: gauge.percent >= 0 ? Theme.textPrimary : Theme.muted
            font.pixelSize: Math.max(11, Math.min(16, Math.round(gauge.width * 0.22)))
            font.family: Theme.fontMono
            font.bold: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: gauge.charging ? "⚡ CHG" : "BATT"
            color: gauge.charging ? Theme.warning : Theme.textSecondary
            font.pixelSize: gauge.width >= 52 ? 8 : 7
            font.letterSpacing: 1
            font.bold: true
            SequentialAnimation on opacity {
                running: gauge.charging
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.35; duration: 700 }
                NumberAnimation { from: 0.35; to: 1; duration: 700 }
            }
        }
    }
}
