import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: placeDialog
    objectName: "placeDialog"
    property string preferredKey: ""
    property string preferredMode: ""
    property string deviceId: ""
    property string startText: ""
    readonly property int sessionsTick: backend.sessions.length + backend.templates.length
    readonly property var recipes: {
        placeDialog.sessionsTick
        placeDialog.preferredKey
        placeDialog.preferredMode
        return placeDialog.buildRecipes()
    }
    readonly property var recipeNames: {
        const list = placeDialog.recipes || []
        const names = []
        for (let i = 0; i < list.length; i++)
            names.push(String((list[i] && list[i].name) || "Recipe"))
        return names
    }
    readonly property var currentRecipe: {
        const list = placeDialog.recipes || []
        const index = recipeBox.currentIndex
        if (index < 0 || index >= list.length)
            return ({})
        return list[index] || ({})
    }
    readonly property var windowHint: {
        placeDialog.sessionsTick
        const recipe = placeDialog.currentRecipe || {}
        const start = startTime.text
        if (!recipe.id)
            return ({})
        if (recipe.kind === "template") {
            const capture = placeDialog.captureNumbers(recipe)
            return backend.templateScheduleWindow(recipe.id, placeDialog.deviceId, start, capture.exposure, capture.frames)
        }
        return backend.duplicatePreview(String(recipe.id), String(recipe.mode || "session"), placeDialog.deviceId, start)
    }
    readonly property bool lockDevice: String((currentRecipe && currentRecipe.mode) || "") === "pane"
                                       || !!(windowHint && windowHint.lock_device)
    readonly property bool canPlace: {
        const recipe = placeDialog.currentRecipe || {}
        const hint = placeDialog.windowHint || {}
        return !!(recipe.id) && startTime.text.trim().length > 0 && !!hint.ok && !hint.conflict
    }
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(460)
    padding: Theme.s4
    height: Math.min(root.height - Theme.px(60), placeColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
    function defaultStart() {
        return backend.deviceNowStamp(placeDialog.deviceId || backend.selectedDeviceId)
    }
    function captureNumbers(recipe) {
        const source = (recipe && recipe.source) || {}
        const camera = source.camera || {}
        let exposure = Number(camera.exposure_seconds)
        let frames = Number(camera.frame_count)
        if (!(exposure > 0) || !(frames >= 1)) {
            const defaults = Util.captureDefaults(Util.deviceById(backend.devices, placeDialog.deviceId) || backend.selectedDevice)
            if (!(exposure > 0))
                exposure = Number(defaults.exposure_seconds) || 15
            if (!(frames >= 1))
                frames = Number(defaults.frame_count) || 1
        }
        return { exposure: exposure, frames: Math.round(frames) }
    }
    function buildRecipes() {
        const out = []
        const templates = backend.templates || []
        for (let i = 0; i < templates.length; i++) {
            const item = templates[i]
            if (!item || !item.id)
                continue
            out.push({
                key: "template:" + String(item.id),
                kind: "template",
                id: String(item.id),
                mode: "",
                name: "Template  ·  " + String(item.name || item.target_name || "Template"),
                deviceId: "",
                source: item
            })
        }
        const sessions = backend.sessions || []
        const seenGroups = {}
        for (let i = 0; i < sessions.length; i++) {
            const item = sessions[i]
            if (!item || !item.id)
                continue
            const group = String(item.group_id || "")
            if (group && item.is_grouped) {
                const key = "mosaic:" + group + "|" + String(item.device_id || "")
                if (seenGroups[key])
                    continue
                seenGroups[key] = true
                out.push({
                    key: key,
                    kind: "session",
                    id: String(item.id),
                    mode: "mosaic",
                    name: "Session  ·  " + String(item.group_title || item.target_name || item.name || "Mosaic"),
                    deviceId: String(item.device_id || ""),
                    source: item
                })
                continue
            }
            out.push({
                key: "session:" + String(item.id),
                kind: "session",
                id: String(item.id),
                mode: "session",
                name: "Session  ·  " + String(item.pane_name || item.name || item.target_name || "Session"),
                deviceId: String(item.device_id || ""),
                source: item
            })
        }
        if (placeDialog.preferredMode === "pane" && placeDialog.preferredKey.indexOf("session:") === 0) {
            let found = false
            for (let i = 0; i < out.length; i++) {
                if (out[i].key === placeDialog.preferredKey)
                    found = true
            }
            if (!found) {
                const id = placeDialog.preferredKey.substring(8)
                for (let i = 0; i < sessions.length; i++) {
                    const item = sessions[i]
                    if (!item || String(item.id) !== id)
                        continue
                    out.push({
                        key: placeDialog.preferredKey,
                        kind: "session",
                        id: id,
                        mode: "pane",
                        name: "Pane  ·  " + String(item.pane_name || item.name || "Pane"),
                        deviceId: String(item.device_id || ""),
                        source: item
                    })
                    break
                }
            }
        }
        return out
    }
    function syncRecipeIndex() {
        const list = placeDialog.recipes || []
        if (!placeDialog.preferredKey) {
            recipeBox.currentIndex = -1
            return
        }
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].key === placeDialog.preferredKey) {
                recipeBox.currentIndex = i
                return
            }
        }
        recipeBox.currentIndex = -1
    }
    function syncDevice() {
        const id = placeDialog.deviceId || backend.selectedDeviceId
        for (let i = 0; i < deviceBox.count; i++) {
            if (deviceBox.valueAt(i) === id) {
                deviceBox.currentIndex = i
                placeDialog.deviceId = id
                return
            }
        }
        if (deviceBox.count > 0) {
            deviceBox.currentIndex = 0
            placeDialog.deviceId = deviceBox.valueAt(0) || backend.selectedDeviceId
        }
    }
    function confirm() {
        if (!placeDialog.canPlace)
            return
        const request = Util.placeOnNightRequest(placeDialog.currentRecipe, placeDialog.deviceId, startTime.text)
        if (!request.ok)
            return
        let placed = false
        if (request.op === "scheduleTemplate")
            placed = backend.scheduleTemplate(request.id, request.start, request.deviceId)
        else if (request.op === "duplicateSession")
            placed = backend.duplicateSession(request.id, request.start, request.deviceId, "", request.mode)
        if (placed)
            close()
    }
    function openForTemplate(data) {
        const item = data || ({})
        preferredMode = ""
        preferredKey = "template:" + String(item.id || "")
        deviceId = backend.selectedDeviceId
        startText = placeDialog.defaultStart()
        open()
    }
    function openForSession(data, mode) {
        const item = data || ({})
        const wanted = String(mode || (item.is_grouped ? "mosaic" : "session"))
        preferredMode = wanted
        if (wanted === "mosaic" && item.group_id)
            preferredKey = "mosaic:" + String(item.group_id) + "|" + String(item.device_id || "")
        else
            preferredKey = "session:" + String(item.id || "")
        deviceId = String(item.device_id || backend.selectedDeviceId)
        const hint = backend.duplicatePreview(String(item.id || ""), wanted, deviceId, "")
        startText = String((hint && (hint.suggested_start || hint.next_free)) || placeDialog.defaultStart())
        open()
    }
    function openForSlot(day, minutes) {
        preferredMode = ""
        preferredKey = ""
        deviceId = backend.selectedDeviceId
        const mins = (minutes === undefined || minutes === null || minutes === "" || Number(minutes) < 0)
                     ? 10 * 60 : Number(minutes)
        startText = backend.nightTimelineIso(String(day || ""), mins) || placeDialog.defaultStart()
        open()
    }
    onOpened: {
        placeDialog.syncDevice()
        placeDialog.syncRecipeIndex()
        startTime.text = placeDialog.startText
        startTime.forceActiveFocus()
        startTime.selectAll()
    }
    onRecipesChanged: if (visible) placeDialog.syncRecipeIndex()
    contentItem: ColumnLayout {
        id: placeColumn
        spacing: Theme.s3
        Text { text: "PLACE ON NIGHT"; color: Theme.accent; font.pixelSize: Theme.fontLg; font.letterSpacing: 1.4 }
        Text {
            text: "Pick a template or an existing session, then the telescope and the start."
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontMd
            Layout.fillWidth: true
        }
        FieldLabel { text: "RECIPE" }
        HudCombo {
            id: recipeBox
            objectName: "place-recipe"
            Layout.fillWidth: true
            accessibleName: "Recipe"
            emptyText: "Choose a recipe"
            model: placeDialog.recipeNames
            onActivated: {
                const item = (placeDialog.recipes || [])[currentIndex] || ({})
                placeDialog.preferredKey = String(item.key || "")
                placeDialog.preferredMode = String(item.mode || "")
                if (item.deviceId) {
                    placeDialog.deviceId = String(item.deviceId)
                    placeDialog.syncDevice()
                }
            }
        }
        Text {
            visible: text !== ""
            text: {
                const source = (placeDialog.currentRecipe && placeDialog.currentRecipe.source) || {}
                return String(source.summary || source.coords_text || "")
            }
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontMd
            font.family: Theme.fontMono
            elide: Text.ElideRight
            maximumLineCount: 2
            Layout.fillWidth: true
        }
        FieldLabel { text: "DEVICE"; visible: !placeDialog.lockDevice }
        HudCombo {
            id: deviceBox
            objectName: "place-device"
            visible: !placeDialog.lockDevice
            Layout.fillWidth: true
            accessibleName: "Telescope"
            model: backend.devices
            textRole: "name"
            valueRole: "id"
            onActivated: {
                if (!currentValue)
                    return
                placeDialog.deviceId = currentValue
            }
        }
        FieldLabel { text: "START" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            HudTimeField {
                id: startTime
                objectName: "place-start"
                deviceId: placeDialog.deviceId
                Layout.fillWidth: true
                onAccepted: placeDialog.confirm()
            }
            HudButton {
                text: "NOW"
                implicitWidth: Theme.px(72)
                onClicked: startTime.text = placeDialog.defaultStart()
            }
        }
        Text {
            visible: !!(placeDialog.windowHint && placeDialog.windowHint.ok)
            text: {
                const hint = placeDialog.windowHint || {}
                const zone = hint.timezone || ""
                const finish = hint.end ? "Finishes " + hint.end : ""
                const length = hint.duration_text ? " ·  " + hint.duration_text : ""
                const tz = zone ? "  ·  " + zone : ""
                return finish + length + tz
            }
            color: Theme.textSecondary
            font.pixelSize: Theme.fontPx(11)
            font.family: Theme.fontMono
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        ColumnLayout {
            visible: !!(placeDialog.windowHint && placeDialog.windowHint.conflict)
            spacing: Theme.s2
            Layout.fillWidth: true
            Text {
                text: "Overlaps " + (placeDialog.windowHint.conflict || "") + "."
                color: Theme.warning
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            HudButton {
                objectName: "placeNextFree"
                visible: !!(placeDialog.windowHint.next_free)
                text: "USE NEXT FREE  " + (placeDialog.windowHint.next_free_time || "")
                Layout.fillWidth: true
                onClicked: startTime.text = placeDialog.windowHint.next_free
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { objectName: "placeCancel"; text: "CANCEL"; onClicked: placeDialog.close() }
            HudButton {
                objectName: "placeConfirm"
                text: "PLACE"
                enabled: placeDialog.canPlace
                busyText: "PLACING…"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: placeDialog.confirm()
            }
        }
    }
}
