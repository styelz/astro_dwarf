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
    objectName: "scheduleDialog"
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
    width: Theme.px(460)
    padding: Theme.s4
    height: Math.min(root.height - Theme.px(60), scheduleColumn.implicitHeight + padding * 2)
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
    function captureFor(deviceId) {
        const id = deviceId || scheduleDialog.deviceId || backend.selectedDeviceId
        return Util.captureDefaults(Util.deviceById(backend.devices, id) || backend.selectedDevice)
    }
    function fillCapture(deviceId) {
        const defaults = scheduleDialog.captureFor(deviceId)
        const camera = (scheduleDialog.templateData && scheduleDialog.templateData.camera) || ({})
        const exposureValue = Number(camera.exposure_seconds)
        const frameValue = Number(camera.frame_count)
        exposure.text = String(Number.isFinite(exposureValue) && exposureValue > 0 ? exposureValue : defaults.exposure_seconds)
        frames.text = String(Number.isFinite(frameValue) && frameValue >= 1 ? frameValue : defaults.frame_count)
    }
    function openFor(data) {
        const item = data || ({})
        templateId = String(item.id || "")
        templateName = String(item.name || item.target_name || "template")
        templateData = item
        deviceId = backend.selectedDeviceId
        syncDevice()
        startTime.text = scheduleDialog.defaultStart()
        scheduleDialog.fillCapture(deviceId)
        open()
        startTime.forceActiveFocus()
        startTime.selectAll()
    }
    contentItem: ColumnLayout {
        id: scheduleColumn
        spacing: Theme.s3
        Text { text: "SCHEDULE TEMPLATE"; color: Theme.accent; font.pixelSize: Theme.fontLg; font.letterSpacing: 1.4 }
        Text {
            text: scheduleDialog.templateName
            color: Theme.textPrimary
            font.pixelSize: Theme.fontPx(15)
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
            font.pixelSize: Theme.fontMd
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
            onActivated: {
                if (!currentValue)
                    return
                scheduleDialog.deviceId = currentValue
                scheduleDialog.fillCapture(currentValue)
            }
        }
        FieldLabel { text: "START" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            HudTimeField {
                id: startTime
                Layout.fillWidth: true
                onAccepted: scheduleDialog.confirm()
            }
            HudButton {
                text: "NOW"
                implicitWidth: Theme.px(72)
                onClicked: startTime.text = scheduleDialog.defaultStart()
            }
        }
        FieldLabel { text: "CAPTURE" }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            ColumnLayout {
                spacing: Theme.px(2)
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
                spacing: Theme.px(2)
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
            font.pixelSize: Theme.fontPx(11)
            font.family: Theme.fontMono
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        ColumnLayout {
            visible: !!(scheduleDialog.windowHint && scheduleDialog.windowHint.conflict)
            spacing: Theme.s2
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
            HudButton { objectName: "scheduleCancel"; text: "CANCEL"; onClicked: scheduleDialog.close() }
            HudButton {
                objectName: "scheduleConfirm"
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
