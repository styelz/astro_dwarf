import QtQuick
import ".."

HudMenuItem {
    objectName: "resetControlLayout"
    text: "Reset layout to default"
    glyph: "\uE72C"
    accessibleDescription: "Put control-page panels and splitters back to their stock arrangement"
    onTriggered: PanelSwap.resetToDefault()
}
