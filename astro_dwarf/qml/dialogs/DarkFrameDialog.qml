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
    readonly property string progressLine: {
        if (!capturing)
            return ""
        const devices = backend.devices || []
        for (let i = 0; i < devices.length; i++) {
            const item = devices[i]
            if (String(item.id || "") !== deviceId)
                continue
            if (String(item.activity || "") !== "dark")
                return "TAKING DARKS"
            const detail = String(item.activity_detail || "")
            const remain = item.telemetry ? Number(item.telemetry.dark_remaining_s || 0) : 0
            if (remain > 0)
                return "TAKING DARKS · " + (detail || "") + " · " + remain + "s LEFT"
            return detail ? "TAKING DARKS · " + detail : "TAKING DARKS"
        }
        return "TAKING DARKS"
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
        Text {
            visible: darkFrameDialog.capturing
            text: darkFrameDialog.progressLine
            color: Theme.warning
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSm
            font.letterSpacing: Theme.tracking1
            Layout.fillWidth: true
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
