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
    property string operation: ""
    property string summary: ""
    property string kind: "device"
    property string headingText: "CONFIRM COMMAND"
    property string confirmLabel: "CONFIRM"
    property var pendingIds: []
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 420
    height: 196
    padding: 16
    background: DialogFrame { tone: Theme.danger }
    contentItem: ColumnLayout {
        spacing: 12
        Text { text: confirmDialog.headingText; color: Theme.danger; font.pixelSize: 16; font.letterSpacing: 1.4 }
        Text { text: confirmDialog.summary; color: Theme.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { text: "CANCEL"; onClicked: confirmDialog.close() }
            HudButton {
                text: confirmDialog.confirmLabel
                busyText: "WORKING…"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: {
                    if (confirmDialog.kind === "clearHistory")
                        backend.clearHistory()
                    else if (confirmDialog.kind === "deleteSessions")
                        backend.deleteSessions(confirmDialog.pendingIds)
                    else if (confirmDialog.kind === "deleteTemplates")
                        backend.deleteTemplates(confirmDialog.pendingIds)
                    else if (confirmDialog.kind === "deleteHistory")
                        backend.deleteHistoryRecords(confirmDialog.pendingIds)
                    else
                        backend.deviceAction(backend.selectedDeviceId, confirmDialog.operation)
                    confirmDialog.close()
                }
            }
        }
    }
}
