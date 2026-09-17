import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import ".."
import "../components"

Dialog {
    id: confirmDialog
    objectName: "confirmDialog"
    property string operation: ""
    property string summary: ""
    property string kind: "device"
    property string headingText: "CONFIRM COMMAND"
    property string confirmLabel: "CONFIRM"
    property var pendingIds: []
    signal viewerCloseRequested()
    function applyConfirm() {
        if (confirmDialog.kind === "clearHistory")
            backend.clearHistory()
        else if (confirmDialog.kind === "clearHistoryDevice")
            backend.clearHistoryForDevice((confirmDialog.pendingIds && confirmDialog.pendingIds[0]) || backend.selectedDeviceId)
        else if (confirmDialog.kind === "deleteSessions")
            backend.deleteSessions(confirmDialog.pendingIds)
        else if (confirmDialog.kind === "deleteTemplates")
            backend.deleteTemplates(confirmDialog.pendingIds)
        else if (confirmDialog.kind === "deleteHistory")
            backend.deleteHistoryRecords(confirmDialog.pendingIds)
        else if (confirmDialog.kind === "deleteDevice")
            backend.deleteDevice((confirmDialog.pendingIds && confirmDialog.pendingIds[0]) || backend.selectedDeviceId)
        else if (confirmDialog.kind === "deleteMedia") {
            confirmDialog.viewerCloseRequested()
            backend.deleteMedia(confirmDialog.pendingIds)
        }
        else
            backend.deviceAction(backend.selectedDeviceId, confirmDialog.operation)
        confirmDialog.close()
    }
    function harnessConfirm(action) {
        if (!confirmDialog.visible)
            return "closed"
        if (String(action || "") === "cancel") {
            confirmDialog.close()
            return "cancel"
        }
        confirmDialog.applyConfirm()
        return "accept"
    }
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 420
    height: Math.max(196, headingLabel.implicitHeight + summaryLabel.implicitHeight + 88)
    padding: Theme.s4
    onOpened: cancelBtn.forceActiveFocus()
    background: DialogFrame { tone: Theme.danger }
    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: confirmDialog.headingText
        Accessible.description: confirmDialog.summary
        Text { id: headingLabel; text: confirmDialog.headingText; color: Theme.danger; font.pixelSize: Theme.fontLg; font.letterSpacing: Theme.tracking2 }
        Text { id: summaryLabel; text: confirmDialog.summary; color: Theme.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { id: cancelBtn; objectName: "confirmCancel"; text: "CANCEL"; onClicked: confirmDialog.close() }
            HudButton {
                objectName: "confirmAccept"
                text: confirmDialog.confirmLabel
                busyText: "WORKING…"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: confirmDialog.applyConfirm()
            }
        }
    }
}
