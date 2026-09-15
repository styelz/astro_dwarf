pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

RowLayout {
    id: navBar
    property int currentIndex: 0
    property int attentionIndex: -1
    property string attentionDescription: "Needs attention"
    property bool skyToolsEnabled: false
    signal pageRequested(int index)
    Layout.fillWidth: true
    Layout.preferredHeight: 48
    Layout.maximumHeight: 48
    Layout.fillHeight: false
    Layout.leftMargin: 10
    Layout.rightMargin: 10
    spacing: 8
    readonly property var pages: {
        void navBar.skyToolsEnabled
        const items = [
            {label: "CONTROL", idx: 0},
            {label: "CALENDAR", idx: 1},
            {label: "SESSIONS", idx: 2},
            {label: "HISTORY", idx: 3},
            {label: "MEDIA", idx: 4}
        ]
        if (navBar.skyToolsEnabled)
            items.push({label: "SKY", idx: 5})
        items.push({label: "SETTINGS", idx: 6})
        return items
    }
    Repeater {
        id: navRepeater
        model: navBar.pages
        delegate: HudButton {
            required property int index
            required property var modelData
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Layout.fillHeight: false
            text: modelData.label
            font.pixelSize: 12
            font.letterSpacing: 1.4
            buttonColor: navBar.currentIndex === modelData.idx ? Theme.fillActive : Theme.inputBg
            foregroundColor: navBar.currentIndex === modelData.idx ? Theme.accent : Theme.textSecondary
            Accessible.name: modelData.label
            Accessible.description: (navBar.currentIndex === modelData.idx ? "Current page" : "Open page")
                                    + (navBar.attentionIndex === modelData.idx ? ". " + navBar.attentionDescription : "")
            onClicked: navBar.pageRequested(modelData.idx)
            Keys.onLeftPressed: {
                const previousIndex = (index + navRepeater.count - 1) % navRepeater.count
                navRepeater.itemAt(previousIndex).forceActiveFocus()
                navBar.pageRequested(navBar.pages[previousIndex].idx)
            }
            Keys.onRightPressed: {
                const nextIndex = (index + 1) % navRepeater.count
                navRepeater.itemAt(nextIndex).forceActiveFocus()
                navBar.pageRequested(navBar.pages[nextIndex].idx)
            }
            Rectangle {
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 1
                anchors.horizontalCenter: parent.horizontalCenter
                height: 2
                width: navBar.currentIndex === parent.modelData.idx ? parent.width - 24 : 0
                color: Theme.accent
                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
            Rectangle {
                visible: navBar.attentionIndex === parent.modelData.idx
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 7
                width: 6
                height: 6
                radius: 3
                color: Theme.warning
            }
        }
    }
}
