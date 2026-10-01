import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: panoramaNoticeDialog
    objectName: "panoramaNoticeDialog"
    property bool continueEnabled: false
    property var continueAction: function() {}
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Theme.px(460)
    height: Math.max(Theme.px(210), headingLabel.implicitHeight + bodyLabel.implicitHeight + Theme.px(100))
    padding: Theme.s4
    standardButtons: Dialog.NoButton
    onOpened: cancelBtn.forceActiveFocus()
    background: DialogFrame { tone: Theme.warning }

    function proceed() {
        if (!panoramaNoticeDialog.continueEnabled)
            return
        panoramaNoticeDialog.close()
        panoramaNoticeDialog.continueAction()
    }

    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: "Panorama work in progress"
        Accessible.description: bodyLabel.text
        Text {
            id: headingLabel
            text: "PANORAMA"
            color: Theme.warning
            font.pixelSize: Theme.fontLg
            font.letterSpacing: Theme.tracking2
        }
        Text {
            id: bodyLabel
            text: "This feature is still a work in progress. Framing does not work yet. It will only capture the frame last set on this telescope from the mobile app."
            color: Theme.textPrimary
            font.pixelSize: Theme.fontMd
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton {
                id: cancelBtn
                objectName: "panoramaNoticeCancel"
                text: "CANCEL"
                onClicked: panoramaNoticeDialog.close()
            }
            HudButton {
                objectName: "panoramaNoticeContinue"
                text: "CONTINUE"
                buttonColor: Theme.fillWarning
                foregroundColor: Theme.warning
                enabled: panoramaNoticeDialog.continueEnabled
                onClicked: panoramaNoticeDialog.proceed()
            }
        }
    }
}
