import QtQuick
import QtQuick.Shapes
import ".."

// Cut-corner frame used by buttons, checks and chips so every control shares the
// panel's notched silhouette. Each corner notch can be sized independently (0 = square).
Shape {
    id: frame
    property real topLeft: Theme.notchSmall
    property real topRight: 0
    property real bottomRight: Theme.notchSmall
    property real bottomLeft: 0
    property color fillColor: "transparent"
    property color strokeColor: Theme.outline
    property real strokeWidth: 1
    readonly property real o: strokeWidth / 2
    preferredRendererType: Shape.CurveRenderer
    antialiasing: true

    ShapePath {
        fillColor: frame.fillColor
        strokeColor: frame.strokeColor
        strokeWidth: frame.strokeWidth
        capStyle: ShapePath.FlatCap
        joinStyle: ShapePath.MiterJoin
        startX: frame.topLeft + frame.o
        startY: frame.o
        PathLine { x: frame.width - frame.topRight - frame.o; y: frame.o }
        PathLine { x: frame.width - frame.o; y: frame.topRight + frame.o }
        PathLine { x: frame.width - frame.o; y: frame.height - frame.bottomRight - frame.o }
        PathLine { x: frame.width - frame.bottomRight - frame.o; y: frame.height - frame.o }
        PathLine { x: frame.bottomLeft + frame.o; y: frame.height - frame.o }
        PathLine { x: frame.o; y: frame.height - frame.bottomLeft - frame.o }
        PathLine { x: frame.o; y: frame.topLeft + frame.o }
        PathLine { x: frame.topLeft + frame.o; y: frame.o }
    }
}
