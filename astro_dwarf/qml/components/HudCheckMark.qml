import QtQuick
import QtQuick.Shapes
import ".."

// Stroked tick that scales in from the corner. Shared by HudCheck and SelectBox.
Item {
    id: mark
    property bool on: false
    property color color: Theme.accent
    property real strokeWidth: 2
    opacity: on ? 1 : 0
    scale: on ? 1 : 0.4
    transformOrigin: Item.BottomLeft
    Behavior on opacity { NumberAnimation { duration: Theme.quick } }
    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        antialiasing: true
        ShapePath {
            strokeColor: mark.color
            strokeWidth: mark.strokeWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            startX: mark.width * 0.14
            startY: mark.height * 0.52
            PathLine { x: mark.width * 0.42; y: mark.height * 0.80 }
            PathLine { x: mark.width * 0.88; y: mark.height * 0.22 }
        }
    }
}
