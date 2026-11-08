import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: darkLibraryDialog
    objectName: "darkLibraryDialog"
    property var choices: ({})
    property bool wideLens: false
    property var exposureNames: []
    property var exposureLabels: []
    property var gainNames: []
    property var binNames: []
    property var binIndexes: []
    readonly property var lensChoices: darkLibraryDialog.wideLens
        ? (darkLibraryDialog.choices.wide_choices || ({}))
        : (darkLibraryDialog.choices.tele || ({}))
    readonly property string sensorText: {
        const device = backend.selectedDevice || ({})
        const telemetry = device.telemetry || ({})
        const text = darkLibraryDialog.wideLens
            ? String(telemetry.cmos_wide_c_text || "")
            : String(telemetry.cmos_tele_c_text || "")
        if (!text || text === "—")
            return ""
        return "SENSOR  " + text
    }
    readonly property bool canStart: darkLibraryDialog.exposureNames.length > 0
        && darkLibraryDialog.gainNames.length > 0
        && exposureBox.currentIndex >= 0
        && gainBox.currentIndex >= 0
        && !!(backend.selectedDevice && backend.selectedDevice.connected)

    function exposureLabel(name) {
        const text = String(name || "")
        return /^\d+$/.test(text) ? text + "s" : text
    }
    function namesOf(rows) {
        const out = []
        const list = rows || []
        for (let i = 0; i < list.length; i++)
            out.push(String((list[i] && list[i].name) || ""))
        return out
    }
    function indexesOf(rows) {
        const out = []
        const list = rows || []
        for (let i = 0; i < list.length; i++)
            out.push(Number((list[i] && list[i].index) || 0))
        return out
    }
    function preferredIndex(names, wanted, fallbackLast) {
        const list = names || []
        for (let i = 0; i < wanted.length; i++) {
            const at = list.indexOf(String(wanted[i]))
            if (at >= 0)
                return at
        }
        if (!list.length)
            return -1
        return fallbackLast ? list.length - 1 : 0
    }
    function loadChoices() {
        darkLibraryDialog.choices = backend.darkLibraryChoices() || ({})
        cameraBox.currentIndex = 0
        darkLibraryDialog.wideLens = false
        darkLibraryDialog.applyLens()
    }
    function applyLens() {
        const pack = darkLibraryDialog.lensChoices || ({})
        darkLibraryDialog.exposureNames = darkLibraryDialog.namesOf(pack.exposures)
        const labels = []
        for (let i = 0; i < darkLibraryDialog.exposureNames.length; i++)
            labels.push(darkLibraryDialog.exposureLabel(darkLibraryDialog.exposureNames[i]))
        darkLibraryDialog.exposureLabels = labels
        darkLibraryDialog.gainNames = darkLibraryDialog.namesOf(pack.gains)
        darkLibraryDialog.binNames = darkLibraryDialog.namesOf(pack.bins)
        darkLibraryDialog.binIndexes = darkLibraryDialog.indexesOf(pack.bins)
        exposureBox.currentIndex = darkLibraryDialog.preferredIndex(darkLibraryDialog.exposureLabels, ["30s", "15s", "10s", "60s"], true)
        gainBox.currentIndex = darkLibraryDialog.preferredIndex(darkLibraryDialog.gainNames, ["60", "80", "40"], false)
        if (binBox.currentIndex < 0 && darkLibraryDialog.binNames.length)
            binBox.currentIndex = 0
    }
    function startCapture() {
        if (!darkLibraryDialog.canStart)
            return
        const exposure = String(darkLibraryDialog.exposureNames[exposureBox.currentIndex] || "")
        const gain = String(darkLibraryDialog.gainNames[gainBox.currentIndex] || "")
        let bin = 1
        if (!darkLibraryDialog.wideLens && binBox.currentIndex >= 0 && binBox.currentIndex < darkLibraryDialog.binIndexes.length)
            bin = Number(darkLibraryDialog.binIndexes[binBox.currentIndex])
        backend.captureDarkFrames(darkLibraryDialog.wideLens ? "wide" : "tele", exposure, gain, bin)
        darkLibraryDialog.close()
    }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(480)
    height: Math.max(Theme.px(320), body.implicitHeight + Theme.px(48))
    padding: Theme.s4
    standardButtons: Dialog.NoButton
    closePolicy: Popup.CloseOnEscape
    onAboutToShow: darkLibraryDialog.loadChoices()
    onOpened: cancelBtn.forceActiveFocus()
    background: DialogFrame {}
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.s3
        Accessible.name: "Take dark frames"
        Accessible.description: String(darkLibraryDialog.choices.steps || "")
        Text {
            text: "TAKE DARKS"
            color: Theme.warning
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            text: String(darkLibraryDialog.choices.steps || "")
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Text {
            text: "Tracking stops while the set is saved. The telescope stores 10 frames."
            color: Theme.textSecondary
            wrapMode: Text.Wrap
            font.pixelSize: Theme.fontSm
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.fillWidth: true
            visible: darkLibraryDialog.choices.wide === true
            spacing: Theme.s2
            FieldLabel {
                text: "CAMERA"
                Layout.preferredWidth: Theme.px(96)
            }
            HudCombo {
                id: cameraBox
                objectName: "darkLibraryCamera"
                Layout.fillWidth: true
                model: ["TELE", "WIDE"]
                accessibleName: "Dark camera"
                tooltip: "Tele or wide darks are stored separately"
                onActivated: {
                    darkLibraryDialog.wideLens = cameraBox.currentIndex === 1
                    darkLibraryDialog.applyLens()
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            FieldLabel {
                text: "EXPOSURE"
                Layout.preferredWidth: Theme.px(96)
            }
            HudCombo {
                id: exposureBox
                objectName: "darkLibraryExposure"
                Layout.fillWidth: true
                model: darkLibraryDialog.exposureLabels
                accessibleName: "Dark exposure"
                tooltip: "Exposure stored with this dark set"
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            FieldLabel {
                text: "GAIN"
                Layout.preferredWidth: Theme.px(96)
            }
            HudCombo {
                id: gainBox
                objectName: "darkLibraryGain"
                Layout.fillWidth: true
                model: darkLibraryDialog.gainNames
                accessibleName: "Dark gain"
                tooltip: darkLibraryDialog.wideLens ? "Wide gain for this set" : "Tele darks use gain 40 to 150"
            }
        }
        RowLayout {
            Layout.fillWidth: true
            visible: !darkLibraryDialog.wideLens && darkLibraryDialog.binNames.length > 0
            spacing: Theme.s2
            FieldLabel {
                text: "SIZE"
                Layout.preferredWidth: Theme.px(96)
            }
            HudCombo {
                id: binBox
                objectName: "darkLibrarySize"
                Layout.fillWidth: true
                model: darkLibraryDialog.binNames
                accessibleName: "Dark resolution"
                tooltip: "4K or 2K. The next stack must use the same size"
            }
        }
        Text {
            visible: darkLibraryDialog.wideLens
            text: "Wide resolution is fixed by the telescope."
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
            Layout.fillWidth: true
        }
        Text {
            visible: darkLibraryDialog.sensorText !== ""
            text: darkLibraryDialog.sensorText
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSm
            font.letterSpacing: Theme.tracking1
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.s2
            HudButton {
                objectName: "darkLibraryStart"
                text: "START"
                enabled: darkLibraryDialog.canStart
                buttonColor: Theme.fillWarning
                foregroundColor: Theme.warning
                Accessible.name: "Start dark capture"
                tooltip: "Cover the lens as described, then capture 10 dark frames"
                onClicked: darkLibraryDialog.startCapture()
            }
            HudButton {
                id: cancelBtn
                objectName: "darkLibraryCancel"
                text: "CANCEL"
                Accessible.name: "Cancel dark capture"
                tooltip: "Leave the dark library unchanged"
                onClicked: darkLibraryDialog.close()
            }
        }
    }
}
