import QtQuick
import QtQuick.Layouts
import ".."

RowLayout {
    id: bar
    property string placeholderText: "Search"
    property string searchAccessibleName: "Search"
    property string comboAccessibleName: "Filter"
    property string searchObjectName: ""
    property string comboObjectName: ""
    property var comboModel: []
    property int comboIndex: 0
    property int comboWidth: Theme.px(160)
    property string query: ""
    property string pendingQuery: ""
    signal comboActivated(int index)

    function clearSearch() {
        searchField.text = ""
        bar.pendingQuery = ""
        bar.query = ""
        searchDebounce.stop()
    }

    Timer {
        id: searchDebounce
        interval: 300
        repeat: false
        onTriggered: bar.query = bar.pendingQuery
    }

    HudField {
        id: searchField
        objectName: bar.searchObjectName
        Layout.fillWidth: true
        Layout.minimumWidth: Theme.px(80)
        placeholderText: bar.placeholderText
        accessibleName: bar.searchAccessibleName
        onTextChanged: {
            bar.pendingQuery = text
            searchDebounce.restart()
        }
    }
    HudCombo {
        objectName: bar.comboObjectName
        Layout.preferredWidth: bar.comboWidth
        Layout.maximumWidth: bar.comboWidth
        accessibleName: bar.comboAccessibleName
        model: bar.comboModel
        currentIndex: bar.comboIndex
        onActivated: bar.comboActivated(currentIndex)
    }
}
