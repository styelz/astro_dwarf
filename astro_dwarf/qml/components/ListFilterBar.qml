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
    property bool showCombo: true
    property bool checkVisible: false
    property string checkText: ""
    property string checkObjectName: ""
    property string checkTooltip: ""
    property bool checkOn: false
    property string query: ""
    property string pendingQuery: ""
    signal comboActivated(int index)
    signal checkToggled(bool checked)

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
        visible: bar.showCombo
        objectName: bar.comboObjectName
        Layout.preferredWidth: bar.showCombo ? bar.comboWidth : 0
        Layout.maximumWidth: bar.showCombo ? bar.comboWidth : 0
        accessibleName: bar.comboAccessibleName
        model: bar.comboModel
        currentIndex: bar.comboIndex
        onActivated: bar.comboActivated(currentIndex)
    }
    HudCheck {
        visible: bar.checkVisible
        objectName: bar.checkObjectName
        text: bar.checkText
        tooltip: bar.checkTooltip
        checked: bar.checkOn
        onToggled: bar.checkToggled(checked)
    }
}
