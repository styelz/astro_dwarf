import QtQuick
import QtQuick.Controls
import QtQuick.Window
import ".."

// Hairline scrollbar. Inside a framed panel the thumb is drawn on that
// panel's right stroke. Page lists with pinToWindow sit on the window border.
ScrollBar {
    id: bar
    policy: ScrollBar.AsNeeded
    hoverEnabled: true
    activeFocusOnTab: false
    minimumSize: 0.08
    padding: 0

    property bool pinToWindow: false
    property Item borderHost: null
    readonly property bool onFrame: borderHost !== null
    readonly property Item windowEdge: {
        const view = parent
        if (!pinToWindow || !view || !view.Window.window)
            return null
        return view.Window.window.contentItem
    }
    readonly property bool onWindow: windowEdge !== null && !onFrame
    readonly property real windowY: {
        const host = windowEdge
        const view = parent
        if (!host || !view)
            return 0
        void view.y
        void view.height
        void host.height
        void host.width
        return view.mapToItem(host, 0, 0).y
    }
    readonly property bool alongX: orientation === Qt.Horizontal
    readonly property bool emphasized: pressed || hovered || active
    readonly property int stroke: Theme.px(2)
    readonly property real frameY: {
        const host = borderHost
        const view = parent
        if (!host || !view)
            return 0
        void view.y
        void view.height
        void host.height
        void host.width
        return view.mapToItem(host, 0, 0).y
    }
    readonly property real viewSpan: parent ? parent.height : 0
    // Effective visibility: a hidden page, timeline, or popup clears it.
    // Walking each ancestor's visible flag loops against layouts and popups.
    readonly property bool viewShown: !!(parent && parent.visible)

    function resolveHost() {
        let node = parent
        while (node) {
            if (node.frameBorder === true)
                return node
            node = node.parent
        }
        return null
    }
    onParentChanged: borderHost = resolveHost()
    Component.onCompleted: borderHost = resolveHost()

    function seek(localY, groove, thumbHeight) {
        const travel = Math.max(1, groove - thumbHeight)
        const fraction = Math.max(0, Math.min(1, (localY - thumbHeight / 2) / travel))
        position = fraction * Math.max(0, 1 - size)
    }

    implicitWidth: (onFrame || onWindow) ? 0 : Theme.px(8)
    implicitHeight: (onFrame || onWindow) ? 0 : Theme.px(8)

    contentItem: Item {
        visible: !bar.onFrame && !bar.onWindow
        implicitWidth: Theme.px(8)
        implicitHeight: Theme.px(8)
        Rectangle {
            // Sit on the content's trailing border, not out in the margin.
            x: 0
            y: 0
            width: bar.alongX ? parent.width : Theme.px(1)
            height: bar.alongX ? Theme.px(1) : parent.height
            color: Theme.accent
            opacity: bar.emphasized ? 1 : 0.75
        }
    }

    background: Item {
        visible: !bar.onFrame && !bar.onWindow
        implicitWidth: Theme.px(8)
        implicitHeight: Theme.px(8)
        Rectangle {
            x: 0
            y: 0
            width: bar.alongX ? parent.width : Theme.px(1)
            height: bar.alongX ? Theme.px(1) : parent.height
            color: Theme.outline
            opacity: 0.85
        }
    }

    Item {
        id: rail
        parent: bar.borderHost || bar
        z: 20
        visible: bar.onFrame && bar.size < 0.999
        width: Theme.px(10)
        height: bar.viewSpan
        x: bar.borderHost ? bar.borderHost.width - width : 0
        y: bar.frameY

        Rectangle {
            id: thumb
            anchors.right: parent.right
            anchors.rightMargin: Math.max(0, (bar.borderHost && bar.borderHost.frameEdge ? bar.borderHost.frameEdge : 0) - width / 2)
            width: bar.stroke
            height: Math.max(Theme.px(16), bar.visualSize * rail.height)
            y: Math.max(0, Math.min(rail.height - height, bar.visualPosition * rail.height))
            color: Theme.accent
            opacity: railDrag.pressed || railDrag.containsMouse ? 1 : 0.9
        }
        MouseArea {
            id: railDrag
            anchors.fill: parent
            hoverEnabled: true
            preventStealing: true
            cursorShape: Qt.SizeVerCursor
            onPressed: (mouse) => bar.seek(mouse.y, rail.height, thumb.height)
            onPositionChanged: (mouse) => {
                if (pressed)
                    bar.seek(mouse.y, rail.height, thumb.height)
            }
        }
    }

    Item {
        id: windowRail
        parent: bar.windowEdge || bar
        z: 2100
        visible: bar.onWindow && bar.viewShown && !bar.alongX && bar.size < 0.999 && bar.viewSpan > 1
        width: Theme.px(12)
        height: bar.viewSpan
        x: parent ? parent.width - width : 0
        y: bar.windowY

        Rectangle {
            id: windowThumb
            anchors.right: parent.right
            width: bar.stroke
            height: Math.max(Theme.px(16), bar.visualSize * windowRail.height)
            y: Math.max(0, Math.min(windowRail.height - height, bar.visualPosition * windowRail.height))
            color: Theme.accent
            opacity: windowDrag.pressed || windowDrag.containsMouse ? 1 : 0.9
        }
        MouseArea {
            id: windowDrag
            anchors.fill: parent
            hoverEnabled: true
            preventStealing: true
            cursorShape: Qt.SizeVerCursor
            onPressed: (mouse) => bar.seek(mouse.y, windowRail.height, windowThumb.height)
            onPositionChanged: (mouse) => {
                if (pressed)
                    bar.seek(mouse.y, windowRail.height, windowThumb.height)
            }
        }
    }
}
