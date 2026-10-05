import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: eqDialog
    objectName: "deviceMosaicEqDialog"
    property string deviceId: ""
    signal runRequested()
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(440)
    height: Math.max(Theme.px(210), headingLabel.implicitHeight + summaryLabel.implicitHeight + Theme.px(96))
    padding: Theme.s4
    onOpened: cancelBtn.forceActiveFocus()
    background: DialogFrame { tone: Theme.notice }
    function runEq() {
        const id = eqDialog.deviceId
        eqDialog.close()
        if (id !== "" && id !== backend.selectedDeviceId)
            backend.selectDevice(id)
        eqDialog.runRequested()
    }
    function harnessConfirm(action) {
        if (!eqDialog.visible)
            return "closed"
        if (String(action || "") === "cancel") {
            eqDialog.close()
            return "cancel"
        }
        eqDialog.runEq()
        return "accept"
    }
    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: "EQ REQUIRED"
        Accessible.description: summaryLabel.text
        Text {
            id: headingLabel
            text: "EQ REQUIRED"
            color: Theme.notice
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            id: summaryLabel
            text: "A device mosaic needs equatorial alignment. The telescope keeps the field from rotating between panes only after EQ solving is within 2°. Run EQ, or cancel this mosaic."
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton {
                id: cancelBtn
                objectName: "deviceMosaicEqCancel"
                text: "CANCEL"
                tooltip: "Leave the device mosaic unstarted"
                onClicked: eqDialog.close()
            }
            HudButton {
                objectName: "deviceMosaicEqRun"
                text: "RUN EQ"
                tooltip: "Open equatorial alignment"
                buttonColor: Theme.surfaceHigh
                foregroundColor: Theme.notice
                onClicked: eqDialog.runEq()
            }
        }
    }
}
