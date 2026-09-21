import QtQuick
import QtQuick.Templates as T
import ".."

T.MenuSeparator {
    implicitHeight: Theme.px(9)
    contentItem: Rectangle {
        implicitHeight: Theme.px(1)
        color: Theme.outline
    }
    leftPadding: Theme.s2
    rightPadding: Theme.s2
    topPadding: Theme.s1
    bottomPadding: Theme.s1
}
