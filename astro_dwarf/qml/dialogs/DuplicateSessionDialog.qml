import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: duplicateDialog
    objectName: "duplicateDialog"
    property string sessionId: ""
    property string duplicateMode: "session"
    property string deviceId: ""
    property var sessionData: ({})
    readonly property int sessionsTick: backend.sessions.length
    readonly property var windowHint: {
        sessionsTick
        if (!duplicateDialog.sessionId)
            return ({})
        return backend.duplicatePreview(duplicateDialog.sessionId, duplicateDialog.duplicateMode,
                                        duplicateDialog.deviceId, startTime.text)
    }
    readonly property string resolvedMode: String((windowHint && windowHint.mode) || duplicateMode)
    readonly property bool lockDevice: !!(windowHint && windowHint.lock_device) || resolvedMode === "pane"
    readonly property bool nameVisible: resolvedMode !== "mosaic"
    readonly property bool canDuplicate: sessionId.length > 0 && startTime.text.trim().length > 0
                                         && !!windowHint.ok && !windowHint.conflict
                                         && (!nameVisible || nameField.text.trim().length > 0)
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(460)
    padding: Theme.s4
    height: Math.min(root.height - Theme.px(60), duplicateColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
    function defaultStart() {
        return backend.deviceNowStamp(duplicateDialog.deviceId || backend.selectedDeviceId)
    }
    function headingText() {
        if (duplicateDialog.resolvedMode === "mosaic")
            return "DUPLICATE MOSAIC"
        if (duplicateDialog.resolvedMode === "pane")
            return "DUPLICATE PANE"
        return "DUPLICATE SESSION"
    }
    function confirm() {
        if (!canDuplicate)
            return
        if (backend.duplicateSession(duplicateDialog.sessionId, startTime.text.trim(),
                                     duplicateDialog.deviceId, nameField.text.trim(),
                                     duplicateDialog.duplicateMode))
            close()
    }
    function syncDevice() {
        const id = duplicateDialog.deviceId || backend.selectedDeviceId
        for (let i = 0; i < deviceBox.count; i++) {
            if (deviceBox.valueAt(i) === id) {
                deviceBox.currentIndex = i
                duplicateDialog.deviceId = id
                return
            }
        }
        if (deviceBox.count > 0) {
            deviceBox.currentIndex = 0
            duplicateDialog.deviceId = deviceBox.valueAt(0) || backend.selectedDeviceId
        }
    }
    function openFor(data, mode) {
        const item = data || ({})
        sessionId = String(item.id || "")
        sessionData = item
        duplicateMode = String(mode || (item.is_grouped ? "mosaic" : "session"))
        deviceId = String(item.device_id || backend.selectedDeviceId)
        syncDevice()
        const hint = backend.duplicatePreview(sessionId, duplicateMode, deviceId, "")
        nameField.text = String((hint && hint.default_name) || "")
        startTime.text = String((hint && hint.suggested_start) || duplicateDialog.defaultStart())
        open()
        startTime.forceActiveFocus()
        startTime.selectAll()
    }
    contentItem: ColumnLayout {
        id: duplicateColumn
        spacing: Theme.s3
        Text {
            text: duplicateDialog.headingText()
            color: Theme.accent
            font.pixelSize: Theme.fontLg
            font.letterSpacing: 1.4
        }
        Text {
            text: {
                const hint = duplicateDialog.windowHint || {}
                const item = duplicateDialog.sessionData || {}
                if (duplicateDialog.resolvedMode === "mosaic")
                    return String(hint.target_name || item.group_title || item.target_name || item.name || "Mosaic")
                return String(item.pane_name || item.name || item.target_name || "Session")
            }
            color: Theme.textPrimary
            font.pixelSize: Theme.fontPx(15)
            font.bold: true
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text {
            visible: text !== ""
            text: {
                if (duplicateDialog.resolvedMode === "mosaic")
                    return "Copies every pane as a new mosaic. Choose a start that does not overlap this telescope."
                if (duplicateDialog.resolvedMode === "pane")
                    return "Adds another capture of this pane to the same mosaic at a new time."
                return "Creates a new session. Choose a start that does not overlap this telescope."
            }
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontMd
            Layout.fillWidth: true
        }
        Text {
            id: recapText
            visible: text !== ""
            text: {
                const item = duplicateDialog.sessionData || {}
                const hint = duplicateDialog.windowHint || {}
                const bits = []
                const coords = Util.targetCoordinates(item)
                if (coords)
                    bits.push(coords)
                if (item.summary)
                    bits.push(item.summary)
                if (duplicateDialog.resolvedMode === "mosaic") {
                    const count = Number(hint.pane_count || item.pane_count || 0)
                    if (count > 1)
                        bits.push(count + " panes")
                    if (item.grid_text)
                        bits.push(item.grid_text)
                    else if (item.group_summary)
                        bits.push(item.group_summary)
                }
                if (hint.original_start)
                    bits.push("was " + hint.original_start)
                return bits.join("  ·  ")
            }
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontMd
            font.family: Theme.fontMono
            Layout.fillWidth: true
        }
        FieldLabel { text: "NAME"; visible: duplicateDialog.nameVisible }
        HudField {
            id: nameField
            objectName: "duplicate-name"
            visible: duplicateDialog.nameVisible
            Layout.fillWidth: true
            accessibleName: "Duplicated session name"
        }
        FieldLabel { text: "DEVICE"; visible: !duplicateDialog.lockDevice }
        HudCombo {
            id: deviceBox
            visible: !duplicateDialog.lockDevice
            Layout.fillWidth: true
            model: backend.devices
            textRole: "name"
            valueRole: "id"
            onActivated: {
                if (!currentValue)
                    return
                duplicateDialog.deviceId = currentValue
            }
        }
        FieldLabel { text: "START" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            HudTimeField {
                id: startTime
                objectName: "duplicate-start"
                Layout.fillWidth: true
                onAccepted: duplicateDialog.confirm()
            }
            HudButton {
                text: "NOW"
                implicitWidth: Theme.px(72)
                onClicked: startTime.text = duplicateDialog.defaultStart()
            }
        }
        Text {
            visible: !!(duplicateDialog.windowHint && duplicateDialog.windowHint.ok)
            text: {
                const hint = duplicateDialog.windowHint || {}
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
            visible: !!(duplicateDialog.windowHint && duplicateDialog.windowHint.conflict)
            spacing: Theme.s2
            Layout.fillWidth: true
            Text {
                text: "Overlaps " + (duplicateDialog.windowHint.conflict || "") + "."
                color: Theme.warning
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            HudButton {
                objectName: "duplicateNextFree"
                visible: !!(duplicateDialog.windowHint.next_free)
                text: "USE NEXT FREE  " + (duplicateDialog.windowHint.next_free_time || "")
                Layout.fillWidth: true
                onClicked: startTime.text = duplicateDialog.windowHint.next_free
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { objectName: "duplicateCancel"; text: "CANCEL"; onClicked: duplicateDialog.close() }
            HudButton {
                objectName: "duplicateConfirm"
                text: "DUPLICATE"
                enabled: duplicateDialog.canDuplicate
                busyText: "COPYING…"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: duplicateDialog.confirm()
            }
        }
    }
}
