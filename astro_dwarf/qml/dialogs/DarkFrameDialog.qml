import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: darkFrameDialog
    objectName: "darkFrameDialog"
    property int token: 0
    property string phase: "ask"
    property string headingText: "DARK FRAMES"
    property string summary: ""
    property string steps: ""
    property string cameraLabel: ""
    property string exposureText: ""
    property string gainText: ""
    property string resolutionText: ""
    property string temperatureText: ""
    property int frames: 10
    property int done: 0
    property int frameElapsed: 0
    property int frameSeconds: 0
    property bool gainOk: true
    property bool exposureOk: true
    property string blockReason: ""
    property string errorText: ""
    property string deviceId: ""
    property bool suppressReply: false
    readonly property bool capturing: phase === "capturing"
    readonly property bool canTake: gainOk && exposureOk && !capturing
    readonly property string settingsLine: cameraLabel + " · " + exposureText + " · GAIN " + gainText
        + " · " + resolutionText + " · " + temperatureText + " · " + frames + " FRAMES"
    readonly property real darkProgress: {
        if (!capturing || done <= 0 || frames <= 0)
            return -1
        const frac = frameSeconds > 0 ? Math.min(1, frameElapsed / frameSeconds) : 0
        return Math.min(0.99, Math.max(0.02, ((done - 1) + frac) / frames))
    }
    readonly property string progressLine: {
        if (!capturing)
            return ""
        if (done <= 0)
            return "STARTING"
        const clock = frameSeconds > 0 ? ("  " + frameElapsed + "s / " + frameSeconds + "s") : ""
        return done + " / " + frames + clock
    }

    function applyPrompt(payload) {
        const data = payload || ({})
        if (String(data.phase || "") === "closed") {
            darkFrameDialog.dismiss()
            return
        }
        darkFrameDialog.token = Number(data.token || 0)
        darkFrameDialog.phase = String(data.phase || "ask")
        darkFrameDialog.headingText = String(data.heading || "DARK FRAMES")
        darkFrameDialog.summary = String(data.summary || "")
        darkFrameDialog.steps = String(data.steps || "")
        darkFrameDialog.cameraLabel = String(data.camera || "")
        darkFrameDialog.exposureText = String(data.exposure || "—")
        darkFrameDialog.gainText = String(data.gain || "—")
        darkFrameDialog.resolutionText = String(data.resolution || "—")
        darkFrameDialog.temperatureText = String(data.temperature || "—")
        darkFrameDialog.frames = Number(data.frames || 10)
        darkFrameDialog.done = Number(data.done || 0)
        darkFrameDialog.frameElapsed = Number(data.elapsed_s || 0)
        darkFrameDialog.frameSeconds = Number(data.frame_s || 0)
        darkFrameDialog.gainOk = data.gain_ok !== false
        darkFrameDialog.exposureOk = data.exposure_ok !== false
        darkFrameDialog.blockReason = String(data.block_reason || "")
        darkFrameDialog.errorText = String(data.error || "")
        darkFrameDialog.deviceId = String(data.device_id || "")
        if (!darkFrameDialog.visible)
            darkFrameDialog.open()
    }
    function dismiss() {
        if (!darkFrameDialog.visible)
            return
        darkFrameDialog.suppressReply = true
        darkFrameDialog.close()
    }
    function reply(choice) {
        if (!darkFrameDialog.token)
            return
        if (choice === "capture") {
            darkFrameDialog.phase = "capturing"
            darkFrameDialog.errorText = ""
        }
        backend.answerDarkPrompt(darkFrameDialog.token, choice)
    }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(480)
    height: Math.max(Theme.px(280), body.implicitHeight + Theme.px(48))
    padding: Theme.s4
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape
    onOpened: cancelBtn.forceActiveFocus()
    onRejected: {
        if (darkFrameDialog.suppressReply) {
            darkFrameDialog.suppressReply = false
            return
        }
        darkFrameDialog.reply("cancel")
    }
    background: DialogFrame { tone: Theme.warning }
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.s3
        Accessible.name: darkFrameDialog.headingText
        Accessible.description: darkFrameDialog.steps
        Text {
            text: darkFrameDialog.headingText
            color: Theme.warning
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            text: darkFrameDialog.summary
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Text {
            text: darkFrameDialog.steps
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Text {
            text: darkFrameDialog.settingsLine
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSm
            font.letterSpacing: Theme.tracking1
            Layout.fillWidth: true
        }
        HudMeter {
            visible: darkFrameDialog.capturing
            running: darkFrameDialog.capturing
            progress: darkFrameDialog.darkProgress
            text: darkFrameDialog.progressLine
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
        }
        Text {
            visible: !darkFrameDialog.capturing && darkFrameDialog.blockReason !== "" && !darkFrameDialog.canTake
            text: darkFrameDialog.blockReason
            color: Theme.warning
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Text {
            visible: !darkFrameDialog.capturing && darkFrameDialog.errorText !== ""
            text: darkFrameDialog.errorText
            color: Theme.danger
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.s2
            HudButton {
                objectName: "darkTake"
                text: "TAKE DARKS"
                enabled: darkFrameDialog.canTake
                buttonColor: Theme.fillWarning
                foregroundColor: Theme.warning
                Accessible.name: "Take darks"
                tooltip: "Cover the lens as described, then capture 10 matching dark frames"
                onClicked: darkFrameDialog.reply("capture")
            }
            HudButton {
                objectName: "darkContinue"
                text: "CONTINUE"
                enabled: !darkFrameDialog.capturing
                Accessible.name: "Continue without darks"
                tooltip: "Stack without matching dark frames"
                onClicked: darkFrameDialog.reply("continue")
            }
            HudButton {
                id: cancelBtn
                objectName: "darkCancel"
                text: "CANCEL"
                Accessible.name: "Cancel stack"
                tooltip: "Do not start this stack"
                onClicked: darkFrameDialog.reply("cancel")
            }
        }
    }
}
