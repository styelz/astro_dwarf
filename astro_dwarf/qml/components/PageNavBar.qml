import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

RowLayout {
    id: navBar
    property int currentIndex: 0
    signal pageRequested(int index)
    Layout.fillWidth: true
    Layout.preferredHeight: 48
    Layout.maximumHeight: 48
    Layout.fillHeight: false
    Layout.leftMargin: 10
    Layout.rightMargin: 10
    spacing: 8
    Repeater {
        model: [
            {label: "CONTROL", idx: 0},
            {label: "CALENDAR", idx: 1},
            {label: "SESSIONS", idx: 2},
            {label: "HISTORY", idx: 3},
            {label: "SETTINGS", idx: 4}
        ]
        delegate: HudButton {
            required property var modelData
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.fillHeight: false
            text: modelData.label
            font.pixelSize: 12
            font.letterSpacing: 1.4
            buttonColor: navBar.currentIndex === modelData.idx ? Theme.fillActive : Theme.inputBg
            foregroundColor: navBar.currentIndex === modelData.idx ? Theme.accent : Theme.textSecondary
            onClicked: navBar.pageRequested(modelData.idx)
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 1
                anchors.horizontalCenter: parent.horizontalCenter
                height: 2
                width: navBar.currentIndex === parent.modelData.idx ? parent.width - 24 : 0
                color: Theme.accent
                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
        }
    }
}
