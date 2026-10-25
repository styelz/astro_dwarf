import QtQuick
import ".."

// Shown on the live view when sidereal tracking still holds the stacking JPEG.
// Entering PHOTO would restart the picture stream and drop that track.
Column {
    id: notice
    spacing: Theme.px(10)
    width: Math.min((parent ? parent.width : Theme.px(568)) - Theme.px(48), 520)
    visible: notice.blocked
    property bool blocked: false
    property string message: ""

    Accessible.role: Accessible.StaticText
    Accessible.name: notice.message

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "LIVE VIEW"
        color: Theme.warning
        font.pixelSize: Theme.fontLg
        font.letterSpacing: 3
        font.bold: true
    }
    Text {
        objectName: "previewTrackingMessage"
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        text: notice.message
        color: Theme.textPrimary
        font.pixelSize: Theme.fontBase
    }
    Text {
        objectName: "previewTrackingHint"
        anchors.horizontalCenter: parent.horizontalCenter
        width: parent.width
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        text: "Use TRACK to stop sidereal tracking."
        color: Theme.textSecondary
        font.pixelSize: Theme.fontPx(11)
    }
}
