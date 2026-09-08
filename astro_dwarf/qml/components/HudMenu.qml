import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Menu {
    id: hudMenu
    popupType: Popup.Item
    implicitWidth: 232
    padding: 6
    topPadding: 6
    bottomPadding: 6
    leftPadding: 6
    rightPadding: 6
    overlap: 2
    background: Rectangle {
        color: Theme.surfaceHigh
        border.color: Theme.outline
        border.width: 1
        radius: 8
    }
}
