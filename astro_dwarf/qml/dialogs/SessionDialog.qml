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
    property string editingAnchorId: ""
    property string editingDeviceId: ""
    property bool editingTemplate: false
    property bool bulkMode: false
    property bool bulkTemplates: false
    property var bulkIds: []
    property var templateMembers: []
    property var paneSelected: []
    property var dirtyFields: ({})
    property int paneIndex: 0
    property bool syncingPane: false
    property bool syncingCommon: false
    readonly property int paneCount: templateMembers.length
    readonly property bool multiPane: paneCount > 1
    readonly property int selectedPaneCount: {
        const flags = paneSelected || []
        let count = 0
        for (let i = 0; i < flags.length; i++) {
            if (flags[i])
                count++
        }
        return count
    }
    readonly property bool commonMulti: bulkMode || (multiPane && selectedPaneCount > 1)
    readonly property bool uniqueVisible: !bulkMode
    readonly property bool mosaicVisible: !bulkMode
    readonly property bool dirty: Object.keys(dirtyFields || {}).length > 0
    readonly property bool focusedPaneSelected: {
        selectedPaneCount
        paneIndex
        return !!(paneSelected && paneSelected[paneIndex])
    }
    padding: 0

    QtObject {
        id: paneFlags
        property bool calibrate: true
        property bool autofocus: true
        property bool infiniteFocus: false
        property bool polar: false
        property bool doGoto: true
    }

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
    function workflowOf(item) {
        const w = (item && item.workflow) || {}
        return {
            calibrate: sessionDialog.flagOn(w.calibrate, true),
            autofocus: sessionDialog.flagOn(w.autofocus, true),
            infinite_focus: sessionDialog.flagOn(w.infinite_focus, false),
            polar_align: sessionDialog.flagOn(w.polar_align, false),
            goto: sessionDialog.flagOn(w.goto, true),
            wait_before_seconds: w.wait_before_seconds,
            wait_after_seconds: w.wait_after_seconds
        }
    }
    function cameraOf(item) {
        const cam = (item && item.camera) || {}
        return {
            camera: cam.camera === "wide" ? "wide" : "tele",
            exposure_seconds: cam.exposure_seconds,
            gain: cam.gain,
            frame_count: cam.frame_count,
            binning: cam.binning,
            ir_filter: cam.ir_filter || "VIS Filter"
        }
    }
    function cloneMember(item) {
        const cloned = sessionDialog.cloneValue(item)
        cloned.workflow = sessionDialog.workflowOf(item)
        cloned.camera = sessionDialog.cameraOf(item)
        cloned.target = sessionDialog.cloneValue((item && item.target) || cloned.target || {})
        cloned.pane_name = (item && (item.pane_name || item.name)) || cloned.name || ""
        cloned.name = cloned.pane_name
        cloned.id = (item && item.id) || cloned.id || ""
        return cloned
    }
    function staggerImportedWorkflows(members) {
        if (members.length < 2)
            return
        for (let i = 1; i < members.length; i++) {
            if (!sessionDialog.flagOn((members[i].workflow || {}).calibrate, true))
                return
        }
        for (let i = 1; i < members.length; i++) {
            members[i].workflow = Object.assign({}, members[i].workflow || {}, {
                calibrate: false,
                polar_align: false
            })
        }
    }
    function applyWorkflowChecks(workflow) {
        const w = workflow || {}
        paneFlags.calibrate = sessionDialog.flagOn(w.calibrate, true)
        paneFlags.autofocus = sessionDialog.flagOn(w.autofocus, true)
        paneFlags.infiniteFocus = sessionDialog.flagOn(w.infinite_focus, false)
        paneFlags.polar = sessionDialog.flagOn(w.polar_align, false)
        paneFlags.doGoto = sessionDialog.flagOn(w.goto, true)
        calibrate.setOn(paneFlags.calibrate)
        autofocus.setOn(paneFlags.autofocus)
        infiniteFocus.setOn(paneFlags.infiniteFocus)
        polar.setOn(paneFlags.polar)
        doGoto.setOn(paneFlags.doGoto)
    }
    function setCheckAgreed(box, flagKey, value) {
        if (value === undefined) {
            box.checkState = Qt.PartiallyChecked
            return
        }
        paneFlags[flagKey] = !!value
        box.setOn(!!value)
    }
    function markDirty(key) {
        if (syncingPane || syncingCommon)
            return
        const next = Object.assign({}, dirtyFields || {})
        next[key] = true
        dirtyFields = next
    }
    function isDirty(key) {
        return !!(dirtyFields && dirtyFields[key])
    }
    function agreedValue(items, read) {
        if (!items.length)
            return undefined
        const first = read(items[0])
        for (let i = 1; i < items.length; i++) {
            if (String(read(items[i])) !== String(first))
                return undefined
        }
        return first
    }
    function irIndex(value) {
        const ir = value || "VIS Filter"
        return Math.max(0, ["VIS Filter", "Astro Filter", "Duo-Band Filter", "VIS"].indexOf(ir) % 3)
    }
    function selectedMembers() {
        const items = templateMembers || []
        const flags = paneSelected || []
        const result = []
        for (let i = 0; i < items.length; i++) {
            if (flags[i])
                result.push(items[i])
        }
        return result
    }
    function loadCommonFields(items, keepDirty) {
        const source = items || []
        const dirty = keepDirty ? (dirtyFields || {}) : {}
        syncingCommon = true
        function agreed(read) {
            return sessionDialog.agreedValue(source, read)
        }
        if (!dirty.camera) {
            const cam = agreed(item => sessionDialog.cameraOf(item).camera)
            camera.currentIndex = cam === "wide" ? 1 : cam === "tele" ? 0 : -1
        }
        if (!dirty.ir_filter) {
            const ir = agreed(item => sessionDialog.irIndex(sessionDialog.cameraOf(item).ir_filter))
            irFilter.currentIndex = ir === undefined ? -1 : ir
        }
        if (!dirty.exposure) {
            const exp = agreed(item => sessionDialog.cameraOf(item).exposure_seconds)
            exposure.text = exp === undefined || exp === null ? "" : String(exp)
            exposure.placeholderText = exp === undefined ? "Mixed" : ""
        }
        if (!dirty.gain) {
            const value = agreed(item => sessionDialog.cameraOf(item).gain)
            gain.text = value === undefined || value === null ? "" : String(value)
            gain.placeholderText = value === undefined ? "Mixed" : "Gain"
        }
        if (!dirty.frame_count) {
            const value = agreed(item => sessionDialog.cameraOf(item).frame_count)
            frames.text = value === undefined || value === null ? "" : String(value)
            frames.placeholderText = value === undefined ? "Mixed" : ""
        }
        if (!dirty.binning) {
            const value = agreed(item => String(sessionDialog.cameraOf(item).binning || "1"))
            binning.currentIndex = value === undefined ? -1 : Math.max(0, ["1", "2"].indexOf(String(value)))
        }
        if (!dirty.wait_before) {
            const value = agreed(item => sessionDialog.workflowOf(item).wait_before_seconds)
            waitBefore.text = value === undefined || value === null ? "" : String(value)
            waitBefore.placeholderText = value === undefined ? "Mixed" : "Before"
        }
        if (!dirty.wait_after) {
            const value = agreed(item => sessionDialog.workflowOf(item).wait_after_seconds)
            waitAfter.text = value === undefined || value === null ? "" : String(value)
            waitAfter.placeholderText = value === undefined ? "Mixed" : "After"
        }
        if (!dirty.calibrate)
            sessionDialog.setCheckAgreed(calibrate, "calibrate", agreed(item => sessionDialog.workflowOf(item).calibrate))
        if (!dirty.autofocus)
            sessionDialog.setCheckAgreed(autofocus, "autofocus", agreed(item => sessionDialog.workflowOf(item).autofocus))
        if (!dirty.infinite_focus)
            sessionDialog.setCheckAgreed(infiniteFocus, "infiniteFocus", agreed(item => sessionDialog.workflowOf(item).infinite_focus))
        if (!dirty.polar_align)
            sessionDialog.setCheckAgreed(polar, "polar", agreed(item => sessionDialog.workflowOf(item).polar_align))
        if (!dirty.goto)
            sessionDialog.setCheckAgreed(doGoto, "doGoto", agreed(item => sessionDialog.workflowOf(item).goto))
        syncingCommon = false
    }
    function applyDirtyToSelected() {
        const dirty = dirtyFields || {}
        const members = templateMembers.slice()
        const flags = paneSelected || []
        for (let i = 0; i < members.length; i++) {
            if (!flags[i])
                continue
            const pane = sessionDialog.cloneValue(members[i] || {})
            pane.camera = sessionDialog.cameraOf(pane)
            pane.workflow = sessionDialog.workflowOf(pane)
            if (dirty.camera && camera.currentIndex >= 0)
                pane.camera.camera = camera.currentIndex === 1 ? "wide" : "tele"
            if (dirty.ir_filter && irFilter.currentIndex >= 0)
                pane.camera.ir_filter = irFilter.currentText
            if (dirty.exposure && exposure.text !== "")
                pane.camera.exposure_seconds = Number(exposure.text)
            if (dirty.gain && gain.text !== "")
                pane.camera.gain = Number(gain.text)
            if (dirty.frame_count && frames.text !== "")
                pane.camera.frame_count = Number(frames.text)
            if (dirty.binning && binning.currentIndex >= 0)
                pane.camera.binning = Number(binning.currentText)
            if (dirty.wait_before && waitBefore.text !== "")
                pane.workflow.wait_before_seconds = Number(waitBefore.text)
            if (dirty.wait_after && waitAfter.text !== "")
                pane.workflow.wait_after_seconds = Number(waitAfter.text)
            if (dirty.calibrate && calibrate.checkState !== Qt.PartiallyChecked)
                pane.workflow.calibrate = calibrate.ticked
            if (dirty.autofocus && autofocus.checkState !== Qt.PartiallyChecked)
                pane.workflow.autofocus = autofocus.ticked
            if (dirty.infinite_focus && infiniteFocus.checkState !== Qt.PartiallyChecked)
                pane.workflow.infinite_focus = infiniteFocus.ticked
            if (dirty.polar_align && polar.checkState !== Qt.PartiallyChecked)
                pane.workflow.polar_align = polar.ticked
            if (dirty.goto && doGoto.checkState !== Qt.PartiallyChecked)
                pane.workflow.goto = doGoto.ticked
            members[i] = pane
        }
        templateMembers = members
    }
    function setPaneSelectedAt(index, on) {
        syncingPane = true
        const flags = (paneSelected || []).slice()
        flags[index] = !!on
        paneSelected = flags
        syncingPane = false
        sessionDialog.loadCommonFields(sessionDialog.selectedMembers(), true)
    }
    function selectAllPanes(on) {
        syncingPane = true
        paneSelected = (templateMembers || []).map(() => !!on)
        syncingPane = false
        sessionDialog.loadCommonFields(sessionDialog.selectedMembers(), true)
    }
    function workflowFromForm(existing) {
        const current = existing || {}
        return {
            calibrate: paneFlags.calibrate,
            autofocus: paneFlags.autofocus,
            infinite_focus: paneFlags.infiniteFocus,
            polar_align: paneFlags.polar,
            goto: paneFlags.doGoto,
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
    }
    function stashCurrentPane() {
        if (paneCount === 0)
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
        members[paneIndex] = current
        templateMembers = members
    }
    function showPane(index) {
        if (syncingPane || paneCount < 2 || index < 0 || index >= paneCount || index === paneIndex)
            return
        syncingPane = true
        stashCurrentPane()
        paneIndex = index
        editingId = templateMembers[index].id || editingId
        loadPaneCoordinates(templateMembers[index])
        panePicker.model = sessionDialog.paneChoices()
        panePicker.currentIndex = index
        syncingPane = false
    }
    function memberPayloads() {
        stashCurrentPane()
        sessionDialog.applyDirtyToSelected()
        const shared = sessionDialog.formPayload()
        const items = templateMembers
        const result = []
        for (let i = 0; i < items.length; i++) {
            const pane = items[i] || {}
            const target = pane.target || {}
            const workflow = pane.workflow || {}
            const cam = sessionDialog.cameraOf(pane)
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
                goto: sessionDialog.flagOn(workflow.goto, shared.goto),
                camera: cam.camera,
                exposure: cam.exposure_seconds != null ? cam.exposure_seconds : shared.exposure,
                gain: cam.gain != null ? cam.gain : shared.gain,
                frame_count: cam.frame_count != null ? cam.frame_count : shared.frame_count,
                binning: cam.binning != null ? cam.binning : shared.binning,
                ir_filter: cam.ir_filter || shared.ir_filter,
                wait_before: workflow.wait_before_seconds != null ? workflow.wait_before_seconds : shared.wait_before,
                wait_after: workflow.wait_after_seconds != null ? workflow.wait_after_seconds : shared.wait_after
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
        exposure.placeholderText = ""
        gain.placeholderText = "Gain"
        frames.placeholderText = ""
        waitBefore.placeholderText = "Before"
        waitAfter.placeholderText = "After"
    }
    function syncDeviceCombo() {
        const wanted = sessionDialog.editingDeviceId || backend.selectedDeviceId
        for (let i = 0; i < sessionDevice.count; i++) {
            if (sessionDevice.valueAt(i) === wanted) {
                sessionDevice.currentIndex = i
                return
            }
        }
    }
    function formPayload() {
        return {
            id: sessionDialog.editingId, anchor_id: sessionDialog.editingAnchorId || sessionDialog.editingId,
            name: sessionName.text, target: targetName.text,
            target_kind: targetType.currentText, ra: ra.text, dec: dec.text,
            scheduled_start: startTime.text, device_id: sessionDialog.editingDeviceId || backend.selectedDeviceId,
            camera: camera.currentIndex === 1 ? "wide" : "tele", exposure: Number(exposure.text),
            gain: Number(gain.text), frame_count: Number(frames.text), binning: Number(binning.currentText),
            ir_filter: irFilter.currentText, rows: Number(rows.text), columns: Number(columns.text),
            rotation: Number(rotation.text), horizontal_scale: Number(hScale.text), vertical_scale: Number(vScale.text),
            wait_before: Number(waitBefore.text), wait_after: Number(waitAfter.text), notes: notes.text,
            calibrate: paneFlags.calibrate, autofocus: paneFlags.autofocus, infinite_focus: paneFlags.infiniteFocus,
            polar_align: paneFlags.polar, goto: paneFlags.doGoto, save_template: saveTemplate.checked
        }
    }
    function bulkPayload() {
        const payload = { ids: bulkIds, templates: bulkTemplates }
        const dirty = dirtyFields || {}
        if (dirty.camera && camera.currentIndex >= 0)
            payload.camera = camera.currentIndex === 1 ? "wide" : "tele"
        if (dirty.ir_filter && irFilter.currentIndex >= 0)
            payload.ir_filter = irFilter.currentText
        if (dirty.exposure && exposure.text !== "")
            payload.exposure = Number(exposure.text)
        if (dirty.gain && gain.text !== "")
            payload.gain = Number(gain.text)
        if (dirty.frame_count && frames.text !== "")
            payload.frame_count = Number(frames.text)
        if (dirty.binning && binning.currentIndex >= 0)
            payload.binning = Number(binning.currentText)
        if (dirty.wait_before && waitBefore.text !== "")
            payload.wait_before = Number(waitBefore.text)
        if (dirty.wait_after && waitAfter.text !== "")
            payload.wait_after = Number(waitAfter.text)
        if (dirty.calibrate && calibrate.checkState !== Qt.PartiallyChecked)
            payload.calibrate = calibrate.ticked
        if (dirty.autofocus && autofocus.checkState !== Qt.PartiallyChecked)
            payload.autofocus = autofocus.ticked
        if (dirty.infinite_focus && infiniteFocus.checkState !== Qt.PartiallyChecked)
            payload.infinite_focus = infiniteFocus.ticked
        if (dirty.polar_align && polar.checkState !== Qt.PartiallyChecked)
            payload.polar_align = polar.ticked
        if (dirty.goto && doGoto.checkState !== Qt.PartiallyChecked)
            payload.goto = doGoto.ticked
        return payload
    }
    function resetEditorState() {
        bulkMode = false
        bulkTemplates = false
        bulkIds = []
        paneSelected = []
        dirtyFields = ({})
        paneIndex = 0
        saveTemplate.checked = false
    }
    function openForDate(day) {
        sessionDialog.resetEditorState()
        editingId = ""
        editingAnchorId = ""
        editingDeviceId = backend.selectedDeviceId
        editingTemplate = false
        templateMembers = []
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
        exposure.placeholderText = ""
        gain.placeholderText = "Gain"
        frames.placeholderText = ""
        waitBefore.placeholderText = "Before"
        waitAfter.placeholderText = "After"
        sessionDialog.applyWorkflowChecks({
            calibrate: true, autofocus: true, infinite_focus: false, polar_align: false, goto: true
        })
        sessionDialog.syncDeviceCombo()
        open()
    }
    function openExisting(data) {
        const panes = backend.sessionPanes(data.id)
        const members = panes && panes.length ? panes : []
        sessionDialog.resetEditorState()
        editingId = data.id
        editingAnchorId = data.id
        editingDeviceId = data.device_id || backend.selectedDeviceId
        editingTemplate = false
        fillForm(data)
        startTime.text = String(data.scheduled_start).substring(0, 16)
        if (members.length > 1) {
            const cloned = []
            let index = 0
            for (let i = 0; i < members.length; i++) {
                cloned.push(sessionDialog.cloneMember(members[i]))
                if (members[i].id === data.id)
                    index = i
            }
            templateMembers = cloned
            paneSelected = cloned.map(() => true)
            paneIndex = index
            editingId = cloned[index].id || data.id
            syncingPane = true
            loadPaneCoordinates(cloned[index])
            panePicker.model = sessionDialog.paneChoices()
            panePicker.currentIndex = index
            syncingPane = false
            sessionDialog.loadCommonFields(cloned)
        } else {
            templateMembers = []
        }
        sessionDialog.syncDeviceCombo()
        open()
    }
    function openTemplate(data) {
        const members = data.members && data.members.length ? data.members : [data]
        const cloned = []
        for (let i = 0; i < members.length; i++)
            cloned.push(sessionDialog.cloneMember(members[i]))
        sessionDialog.staggerImportedWorkflows(cloned)
        sessionDialog.resetEditorState()
        editingTemplate = true
        editingAnchorId = cloned[0].id || data.id
        editingDeviceId = backend.selectedDeviceId
        templateMembers = cloned
        paneSelected = cloned.map(() => true)
        editingId = cloned[0].id || data.id
        syncingPane = true
        fillForm(data)
        loadPaneCoordinates(cloned[0])
        startTime.text = ""
        panePicker.model = sessionDialog.paneChoices()
        panePicker.currentIndex = 0
        syncingPane = false
        if (cloned.length > 1)
            sessionDialog.loadCommonFields(cloned)
        open()
    }
    function editableItems(items, templates) {
        const list = items || []
        const result = []
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item)
                continue
            if (!templates && item.status === "running")
                continue
            result.push(item)
        }
        return result
    }
    function openSelected(items, templates) {
        const list = sessionDialog.editableItems(items, !!templates)
        if (!list.length)
            return
        if (list.length === 1) {
            if (templates)
                sessionDialog.openTemplate(list[0])
            else
                sessionDialog.openExisting(list[0])
            return
        }
        sessionDialog.openBulk(list, !!templates)
    }
    function openBulk(items, templates) {
        const list = sessionDialog.editableItems(items, !!templates)
        if (!list.length)
            return
        sessionDialog.resetEditorState()
        bulkMode = true
        bulkTemplates = !!templates
        bulkIds = list.map(item => item.id)
        editingTemplate = !!templates
        editingId = ""
        editingAnchorId = ""
        editingDeviceId = backend.selectedDeviceId
        templateMembers = []
        startTime.text = ""
        notes.text = ""
        saveTemplate.checked = false
        sessionDialog.loadCommonFields(list.map(item => sessionDialog.cloneMember(item)))
        sessionDialog.syncDeviceCombo()
        open()
    }

    background: DialogFrame {}
    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 10
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: {
                    if (sessionDialog.bulkMode)
                        return "EDIT " + sessionDialog.bulkIds.length + (sessionDialog.bulkTemplates ? " TEMPLATES" : " SESSIONS")
                    if (sessionDialog.editingTemplate)
                        return "EDIT TEMPLATE"
                    return sessionDialog.editingId ? "EDIT SESSION" : "NEW SESSION"
                }
                color: Theme.accent
                font.pixelSize: 20
                font.letterSpacing: 2
                Layout.fillWidth: true
            }
            HudButton { text: "×"; implicitWidth: 40; onClicked: sessionDialog.close() }
        }
        RowLayout {
            visible: sessionDialog.multiPane
            Layout.fillWidth: true
            spacing: 8
            HudCheck {
                text: "THIS PANE"
                checked: sessionDialog.focusedPaneSelected
                onClicked: sessionDialog.setPaneSelectedAt(sessionDialog.paneIndex, checked)
            }
            HudButton {
                text: sessionDialog.selectedPaneCount === sessionDialog.paneCount ? "NONE" : "ALL PANES"
                busyMs: 0
                onClicked: sessionDialog.selectAllPanes(sessionDialog.selectedPaneCount !== sessionDialog.paneCount)
            }
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
            visible: sessionDialog.multiPane || sessionDialog.bulkMode
            text: sessionDialog.bulkMode
                  ? "Name, coordinates, start time, and device stay unchanged. Camera, wait, and workflow apply to every selected item."
                  : "Name and coordinates follow the focused pane. Camera, wait, and workflow apply to checked panes. Mosaic and notes apply to every pane."
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
            FieldLabel { text: "SESSION NAME"; visible: sessionDialog.uniqueVisible }
            HudField { id: sessionName; Layout.fillWidth: true; Layout.columnSpan: 2; visible: sessionDialog.uniqueVisible }
            FieldLabel { text: "TARGET TYPE"; visible: sessionDialog.uniqueVisible }
            HudCombo { id: targetType; model: ["equatorial", "solar", "none"]; Layout.fillWidth: true; visible: sessionDialog.uniqueVisible }
            HudField { id: targetName; placeholderText: "Target name"; Layout.fillWidth: true; visible: sessionDialog.uniqueVisible }
            FieldLabel { text: "RA HOURS"; visible: sessionDialog.uniqueVisible }
            HudField { id: ra; Layout.fillWidth: true; visible: sessionDialog.uniqueVisible }
            HudField { id: dec; placeholderText: "Dec degrees"; Layout.fillWidth: true; visible: sessionDialog.uniqueVisible }
            FieldLabel { text: "START"; visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate }
            HudField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2; visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate }
            FieldLabel { text: "DEVICE"; visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate }
            HudCombo {
                id: sessionDevice
                visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate
                Layout.fillWidth: true
                Layout.columnSpan: 2
                model: backend.devices
                textRole: "name"
                valueRole: "id"
                onActivated: if (currentValue) sessionDialog.editingDeviceId = currentValue
            }
            FieldLabel { text: "CAMERA" }
            HudCombo {
                id: camera
                model: ["Tele", "Wide"]
                Layout.fillWidth: true
                Layout.columnSpan: currentIndex === 1 ? 2 : 1
                onActivated: sessionDialog.markDirty("camera")
            }
            HudCombo {
                id: irFilter
                visible: camera.currentIndex !== 1
                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                Layout.fillWidth: true
                onActivated: sessionDialog.markDirty("ir_filter")
            }
            FieldLabel { text: "EXPOSURE" }
            HudField { id: exposure; Layout.fillWidth: true; onTextEdited: sessionDialog.markDirty("exposure") }
            HudField { id: gain; placeholderText: "Gain"; Layout.fillWidth: true; onTextEdited: sessionDialog.markDirty("gain") }
            FieldLabel { text: "FRAMES" }
            HudField { id: frames; Layout.fillWidth: true; onTextEdited: sessionDialog.markDirty("frame_count") }
            HudCombo { id: binning; model: ["1", "2"]; Layout.fillWidth: true; onActivated: sessionDialog.markDirty("binning") }
            FieldLabel { text: "MOSAIC"; visible: sessionDialog.mosaicVisible }
            HudField { id: rows; placeholderText: "Rows"; Layout.fillWidth: true; visible: sessionDialog.mosaicVisible }
            HudField { id: columns; placeholderText: "Columns"; Layout.fillWidth: true; visible: sessionDialog.mosaicVisible }
            FieldLabel { text: "ROTATION / SCALE"; visible: sessionDialog.mosaicVisible }
            HudField { id: rotation; placeholderText: "Rotation °"; Layout.fillWidth: true; visible: sessionDialog.mosaicVisible }
            RowLayout {
                visible: sessionDialog.mosaicVisible
                HudField { id: hScale; placeholderText: "H scale"; Layout.fillWidth: true }
                HudField { id: vScale; placeholderText: "V scale"; Layout.fillWidth: true }
            }
            FieldLabel { text: "WAIT S" }
            HudField { id: waitBefore; placeholderText: "Before"; Layout.fillWidth: true; onTextEdited: sessionDialog.markDirty("wait_before") }
            HudField { id: waitAfter; placeholderText: "After"; Layout.fillWidth: true; onTextEdited: sessionDialog.markDirty("wait_after") }
            FieldLabel { text: "NOTES"; visible: sessionDialog.mosaicVisible }
            HudField { id: notes; Layout.fillWidth: true; Layout.columnSpan: 2; visible: sessionDialog.mosaicVisible }
            FieldLabel { text: "WORKFLOW"; Layout.alignment: Qt.AlignTop; Layout.topMargin: 8 }
            Flow {
                Layout.fillWidth: true
                Layout.columnSpan: 2
                Layout.topMargin: 4
                spacing: 22
                HudCheck {
                    id: calibrate
                    text: "Calibrate"
                    tristate: sessionDialog.commonMulti
                    onToggled: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
                        paneFlags.calibrate = checked
                        sessionDialog.markDirty("calibrate")
                    }
                    Binding on checked {
                        value: paneFlags.calibrate
                        when: !calibrate.pressed && !sessionDialog.commonMulti && !sessionDialog.syncingCommon
                        restoreMode: Binding.RestoreNone
                    }
                }
                HudCheck {
                    id: autofocus
                    text: "Auto focus"
                    tristate: sessionDialog.commonMulti
                    onToggled: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
                        paneFlags.autofocus = checked
                        sessionDialog.markDirty("autofocus")
                    }
                    Binding on checked {
                        value: paneFlags.autofocus
                        when: !autofocus.pressed && !sessionDialog.commonMulti && !sessionDialog.syncingCommon
                        restoreMode: Binding.RestoreNone
                    }
                }
                HudCheck {
                    id: infiniteFocus
                    text: "Infinity focus"
                    tristate: sessionDialog.commonMulti
                    onToggled: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
                        paneFlags.infiniteFocus = checked
                        sessionDialog.markDirty("infinite_focus")
                    }
                    Binding on checked {
                        value: paneFlags.infiniteFocus
                        when: !infiniteFocus.pressed && !sessionDialog.commonMulti && !sessionDialog.syncingCommon
                        restoreMode: Binding.RestoreNone
                    }
                }
                HudCheck {
                    id: polar
                    text: "Polar / EQ"
                    tristate: sessionDialog.commonMulti
                    onToggled: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
                        paneFlags.polar = checked
                        sessionDialog.markDirty("polar_align")
                    }
                    Binding on checked {
                        value: paneFlags.polar
                        when: !polar.pressed && !sessionDialog.commonMulti && !sessionDialog.syncingCommon
                        restoreMode: Binding.RestoreNone
                    }
                }
                HudCheck {
                    id: doGoto
                    text: "GOTO"
                    tristate: sessionDialog.commonMulti
                    onToggled: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
                        paneFlags.doGoto = checked
                        sessionDialog.markDirty("goto")
                    }
                    Binding on checked {
                        value: paneFlags.doGoto
                        when: !doGoto.pressed && !sessionDialog.commonMulti && !sessionDialog.syncingCommon
                        restoreMode: Binding.RestoreNone
                    }
                }
                HudCheck { id: saveTemplate; text: "Save template"; visible: !sessionDialog.editingTemplate && !sessionDialog.bulkMode }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { text: "CANCEL"; onClicked: sessionDialog.close() }
            HudButton {
                text: sessionDialog.bulkMode ? "UPDATE SELECTED" : (sessionDialog.editingTemplate ? "SAVE TEMPLATE" : "SAVE SESSION")
                busyText: sessionDialog.bulkMode ? "UPDATING…" : "SAVING…"
                enabled: !sessionDialog.bulkMode || sessionDialog.dirty
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: {
                    if (sessionDialog.bulkMode) {
                        backend.updateSharedSettings(JSON.stringify(sessionDialog.bulkPayload()))
                        sessionDialog.close()
                        return
                    }
                    const payload = sessionDialog.formPayload()
                    if (sessionDialog.paneCount > 1)
                        payload.members = sessionDialog.memberPayloads()
                    if (sessionDialog.editingTemplate)
                        backend.saveTemplate(JSON.stringify(payload))
                    else
                        backend.saveSession(JSON.stringify(payload))
                    sessionDialog.close()
                }
            }
        }
    }
}
