pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

// Live HUD fragment so palette edits can be judged against buttons, type,
// inputs and the fixed semantic colours without leaving Settings.
// Click a sample to select that colour; the current role is ringed.
Rectangle {
    id: preview
    property string highlightRole: ""
    signal rolePicked(string key)

    implicitHeight: 86
    color: Theme.windowBase
    border.color: preview.lit("windowBase") ? Theme.accentSoft : Theme.outline
    border.width: 2
    radius: Theme.radius
    clip: true
    Layout.minimumWidth: 0
    Accessible.role: Accessible.StaticText
    Accessible.name: "Theme preview"
    Accessible.description: preview.highlightRole
        ? "Live sample. Editing " + Theme.roleName(preview.highlightRole) + ". " + Theme.roleHint(preview.highlightRole)
        : "Live sample of window, panel, type, accent, input and status colours. Click a piece to edit it."

    function lit(role) {
        return preview.highlightRole === role
    }

    function pick(role) {
        if (role)
            preview.rolePicked(role)
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 6

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: Theme.panelFill
            border.color: preview.lit("panelFill") || preview.lit("outline") ? Theme.accentSoft : Theme.outline
            border.width: 2
            radius: Theme.radius

            TapHandler {
                onTapped: preview.pick(preview.lit("outline") ? "outline" : "panelFill")
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 6
                spacing: 6

                Text {
                    text: "PREVIEW"
                    color: Theme.accent
                    font.pixelSize: Theme.fontXs
                    font.bold: true
                    font.letterSpacing: Theme.tracking2
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: preview.pick("accent") }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -2
                        z: -1
                        color: "transparent"
                        border.color: preview.lit("accent") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: 2
                    }
                }
                Item {
                    implicitWidth: actionBtn.implicitWidth
                    implicitHeight: actionBtn.implicitHeight
                    HudButton {
                        id: actionBtn
                        text: "ACTION"
                        implicitHeight: Theme.compactControlHeight
                        Accessible.name: "Preview default button"
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -1
                        color: "transparent"
                        border.color: preview.lit("surfaceHigh") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: 2
                    }
                    TapHandler { onTapped: preview.pick("surfaceHigh") }
                }
                Item {
                    implicitWidth: liveBtn.implicitWidth
                    implicitHeight: liveBtn.implicitHeight
                    Rectangle {
                        anchors.fill: liveBtn
                        anchors.margins: -3
                        radius: 3
                        color: Theme.glowAccent
                        visible: preview.lit("glowAccent") || preview.highlightRole === ""
                        opacity: preview.lit("glowAccent") ? 1 : 0.35
                    }
                    HudButton {
                        id: liveBtn
                        text: "LIVE"
                        implicitHeight: Theme.compactControlHeight
                        buttonColor: Theme.fillActive
                        foregroundColor: Theme.accent
                        Accessible.name: "Preview live button"
                    }
                    Rectangle {
                        anchors.fill: liveBtn
                        anchors.margins: -1
                        color: "transparent"
                        border.color: preview.lit("fillActive") || preview.lit("glowAccent") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: 2
                    }
                    TapHandler {
                        onTapped: preview.pick(preview.lit("glowAccent") ? "glowAccent" : "fillActive")
                    }
                }
                Item {
                    implicitWidth: chipSample.implicitWidth
                    implicitHeight: chipSample.implicitHeight
                    HudChip {
                        id: chipSample
                        label: "CHIP"
                        tone: Theme.accent
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -1
                        color: "transparent"
                        border.color: preview.lit("accent") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: 2
                    }
                    TapHandler { onTapped: preview.pick("accent") }
                }
                Rectangle {
                    Layout.preferredWidth: 72
                    Layout.preferredHeight: Theme.compactControlHeight
                    color: Theme.inputBg
                    border.color: preview.lit("inputBg") || preview.lit("outline") || preview.lit("textPrimary") ? Theme.accentSoft : Theme.outline
                    border.width: 2
                    radius: 2
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: preview.pick(preview.lit("textPrimary") ? "textPrimary" : (preview.lit("outline") ? "outline" : "inputBg"))
                    }
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        text: "FIELD"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSm
                        font.family: Theme.fontMono
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
                Text {
                    text: "DIM"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSm
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: preview.pick("textSecondary") }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: -2
                        z: -1
                        color: "transparent"
                        border.color: preview.lit("textSecondary") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: 2
                    }
                }
                Item { Layout.fillWidth: true }
                HudChip { label: "OK"; tone: Theme.success }
                HudChip { label: "WARN"; tone: Theme.warning }
                HudChip { label: "ERR"; tone: Theme.danger }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            PreviewChip {
                label: "WINDOW"
                fill: Theme.windowBase
                line: Theme.outline
                roleKey: "windowBase"
            }
            PreviewChip {
                label: "CARD"
                fill: Theme.surface
                line: Theme.outline
                roleKey: "surface"
            }
            PreviewChip {
                label: "MENU"
                fill: Theme.popupBg
                line: Theme.outline
                roleKey: "popupBg"
            }
            PreviewChip {
                label: "DIMMER"
                fill: Theme.scrim
                line: Theme.outlineSoft
                roleKey: "scrim"
                ink: Theme.muted
            }
            PreviewChip {
                label: "OFF"
                fill: Theme.disabledBg
                line: Theme.disabledOutline
                roleKey: "disabledBg"
                alsoRole: "disabledOutline"
                ink: Theme.disabledOutline
            }
            PreviewChip {
                label: "CHECKED"
                fill: Theme.fillChecked
                line: Theme.accent
                roleKey: "fillChecked"
                ink: Theme.accent
            }
            PreviewChip {
                label: "SOFT"
                fill: Theme.inputBg
                line: Theme.outlineSoft
                roleKey: "outlineSoft"
            }
            PreviewChip {
                label: "HARD"
                fill: Theme.surfaceHigh
                line: Theme.outlineStrong
                roleKey: "outlineStrong"
            }
            PreviewChip {
                label: "HI"
                fill: Theme.surface
                line: Theme.accentSoft
                roleKey: "accentSoft"
                ink: Theme.accentSoft
            }
            Text {
                text: "HINT"
                color: Theme.muted
                font.pixelSize: Theme.fontXs
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: preview.pick("muted") }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -2
                    z: -1
                    color: "transparent"
                    border.color: preview.lit("muted") ? Theme.accentSoft : "transparent"
                    border.width: 2
                    radius: 2
                }
            }
            Item { Layout.fillWidth: true }
        }
    }

    component PreviewChip: Rectangle {
        id: chip
        property string label: ""
        property color fill: Theme.surface
        property color line: Theme.outline
        property color ink: Theme.textSecondary
        property string roleKey: ""
        property string alsoRole: ""

        Layout.preferredWidth: 56
        Layout.preferredHeight: 22
        color: chip.fill
        border.color: preview.lit(chip.roleKey) || (chip.alsoRole && preview.lit(chip.alsoRole)) ? Theme.accentSoft : chip.line
        border.width: 2
        radius: 2
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: preview.pick(chip.roleKey) }
        Text {
            anchors.centerIn: parent
            text: chip.label
            color: chip.ink
            font.pixelSize: Theme.fontXs
            font.bold: true
            font.letterSpacing: 0.5
        }
    }
}
