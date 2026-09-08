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
    id: sessionDialog
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(root.width - 80, 900)
    // size to the form so the dialog doesn't float in a sea of empty surface
    height: Math.min(root.height - 80, Math.max(420, contentItem.implicitHeight + 40))
    property string editingId: ""
    property bool editingTemplate: false
    property var templateMembers: []
    property int paneIndex: 0
    property bool syncingPane: false
    readonly property int paneCount: templateMembers.length
    readonly property bool multiPaneTemplate: editingTemplate && paneCount > 1
    padding: 0

    function cloneValue(value) {
        return JSON.parse(JSON.stringify(value || {}))
    }
    function paneLabel(item, index) {
        const name = (item && (item.pane_name || item.name)) || ("Pane " + (index + 1))
        return "Pane " + (index + 1) + " · " + name
    }
    function paneChoices() {
        const items = templateMembers
        const labels = []
        for (let i = 0; i < items.length; i++)
            labels.push(sessionDialog.paneLabel(items[i], i))
        return labels
    }
    function flagOn(value, fallback) {
        if (value === undefined || value === null)
            return fallback
        return !!value
    }
    function setChecked(box, value) {
        box.checkState = value ? Qt.Checked : Qt.Unchecked
    }
    function applyWorkflowChecks(workflow) {
        const w = workflow || {}
        setChecked(calibrate, sessionDialog.flagOn(w.calibrate, true))
        setChecked(autofocus, sessionDialog.flagOn(w.autofocus, true))
        setChecked(infiniteFocus, sessionDialog.flagOn(w.infinite_focus, false))
        setChecked(polar, sessionDialog.flagOn(w.polar_align, false))
        setChecked(doGoto, sessionDialog.flagOn(w.goto, true))
    }
    function workflowFromForm(existing) {
        const current = existing || {}
        return {
            calibrate: calibrate.checked,
            autofocus: autofocus.checked,
            infinite_focus: infiniteFocus.checked,
            polar_align: polar.checked,
            goto: doGoto.checked,
            wait_before_seconds: current.wait_before_seconds,
            wait_after_seconds: current.wait_after_seconds
        }
    }
    function loadPaneCoordinates(data) {
        sessionName.text = data.pane_name || data.name || ""
        const target = data.target || {}
        targetName.text = target.name || data.target_name || ""
        const kind = target.kind || "equatorial"
        targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
        ra.text = target.ra_hours != null && target.ra_hours !== "" ? target.ra_hours : ""
        dec.text = target.dec_degrees != null && target.dec_degrees !== "" ? target.dec_degrees : ""
        sessionDialog.applyWorkflowChecks(data.workflow)
    }
    function stashCurrentPane() {
        if (!editingTemplate || paneCount === 0)
            return
        const members = templateMembers.slice()
        const current = sessionDialog.cloneValue(members[paneIndex] || {})
        current.id = editingId || current.id
        current.pane_name = sessionName.text
        current.name = sessionName.text
        current.target = {
            name: targetName.text,
            kind: targetType.currentText,
            ra_hours: ra.text,
            dec_degrees: dec.text
        }
        current.workflow = sessionDialog.workflowFromForm(current.workflow)
        members[paneIndex] = current
        templateMembers = members
    }
    function showPane(index) {
        if (syncingPane || !editingTemplate || index < 0 || index >= paneCount || index === paneIndex)
            return
        syncingPane = true
        stashCurrentPane()
        paneIndex = index
        editingId = templateMembers[index].id || editingId
        loadPaneCoordinates(templateMembers[index])
        panePicker.currentIndex = index
        syncingPane = false
    }
    function memberPayloads() {
        stashCurrentPane()
        const shared = sessionDialog.formPayload()
        const items = templateMembers
        const result = []
        for (let i = 0; i < items.length; i++) {
            const pane = items[i] || {}
            const target = pane.target || {}
            const workflow = pane.workflow || {}
            result.push(Object.assign({}, shared, {
                id: pane.id || "",
                name: pane.pane_name || pane.name || shared.name,
                target: target.name || shared.target,
                target_kind: target.kind || shared.target_kind,
                ra: target.ra_hours != null ? String(target.ra_hours) : "",
                dec: target.dec_degrees != null ? String(target.dec_degrees) : "",
                calibrate: sessionDialog.flagOn(workflow.calibrate, shared.calibrate),
                autofocus: sessionDialog.flagOn(workflow.autofocus, shared.autofocus),
                infinite_focus: sessionDialog.flagOn(workflow.infinite_focus, shared.infinite_focus),
                polar_align: sessionDialog.flagOn(workflow.polar_align, shared.polar_align),
                goto: sessionDialog.flagOn(workflow.goto, shared.goto)
            }))
        }
        return result
    }

    function fillForm(data) {
        sessionName.text = data.pane_name || data.name || ""
        targetName.text = (data.target && data.target.name) ? data.target.name : (data.target_name || "")
        const kind = data.target ? data.target.kind : "equatorial"
        targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
        ra.text = data.target && data.target.ra_hours != null ? data.target.ra_hours : ""
        dec.text = data.target && data.target.dec_degrees != null ? data.target.dec_degrees : ""
        exposure.text = data.camera.exposure_seconds
        gain.text = data.camera.gain
        frames.text = data.camera.frame_count
        camera.currentIndex = data.camera.camera === "wide" ? 1 : 0
        binning.currentIndex = Math.max(0, ["1", "2"].indexOf(String(data.camera.binning)))
        const ir = data.camera.ir_filter || "VIS Filter"
        irFilter.currentIndex = Math.max(0, ["VIS Filter", "Astro Filter", "Duo-Band Filter", "VIS"].indexOf(ir) % 3)
        rows.text = data.mosaic.rows
        columns.text = data.mosaic.columns
        rotation.text = data.mosaic.rotation_degrees
        hScale.text = data.mosaic.horizontal_scale
        vScale.text = data.mosaic.vertical_scale
        waitBefore.text = data.workflow.wait_before_seconds
        waitAfter.text = data.workflow.wait_after_seconds
        notes.text = data.notes || ""
        sessionDialog.applyWorkflowChecks(data.workflow)
        saveTemplate.checked = false
    }
    function formPayload() {
        return {
            id: sessionDialog.editingId, name: sessionName.text, target: targetName.text,
            target_kind: targetType.currentText, ra: ra.text, dec: dec.text,
            scheduled_start: startTime.text, device_id: backend.selectedDeviceId,
            camera: camera.currentIndex === 1 ? "wide" : "tele", exposure: Number(exposure.text),
            gain: Number(gain.text), frame_count: Number(frames.text), binning: Number(binning.currentText),
            ir_filter: irFilter.currentText, rows: Number(rows.text), columns: Number(columns.text),
            rotation: Number(rotation.text), horizontal_scale: Number(hScale.text), vertical_scale: Number(vScale.text),
            wait_before: Number(waitBefore.text), wait_after: Number(waitAfter.text), notes: notes.text,
            calibrate: calibrate.checked, autofocus: autofocus.checked, infinite_focus: infiniteFocus.checked,
            polar_align: polar.checked, goto: doGoto.checked, save_template: saveTemplate.checked
        }
    }
    function openForDate(day) {
        editingId = ""
        editingTemplate = false
        templateMembers = []
        paneIndex = 0
        sessionName.text = ""
        targetName.text = ""
        targetType.currentIndex = 0
        ra.text = ""
        dec.text = ""
        startTime.text = day + "T22:00"
        exposure.text = "15"
        gain.text = "80"
        frames.text = "120"
        binning.currentIndex = 0
        irFilter.currentIndex = 0
        camera.currentIndex = 0
        rows.text = "1"
        columns.text = "1"
        rotation.text = "0"
        hScale.text = "150"
        vScale.text = "150"
        waitBefore.text = "0"
        waitAfter.text = "10"
        notes.text = ""
        calibrate.checked = true
        autofocus.checked = true
        infiniteFocus.checked = false
        polar.checked = false
        doGoto.checked = true
        saveTemplate.checked = false
        open()
    }
    function openExisting(data) {
        editingId = data.id
        editingTemplate = false
        templateMembers = []
        paneIndex = 0
        fillForm(data)
        startTime.text = String(data.scheduled_start).substring(0, 16)
        open()
    }
    function openTemplate(data) {
        const members = data.members && data.members.length ? data.members : [data]
        const cloned = []
        for (let i = 0; i < members.length; i++)
            cloned.push(sessionDialog.cloneValue(members[i]))
        editingTemplate = true
        templateMembers = cloned
        paneIndex = 0
        editingId = cloned[0].id || data.id
        fillForm(data)
        loadPaneCoordinates(cloned[0])
        startTime.text = ""
        syncingPane = true
        panePicker.model = sessionDialog.paneChoices()
        panePicker.currentIndex = 0
        syncingPane = false
        open()
    }

    background: DialogFrame {}
    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Text { text: sessionDialog.editingTemplate ? "EDIT TEMPLATE" : (sessionDialog.editingId ? "EDIT SESSION" : "NEW SESSION"); color: Theme.accent; font.pixelSize: 20; font.letterSpacing: 2; Layout.fillWidth: true }
            HudButton { text: "×"; implicitWidth: 40; onClicked: sessionDialog.close() }
        }
        RowLayout {
            visible: sessionDialog.multiPaneTemplate
            Layout.fillWidth: true
            spacing: 8
            HudButton {
                text: "‹ PREV"
                busyMs: 0
                enabled: sessionDialog.paneIndex > 0
                onClicked: sessionDialog.showPane(sessionDialog.paneIndex - 1)
            }
            HudCombo {
                id: panePicker
                Layout.fillWidth: true
                model: []
                onActivated: sessionDialog.showPane(currentIndex)
            }
            HudButton {
                text: "NEXT ›"
                busyMs: 0
                enabled: sessionDialog.paneIndex < sessionDialog.paneCount - 1
                onClicked: sessionDialog.showPane(sessionDialog.paneIndex + 1)
            }
        }
        Text {
            visible: sessionDialog.multiPaneTemplate
            text: "Each pane has its own name, coordinates, and workflow. Camera, mosaic, and wait apply to every pane."
            color: Theme.textSecondary
            font.pixelSize: 12
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 10
            rowSpacing: 8
            FieldLabel { text: "SESSION NAME" }
            HudField { id: sessionName; Layout.fillWidth: true; Layout.columnSpan: 2 }
            FieldLabel { text: "TARGET TYPE" }
            HudCombo { id: targetType; model: ["equatorial", "solar", "none"]; Layout.fillWidth: true }
            HudField { id: targetName; placeholderText: "Target name"; Layout.fillWidth: true }
            FieldLabel { text: "RA HOURS" }
            HudField { id: ra; Layout.fillWidth: true }
            HudField { id: dec; placeholderText: "Dec degrees"; Layout.fillWidth: true }
            FieldLabel { text: "START"; visible: !sessionDialog.editingTemplate }
            HudField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2; visible: !sessionDialog.editingTemplate }
            FieldLabel { text: "CAMERA" }
            HudCombo { id: camera; model: ["Tele", "Wide"]; Layout.fillWidth: true; Layout.columnSpan: currentIndex === 1 ? 2 : 1 }
            HudCombo {
                id: irFilter
                visible: camera.currentIndex === 0
                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                Layout.fillWidth: true
            }
            FieldLabel { text: "EXPOSURE" }
            HudField { id: exposure; Layout.fillWidth: true }
            HudField { id: gain; placeholderText: "Gain"; Layout.fillWidth: true }
            FieldLabel { text: "FRAMES" }
            HudField { id: frames; Layout.fillWidth: true }
            HudCombo { id: binning; model: ["1", "2"]; Layout.fillWidth: true }
            FieldLabel { text: "MOSAIC" }
            HudField { id: rows; placeholderText: "Rows"; Layout.fillWidth: true }
            HudField { id: columns; placeholderText: "Columns"; Layout.fillWidth: true }
            FieldLabel { text: "ROTATION / SCALE" }
            HudField { id: rotation; placeholderText: "Rotation °"; Layout.fillWidth: true }
            RowLayout {
                HudField { id: hScale; placeholderText: "H scale"; Layout.fillWidth: true }
                HudField { id: vScale; placeholderText: "V scale"; Layout.fillWidth: true }
            }
            FieldLabel { text: "WAIT S" }
            HudField { id: waitBefore; placeholderText: "Before"; Layout.fillWidth: true }
            HudField { id: waitAfter; placeholderText: "After"; Layout.fillWidth: true }
            FieldLabel { text: "NOTES" }
            HudField { id: notes; Layout.fillWidth: true; Layout.columnSpan: 2 }
            FieldLabel { text: "WORKFLOW"; Layout.alignment: Qt.AlignTop; Layout.topMargin: 8 }
            Flow {
                Layout.fillWidth: true
                Layout.columnSpan: 2
                Layout.topMargin: 4
                spacing: 22
                HudCheck { id: calibrate; text: "Calibrate" }
                HudCheck { id: autofocus; text: "Auto focus" }
                HudCheck { id: infiniteFocus; text: "Infinity focus" }
                HudCheck { id: polar; text: "Polar / EQ" }
                HudCheck { id: doGoto; text: "GOTO" }
                HudCheck { id: saveTemplate; text: "Save template"; visible: !sessionDialog.editingTemplate }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { text: "CANCEL"; onClicked: sessionDialog.close() }
            HudButton {
                text: sessionDialog.editingTemplate ? "SAVE TEMPLATE" : "SAVE SESSION"
                busyText: "SAVING…"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: {
                    if (sessionDialog.editingTemplate) {
                        const payload = sessionDialog.formPayload()
                        if (sessionDialog.paneCount > 1)
                            payload.members = sessionDialog.memberPayloads()
                        backend.saveTemplate(JSON.stringify(payload))
                    } else {
                        backend.saveSession(JSON.stringify(sessionDialog.formPayload()))
                    }
                    sessionDialog.close()
                }
            }
        }
    }
}
