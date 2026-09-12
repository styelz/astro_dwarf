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
    property string deviceId: ""
    property var templateData: ({})
    readonly property int sessionsTick: backend.sessions.length
    readonly property var windowHint: {
        sessionsTick
        return backend.templateScheduleWindow(scheduleDialog.templateId, scheduleDialog.deviceId, startTime.text,
                                              Number(exposure.text), Number(frames.text))
    }
    readonly property bool captureValid: Number(exposure.text) > 0 && Number(frames.text) >= 1
    readonly property bool canSchedule: templateId.length > 0 && startTime.text.trim().length > 0 && captureValid && !!windowHint.ok && !windowHint.conflict
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 460
    padding: 16
    height: Math.min(root.height - 60, scheduleColumn.implicitHeight + padding * 2)
    background: DialogFrame {}
    function defaultStart() {
        return backend.deviceNowStamp(scheduleDialog.deviceId || backend.selectedDeviceId)
    }
    function confirm() {
        if (!canSchedule)
            return
        if (backend.scheduleTemplate(templateId, startTime.text.trim(), scheduleDialog.deviceId,
                                     Number(exposure.text), Number(frames.text)))
            close()
    }
    function syncDevice() {
        const id = scheduleDialog.deviceId || backend.selectedDeviceId
        for (let i = 0; i < deviceBox.count; i++) {
            if (deviceBox.valueAt(i) === id) {
                deviceBox.currentIndex = i
                scheduleDialog.deviceId = id
                return
            }
        }
        if (deviceBox.count > 0) {
            deviceBox.currentIndex = 0
            scheduleDialog.deviceId = deviceBox.valueAt(0) || backend.selectedDeviceId
        }
    }
    function openFor(data) {
        const item = data || ({})
        templateId = String(item.id || "")
        templateName = String(item.name || item.target_name || "template")
        templateData = item
        deviceId = backend.selectedDeviceId
        syncDevice()
        startTime.text = scheduleDialog.defaultStart()
        const camera = item.camera || ({})
        exposure.text = String(camera.exposure_seconds || 15)
        frames.text = String(camera.frame_count || 120)
        open()
        startTime.forceActiveFocus()
        startTime.selectAll()
    }
    contentItem: ColumnLayout {
        id: scheduleColumn
        spacing: 12
        Text { text: "SCHEDULE TEMPLATE"; color: Theme.accent; font.pixelSize: 16; font.letterSpacing: 1.4 }
        Text {
            text: scheduleDialog.templateName
            color: Theme.textPrimary
            font.pixelSize: 15
            font.bold: true
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text {
            id: recapText
            visible: text !== ""
            text: {
                const item = scheduleDialog.templateData || {}
                const bits = []
                if (item.coords_text)
                    bits.push(item.coords_text)
                if (item.capture_text)
                    bits.push(item.capture_text + (item.gain_text ? "  " + item.gain_text : ""))
                if (item.camera_text)
                    bits.push(item.camera_text)
                if (item.mosaic_text)
                    bits.push(item.mosaic_text)
                if (item.workflow_text)
                    bits.push(item.workflow_text)
                return bits.join("  ·  ")
            }
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: 12
            font.family: Theme.fontMono
            Layout.fillWidth: true
        }
        FieldLabel { text: "DEVICE" }
        HudCombo {
            id: deviceBox
            Layout.fillWidth: true
            model: backend.devices
            textRole: "name"
            valueRole: "id"
            onActivated: if (currentValue) scheduleDialog.deviceId = currentValue
        }
        FieldLabel { text: "START" }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            HudTimeField {
                id: startTime
                Layout.fillWidth: true
                onAccepted: scheduleDialog.confirm()
            }
            HudButton {
                text: "NOW"
                implicitWidth: 72
                onClicked: startTime.text = scheduleDialog.defaultStart()
            }
        }
        FieldLabel { text: "CAPTURE" }
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldLabel { text: "EXPOSURE (SECONDS)" }
                HudField {
                    id: exposure
                    Layout.fillWidth: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.001; notation: DoubleValidator.StandardNotation }
                    accessibleName: "Exposure in seconds"
                }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                FieldLabel { text: "FRAMES" }
                HudField {
                    id: frames
                    Layout.fillWidth: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 99999 }
                    accessibleName: "Frame count"
                }
            }
        }
        Text {
            visible: !!(scheduleDialog.windowHint && scheduleDialog.windowHint.ok)
            text: {
                const hint = scheduleDialog.windowHint || {}
                const zone = hint.timezone || ""
                const finish = hint.end ? "Finishes " + hint.end : ""
                const length = hint.duration_text ? " ·  " + hint.duration_text : ""
                const tz = zone ? "  ·  " + zone : ""
                return finish + length + tz
            }
            color: Theme.textSecondary
            font.pixelSize: 11
            font.family: Theme.fontMono
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        ColumnLayout {
            visible: !!(scheduleDialog.windowHint && scheduleDialog.windowHint.conflict)
            spacing: 8
            Layout.fillWidth: true
            Text {
                text: "Overlaps " + (scheduleDialog.windowHint.conflict || "") + "."
                color: Theme.warning
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            HudButton {
                visible: !!(scheduleDialog.windowHint.next_free)
                text: "USE NEXT FREE  " + (scheduleDialog.windowHint.next_free_time || "")
                Layout.fillWidth: true
                onClicked: startTime.text = scheduleDialog.windowHint.next_free
            }
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
