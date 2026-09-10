import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

RowLayout {
    id: selectionBar
    property int selectedCount: 0
    property int totalCount: 0
    property string noun: "item"
    property bool active: true
    property bool allowMove: false
    property bool allowEdit: true
    property var sessionIds: []
    signal selectAllRequested()
    signal clearRequested()
    signal editRequested()
    signal deleteRequested()
    Layout.fillWidth: true
    visible: active && totalCount > 0
    spacing: 8
    HudButton {
        text: selectionBar.selectedCount > 0 && selectionBar.selectedCount === selectionBar.totalCount ? "CLEAR" : "SELECT ALL"
        implicitHeight: 28
        onClicked: {
            if (selectionBar.selectedCount > 0 && selectionBar.selectedCount === selectionBar.totalCount)
                selectionBar.clearRequested()
            else
                selectionBar.selectAllRequested()
        }
    }
    Text {
        visible: selectionBar.selectedCount > 0
        text: selectionBar.selectedCount + " selected"
        color: Theme.accent
        font.pixelSize: 11
        font.letterSpacing: 0.4
    }
    Item { Layout.fillWidth: true }
    HudButton {
        text: selectionBar.selectedCount > 1 ? "EDIT " + selectionBar.selectedCount : "EDIT SELECTED"
        visible: selectionBar.allowEdit && selectionBar.selectedCount > 1
        implicitHeight: 28
        onClicked: selectionBar.editRequested()
    }
    HudButton {
        text: "MOVE TO"
        visible: selectionBar.allowMove && selectionBar.selectedCount > 0 && (backend.devices || []).length > 1
        implicitHeight: 28
        onClicked: moveMenu.popup()
    }
    MoveDeviceMenu {
        id: moveMenu
        sessionIds: selectionBar.sessionIds
    }
    HudButton {
        text: selectionBar.selectedCount > 1 ? "DELETE " + selectionBar.selectedCount : "DELETE SELECTED"
        enabled: selectionBar.selectedCount > 0
        implicitHeight: 28
        busyText: "DELETING…"
        buttonColor: Theme.fillDanger
        foregroundColor: Theme.danger
        onClicked: selectionBar.deleteRequested()
    }
}
