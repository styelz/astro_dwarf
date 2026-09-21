import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import ".."

Item {
    id: panel
    property alias title: heading.text
    property alias headerExtra: headerExtraRow.data
    property alias overlay: overlayHost.data
    property color fill: Theme.panelFill
    property color titleColor: Theme.accent
    default property alias contents: body.data
    implicitWidth: 240
    implicitHeight: (headerRow.visible ? headerRow.implicitHeight + 17 : 0) + body.implicitHeight + 24
    clip: true

    property string panelId: ""
    property bool movable: panelId !== ""
    property string moveLabel: heading.text
    property string swapHome: ""
    property int swapHomeIndex: -1
    property var swapDefaultProps: null
    property string dropMode: ""
    property bool moveStarted: false
    property bool hot: false          // set by callers for the "active" panel; hover also lights it
    readonly property bool dropTarget: dropMode === "swap"
    readonly property bool lit: hot || panelHover.hovered || panel.dropTarget || panel.dropMode === "before" || panel.dropMode === "after"
    readonly property bool dragging: PanelSwap.source === panel
    HoverHandler { id: panelHover }

    function mapPoint(item, x, y) {
        const host = PanelSwap.host
        if (!host || !item)
            return Qt.point(0, 0)
        return item.mapToItem(host, x, y)
    }
    function beginMoveAt(item, x, y) {
        panel.moveStarted = true
        PanelSwap.begin(panel, panel.mapPoint(item, x, y))
    }
    function finishMoveAt(item, x, y) {
        if (!panel.moveStarted)
            return
        panel.moveStarted = false
        PanelSwap.finish(panel.mapPoint(item, x, y))
    }
    function cancelMove() {
        if (!panel.moveStarted)
            return
        panel.moveStarted = false
        PanelSwap.cancel()
    }
    function dragMoved(item, mouse) {
        const dx = mouse.x - item.pressPos.x
        const dy = mouse.y - item.pressPos.y
        if (!panel.moveStarted) {
            if (dx * dx + dy * dy < 36)
                return
            panel.beginMoveAt(item, mouse.x, mouse.y)
            return
        }
        PanelSwap.update(panel.mapPoint(item, mouse.x, mouse.y))
    }
    function openLayoutMenu() {
        if (!panel.movable)
            return
        layoutMenu.popup()
    }
    function closeLayoutMenu() {
        layoutMenu.close()
    }
    readonly property bool layoutMenuOpen: layoutMenu.opened

    Component.onCompleted: {
        if (panel.panelId !== "")
            PanelSwap.register(panel)
    }
    Component.onDestruction: PanelSwap.unregister(panel)

    Rectangle { anchors.fill: parent; color: panel.fill }
    // inner vignette: a lit top edge fading into the body
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 2
        height: Math.min(64, parent.height * 0.35)
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, panel.lit ? 0.10 : 0.05) }
            GradientStop { position: 1.0; color: "transparent" }
        }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    }
    Shape {
        id: frame
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        readonly property real n: Theme.notch
        readonly property real o: 1.5
        readonly property real t: 14
        ShapePath {
            strokeColor: Theme.hsl(-0.021, 1.000, 0.955, panel.lit ? 0.55 : 0.40)
            strokeWidth: 1.25
            fillColor: "transparent"
            capStyle: ShapePath.FlatCap
            joinStyle: ShapePath.MiterJoin
            startX: frame.n
            startY: frame.o
            PathLine { x: panel.width - frame.n; y: frame.o }
            PathLine { x: panel.width - frame.o; y: frame.n }
            PathLine { x: panel.width - frame.o; y: panel.height - frame.n }
            PathLine { x: panel.width - frame.n; y: panel.height - frame.o }
            PathLine { x: frame.n; y: panel.height - frame.o }
            PathLine { x: frame.o; y: panel.height - frame.n }
            PathLine { x: frame.o; y: frame.n }
            PathLine { x: frame.n; y: frame.o }
        }
        ShapePath {
            strokeColor: Theme.hsl(0.001, 1.000, 0.651, panel.lit ? 1.0 : 0.8)
            strokeWidth: panel.lit ? 2.5 : 2
            fillColor: "transparent"
            capStyle: ShapePath.FlatCap
            startX: frame.n
            startY: frame.o
            PathLine { x: frame.n + frame.t; y: frame.o }
            PathMove { x: frame.o; y: frame.n }
            PathLine { x: frame.o; y: frame.n + frame.t }
            PathMove { x: panel.width - frame.n; y: panel.height - frame.o }
            PathLine { x: panel.width - frame.n - frame.t; y: panel.height - frame.o }
            PathMove { x: panel.width - frame.o; y: panel.height - frame.n }
            PathLine { x: panel.width - frame.o; y: panel.height - frame.n - frame.t }
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8
        RowLayout {
            id: headerRow
            visible: heading.text.length || headerExtraRow.children.length
            Layout.fillWidth: true
            spacing: 8
            Item {
                id: dragHandle
                objectName: panel.panelId !== "" ? "panelDrag-" + panel.panelId : ""
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: Math.max(heading.implicitHeight, 14)
                Accessible.role: Accessible.Button
                Accessible.name: "Move " + (panel.moveLabel || heading.text || "panel")
                Accessible.description: "Drag onto another panel to swap, or onto an edge to insert"
                property point pressPos: Qt.point(0, 0)
                Row {
                    id: handleRow
                    anchors.fill: parent
                    spacing: 6
                    Item {
                        id: grip
                        visible: panel.movable
                        width: visible ? 8 : 0
                        height: parent.height
                        readonly property color dot: headerMove.pressed || headerMove.containsMouse ? Theme.accent : Theme.textSecondary
                        Column {
                            anchors.centerIn: parent
                            spacing: 2
                            Row { spacing: 2; Rectangle { width: 2; height: 2; color: grip.dot } Rectangle { width: 2; height: 2; color: grip.dot } }
                            Row { spacing: 2; Rectangle { width: 2; height: 2; color: grip.dot } Rectangle { width: 2; height: 2; color: grip.dot } }
                            Row { spacing: 2; Rectangle { width: 2; height: 2; color: grip.dot } Rectangle { width: 2; height: 2; color: grip.dot } }
                        }
                    }
                    Text {
                        id: heading
                        visible: text.length
                        width: visible ? Math.max(0, handleRow.width - grip.width - (grip.visible ? handleRow.spacing : 0)) : 0
                        color: panel.titleColor
                        font.pixelSize: Theme.fontPx(11)
                        font.letterSpacing: 1.6
                        font.bold: true
                        elide: Text.ElideRight
                    }
                }
                MouseArea {
                    id: headerMove
                    anchors.fill: parent
                    z: 10
                    enabled: panel.movable && !DragCoordinator.active
                    hoverEnabled: true
                    preventStealing: true
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    cursorShape: pressed && (pressedButtons & Qt.LeftButton) ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    onPressed: (mouse) => {
                        if (mouse.button === Qt.RightButton) {
                            panel.openLayoutMenu()
                            mouse.accepted = true
                            return
                        }
                        dragHandle.pressPos = Qt.point(mouse.x, mouse.y)
                    }
                    onPositionChanged: (mouse) => {
                        if (mouse.buttons & Qt.LeftButton)
                            panel.dragMoved(dragHandle, mouse)
                    }
                    onReleased: (mouse) => {
                        if (mouse.button === Qt.LeftButton && panel.moveStarted)
                            panel.finishMoveAt(dragHandle, mouse.x, mouse.y)
                    }
                    onCanceled: panel.cancelMove()
                }
                HudToolTip {
                    visible: panel.movable && headerMove.containsMouse && !headerMove.pressed && !PanelSwap.active
                    text: "Drag onto a panel to swap, onto a panel edge to insert, or onto a column edge to create a column. Right-click to reset the layout."
                }
            }
            Row {
                id: headerExtraRow
                spacing: 4
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            }
        }
        Rectangle {
            visible: headerRow.visible
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            implicitHeight: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6) }
                GradientStop { position: 0.55; color: Theme.hsl(0.039, 0.535, 0.253, 0.200) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
        Flickable {
            id: panelFlick
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            contentWidth: width
            contentHeight: Math.max(height, body.implicitHeight)
            interactive: contentHeight > height + 1
            ScrollBar.vertical: HiddenBar {}
            ScrollBar.horizontal: HiddenBar {}
            Item {
                width: panelFlick.width
                height: Math.max(body.implicitHeight, panelFlick.height)
                ColumnLayout {
                    id: body
                    anchors.fill: parent
                    spacing: 8
                }
            }
            ScrollHint { flick: panelFlick; active: panelHover.hovered }
        }
    }
    Item {
        id: overlayHost
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.top: parent.top
        anchors.topMargin: headerRow.visible ? 12 + headerRow.height + 8 : 0
        z: 5
    }
    Item {
        id: edgeHandle
        visible: panel.movable && !headerRow.visible
        z: 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 14
        objectName: panel.panelId !== "" ? "panelEdge-" + panel.panelId : ""
        property point pressPos: Qt.point(0, 0)
        Accessible.role: Accessible.Button
        Accessible.name: "Move " + (panel.moveLabel || "panel")
        Accessible.description: "Drag onto another panel to swap, or onto an edge to insert"
        Row {
            anchors.centerIn: parent
            spacing: 3
            readonly property color dot: edgeMove.pressed || edgeMove.containsMouse ? Theme.accent : Theme.textSecondary
            readonly property real dim: edgeMove.pressed || edgeMove.containsMouse ? 0.95 : 0.45
            Rectangle { width: 3; height: 3; radius: 1; color: parent.dot; opacity: parent.dim }
            Rectangle { width: 3; height: 3; radius: 1; color: parent.dot; opacity: parent.dim }
            Rectangle { width: 3; height: 3; radius: 1; color: parent.dot; opacity: parent.dim }
            Rectangle { width: 3; height: 3; radius: 1; color: parent.dot; opacity: parent.dim }
            Rectangle { width: 3; height: 3; radius: 1; color: parent.dot; opacity: parent.dim }
        }
        MouseArea {
            id: edgeMove
            anchors.fill: parent
            enabled: edgeHandle.visible && !DragCoordinator.active
            hoverEnabled: true
            preventStealing: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            cursorShape: pressed && (pressedButtons & Qt.LeftButton) ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            onPressed: (mouse) => {
                if (mouse.button === Qt.RightButton) {
                    panel.openLayoutMenu()
                    mouse.accepted = true
                    return
                }
                edgeHandle.pressPos = Qt.point(mouse.x, mouse.y)
            }
            onPositionChanged: (mouse) => {
                if (mouse.buttons & Qt.LeftButton)
                    panel.dragMoved(edgeHandle, mouse)
            }
            onReleased: (mouse) => {
                if (mouse.button === Qt.LeftButton && panel.moveStarted)
                    panel.finishMoveAt(edgeHandle, mouse.x, mouse.y)
            }
            onCanceled: panel.cancelMove()
        }
        HudToolTip {
            visible: edgeHandle.visible && edgeMove.containsMouse && !edgeMove.pressed && !PanelSwap.active
            text: "Drag onto a panel to swap, onto a panel edge to insert, or onto a column edge to create a column. Right-click to reset the layout."
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.topMargin: headerRow.visible ? 12 + headerRow.height + 8 : (panel.movable ? 14 : 0)
        z: 20
        enabled: false
        visible: panel.dragging || panel.dropMode === "swap"
        color: panel.dropMode === "swap" ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12) : Qt.rgba(0, 0, 0, 0.22)
        border.color: panel.dropMode === "swap" ? Theme.accent : Theme.outlineStrong
        border.width: panel.dropMode === "swap" ? 2 : 1
    }
    Rectangle {
        z: 21
        enabled: false
        visible: panel.dropMode === "before" || panel.dropMode === "after"
        height: 3
        width: parent.width
        y: panel.dropMode === "after" ? parent.height - height : 0
        color: Theme.accent
    }
    TapHandler {
        id: panelLayoutTap
        acceptedButtons: Qt.RightButton
        enabled: panel.movable && !DragCoordinator.active && !PanelSwap.active
        grabPermissions: PointerHandler.ApprovesTakeOverByAnything
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: (eventPoint) => {
            const grabber = eventPoint["exclusiveGrabber"]
            if (grabber && grabber !== panelLayoutTap)
                return
            panel.openLayoutMenu()
        }
    }
    LayoutContextMenu {
        id: layoutMenu
        objectName: panel.panelId !== "" ? "layoutResetMenu-" + panel.panelId : "layoutResetMenu"
    }
}
