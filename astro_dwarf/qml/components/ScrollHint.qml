pragma ComponentBehavior: Bound
import QtQuick
import ".."

// Scroll affordance. Declare this INSIDE a Flickable (or ListView / GridView)
// and point `flick` at it. It pins itself to the viewport and fades a faded,
// gently bobbing chevron in at the top or bottom edge whenever there is more
// content hidden in that direction. Purely decorative: it never eats input, so
// flicking and wheel scrolling pass straight through.
Item {
    id: root
    required property Flickable flick
    // Only reveal the arrows while this is true (e.g. panel hover).
    property bool active: true

    // Follow the viewport even though we live in the flickable's content item.
    x: flick ? flick.contentX : 0
    y: flick ? flick.contentY : 0
    width: flick ? flick.width : 0
    height: flick ? flick.height : 0
    z: 50

    readonly property bool scrollable: flick && flick.contentHeight > flick.height + 1
    readonly property real hiddenAbove: flick ? flick.contentY - flick.originY : 0
    readonly property real hiddenBelow: flick ? (flick.originY + flick.contentHeight) - (flick.contentY + flick.height) : 0

    component Chevron: Item {
        id: hint
        property bool pointsDown: true
        property bool shown: false
        readonly property color tint: Theme.warning   // stands out against the cyan HUD
        width: parent.width
        height: 26
        visible: opacity > 0.01
        opacity: shown ? 0.6 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: hint.pointsDown ? "transparent" : Qt.rgba(hint.tint.r, hint.tint.g, hint.tint.b, 0.10) }
                GradientStop { position: 1.0; color: hint.pointsDown ? Qt.rgba(hint.tint.r, hint.tint.g, hint.tint.b, 0.10) : "transparent" }
            }
        }
        // triple chevron; the leading arrow (nearest the edge) is brightest
        Column {
            anchors.horizontalCenter: parent.horizontalCenter
            y: hint.pointsDown ? parent.height - height - hint.bob : hint.bob
            spacing: -4
            Repeater {
                model: 3
                Text {
                    required property int index
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: hint.pointsDown ? "\uE70D" : "\uE70E"   // Segoe MDL2 ChevronDown / ChevronUp
                    font.family: Theme.fontIcon
                    font.pixelSize: 9
                    color: hint.tint
                    opacity: 0.35 + 0.3 * (hint.pointsDown ? index : 2 - index)
                }
            }
        }
        // gentle bob to read as "there is more this way"
        property real bob: 2
        SequentialAnimation on bob {
            running: hint.visible
            loops: Animation.Infinite
            NumberAnimation { from: 3; to: 1; duration: 820; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 3; duration: 820; easing.type: Easing.InOutSine }
        }
    }

    Chevron {
        anchors.top: parent.top
        pointsDown: false
        shown: root.active && root.scrollable && root.hiddenAbove > 1
    }
    Chevron {
        anchors.bottom: parent.bottom
        pointsDown: true
        shown: root.active && root.scrollable && root.hiddenBelow > 1
    }
}
