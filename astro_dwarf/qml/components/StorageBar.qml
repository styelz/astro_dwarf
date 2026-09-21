import QtQuick
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
    implicitHeight: Theme.px(10)
    Rectangle {
        anchors.fill: parent
        radius: Theme.px(2)
        color: Theme.inputBg
        border.color: storage.valid ? Theme.outline : Theme.danger
        Rectangle {
            x: Theme.px(1); y: Theme.px(1)
            height: parent.height - Theme.px(2)
            width: Math.max(0, (parent.width - Theme.px(2)) * Math.min(1, storage.shown))
            radius: Theme.px(1)
            color: storage.toneColor
            opacity: storage.valid ? 0.9 : 0
        }
        Row {
            anchors.fill: parent
            anchors.margins: Theme.px(1)
            spacing: 0
            Repeater {
                model: 8
                Item {
                    width: parent.width / 8; height: parent.height
                    Rectangle { anchors.right: parent.right; width: Theme.px(1); height: parent.height; color: Theme.windowBase; opacity: 0.8; visible: index < 7 }
                }
            }
        }
    }
}
