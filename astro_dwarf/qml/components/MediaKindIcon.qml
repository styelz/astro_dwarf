pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import ".."

// Large Explorer-style placeholder for album folders and files with no thumbnail.
Item {
    id: icon
    property var item: ({})
    readonly property bool isFolder: Util.isFolderMedia(item)
    implicitWidth: 72
    implicitHeight: 72
    Accessible.ignored: true

    readonly property color folderFront: Theme.bake(0.12, 0.74, 0.58, 1, 0.45, Theme.brightness)
    readonly property color folderTab: Theme.bake(0.11, 0.68, 0.46, 1, 0.45, Theme.brightness)
    readonly property color folderEdge: Theme.bake(0.10, 0.52, 0.34, 1, 0.40, Theme.brightness)
    readonly property color folderPaper: Theme.hsl(0.02, 0.18, 0.78)
    readonly property color fileFill: Theme.surfaceHigh
    readonly property color fileEdge: Theme.outline
    readonly property color fileFold: Theme.inputBg
    readonly property color fileRule: Theme.outlineSoft

    Item {
        visible: icon.isFolder
        anchors.centerIn: parent
        width: parent.width * 0.90
        height: parent.height * 0.76

        Rectangle {
            width: parent.width * 0.40
            height: parent.height * 0.28
            radius: Math.max(2, parent.width * 0.07)
            color: icon.folderTab
        }
        Rectangle {
            y: parent.height * 0.16
            width: parent.width
            height: parent.height * 0.84
            radius: Math.max(3, parent.width * 0.09)
            color: icon.folderFront
            border.width: 1
            border.color: icon.folderEdge
        }
        Rectangle {
            x: parent.width * 0.08
            y: parent.height * 0.28
            width: parent.width * 0.84
            height: Math.max(3, parent.height * 0.10)
            radius: 1
            color: icon.folderPaper
            opacity: 0.42
        }
    }

    Item {
        id: fileMark
        visible: !icon.isFolder
        anchors.centerIn: parent
        width: parent.width * 0.58
        height: parent.height * 0.78

        Rectangle {
            anchors.fill: parent
            radius: Math.max(2, fileMark.width * 0.08)
            color: icon.fileFill
            border.width: 1
            border.color: icon.fileEdge
        }
        Rectangle {
            anchors.right: parent.right
            anchors.top: parent.top
            width: fileMark.width * 0.34
            height: width
            color: Theme.surface
        }
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            antialiasing: true
            ShapePath {
                fillColor: icon.fileFold
                strokeColor: icon.fileEdge
                strokeWidth: 1
                startX: fileMark.width * 0.66
                startY: 0
                PathLine { x: fileMark.width; y: fileMark.height * 0.26 }
                PathLine { x: fileMark.width * 0.66; y: fileMark.height * 0.26 }
                PathLine { x: fileMark.width * 0.66; y: 0 }
            }
        }
        Repeater {
            model: 3
            Rectangle {
                required property int index
                x: fileMark.width * 0.16
                y: fileMark.height * (0.42 + index * 0.14)
                width: fileMark.width * 0.56
                height: Math.max(1, fileMark.height * 0.045)
                radius: 1
                color: icon.fileRule
            }
        }
    }
}
