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
        width: parent.width
        height: 30
        visible: opacity > 0.01
        opacity: shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: hint.pointsDown ? "transparent" : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18) }
                GradientStop { position: 1.0; color: hint.pointsDown ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.18) : "transparent" }
            }
        }
        Text {
            id: glyph
            anchors.horizontalCenter: parent.horizontalCenter
            y: hint.pointsDown ? parent.height - height - hint.bob : hint.bob
            text: hint.pointsDown ? "\uE70D" : "\uE70E"   // Segoe MDL2 ChevronDown / ChevronUp
            font.family: Theme.fontIcon
            font.pixelSize: 13
            color: Theme.accent
            opacity: 0.85
        }
        // gentle bob to read as "there is more this way"
        property real bob: 3
        SequentialAnimation on bob {
            running: hint.visible
            loops: Animation.Infinite
            NumberAnimation { from: 5; to: 1; duration: 720; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 5; duration: 720; easing.type: Easing.InOutSine }
        }
    }

    Chevron {
        anchors.top: parent.top
        pointsDown: false
        shown: root.scrollable && root.hiddenAbove > 1
    }
    Chevron {
        anchors.bottom: parent.bottom
        pointsDown: true
        shown: root.scrollable && root.hiddenBelow > 1
    }
}
