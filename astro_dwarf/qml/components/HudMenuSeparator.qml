import QtQuick
import QtQuick.Templates as T
import ".."

T.MenuSeparator {
    implicitHeight: 9
    contentItem: Rectangle {
        implicitHeight: 1
        color: Theme.outline
    }
    leftPadding: 8
    rightPadding: 8
    topPadding: 4
    bottomPadding: 4
}
