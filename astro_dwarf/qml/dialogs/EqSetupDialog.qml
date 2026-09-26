import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Official DWARF EQ mode: point at the stars, set the wedge, plate-solve,
// then adjust and check again until both residuals are within 2°.
Dialog {
    id: eqSetupDialog
    objectName: "eqSetupDialog"
    property string phase: "stars"
    property string errorText: ""
    property bool sawSolving: false
    property bool suppressStop: false
    property var canRun: function(op) { return false }
    property var runAction: function(op, label) {}
    readonly property var device: backend.selectedDevice || ({})
    readonly property var telemetry: (device && device.telemetry) || ({})
    readonly property bool siteReady: !!(device && device.location_configured)
    readonly property real latitude: Number(device.latitude || 0)
    readonly property var pose: backend.eqSetupPose(latitude)
    readonly property bool aligned: !!telemetry.eq_ready
    readonly property bool solving: phase === "solving"
    readonly property color tone: aligned && phase === "result" ? Theme.success
                                   : (phase === "result" || phase === "adjust" ? Theme.warning : Theme.notice)
    readonly property string headingText: {
        if (phase === "stars")
            return "EQ MODE"
        if (phase === "gear")
            return "BEFORE YOU ALIGN"
        if (phase === "pose")
            return "SET THE WEDGE"
        if (phase === "solving")
            return "MEASURING"
        if (phase === "adjust")
            return "BE MORE PRECISE"
        return aligned ? "EQ ALIGNED" : "ADJUST THE WEDGE"
    }
    readonly property string bodyText: {
        if (phase === "stars")
            return "Point the telescope up at the stars. EQ solving plate-solves the sky, so a roof or a wall will not produce an alignment."
        if (phase === "gear")
            return "Use a stable tripod with a head that tilts and rotates. A compass and a level help when the pole is hidden. The tripod legs stay where they are for the rest of the alignment."
        if (phase === "pose")
            return siteReady ? String(pose.text || "") : "Set the observing site before EQ solving. The wedge tilt has to match your latitude."
        if (phase === "solving")
            return "The telescope is taking short pictures and comparing them to the star catalog."
        if (phase === "adjust")
            return "Make the moves below, lock the head, then check again. Leave the tripod legs where they are."
        if (!telemetry.eq_has_result)
            return "The plate-solve finished without an azimuth or altitude error."
        if (aligned)
            return "Within 2°. You can image. Be more precise until both read 0° for exposures of 30–120 seconds, and for a mosaic."
        return "Loosen the head, make both moves, then lock it. Do not move the tripod legs."
    }

    function openSetup() {
        eqSetupDialog.phase = "stars"
        eqSetupDialog.errorText = ""
        eqSetupDialog.sawSolving = false
        eqSetupDialog.suppressStop = false
        eqSetupDialog.open()
    }
    function startSolve() {
        if (!eqSetupDialog.siteReady || !eqSetupDialog.canRun("polar")) {
            eqSetupDialog.errorText = eqSetupDialog.siteReady
                    ? "EQ solving is unavailable while the telescope is busy."
                    : "Set the observing site before EQ solving."
            return
        }
        eqSetupDialog.errorText = ""
        eqSetupDialog.sawSolving = false
        eqSetupDialog.phase = "solving"
        eqSetupDialog.runAction("polar", "POLAR / EQ")
    }
    function finish() {
        eqSetupDialog.suppressStop = true
        eqSetupDialog.close()
    }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(560)
    height: Math.min(Theme.px(560), Math.max(Theme.px(480), body.implicitHeight + Theme.px(36)))
    padding: Theme.s4
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape
    onOpened: primaryBtn.forceActiveFocus()
    onRejected: {
        if (eqSetupDialog.suppressStop) {
            eqSetupDialog.suppressStop = false
            return
        }
        if (eqSetupDialog.phase === "solving" && eqSetupDialog.canRun("stop_polar"))
            eqSetupDialog.runAction("stop_polar", "POLAR / EQ")
    }

    Connections {
        target: backend
        function onCommandFeedback(deviceId, operation, ok) {
            if (!eqSetupDialog.visible || deviceId !== backend.selectedDeviceId)
                return
            if (operation === "polar" && !ok && eqSetupDialog.phase === "solving") {
                eqSetupDialog.phase = "pose"
                eqSetupDialog.errorText = "EQ solving did not start."
            }
        }
    }

    onTelemetryChanged: {
        if (!eqSetupDialog.visible || eqSetupDialog.phase !== "solving")
            return
        const state = String(eqSetupDialog.telemetry.eq_state || "")
        if (state === "running" || state === "solving") {
            eqSetupDialog.sawSolving = true
            return
        }
        if (eqSetupDialog.sawSolving && (state === "idle" || state === "stopped")) {
            eqSetupDialog.sawSolving = false
            eqSetupDialog.phase = "result"
            eqSetupDialog.errorText = ""
        }
    }

    background: DialogFrame { tone: eqSetupDialog.tone }
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.s3
        Accessible.name: eqSetupDialog.headingText
        Accessible.description: eqSetupDialog.bodyText
        Text {
            text: eqSetupDialog.headingText
            color: eqSetupDialog.tone
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            text: eqSetupDialog.bodyText
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        EqGuideArt {
            objectName: "eqGuide"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: Theme.px(148)
            phase: eqSetupDialog.phase
            aziErr: Number(eqSetupDialog.telemetry.eq_azi_err || 0)
            altErr: Number(eqSetupDialog.telemetry.eq_alt_err || 0)
            hasResult: !!eqSetupDialog.telemetry.eq_has_result
            aligned: eqSetupDialog.aligned
            tiltDeg: Number(eqSetupDialog.pose.tilt_deg || 0)
            hemisphere: String(eqSetupDialog.pose.hemisphere || "")
            siteReady: eqSetupDialog.siteReady
            aziText: String(eqSetupDialog.telemetry.eq_azi_text || "")
            aziAction: String(eqSetupDialog.telemetry.eq_azi_action || "")
            altText: String(eqSetupDialog.telemetry.eq_alt_text || "")
            altAction: String(eqSetupDialog.telemetry.eq_alt_action || "")
        }
        Text {
            visible: eqSetupDialog.errorText !== ""
            text: eqSetupDialog.errorText
            color: Theme.danger
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.s2
            HudButton {
                id: secondaryBtn
                objectName: "eqSecondary"
                visible: eqSetupDialog.phase !== "stars" && eqSetupDialog.phase !== "solving"
                text: {
                    if (eqSetupDialog.phase === "result")
                        return eqSetupDialog.aligned ? "BE MORE PRECISE" : "CLOSE"
                    if (eqSetupDialog.phase === "adjust")
                        return "BACK"
                    return "BACK"
                }
                Accessible.name: text
                onClicked: {
                    if (eqSetupDialog.phase === "gear")
                        eqSetupDialog.phase = "stars"
                    else if (eqSetupDialog.phase === "pose")
                        eqSetupDialog.phase = "gear"
                    else if (eqSetupDialog.phase === "adjust")
                        eqSetupDialog.phase = "result"
                    else if (eqSetupDialog.phase === "result" && eqSetupDialog.aligned)
                        eqSetupDialog.phase = "adjust"
                    else
                        eqSetupDialog.finish()
                }
            }
            HudButton {
                id: primaryBtn
                objectName: "eqPrimary"
                text: {
                    if (eqSetupDialog.phase === "stars")
                        return "CONTINUE"
                    if (eqSetupDialog.phase === "gear")
                        return "I'M READY"
                    if (eqSetupDialog.phase === "pose")
                        return "NEXT"
                    if (eqSetupDialog.phase === "solving")
                        return "STOP"
                    if (eqSetupDialog.phase === "adjust")
                        return "I'M READY"
                    return eqSetupDialog.aligned ? "GOT IT" : "BE MORE PRECISE"
                }
                enabled: eqSetupDialog.phase !== "pose" || eqSetupDialog.siteReady
                buttonColor: eqSetupDialog.tone === Theme.warning ? Theme.fillWarning
                             : (eqSetupDialog.tone === Theme.success ? Theme.fillSuccess : Theme.surfaceHigh)
                foregroundColor: eqSetupDialog.tone === Theme.notice ? Theme.textPrimary : eqSetupDialog.tone
                Accessible.name: text
                tooltip: eqSetupDialog.phase === "pose" && !eqSetupDialog.siteReady
                         ? "Set the observing site before EQ solving"
                         : ""
                onClicked: {
                    if (eqSetupDialog.phase === "stars")
                        eqSetupDialog.phase = "gear"
                    else if (eqSetupDialog.phase === "gear")
                        eqSetupDialog.phase = "pose"
                    else if (eqSetupDialog.phase === "pose" || eqSetupDialog.phase === "adjust")
                        eqSetupDialog.startSolve()
                    else if (eqSetupDialog.phase === "solving") {
                        if (eqSetupDialog.canRun("stop_polar"))
                            eqSetupDialog.runAction("stop_polar", "POLAR / EQ")
                        eqSetupDialog.finish()
                    } else if (eqSetupDialog.aligned)
                        eqSetupDialog.finish()
                    else
                        eqSetupDialog.phase = "adjust"
                }
            }
        }
    }
}
