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
    implicitWidth: Theme.px(232)
    padding: Theme.px(6)
    topPadding: Theme.px(6)
    bottomPadding: Theme.px(6)
    leftPadding: Theme.px(6)
    rightPadding: Theme.px(6)
    overlap: 2
    background: Rectangle {
        color: Theme.surfaceHigh
        border.color: Theme.outline
        border.width: 1
        radius: Theme.notchSmall + Theme.radius
    }
}
