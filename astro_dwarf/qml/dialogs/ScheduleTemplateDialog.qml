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
    id: scheduleDialog
    property string templateId: ""
    property string templateName: ""
    readonly property bool canSchedule: templateId.length > 0 && startTime.text.trim().length > 0
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 420
    padding: 16
    height: Math.min(root.height - 60, scheduleColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
    function defaultStart() {
        return Qt.formatDate(new Date(), "yyyy-MM-dd") + "T22:00"
    }
    function confirm() {
        if (!canSchedule)
            return
        if (backend.scheduleTemplate(templateId, startTime.text.trim()))
            close()
    }
    function openFor(data) {
        const item = data || ({})
        templateId = String(item.id || "")
        templateName = String(item.name || item.target_name || "template")
        startTime.text = scheduleDialog.defaultStart()
        open()
        startTime.forceActiveFocus()
        startTime.selectAll()
    }
    contentItem: ColumnLayout {
        id: scheduleColumn
        spacing: 12
        Text { text: "SCHEDULE TEMPLATE"; color: Theme.accent; font.pixelSize: 16; font.letterSpacing: 1.4 }
        Text {
            text: "Choose a start time for " + scheduleDialog.templateName + "."
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        FieldLabel { text: "START" }
        HudField {
            id: startTime
            Layout.fillWidth: true
            placeholderText: "yyyy-MM-ddTHH:mm"
            onAccepted: scheduleDialog.confirm()
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { text: "CANCEL"; onClicked: scheduleDialog.close() }
            HudButton {
                text: "SCHEDULE"
                enabled: scheduleDialog.canSchedule
                busyText: "SCHEDULING…"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: scheduleDialog.confirm()
            }
        }
    }
}
