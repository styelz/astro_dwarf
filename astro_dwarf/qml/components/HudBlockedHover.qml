import QtQuick

// Sits beside a disabled control, not inside it. A disabled item never
// receives hover, so the forbidden cursor has to live on an enabled sibling.
MouseArea {
    id: block
    property Item control: null
    property string reason: "Unavailable"
    anchors.fill: parent
    z: 40
    enabled: control !== null && !control.enabled
    visible: enabled
    hoverEnabled: true
    cursorShape: Qt.ForbiddenCursor
    preventStealing: true
    acceptedButtons: Qt.AllButtons
    onPressed: function(mouse) { mouse.accepted = true }
    onWheel: function(wheel) { wheel.accepted = true }

    HudToolTip {
        visible: block.containsMouse && block.reason !== ""
        text: block.reason
    }
}
