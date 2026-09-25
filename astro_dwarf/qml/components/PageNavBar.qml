pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: navBar
    objectName: "pageNavBar"
    property int currentIndex: 0
    property int attentionIndex: -1
    property string attentionDescription: "Needs attention"
    property bool skyToolsEnabled: false
    property bool barOnTop: true
    // Persisted display order (list of page idx). Supplied by the caller and
    // mirrored into visualOrder; drags mutate visualOrder only, then commit.
    property var order: []
    signal pageRequested(int index)
    signal placementRequested(bool onTop)
    signal orderCommitted(var order)
    Layout.fillWidth: true
    Layout.preferredHeight: Theme.px(48)
    Layout.maximumHeight: Theme.px(48)
    Layout.fillHeight: false
    Layout.leftMargin: Theme.px(10)
    Layout.rightMargin: Theme.px(10)
    readonly property real spacing: Theme.s2
    readonly property var pages: {
        void navBar.skyToolsEnabled
        const items = [
            {label: "CONTROL", idx: 0},
            {label: "CALENDAR", idx: 1},
            {label: "SESSIONS", idx: 2},
            {label: "HISTORY", idx: 3},
            {label: "MEDIA", idx: 4}
        ]
        if (navBar.skyToolsEnabled)
            items.push({label: "SKY", idx: 5})
        items.push({label: "SETTINGS", idx: 6})
        return items
    }

    // Working copy of the display order used for rendering. Kept in sync with
    // the externally-supplied `order` except while a drag is in progress.
    property var visualOrder: []
    property int draggingIdx: -1
    property var slotsByIdx: ({})
    readonly property int buttonCount: navBar.pages.length
    readonly property real buttonWidth: navBar.buttonCount > 0
        ? (navBar.width - navBar.spacing * (navBar.buttonCount - 1)) / navBar.buttonCount
        : 0

    function normalizedOrder(candidate) {
        const known = {}
        for (const p of navBar.pages) known[p.idx] = true
        const seen = {}
        const result = []
        for (const raw of (candidate || [])) {
            const idx = Number(raw)
            if (known[idx] && !seen[idx]) {
                result.push(idx)
                seen[idx] = true
            }
        }
        for (const p of navBar.pages) {
            if (!seen[p.idx])
                result.push(p.idx)
        }
        return result
    }
    function stride() {
        return navBar.buttonWidth + navBar.spacing
    }
    function registerSlot(idx, slot) {
        navBar.slotsByIdx[idx] = slot
    }
    function unregisterSlot(idx) {
        delete navBar.slotsByIdx[idx]
    }
    function focusVisualNeighbor(idx, delta) {
        const order = navBar.visualOrder
        const count = order.length
        if (count === 0)
            return
        const curVis = order.indexOf(idx)
        if (curVis < 0)
            return
        const nextIdx = order[(curVis + delta + count) % count]
        const item = navBar.slotsByIdx[nextIdx]
        if (item)
            item.button.forceActiveFocus()
        navBar.pageRequested(nextIdx)
    }
    function beginDrag(idx) {
        navBar.draggingIdx = idx
    }
    function updateDragPosition(idx, x) {
        const st = navBar.stride()
        let targetVis = st > 0 ? Math.round(x / st) : 0
        targetVis = Math.max(0, Math.min(navBar.visualOrder.length - 1, targetVis))
        const currentVis = navBar.visualOrder.indexOf(idx)
        if (currentVis < 0 || targetVis === currentVis)
            return
        const arr = navBar.visualOrder.slice()
        arr.splice(currentVis, 1)
        arr.splice(targetVis, 0, idx)
        navBar.visualOrder = arr
    }
    function endDrag() {
        navBar.draggingIdx = -1
        navBar.orderCommitted(navBar.visualOrder)
    }
    function resetOrder() {
        const arr = navBar.pages.map(p => p.idx)
        navBar.visualOrder = arr
        navBar.orderCommitted(arr)
    }

    Component.onCompleted: navBar.visualOrder = navBar.normalizedOrder(navBar.order)
    onOrderChanged: {
        if (navBar.draggingIdx < 0)
            navBar.visualOrder = navBar.normalizedOrder(navBar.order)
    }
    onPagesChanged: navBar.visualOrder = navBar.normalizedOrder(navBar.visualOrder)

    Repeater {
        id: navRepeater
        model: navBar.pages
        delegate: Item {
            id: slot
            required property var modelData
            readonly property alias button: btn
            readonly property int idx: modelData.idx
            readonly property int visualIndex: navBar.visualOrder.indexOf(idx)
            readonly property bool dragging: navBar.draggingIdx === idx
            property real dragX: 0
            width: navBar.buttonWidth
            height: Theme.px(40)
            y: (navBar.height - height) / 2
            z: slot.dragging ? 10 : 1
            x: slot.dragging ? slot.dragX : slot.visualIndex * navBar.stride()
            Component.onCompleted: navBar.registerSlot(slot.idx, slot)
            Component.onDestruction: navBar.unregisterSlot(slot.idx)
            Behavior on x {
                enabled: !slot.dragging
                NumberAnimation { duration: Theme.quick; easing.type: Easing.OutCubic }
            }

            HudButton {
                id: btn
                anchors.fill: parent
                text: slot.modelData.label
                font.pixelSize: Theme.fontMd
                font.letterSpacing: 1.4
                buttonColor: navBar.currentIndex === slot.idx ? Theme.fillActive : Theme.inputBg
                foregroundColor: navBar.currentIndex === slot.idx ? Theme.accent : Theme.textSecondary
                Accessible.name: slot.modelData.label
                Accessible.description: (navBar.currentIndex === slot.idx ? "Current page" : "Open page")
                                        + (navBar.attentionIndex === slot.idx ? ". " + navBar.attentionDescription : "")
                                        + ". Drag to reorder."
                onClicked: navBar.pageRequested(slot.idx)
                Keys.onLeftPressed: navBar.focusVisualNeighbor(slot.idx, -1)
                Keys.onRightPressed: navBar.focusVisualNeighbor(slot.idx, 1)

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Theme.px(1)
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: Theme.px(2)
                    width: navBar.currentIndex === slot.idx ? parent.width - Theme.px(24) : 0
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                }
                Rectangle {
                    visible: navBar.attentionIndex === slot.idx
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: Theme.px(7)
                    width: Theme.px(6)
                    height: Theme.px(6)
                    radius: Theme.px(3)
                    color: Theme.warning
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: navPlacementMenu.popup()
                }
                DragHandler {
                    id: dragHandler
                    target: null
                    acceptedButtons: Qt.LeftButton
                    xAxis.enabled: true
                    yAxis.enabled: false
                    cursorShape: Qt.ClosedHandCursor
                    property real pressX: 0
                    onActiveChanged: {
                        if (dragHandler.active) {
                            dragHandler.pressX = slot.x
                            slot.dragX = slot.x
                            navBar.beginDrag(slot.idx)
                        } else {
                            navBar.endDrag()
                        }
                    }
                    onTranslationChanged: {
                        if (!dragHandler.active)
                            return
                        const maxX = (navBar.buttonCount - 1) * navBar.stride()
                        const nx = Math.max(0, Math.min(maxX, dragHandler.pressX + dragHandler.translation.x))
                        slot.dragX = nx
                        navBar.updateDragPosition(slot.idx, nx)
                    }
                    onCanceled: navBar.draggingIdx = -1
                }
            }
        }
    }
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: navPlacementMenu.popup()
    }
    HudMenu {
        id: navPlacementMenu
        objectName: "navBarPlacementMenu"
        HudMenuItem {
            text: "Move to top"
            glyph: "\uE74A"
            trailingText: navBar.barOnTop ? "ON" : ""
            enabled: !navBar.barOnTop
            onTriggered: navBar.placementRequested(true)
        }
        HudMenuItem {
            text: "Move to bottom"
            glyph: "\uE74B"
            trailingText: navBar.barOnTop ? "" : "ON"
            enabled: navBar.barOnTop
            onTriggered: navBar.placementRequested(false)
        }
        HudMenuItem {
            text: "Reset button order"
            glyph: "\uE72C"
            onTriggered: navBar.resetOrder()
        }
    }
}
