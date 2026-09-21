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
    width: Theme.px(480)
    height: Theme.px(176)
    padding: Theme.s4
    background: DialogFrame { tone: Theme.warning }
    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: "Unsaved settings"
        Accessible.description: settingsLeaveDialog.pendingPage === -2
            ? "Save your device settings before closing?"
            : (settingsLeaveDialog.pendingDeviceId
                ? "Save your device settings before switching telescopes?"
                : "Save your device settings before leaving this page?")
        Text { text: "UNSAVED SETTINGS"; color: Theme.warning; font.pixelSize: Theme.fontLg; font.letterSpacing: 1.4 }
        Text {
            text: settingsLeaveDialog.pendingPage === -2
                ? "Save your device settings before closing?"
                : (settingsLeaveDialog.pendingDeviceId
                    ? "Save your device settings before switching telescopes?"
                    : "Save your device settings before leaving this page?")
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
                    if (idx === -2)
                        root.close()
                }
            }
            HudButton {
                text: "SAVE"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                onClicked: {
                    const idx = settingsLeaveDialog.pendingPage
                    const deviceId = settingsLeaveDialog.pendingDeviceId
                    if (!settingsPage.saveCurrent())
                        return
                    settingsLeaveDialog.close()
                    if (deviceId)
                        backend.selectDevice(deviceId)
                    if (idx >= 0)
                        root.currentPage = idx
                    if (idx === -2)
                        root.close()
                }
            }
        }
    }
}
