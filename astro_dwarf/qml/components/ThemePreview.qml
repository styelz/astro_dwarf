pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

// Live HUD fragment so palette edits can be judged against buttons, type,
// inputs and the fixed semantic colours without leaving Settings.
// Click a sample to select that colour; the current role is ringed.
Rectangle {
    id: preview
    objectName: "themePreview"
    property string highlightRole: ""
    signal rolePicked(string key)

    implicitHeight: Theme.px(86)
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
        anchors.margins: Theme.px(6)
        spacing: Theme.px(6)

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.px(36)
            color: Theme.panelFill
            border.color: preview.lit("panelFill") || preview.lit("outline") ? Theme.accentSoft : Theme.outline
            border.width: 2
            radius: Theme.radius

            TapHandler {
                onTapped: preview.pick(preview.lit("outline") ? "outline" : "panelFill")
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.px(6)
                anchors.rightMargin: Theme.px(6)
                spacing: Theme.px(6)

                Text {
                    text: "PREVIEW"
                    color: Theme.accent
                    font.pixelSize: Theme.fontXs
                    font.bold: true
                    font.letterSpacing: Theme.tracking2
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onTapped: preview.pick("accent")
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: Theme.px(-2)
                        z: -1
                        color: "transparent"
                        border.color: preview.lit("accent") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: Theme.px(2)
                    }
                }
                Item {
                    implicitWidth: actionBtn.implicitWidth
                    implicitHeight: actionBtn.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    HudButton {
                        id: actionBtn
                        objectName: "previewAction"
                        text: "ACTION"
                        implicitHeight: Theme.compactControlHeight
                        focusPolicy: Qt.NoFocus
                        Accessible.name: "Preview default button"
                        onClicked: preview.pick("surfaceHigh")
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: Theme.px(-1)
                        color: "transparent"
                        border.color: preview.lit("surfaceHigh") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: Theme.px(2)
                    }
                }
                Item {
                    implicitWidth: liveBtn.implicitWidth
                    implicitHeight: liveBtn.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    Rectangle {
                        anchors.fill: liveBtn
                        anchors.margins: Theme.px(-3)
                        radius: Theme.px(3)
                        color: Theme.glowAccent
                        visible: preview.lit("glowAccent") || preview.highlightRole === ""
                        opacity: preview.lit("glowAccent") ? 1 : 0.35
                    }
                    HudButton {
                        id: liveBtn
                        objectName: "previewLive"
                        text: "LIVE"
                        implicitHeight: Theme.compactControlHeight
                        focusPolicy: Qt.NoFocus
                        buttonColor: Theme.fillActive
                        foregroundColor: Theme.accent
                        Accessible.name: "Preview live button"
                        onClicked: preview.pick(preview.lit("glowAccent") ? "glowAccent" : "fillActive")
                    }
                    Rectangle {
                        anchors.fill: liveBtn
                        anchors.margins: Theme.px(-1)
                        color: "transparent"
                        border.color: preview.lit("fillActive") || preview.lit("glowAccent") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: Theme.px(2)
                    }
                }
                PreviewHit {
                    objectName: "previewChip"
                    roleKey: "accent"
                    implicitWidth: chipSample.implicitWidth
                    implicitHeight: chipSample.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    HudChip {
                        id: chipSample
                        label: "CHIP"
                        tone: Theme.accent
                    }
                }
                Rectangle {
                    id: fieldSample
                    objectName: "previewField"
                    signal clicked()
                    Layout.preferredWidth: Theme.px(72)
                    Layout.preferredHeight: Theme.compactControlHeight
                    Layout.alignment: Qt.AlignVCenter
                    color: Theme.inputBg
                    border.color: preview.lit("inputBg") || preview.lit("outline") || preview.lit("textPrimary") ? Theme.accentSoft : Theme.outline
                    border.width: 2
                    radius: Theme.px(2)
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    onClicked: preview.pick(preview.lit("textPrimary") ? "textPrimary" : (preview.lit("outline") ? "outline" : "inputBg"))
                    TapHandler {
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onTapped: fieldSample.clicked()
                    }
                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.px(6)
                        anchors.rightMargin: Theme.px(6)
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
                    TapHandler {
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        onTapped: preview.pick("textSecondary")
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: Theme.px(-2)
                        z: -1
                        color: "transparent"
                        border.color: preview.lit("textSecondary") ? Theme.accentSoft : "transparent"
                        border.width: 2
                        radius: Theme.px(2)
                    }
                }
                Item { Layout.fillWidth: true }
                PreviewHit {
                    objectName: "previewOk"
                    roleKey: "success"
                    implicitWidth: okChip.implicitWidth
                    implicitHeight: okChip.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    HudChip { id: okChip; label: "OK"; tone: Theme.success }
                }
                PreviewHit {
                    objectName: "previewWarn"
                    roleKey: "warning"
                    implicitWidth: warnChip.implicitWidth
                    implicitHeight: warnChip.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    HudChip { id: warnChip; label: "WARN"; tone: Theme.warning }
                }
                PreviewHit {
                    objectName: "previewErr"
                    roleKey: "danger"
                    implicitWidth: errChip.implicitWidth
                    implicitHeight: errChip.implicitHeight
                    Layout.preferredWidth: implicitWidth
                    Layout.preferredHeight: implicitHeight
                    Layout.alignment: Qt.AlignVCenter
                    HudChip { id: errChip; label: "ERR"; tone: Theme.danger }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.px(6)

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
            PreviewChip {
                objectName: "previewFov"
                label: "FOV"
                fill: Theme.surface
                line: Theme.fov
                roleKey: "fov"
                ink: Theme.fov
            }
            Text {
                text: "HINT"
                color: Theme.muted
                font.pixelSize: Theme.fontXs
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler {
                    gesturePolicy: TapHandler.ReleaseWithinBounds
                    onTapped: preview.pick("muted")
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: Theme.px(-2)
                    z: -1
                    color: "transparent"
                    border.color: preview.lit("muted") ? Theme.accentSoft : "transparent"
                    border.width: 2
                    radius: Theme.px(2)
                }
            }
            Item { Layout.fillWidth: true }
        }
    }

    component PreviewHit: Item {
        id: hit
        property string roleKey: ""
        property string alsoRole: ""
        signal clicked()

        Accessible.role: Accessible.Button
        Accessible.name: hit.roleKey ? Theme.roleName(hit.roleKey) + " preview" : "Theme preview sample"
        onClicked: preview.pick(hit.alsoRole && preview.lit(hit.roleKey) ? hit.alsoRole : hit.roleKey)
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler {
            gesturePolicy: TapHandler.ReleaseWithinBounds
            onTapped: hit.clicked()
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.px(-1)
            color: "transparent"
            border.color: preview.lit(hit.roleKey) || (hit.alsoRole && preview.lit(hit.alsoRole)) ? Theme.accentSoft : "transparent"
            border.width: 2
            radius: Theme.px(2)
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
        signal clicked()

        Layout.preferredWidth: Theme.px(56)
        Layout.preferredHeight: Theme.px(22)
        color: chip.fill
        border.color: preview.lit(chip.roleKey) || (chip.alsoRole && preview.lit(chip.alsoRole)) ? Theme.accentSoft : chip.line
        border.width: 2
        radius: Theme.px(2)
        onClicked: preview.pick(chip.roleKey)
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler {
            gesturePolicy: TapHandler.ReleaseWithinBounds
            onTapped: chip.clicked()
        }
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
