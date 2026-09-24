import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Dialog {
    id: helpDialog
    objectName: "helpDialog"
    modal: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(Theme.px(560), root.width - Theme.px(48))
    height: Math.min(root.height - Theme.px(80), Math.max(Theme.px(240), helpColumn.implicitHeight + padding * 2 + Theme.px(56)))
    padding: Theme.s4
    onOpened: helpClose.forceActiveFocus()
    background: DialogFrame {}

    readonly property int labelWidth: Theme.px(168)
    readonly property var sections: [
        {
            title: "LIVE VIEW",
            rows: [
                { gesture: "DOUBLE-CLICK WIDE", detail: "Centers the telephoto on that spot." },
                { gesture: "DOUBLE-CLICK TELE", detail: "Full screen. F does the same. Esc leaves." },
                { gesture: "HOVER", detail: "Preview buttons show, then hide when the pointer leaves." },
                { gesture: "DRAG PIP", detail: "Moves the small view. Hover it to swap cameras or hide it." },
                { gesture: "RIGHT-CLICK", detail: "Start or stop preview, swap views, full screen, or copy the stream." }
            ]
        },
        {
            title: "SKY",
            rows: [
                { gesture: "RIGHT-CLICK", detail: "Go to coordinates, show the live view, or track the target." },
                { gesture: "DOUBLE-CLICK", detail: "Centers the map. The menu can also slew and start tracking." },
                { gesture: "CTRL + SCROLL", detail: "Changes how bright the live view is on the map." }
            ]
        },
        {
            title: "EVERYWHERE ELSE",
            rows: [
                { gesture: "DOUBLE-CLICK", detail: "Opens that session in the editor." },
                { gesture: "RIGHT-CLICK", detail: "Menu for a session, device, photo, history row, or the log." },
                { gesture: "DRAG SESSION", detail: "Moves it to another night or a new start time." },
                { gesture: "EMPTY DAY", detail: "Right-click to add a session." },
                { gesture: "DRAG PANEL", detail: "Rearranges Control. Right-click a panel to reset the layout." },
                { gesture: "SCHEDULER", detail: "Title-bar switch. On, planned sessions run by themselves." }
            ]
        }
    ]

    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: "Quick help"
        Accessible.description: "Clicks and drags that are easy to miss"

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s3
            Text {
                text: "QUICK HELP"
                color: Theme.accent
                font.pixelSize: Theme.fontLg
                font.letterSpacing: Theme.tracking2
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            HudButton {
                id: helpClose
                objectName: "helpClose"
                text: "CLOSE"
                busyMs: 0
                onClicked: helpDialog.close()
            }
        }

        Flickable {
            id: scroller
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            contentWidth: width
            contentHeight: helpColumn.implicitHeight
            interactive: contentHeight > height + Theme.px(1)
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            ColumnLayout {
                id: helpColumn
                width: scroller.width - Theme.s3
                spacing: Theme.s4
                Repeater {
                    model: helpDialog.sections
                    delegate: ColumnLayout {
                        id: sectionBlock
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Theme.s2
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.s2
                            Text {
                                text: sectionBlock.modelData.title
                                color: Theme.accent
                                font.pixelSize: Theme.fontSm
                                font.bold: true
                                font.letterSpacing: Theme.tracking2
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: Theme.px(1)
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.35) }
                                    GradientStop { position: 1.0; color: Theme.hsl(0.039, 0.535, 0.253, 0.15) }
                                }
                            }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.s2
                            Repeater {
                                model: sectionBlock.modelData.rows
                                delegate: RowLayout {
                                    id: helpRow
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: Theme.s3
                                    Text {
                                        text: helpRow.modelData.gesture
                                        color: Theme.textSecondary
                                        font.pixelSize: Theme.fontSm
                                        font.bold: true
                                        font.letterSpacing: Theme.tracking1
                                        wrapMode: Text.Wrap
                                        Layout.preferredWidth: helpDialog.labelWidth
                                        Layout.maximumWidth: helpDialog.labelWidth
                                        Layout.alignment: Qt.AlignLeft | Qt.AlignTop
                                        topPadding: Theme.px(1)
                                    }
                                    Text {
                                        text: helpRow.modelData.detail
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fontMd
                                        wrapMode: Text.Wrap
                                        Layout.fillWidth: true
                                        Layout.alignment: Qt.AlignLeft | Qt.AlignTop
                                    }
                                }
                            }
                        }
                    }
                }
            }
            ScrollHint { flick: scroller }
        }
    }
}
