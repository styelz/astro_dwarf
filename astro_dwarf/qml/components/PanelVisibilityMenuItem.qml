import QtQuick
import ".."

HudMenuItem {
    id: item
    property string panelId: ""
    property string panelLabel: ""
    readonly property bool hidden: PanelSwap.panelHidden(item.panelId)
    objectName: "panelVisibilityMenuItem-" + item.panelId
    text: item.panelLabel
    glyph: item.hidden ? "" : "\uE73E"
    trailingText: item.hidden ? "OFF" : "ON"
    enabled: item.hidden || PanelSwap.visiblePanelCount() > 1
    accessibleDescription: item.hidden
                           ? "Show the " + item.panelLabel + " panel"
                           : "Hide the " + item.panelLabel + " panel"
    onTriggered: PanelSwap.togglePanelHidden(item.panelId)
}
