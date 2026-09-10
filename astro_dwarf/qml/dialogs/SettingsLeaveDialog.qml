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
    id: settingsLeaveDialog
    property int pendingPage: -1
    property string pendingDeviceId: ""
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 480
    height: 176
    padding: 16
    background: DialogFrame { tone: Theme.warning }
    contentItem: ColumnLayout {
        spacing: 12
        Text { text: "UNSAVED SETTINGS"; color: Theme.warning; font.pixelSize: 16; font.letterSpacing: 1.4 }
        Text {
            text: settingsLeaveDialog.pendingDeviceId
                ? "Save your device settings before switching telescopes?"
                : "Save your device settings before leaving this page?"
            color: Theme.textPrimary
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            HudButton { text: "CANCEL"; onClicked: settingsLeaveDialog.close() }
            HudButton {
                text: "DISCARD"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: {
                    const idx = settingsLeaveDialog.pendingPage
                    const deviceId = settingsLeaveDialog.pendingDeviceId
                    settingsLeaveDialog.close()
                    settingsPage.load()
                    if (deviceId)
                        backend.selectDevice(deviceId)
                    if (idx >= 0)
                        root.currentPage = idx
                }
            }
            HudButton {
                text: "SAVE"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: {
                    const idx = settingsLeaveDialog.pendingPage
                    const deviceId = settingsLeaveDialog.pendingDeviceId
                    settingsPage.saveCurrent()
                    settingsLeaveDialog.close()
                    if (deviceId)
                        backend.selectDevice(deviceId)
                    if (idx >= 0)
                        root.currentPage = idx
                }
            }
        }
    }
}
