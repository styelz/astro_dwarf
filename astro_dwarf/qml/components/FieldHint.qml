import QtQuick
import QtQuick.Layouts
import ".."

// One-line-or-two explanation that sits beside or under a field: what the
// control does and what the device or scheduler does with the value.
Text {
    property bool emphasis: false
    color: emphasis ? Theme.warning : Theme.textSecondary
    font.pixelSize: Theme.fontSm
    lineHeight: 1.15
    wrapMode: Text.Wrap
    Layout.fillWidth: true
    Layout.minimumWidth: 120
    Layout.maximumWidth: 620
    Layout.alignment: Qt.AlignVCenter
}
