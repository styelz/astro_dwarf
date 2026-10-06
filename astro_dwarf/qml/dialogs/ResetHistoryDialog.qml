import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: resetDialog
    objectName: "resetHistoryDialog"
    property var sessionIds: []
    property int historyCount: 0
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(460)
    padding: Theme.s4
    height: Math.max(Theme.px(210), headingLabel.implicitHeight + summaryLabel.implicitHeight + Theme.px(96))
    background: DialogFrame {}
    function matchingHistory(ids) {
        const wanted = {}
        const list = ids || []
        for (let i = 0; i < list.length; i++) {
            const id = String(list[i] || "")
            if (id)
                wanted[id] = true
        }
        const rows = backend.history || []
        const found = []
        for (let i = 0; i < rows.length; i++) {
            const row = rows[i]
            const sessionId = String((row && row.session_id) || "")
            if (sessionId && wanted[sessionId])
                found.push(row.id)
        }
        return found
    }
    function openFor(ids) {
        const raw = Array.isArray(ids) ? ids : [ids]
        const list = []
        const seen = {}
        for (let i = 0; i < raw.length; i++) {
            const id = String(raw[i] || "").trim()
            if (!id || seen[id])
                continue
            seen[id] = true
            list.push(id)
        }
        if (!list.length)
            return
        sessionIds = list
        historyCount = resetDialog.matchingHistory(list).length
        open()
    }
    function keep() {
        backend.resetSessions(resetDialog.sessionIds, false)
        close()
    }
    function discard() {
        if (resetDialog.historyCount < 1)
            return
        backend.resetSessions(resetDialog.sessionIds, true)
        close()
    }
    contentItem: ColumnLayout {
        spacing: Theme.s3
        Text {
            id: headingLabel
            text: "RESET SESSION"
            color: Theme.accent
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            id: summaryLabel
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: Theme.textPrimary
            text: resetDialog.historyCount > 0
                  ? "Reset puts "
                    + (resetDialog.sessionIds.length === 1 ? "this session" : "these sessions")
                    + " back on the plan. Keep the recorded run on History, or discard it."
                  : "Reset puts "
                    + (resetDialog.sessionIds.length === 1 ? "this session" : "these sessions")
                    + " back on the plan. There is no recorded run to discard."
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton {
                objectName: "resetCancel"
                text: "CANCEL"
                onClicked: resetDialog.close()
            }
            HudButton {
                objectName: "resetDiscard"
                text: "DISCARD"
                enabled: resetDialog.historyCount > 0
                tooltip: resetDialog.historyCount > 0 ? "Delete the recorded run, then put the session back on the plan" : "No recorded run"
                busyText: "DISCARDING…"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: resetDialog.discard()
            }
            HudButton {
                objectName: "resetKeep"
                text: "KEEP"
                tooltip: "Put the session back on the plan and leave the recorded run on History"
                busyText: "RESETTING…"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: resetDialog.keep()
            }
        }
    }
}
