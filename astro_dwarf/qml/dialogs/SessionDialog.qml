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
    property bool importedPlan: false
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
    // camera, wait, and workflow edits need at least one checked pane to land on
    readonly property bool sharedEnabled: !multiPane || selectedPaneCount > 0
    readonly property bool uniqueVisible: !bulkMode
    readonly property bool mosaicVisible: !bulkMode
    readonly property bool equatorialTarget: targetType.currentIndex === 0
    readonly property var focusedMosaic: {
        const item = templateMembers[paneIndex]
        return (item && item.mosaic) || null
    }
    readonly property string planGridText: {
        const grid = focusedMosaic
        if (!importedPlan)
            return ""
        const size = grid && grid.grid_rows && grid.grid_columns
            ? grid.grid_rows + " × " + grid.grid_columns + " imported panes. "
            : ""
        return size + "Each pane is captured on its own; the telescope mosaic is not used."
    }
    readonly property bool mosaicScaleVisible: {
        if (!mosaicVisible || importedPlan)
            return false
        const r = Math.max(1, parseInt(rows.text, 10) || 1)
        const c = Math.max(1, parseInt(columns.text, 10) || 1)
        return r * c > 1
    }
    readonly property bool dirty: Object.keys(dirtyFields || {}).length > 0
    readonly property bool focusedPaneSelected: {
        selectedPaneCount
        paneIndex
        return !!(paneSelected && paneSelected[paneIndex])
    }
    padding: 0

    component FieldCaption: Text {
        color: Theme.textSecondary
        font.pixelSize: 9
        font.letterSpacing: 1.0
        font.bold: true
    }
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
        const position = "Pane " + (index + 1)
        const parts = [position]
        const cell = (item && item.pane_position) || ""
        const name = (item && (item.pane_name || item.name)) || ""
        if (cell)
            parts.push(cell)
        if (name && name !== position)
            parts.push(name)
        return parts.join(" · ")
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
    // Stored 1/2 match the old combo; Dwarf labels those as 4K / 2K.
    function binningIndex(value) {
        return Number(value) >= 2 ? 1 : 0
    }
    function binningValue() {
        return binning.currentIndex === 1 ? 2 : 1
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
        // with no pane checked the shared fields are read-only, so preview the focused pane
        const focused = templateMembers[paneIndex]
        const source = (items && items.length) ? items : (focused ? [focused] : [])
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
            const value = agreed(item => sessionDialog.binningIndex(sessionDialog.cameraOf(item).binning))
            binning.currentIndex = value === undefined ? -1 : value
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
                pane.camera.binning = sessionDialog.binningValue()
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
    function flagsForOnlyPane(index) {
        const items = templateMembers || []
        const flags = []
        for (let i = 0; i < items.length; i++)
            flags.push(i === index)
        return flags
    }
    // pending edits belong to the panes that were checked while they were typed
    function commitPendingEdits() {
        if (!sessionDialog.dirty)
            return
        sessionDialog.applyDirtyToSelected()
        dirtyFields = ({})
    }
    function setPaneSelectedAt(index, on) {
        sessionDialog.commitPendingEdits()
        syncingPane = true
        const flags = (paneSelected || []).slice()
        flags[index] = !!on
        paneSelected = flags
        syncingPane = false
        sessionDialog.loadCommonFields(sessionDialog.selectedMembers())
    }
    function selectAllPanes(on) {
        sessionDialog.commitPendingEdits()
        syncingPane = true
        paneSelected = (templateMembers || []).map(() => !!on)
        syncingPane = false
        sessionDialog.loadCommonFields(sessionDialog.selectedMembers())
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
    function loadMosaicFields(data) {
        const mosaic = (data && data.mosaic) || {}
        importedPlan = !!(mosaic.grid_rows && mosaic.grid_columns)
        if (importedPlan) {
            rows.text = mosaic.row || ""
            columns.text = mosaic.column || ""
            return
        }
        rows.text = mosaic.rows
        columns.text = mosaic.columns
    }
    function loadPaneCoordinates(data) {
        sessionName.text = data.pane_name || data.name || ""
        const target = data.target || {}
        targetName.text = target.name || data.target_name || ""
        const kind = target.kind || "equatorial"
        targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
        ra.text = target.ra_hours != null && target.ra_hours !== "" ? target.ra_hours : ""
        dec.text = target.dec_degrees != null && target.dec_degrees !== "" ? target.dec_degrees : ""
        sessionDialog.loadMosaicFields(data)
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
        sessionDialog.applyDirtyToSelected()
        const followFocused = sessionDialog.selectedPaneCount === 1 && !!(paneSelected && paneSelected[paneIndex])
        paneIndex = index
        editingId = templateMembers[index].id || editingId
        loadPaneCoordinates(templateMembers[index])
        panePicker.model = sessionDialog.paneChoices()
        panePicker.currentIndex = index
        if (followFocused)
            paneSelected = sessionDialog.flagsForOnlyPane(index)
        dirtyFields = ({})
        syncingPane = false
        sessionDialog.loadCommonFields(sessionDialog.selectedMembers())
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
        binning.currentIndex = sessionDialog.binningIndex(data.camera.binning)
        const ir = data.camera.ir_filter || "VIS Filter"
        irFilter.currentIndex = Math.max(0, ["VIS Filter", "Astro Filter", "Duo-Band Filter", "VIS"].indexOf(ir) % 3)
        sessionDialog.loadMosaicFields(data)
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
            gain: Number(gain.text), frame_count: Number(frames.text), binning: sessionDialog.binningValue(),
            ir_filter: irFilter.currentText,
            rows: sessionDialog.importedPlan ? 1 : Number(rows.text),
            columns: sessionDialog.importedPlan ? 1 : Number(columns.text),
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
            payload.binning = sessionDialog.binningValue()
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
        importedPlan = false
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
            paneIndex = index
            paneSelected = sessionDialog.flagsForOnlyPane(index)
            editingId = cloned[index].id || data.id
            syncingPane = true
            loadPaneCoordinates(cloned[index])
            panePicker.model = sessionDialog.paneChoices()
            panePicker.currentIndex = index
            syncingPane = false
            sessionDialog.loadCommonFields(sessionDialog.selectedMembers())
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
        paneIndex = 0
        paneSelected = sessionDialog.flagsForOnlyPane(0)
        editingId = cloned[0].id || data.id
        syncingPane = true
        fillForm(data)
        loadPaneCoordinates(cloned[0])
        startTime.text = ""
        panePicker.model = sessionDialog.paneChoices()
        panePicker.currentIndex = 0
        syncingPane = false
        if (cloned.length > 1)
            sessionDialog.loadCommonFields(sessionDialog.selectedMembers())
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
                id: thisPane
                text: "THIS PANE"
                onClicked: sessionDialog.setPaneSelectedAt(sessionDialog.paneIndex, checked)
                Binding on checked {
                    value: sessionDialog.focusedPaneSelected
                    when: !thisPane.pressed
                    restoreMode: Binding.RestoreNone
                }
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
            text: {
                if (sessionDialog.bulkMode)
                    return "Name, coordinates, start time, and device stay unchanged. Camera, wait, and workflow apply to every selected item."
                if (!sessionDialog.sharedEnabled)
                    return "No pane is checked, so camera, wait, and workflow are read-only and show the focused pane. Name and coordinates follow the focused pane; mosaic and notes apply to every pane."
                return "Name and coordinates follow the focused pane. Camera, wait, and workflow apply to checked panes. Mosaic and notes apply to every pane."
            }
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
            HudField {
                id: targetName
                placeholderText: targetType.currentIndex === 1 ? "Sun, moon, planet…" : "Target name"
                Layout.fillWidth: true
                visible: sessionDialog.uniqueVisible
            }
            FieldLabel { text: "RA / DEC"; visible: sessionDialog.uniqueVisible && sessionDialog.equatorialTarget }
            ColumnLayout {
                visible: sessionDialog.uniqueVisible && sessionDialog.equatorialTarget
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "RA HOURS" }
                HudField { id: ra; Layout.fillWidth: true }
            }
            ColumnLayout {
                visible: sessionDialog.uniqueVisible && sessionDialog.equatorialTarget
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "DEC °" }
                HudField { id: dec; Layout.fillWidth: true }
            }
            FieldLabel { text: "START"; visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate }
            HudTimeField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2; visible: sessionDialog.uniqueVisible && !sessionDialog.editingTemplate }
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
                emptyText: "Mixed"
                enabled: sessionDialog.sharedEnabled
                Layout.fillWidth: true
                Layout.columnSpan: currentIndex === 1 ? 2 : 1
                onActivated: sessionDialog.markDirty("camera")
            }
            HudCombo {
                id: irFilter
                visible: camera.currentIndex !== 1
                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                emptyText: "Mixed"
                enabled: sessionDialog.sharedEnabled
                Layout.fillWidth: true
                onActivated: sessionDialog.markDirty("ir_filter")
            }
            FieldLabel { text: "EXPOSURE / GAIN" }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "SECONDS" }
                HudField {
                    id: exposure
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onTextEdited: sessionDialog.markDirty("exposure")
                }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "GAIN" }
                HudField {
                    id: gain
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onTextEdited: sessionDialog.markDirty("gain")
                }
            }
            FieldLabel { text: "FRAMES / BIN" }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "FRAMES" }
                HudField {
                    id: frames
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onTextEdited: sessionDialog.markDirty("frame_count")
                }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "BINNING" }
                HudCombo {
                    id: binning
                    model: ["4K", "2K"]
                    emptyText: "Mixed"
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onActivated: sessionDialog.markDirty("binning")
                }
            }
            FieldLabel { text: "MOSAIC"; visible: sessionDialog.mosaicVisible }
            ColumnLayout {
                visible: sessionDialog.mosaicVisible
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: sessionDialog.importedPlan ? "ROW" : "ROWS" }
                HudField {
                    id: rows
                    placeholderText: "1"
                    enabled: !sessionDialog.importedPlan
                    Layout.fillWidth: true
                }
            }
            ColumnLayout {
                visible: sessionDialog.mosaicVisible
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: sessionDialog.importedPlan ? "COLUMN" : "COLUMNS" }
                HudField {
                    id: columns
                    placeholderText: "1"
                    enabled: !sessionDialog.importedPlan
                    Layout.fillWidth: true
                }
            }
            FieldLabel { text: "PLAN GRID"; visible: sessionDialog.mosaicVisible && sessionDialog.planGridText !== "" }
            Text {
                visible: sessionDialog.mosaicVisible && sessionDialog.planGridText !== ""
                Layout.columnSpan: 2
                Layout.fillWidth: true
                text: sessionDialog.planGridText
                color: Theme.textSecondary
                font.pixelSize: 12
                wrapMode: Text.Wrap
            }
            FieldLabel { text: "ROTATION / SCALE"; visible: sessionDialog.mosaicScaleVisible }
            ColumnLayout {
                visible: sessionDialog.mosaicScaleVisible
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "ROTATION °" }
                HudField { id: rotation; Layout.fillWidth: true }
            }
            RowLayout {
                visible: sessionDialog.mosaicScaleVisible
                Layout.fillWidth: true
                spacing: 10
                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true
                    FieldCaption { text: "H SCALE %" }
                    HudField { id: hScale; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                }
                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true
                    FieldCaption { text: "V SCALE %" }
                    HudField { id: vScale; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                }
            }
            FieldLabel { text: "WAIT S" }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "BEFORE" }
                HudField {
                    id: waitBefore
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onTextEdited: sessionDialog.markDirty("wait_before")
                }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldCaption { text: "AFTER" }
                HudField {
                    id: waitAfter
                    enabled: sessionDialog.sharedEnabled
                    Layout.fillWidth: true
                    onTextEdited: sessionDialog.markDirty("wait_after")
                }
            }
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
                    enabled: sessionDialog.sharedEnabled
                    tristate: sessionDialog.commonMulti
                    // a click always lands on a real value; the dash only ever reports mixed panes
                    nextCheckState: function() { return calibrate.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked }
                    onClicked: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
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
                    enabled: sessionDialog.sharedEnabled
                    tristate: sessionDialog.commonMulti
                    nextCheckState: function() { return autofocus.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked }
                    onClicked: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
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
                    enabled: sessionDialog.sharedEnabled
                    tristate: sessionDialog.commonMulti
                    nextCheckState: function() { return infiniteFocus.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked }
                    onClicked: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
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
                    enabled: sessionDialog.sharedEnabled
                    tristate: sessionDialog.commonMulti
                    nextCheckState: function() { return polar.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked }
                    onClicked: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
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
                    enabled: sessionDialog.sharedEnabled
                    tristate: sessionDialog.commonMulti
                    nextCheckState: function() { return doGoto.checkState === Qt.Checked ? Qt.Unchecked : Qt.Checked }
                    onClicked: if (!sessionDialog.syncingPane && !sessionDialog.syncingCommon) {
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
