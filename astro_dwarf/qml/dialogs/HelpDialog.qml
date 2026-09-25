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
    width: Math.min(Theme.px(620), root.width - Theme.px(48))
    height: Math.min(root.height - Theme.px(80), Math.max(Theme.px(240), helpColumn.implicitHeight + padding * 2 + Theme.px(92)))
    padding: Theme.s4
    onOpened: helpClose.forceActiveFocus()
    background: DialogFrame {}

    property int activeTab: 0
    readonly property int labelWidth: Theme.px(168)
    readonly property var tabs: [
        { key: "quick", label: "QUICK HELP" },
        { key: "guide", label: "GUIDE" }
    ]
    readonly property var activeSections: helpDialog.activeTab === 1 ? helpDialog.guideSections : helpDialog.sections
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
    readonly property var guideSections: [
        {
            title: "THE BASICS",
            rows: [
                { gesture: "STACK", detail: "Repeated exposures of one target that the telescope combines into one deeper image." },
                { gesture: "MOSAIC", detail: "Two or more overlapping stacks stitched into a wider view than a single frame." }
            ]
        },
        {
            title: "PLAN A STACK",
            rows: [
                { gesture: "STEP 1", detail: "On SKY, search or click a catalog object, or right-click and choose Enter RA / Dec." },
                { gesture: "STEP 2", detail: "Choose Tele or Wide and set exposure, gain, and frame count — the frames you want stacked." },
                { gesture: "STEP 3", detail: "Leave Calibrate, Auto focus, and GOTO on for an unattended run. Add Polar / EQ if the mount needs it." },
                { gesture: "STEP 4", detail: "Press CREATE SINGLE SESSION on SKY, or + MANUAL SESSION on SESSIONS." }
            ]
        },
        {
            title: "PLAN A MOSAIC",
            rows: [
                { gesture: "STEP 1", detail: "On SKY, pick CUSTOM (host-planned columns, rows, and overlap — each pane is its own GOTO and stack) or DEVICE (the telescope frames up to 2×2 panes itself)." },
                { gesture: "STEP 2", detail: "Size the grid. CUSTOM: set COL, ROW, and OVL. DEVICE: set H and V from 1.0× to 1.8×." },
                { gesture: "STEP 3", detail: "Optional: set PA to rotate an equatorial camera. Alt-az mounts follow the zenith automatically." },
                { gesture: "STEP 4", detail: "Pick the centre target the same way as a single session." },
                { gesture: "STEP 5", detail: "Press CREATE MOSAIC SESSION (custom, one session per pane) or CREATE DEVICE MOSAIC (one session, the telescope frames the grid)." }
            ]
        },
        {
            title: "RUN IT",
            rows: [
                { gesture: "LATER", detail: "New sessions appear on SESSIONS and CALENDAR. Turn on the title-bar SCHEDULER switch and they start themselves." },
                { gesture: "NOW", detail: "Track or GOTO the target, then press STACK on CONTROL. It reads MOSAIC STACK when a grid is armed." },
                { gesture: "PROGRESS", detail: "CONTROL shows live stacked-frame counts and mosaic pane progress. STOP SESSION ends it early." }
            ]
        },
        {
            title: "GOOD TO KNOW",
            rows: [
                { gesture: "IMPORTED PLANS", detail: "A Stellarium or Telescopius pane list also creates one session per pane. Edit them with THIS PANE / ALL PANES in the session editor." },
                { gesture: "EDITING", detail: "Double-click a session to reopen this same editor and adjust camera, workflow, or mosaic settings." },
                { gesture: "TEMPLATES", detail: "Tick Save template on a session to reuse its target and settings later without retyping them." }
            ]
        }
    ]

    contentItem: ColumnLayout {
        spacing: Theme.s3
        Accessible.name: helpDialog.activeTab === 1 ? "Guide" : "Quick help"
        Accessible.description: helpDialog.activeTab === 1
                                 ? "Step-by-step guide to creating stacks and mosaics"
                                 : "Clicks and drags that are easy to miss"

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s3
            Repeater {
                model: helpDialog.tabs
                delegate: HudButton {
                    required property var modelData
                    required property int index
                    objectName: "helpTab-" + modelData.key
                    text: modelData.label
                    busyMs: 0
                    buttonColor: helpDialog.activeTab === index ? Theme.fillActive : Theme.surfaceHigh
                    foregroundColor: helpDialog.activeTab === index ? Theme.accent : Theme.textSecondary
                    accessibleDescription: "Show the " + modelData.label.toLowerCase() + " tab"
                    onClicked: helpDialog.activeTab = index
                }
            }
            Item { Layout.fillWidth: true }
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
                    model: helpDialog.activeSections
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
