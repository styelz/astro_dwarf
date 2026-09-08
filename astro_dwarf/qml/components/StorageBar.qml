import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

Item {
    id: storage
    property real fraction: 0      // used fraction 0..1
    property string text: "—"
    property string tone: "unknown"
    property bool valid: true
    readonly property color toneColor: !valid ? Theme.danger : tone === "unknown" ? Theme.muted : (tone === "good" ? Theme.accent : Util.toneColor(tone))
    property real shown: fraction
    Behavior on shown { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
    implicitHeight: 10
    Rectangle {
        anchors.fill: parent
        radius: 2
        color: Theme.inputBg
        border.color: storage.valid ? Theme.outline : Theme.danger
        Rectangle {
            x: 1; y: 1
            height: parent.height - 2
            width: Math.max(0, (parent.width - 2) * Math.min(1, storage.shown))
            radius: 1
            color: storage.toneColor
            opacity: storage.valid ? 0.9 : 0
        }
        Row {
            anchors.fill: parent
            anchors.margins: 1
            spacing: 0
            Repeater {
                model: 8
                Item {
                    width: parent.width / 8; height: parent.height
                    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.windowBase; opacity: 0.8; visible: index < 7 }
                }
            }
        }
    }
}
