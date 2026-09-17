import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Menu {
    id: hudMenu
    // Native WebView2 / WKWebView paint above QML items. Window popups
    // stay above the sky map so device and page menus remain usable.
    popupType: Popup.Window
    delegate: HudMenuItem {}
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
        radius: Theme.notchSmall + Theme.radius
    }
}
