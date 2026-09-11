import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: searchCombo
    property var allItems: []
    property int filterLimit: 120
    property string selectedName: ""
    property alias editText: searchField.text
    property bool listOpen: false
    property var filtered: []
    signal itemChosen(var item)
    implicitHeight: 34
    implicitWidth: 240

    function copyAllItems() {
        const items = searchCombo.allItems || []
        const out = []
        for (let i = 0; i < items.length; i++)
            out.push(items[i])
        return out
    }

    function indexOfCurrent(items) {
        const name = searchCombo.selectedName
        const text = String(searchField.text || "")
        for (let i = 0; i < items.length; i++) {
            if ((name && items[i].name === name) || items[i].name === text || items[i].label === text)
                return i
        }
        return items.length ? 0 : -1
    }

    function revealCurrent() {
        const idx = suggestionView.currentIndex
        if (idx < 0)
            return
        suggestionView.positionViewAtIndex(idx, ListView.Center)
    }

    function openFullList() {
        const items = copyAllItems()
        const idx = searchCombo.indexOfCurrent(items)
        searchCombo.filtered = items
        searchCombo.listOpen = true
        Qt.callLater(function () {
            suggestionView.currentIndex = idx
            searchCombo.revealCurrent()
            if (searchCombo.selectedName)
                searchField.selectAll()
        })
    }

    function refreshFilter() {
        const needle = String(searchField.text || "").toLowerCase().replace(/_/g, " ")
        if (!needle) {
            const items = copyAllItems()
            searchCombo.filtered = items
            suggestionView.currentIndex = searchCombo.indexOfCurrent(items)
            Qt.callLater(searchCombo.revealCurrent)
            return
        }
        const items = searchCombo.allItems || []
        const ranked = []
        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            const hay = [item.name, item.label, item.comment].join(" ").toLowerCase().replace(/_/g, " ")
            if (hay.indexOf(needle) < 0)
                continue
            const city = String(item.name).split("/").pop().toLowerCase().replace(/_/g, " ")
            let score = 2
            if (city === needle || String(item.name).toLowerCase() === needle)
                score = 0
            else if (city.startsWith(needle) || String(item.name).toLowerCase().replace(/_/g, " ").startsWith(needle))
                score = 1
            ranked.push({score: score, name: item.name, item: item})
        }
        ranked.sort(function (a, b) { return a.score - b.score || a.name.localeCompare(b.name) })
        const out = []
        for (let i = 0; i < ranked.length && i < searchCombo.filterLimit; i++)
            out.push(ranked[i].item)
        searchCombo.filtered = out
        suggestionView.currentIndex = out.length ? 0 : -1
    }

    function setFromName(name) {
        searchCombo.selectedName = name || ""
        searchCombo.listOpen = false
        let label = name || ""
        const items = searchCombo.allItems || []
        for (let i = 0; i < items.length; i++) {
            if (items[i].name === name) {
                label = items[i].label
                break
            }
        }
        searchField.text = label
    }

    function chooseItem(item) {
        if (!item)
            return
        searchCombo.selectedName = item.name || ""
        searchCombo.listOpen = false
        searchField.text = item.label || item.name || ""
        searchCombo.itemChosen(item)
    }

    function acceptTyped() {
        if (listOpen && suggestionView.currentIndex >= 0 && suggestionView.currentIndex < filtered.length) {
            chooseItem(filtered[suggestionView.currentIndex])
            return
        }
        backend.lookupLocation(searchField.text)
    }

    onListOpenChanged: {
        if (listOpen) {
            if (!suggestionPopup.opened)
                suggestionPopup.open()
        } else if (suggestionPopup.opened) {
            suggestionPopup.close()
        }
    }

    HudField {
        id: searchField
        width: parent.width
        height: parent.height
        placeholderText: "Search city or timezone"
        rightPadding: 26
        releaseFocusOnEnter: false
        Keys.priority: Keys.BeforeItem
        onTextEdited: {
            searchCombo.selectedName = ""
            searchCombo.refreshFilter()
            searchCombo.listOpen = true
        }
        onActiveFocusChanged: {
            if (activeFocus && !searchCombo.listOpen)
                searchCombo.openFullList()
        }
        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: 26
            propagateComposedEvents: true
            onPressed: function (mouse) {
                if (!searchCombo.listOpen)
                    searchCombo.openFullList()
                mouse.accepted = false
            }
        }
        Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Down) {
                event.accepted = true
                if (!searchCombo.listOpen)
                    searchCombo.openFullList()
                else if (suggestionView.currentIndex < filtered.length - 1)
                    suggestionView.incrementCurrentIndex()
            } else if (event.key === Qt.Key_Up) {
                event.accepted = true
                if (!searchCombo.listOpen)
                    searchCombo.openFullList()
                else if (suggestionView.currentIndex > 0)
                    suggestionView.decrementCurrentIndex()
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                event.accepted = true
                searchCombo.acceptTyped()
            } else if (event.key === Qt.Key_Escape) {
                event.accepted = true
                searchCombo.listOpen = false
            } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                searchCombo.listOpen = false
            }
        }
    }
    Text {
        text: "▾"
        color: Theme.accent
        z: 2
        anchors.right: searchField.right
        anchors.rightMargin: 8
        anchors.verticalCenter: searchField.verticalCenter
        MouseArea {
            anchors.fill: parent
            anchors.margins: -8
            onClicked: {
                if (searchCombo.listOpen) {
                    searchCombo.listOpen = false
                    return
                }
                searchField.forceActiveFocus()
                searchCombo.openFullList()
            }
        }
    }
    Popup {
        id: suggestionPopup
        y: searchField.height + 3
        width: Math.max(searchCombo.width, 360)
        height: Math.min(Math.max(searchCombo.filtered.length, 1), 10) * 32 + 2
        padding: 1
        modal: false
        focus: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        palette.base: Theme.popupBg
        palette.text: Theme.textPrimary
        background: HudFrame {
            topLeft: 0
            topRight: 0
            bottomRight: Theme.notchSmall
            bottomLeft: 0
            fillColor: Theme.popupBg
            strokeColor: Theme.accent
        }
        onOpened: searchCombo.listOpen = true
        onClosed: searchCombo.listOpen = false
        contentItem: Item {
            ListView {
                id: suggestionView
                anchors.fill: parent
                clip: true
                visible: searchCombo.filtered.length > 0
                boundsBehavior: Flickable.StopAtBounds
                model: searchCombo.filtered
                currentIndex: 0
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                onCurrentIndexChanged: {
                    if (currentIndex >= 0)
                        positionViewAtIndex(currentIndex, ListView.Contain)
                }
                delegate: Rectangle {
                    width: suggestionView.width
                    height: 32
                    readonly property var item: modelData
                    readonly property int row: index
                    color: suggestionView.currentIndex === row ? Theme.fillChecked : Theme.popupBg
                    Text {
                        anchors.fill: parent
                        leftPadding: 10
                        rightPadding: 10
                        text: item && (item.label || item.name) || ""
                        color: suggestionView.currentIndex === row ? Theme.accent : Theme.textPrimary
                        font.pixelSize: 13
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: suggestionView.currentIndex = row
                        onClicked: searchCombo.chooseItem(item)
                    }
                }
            }
            Text {
                anchors.fill: parent
                visible: searchCombo.filtered.length === 0
                leftPadding: 10
                text: "No matches"
                color: Theme.textSecondary
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
