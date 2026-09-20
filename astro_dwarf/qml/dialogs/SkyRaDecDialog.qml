import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import ".."
import "../components"

Dialog {
    id: dialog
    objectName: "skyRaDecDialog"
    property int formatIndex: 0
    property bool hasCoords: false
    property real raHours: 0
    property real decDegrees: 0
    property string formatName: ""
    property string formatHint: ""
    property string errorText: ""
    signal gotoRequested(real raHours, real decDegrees)

    // Same native window path as HudMenu / the sky right-click menu so
    // WebView2 cannot paint over the dialog and the map can stay visible.
    popupType: Popup.Window
    modal: true
    dim: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    header: null
    footer: null
    width: 420
    height: body.implicitHeight + padding * 2
    padding: Theme.s4
    background: DialogFrame {}
    onAboutToShow: dialog.placeCentered()

    function placeCentered() {
        const win = dialog.Window.window
        const host = dialog.parent
        if (!win || !host)
            return
        const origin = host.mapToItem(null, 0, 0)
        dialog.x = Math.round((win.width - dialog.width) / 2 - origin.x)
        dialog.y = Math.round((win.height - dialog.height) / 2 - origin.y)
    }

    component IconBtn: HudButton {
        implicitWidth: Theme.controlHeight
        implicitHeight: Theme.controlHeight
        Layout.preferredWidth: Theme.controlHeight
        Layout.preferredHeight: Theme.controlHeight
        leftPadding: 0
        rightPadding: 0
        font.family: Theme.fontIcon
        font.pixelSize: 13
        font.letterSpacing: 0
        buttonColor: "transparent"
        foregroundColor: Theme.textSecondary
    }

    function applyInfo(info, fillFields) {
        const data = info || ({})
        dialog.formatName = String(data.format_name || "")
        dialog.formatHint = String(data.format_hint || "")
        raField.placeholderText = String(data.ra_placeholder || "")
        decField.placeholderText = String(data.dec_placeholder || "")
        if (fillFields && data.valid) {
            raField.text = String(data.ra_text || "")
            decField.text = String(data.dec_text || "")
        }
    }

    function applyFormatToFields() {
        if (dialog.hasCoords)
            dialog.applyInfo(backend.formatSkyCoordinateFields(dialog.raHours, dialog.decDegrees, dialog.formatIndex), true)
        else
            dialog.applyInfo(backend.skyCoordinateFormatInfo(dialog.formatIndex), false)
    }

    function commitFields() {
        const parsed = backend.parseSkyCoordinateFields(raField.text, decField.text, dialog.formatIndex) || ({})
        if (!parsed.valid)
            return false
        dialog.raHours = Number(parsed.ra_hours)
        dialog.decDegrees = Number(parsed.dec_degrees)
        dialog.hasCoords = isFinite(dialog.raHours) && isFinite(dialog.decDegrees)
        dialog.errorText = ""
        return dialog.hasCoords
    }

    function openAt(raHours, decDegrees) {
        const ra = Number(raHours)
        const dec = Number(decDegrees)
        dialog.errorText = ""
        dialog.hasCoords = isFinite(ra) && isFinite(dec)
        if (dialog.hasCoords) {
            dialog.raHours = ra
            dialog.decDegrees = dec
        } else {
            raField.text = ""
            decField.text = ""
        }
        dialog.applyFormatToFields()
        dialog.open()
    }

    function cycleFormat() {
        dialog.commitFields()
        dialog.formatIndex = (dialog.formatIndex + 1) % 4
        dialog.applyFormatToFields()
    }

    function copyField(field) {
        const text = String(field.text || "").trim()
        if (!text)
            return
        backend.copyText(text)
    }

    function applyGoto() {
        if (!dialog.commitFields()) {
            dialog.errorText = "Enter a valid RA and Dec in the current format."
            raField.forceActiveFocus()
            return
        }
        dialog.gotoRequested(dialog.raHours, dialog.decDegrees)
        dialog.close()
    }

    onOpened: {
        dialog.applyFormatToFields()
        raField.forceActiveFocus()
        raField.selectAll()
    }

    contentItem: ColumnLayout {
        id: body
        spacing: Theme.s3
        Accessible.name: "Enter RA and Dec"
        Accessible.description: "Center the sky map on right ascension and declination"

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            Text {
                text: "ENTER RA / DEC"
                color: Theme.accent
                font.pixelSize: Theme.fontLg
                font.letterSpacing: Theme.tracking2
                Layout.fillWidth: true
            }
            HudButton {
                objectName: "skyRaDecClose"
                text: "×"
                implicitWidth: 40
                tooltip: "Close"
                accessibleDescription: "Close the RA and Dec dialog"
                onClicked: dialog.close()
            }
        }

        Text {
            text: "Center the sky map on these ICRS coordinates. Opening the dialog fills the current map centre."
            color: Theme.textSecondary
            font.pixelSize: Theme.fontMd
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: Theme.s2
            rowSpacing: Theme.s2

            FieldLabel {
                text: "RA"
                Layout.preferredWidth: implicitWidth
            }
            HudField {
                id: raField
                objectName: "skyRaField"
                accessibleName: "Right ascension"
                Layout.fillWidth: true
                releaseFocusOnEnter: false
                Keys.onReturnPressed: (event) => { event.accepted = true; dialog.applyGoto() }
                Keys.onEnterPressed: (event) => { event.accepted = true; dialog.applyGoto() }
            }
            IconBtn {
                objectName: "skyRaCopy"
                text: "\uE8C8"
                tooltip: "Copy RA"
                accessibleDescription: "Copy the right ascension field"
                Accessible.name: "Copy RA"
                busyText: "\uE73E"
                busyMs: 900
                enabled: raField.text.trim() !== ""
                onClicked: dialog.copyField(raField)
            }

            FieldLabel {
                text: "DEC"
                Layout.preferredWidth: implicitWidth
            }
            HudField {
                id: decField
                objectName: "skyDecField"
                accessibleName: "Declination"
                Layout.fillWidth: true
                releaseFocusOnEnter: false
                Keys.onReturnPressed: (event) => { event.accepted = true; dialog.applyGoto() }
                Keys.onEnterPressed: (event) => { event.accepted = true; dialog.applyGoto() }
            }
            IconBtn {
                objectName: "skyDecCopy"
                text: "\uE8C8"
                tooltip: "Copy Dec"
                accessibleDescription: "Copy the declination field"
                Accessible.name: "Copy Dec"
                busyText: "\uE73E"
                busyMs: 900
                enabled: decField.text.trim() !== ""
                onClicked: dialog.copyField(decField)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2
            HudButton {
                objectName: "skyRaDecChangeFormat"
                text: "CHANGE FORMAT"
                tooltip: "Cycle HMS/DMS, spaces, decimal hours, and decimal degrees"
                accessibleDescription: "Cycle through four RA and Dec formats. Current format "
                                       + dialog.formatName
                onClicked: dialog.cycleFormat()
            }
            Text {
                text: dialog.formatName
                color: Theme.accent
                font.pixelSize: Theme.fontMd
                font.letterSpacing: Theme.tracking1
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }

        FieldHint {
            text: dialog.errorText !== "" ? dialog.errorText : dialog.formatHint
            emphasis: dialog.errorText !== ""
            color: dialog.errorText !== "" ? Theme.danger : Theme.textSecondary
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            spacing: Theme.s2
            HudButton {
                objectName: "skyRaDecCancel"
                text: "CANCEL"
                onClicked: dialog.close()
            }
            HudButton {
                objectName: "skyRaDecGoto"
                text: "GO TO"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                accessibleDescription: "Center the sky map on the entered RA and Dec"
                onClicked: dialog.applyGoto()
            }
        }
    }
}
