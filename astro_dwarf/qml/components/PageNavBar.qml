pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

RowLayout {
    id: navBar
    objectName: "pageNavBar"
    property int currentIndex: 0
    property int attentionIndex: -1
    property string attentionDescription: "Needs attention"
    property bool skyToolsEnabled: false
    property bool barOnTop: true
    signal pageRequested(int index)
    signal placementRequested(bool onTop)
    Layout.fillWidth: true
    Layout.preferredHeight: Theme.px(48)
    Layout.maximumHeight: Theme.px(48)
    Layout.fillHeight: false
    Layout.leftMargin: Theme.px(10)
    Layout.rightMargin: Theme.px(10)
    spacing: Theme.s2
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
            Layout.preferredHeight: Theme.px(40)
            Layout.fillHeight: false
            text: modelData.label
            font.pixelSize: Theme.fontMd
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
                anchors.bottomMargin: Theme.px(1)
                anchors.horizontalCenter: parent.horizontalCenter
                height: Theme.px(2)
                width: navBar.currentIndex === parent.modelData.idx ? parent.width - Theme.px(24) : 0
                color: Theme.accent
                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
            Rectangle {
                visible: navBar.attentionIndex === parent.modelData.idx
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.px(7)
                width: Theme.px(6)
                height: Theme.px(6)
                radius: Theme.px(3)
                color: Theme.warning
            }
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: navPlacementMenu.popup()
            }
        }
    }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: navPlacementMenu.popup()
    }
    HudMenu {
        id: navPlacementMenu
        objectName: "navBarPlacementMenu"
        HudMenuItem {
            text: "Move to top"
            glyph: "\uE74A"
            trailingText: navBar.barOnTop ? "ON" : ""
            enabled: !navBar.barOnTop
            onTriggered: navBar.placementRequested(true)
        }
        HudMenuItem {
            text: "Move to bottom"
            glyph: "\uE74B"
            trailingText: navBar.barOnTop ? "" : "ON"
            enabled: navBar.barOnTop
            onTriggered: navBar.placementRequested(false)
        }
    }
}
