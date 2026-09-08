import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: panel
    property alias title: heading.text
    property alias headerExtra: headerExtraRow.data
    property alias overlay: overlayHost.data
    property color fill: Theme.panelFill
    default property alias contents: body.data
    implicitWidth: 240
    implicitHeight: (headerRow.visible ? headerRow.implicitHeight + 17 : 0) + body.implicitHeight + 24
    clip: true

    property bool hot: false          // set by callers for the "active" panel; hover also lights it
    readonly property bool lit: hot || panelHover.hovered
    HoverHandler { id: panelHover }

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
            Text {
                id: heading
                visible: text.length
                color: Theme.accent
                font.pixelSize: 11
                font.letterSpacing: 1.6
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.minimumWidth: 0
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
        anchors.fill: parent
        z: 5
    }
}
