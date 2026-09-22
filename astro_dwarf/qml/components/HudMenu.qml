import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import ".."

Menu {
    id: hudMenu
    // Native WebView2 / WKWebView paint above QML items. Window popups
    // stay above the sky map so device and page menus remain usable.
    // They stay owned by the HUD, so they do not float above other apps.
    popupType: Popup.Window
    // The opening right-click release must not count as clicking away.
    // Arm outside-press after the menu is up. Escape and choosing an item
    // still close immediately. Child menus stay in the cascade: a press
    // inside an open submenu is inside this popup tree.
    property var appWindow: null
    property bool dismissArmed: false
    closePolicy: Popup.CloseOnEscape | (dismissArmed ? Popup.CloseOnPressOutside : Popup.NoAutoClose)
    function captureAppWindow() {
        if (hudMenu.appWindow)
            return
        if (root && root.currentPage !== undefined && root.goToPage !== undefined) {
            hudMenu.appWindow = root
            return
        }
        let item = hudMenu.parent
        while (item) {
            if (item.goToPage !== undefined && item.currentPage !== undefined) {
                hudMenu.appWindow = item
                return
            }
            item = item.parent
        }
    }
    function hideMenu() {
        if (hudMenu.opened || hudMenu.visible)
            hudMenu.close()
    }
    function ownPopupWindow() {
        const popupWindow = hudMenu.contentItem ? hudMenu.contentItem.Window.window : null
        const owner = hudMenu.appWindow
        if (!popupWindow || !owner || popupWindow === owner || popupWindow.visible)
            return
        popupWindow.transientParent = owner
        popupWindow.flags = Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
    }
    Timer {
        id: dismissArm
        interval: 250
        repeat: false
        onTriggered: hudMenu.dismissArmed = true
    }
    onAboutToShow: {
        hudMenu.captureAppWindow()
        hudMenu.dismissArmed = false
        // Opening while another app is in front must not raise this window
        // over that app. A real right-click already has the HUD active.
        hudMenu.focus = Qt.application.state === Qt.ApplicationActive
        hudMenu.ownPopupWindow()
    }
    onOpened: {
        dismissArm.restart()
        if (Qt.application.state !== Qt.ApplicationActive)
            hudMenu.hideMenu()
    }
    onClosed: {
        dismissArm.stop()
        hudMenu.dismissArmed = false
    }
    Connections {
        target: hudMenu.appWindow
        function onCurrentPageChanged() {
            hudMenu.hideMenu()
        }
    }
    Connections {
        target: Qt.application
        function onStateChanged() {
            if (Qt.application.state !== Qt.ApplicationActive)
                hudMenu.hideMenu()
        }
    }
    Component.onCompleted: hudMenu.captureAppWindow()
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
