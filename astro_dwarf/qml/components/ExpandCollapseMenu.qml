import QtQuick

HudMenu {
    id: expandCollapseMenu
    property bool canExpandAll: false
    property bool canCollapseAll: false
    property string expandObjectName: "expand-all"
    property string collapseObjectName: "collapse-all"
    signal expandAllRequested()
    signal collapseAllRequested()

    HudMenuItem {
        objectName: expandCollapseMenu.expandObjectName
        text: "Expand all"
        glyph: "\uE70D"
        enabled: expandCollapseMenu.canExpandAll
        accessibleDescription: "Expand every collapsible session group or row on this page"
        onTriggered: expandCollapseMenu.expandAllRequested()
    }
    HudMenuItem {
        objectName: expandCollapseMenu.collapseObjectName
        text: "Collapse all"
        glyph: "\uE70E"
        enabled: expandCollapseMenu.canCollapseAll
        accessibleDescription: "Collapse every expanded session group or row on this page"
        onTriggered: expandCollapseMenu.collapseAllRequested()
    }
}
