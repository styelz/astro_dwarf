pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import ".."
import "../components"

// Compact HUD colour modal. The MDL2 pipette samples a screen pixel; while
// it is live the veil lifts so the rest of the console stays visible.
Dialog {
    id: pick
    objectName: "colourPick"
    property string roleName: "COLOUR"
    property color selectedColor: Theme.accent
    property color _original: Theme.accent
    property color _dropSaved: Theme.accent
    property var screenPicker: null
    property real hue: Theme.defaultHue
    property real sat: 0.8
    property real val: 0.8
    readonly property color currentColor: Qt.hsva(Theme.wrapHue(pick.hue), pick.sat, pick.val, 1)
    readonly property string currentHex: Theme.colorToHex(pick.currentColor)
    readonly property bool dropping: !!(pick.screenPicker && pick.screenPicker.picking)

    modal: !pick.dropping
    dim: !pick.dropping
    popupType: Popup.Item
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    closePolicy: pick.dropping ? Popup.NoAutoClose : Popup.CloseOnEscape
    header: null
    footer: null
    padding: Theme.s3
    width: 292
    height: body.implicitHeight + padding * 2
    background: DialogFrame {}
    Overlay.modal: Rectangle {
        color: Qt.rgba(Theme.windowBase.r, Theme.windowBase.g, Theme.windowBase.b, 0.32)
    }
    opacity: pick.dropping ? 0 : 1
    enabled: !pick.dropping

    function syncFrom(col) {
        pick._original = col
        const h = col.hsvHue
        pick.hue = h >= 0 ? Theme.wrapHue(h) : Theme.defaultHue
        pick.sat = Math.max(0, Math.min(1, col.hsvSaturation))
        pick.val = Math.max(0, Math.min(1, col.hsvValue))
        hexField.text = Theme.colorToHex(pick.currentColor)
    }

    function commit() {
        pick.selectedColor = pick.currentColor
        pick.accept()
    }

    function pickPlane(px, py) {
        const w = Math.max(1, plane.width)
        const h = Math.max(1, plane.height)
        pick.sat = Math.max(0, Math.min(1, px / w))
        pick.val = Math.max(0, Math.min(1, 1 - py / h))
    }

    function pickHue(py) {
        const h = Math.max(1, hueBar.height)
        pick.hue = Theme.wrapHue(py / h)
    }

    function pickAtNorm(nx, ny) {
        pick.pickPlane(plane.width * Math.max(0, Math.min(1, nx)), plane.height * Math.max(0, Math.min(1, ny)))
    }

    function pickHueNorm(ny) {
        pick.pickHue(hueBar.height * Math.max(0, Math.min(1, ny)))
    }

    function applyLive(col) {
        if (col === undefined || col === null)
            return
        const h = col.hsvHue
        pick.hue = h >= 0 ? Theme.wrapHue(h) : pick.hue
        pick.sat = Math.max(0, Math.min(1, col.hsvSaturation))
        pick.val = Math.max(0, Math.min(1, col.hsvValue))
    }

    function beginDrop() {
        if (!pick.screenPicker || pick.dropping)
            return
        pick._dropSaved = pick.currentColor
        pick.screenPicker.start()
    }

    onAboutToShow: {
        if (Overlay.overlay)
            pick.parent = Overlay.overlay
    }
    onOpened: {
        pick.syncFrom(pick.selectedColor)
        plane.forceActiveFocus()
    }
    onClosed: {
        if (pick.screenPicker && pick.screenPicker.picking)
            pick.screenPicker.cancel()
    }

    Connections {
        target: pick.screenPicker
        function onSampleChanged() {
            if (pick.dropping)
                pick.applyLive(pick.screenPicker.sample)
        }
        function onPicked(col) { pick.applyLive(col) }
        function onCancelled() { pick.applyLive(pick._dropSaved) }
    }

    contentItem: ColumnLayout {
        id: body
        spacing: Theme.s2

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2

            Text {
                Layout.fillWidth: true
                text: "PICK " + pick.roleName
                color: Theme.accent
                font.pixelSize: Theme.fontLg
                font.letterSpacing: Theme.tracking2
                elide: Text.ElideRight
                Accessible.name: "Pick " + pick.roleName
            }
            HudButton {
                id: dropperBtn
                objectName: "colourSample"
                Layout.preferredWidth: implicitWidth
                Layout.preferredHeight: Theme.controlHeight
                text: "DROP"
                enabled: !!pick.screenPicker
                tooltip: "Eyedropper. Click a pixel on screen. Escape cancels."
                accessibleDescription: "Sample a colour from anywhere on screen. Click a pixel, Escape cancels."
                onClicked: pick.beginDrop()
                contentItem: Row {
                    spacing: 6
                    leftPadding: 2
                    rightPadding: 2
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "\uEF3C"
                        font.family: Theme.fontIcon
                        font.pixelSize: Theme.fontPx(14)
                        color: dropperBtn.enabled || dropperBtn.isBusy ? dropperBtn.foregroundColor : Theme.textSecondary
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: dropperBtn.isBusy && dropperBtn.busyText !== "" ? dropperBtn.busyText : dropperBtn.text
                        color: dropperBtn.enabled || dropperBtn.isBusy ? dropperBtn.foregroundColor : Theme.textSecondary
                        font: dropperBtn.font
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2

            Item {
                id: plane
                objectName: "colourPlane"
                Layout.preferredWidth: 216
                Layout.preferredHeight: 216
                implicitWidth: 216
                implicitHeight: 216
                activeFocusOnTab: true
                Accessible.role: Accessible.Slider
                Accessible.name: pick.roleName + " saturation and brightness"
                Accessible.description: "Left is grey, right is vivid. Top is bright, bottom is dark. Arrow keys nudge."
                Keys.onPressed: function (event) {
                    const step = event.modifiers & Qt.ShiftModifier ? 0.01 : 0.04
                    if (event.key === Qt.Key_Left) {
                        pick.sat = Math.max(0, pick.sat - step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Right) {
                        pick.sat = Math.min(1, pick.sat + step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Down) {
                        pick.val = Math.max(0, pick.val - step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up) {
                        pick.val = Math.min(1, pick.val + step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        pick.commit()
                        event.accepted = true
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    color: Qt.hsva(Theme.wrapHue(pick.hue), 1, 1, 1)
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#ffffffff" }
                        GradientStop { position: 1.0; color: "#00ffffff" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    gradient: Gradient {
                        orientation: Gradient.Vertical
                        GradientStop { position: 0.0; color: "#00000000" }
                        GradientStop { position: 1.0; color: "#ff000000" }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    color: "transparent"
                    border.color: plane.activeFocus ? Theme.accent : Theme.outline
                    border.width: plane.activeFocus ? 2 : 1
                }
                Rectangle {
                    x: Math.round(pick.sat * plane.width) - width / 2
                    y: Math.round((1 - pick.val) * plane.height) - height / 2
                    width: 12
                    height: 12
                    radius: 6
                    color: "transparent"
                    border.color: pick.val > 0.55 ? "#111111" : "#ffffff"
                    border.width: 2
                }
                MouseArea {
                    anchors.fill: parent
                    preventStealing: true
                    hoverEnabled: true
                    cursorShape: Qt.CrossCursor
                    onPressed: function (mouse) {
                        plane.forceActiveFocus()
                        pick.pickPlane(mouse.x, mouse.y)
                    }
                    onPositionChanged: function (mouse) {
                        if (pressed)
                            pick.pickPlane(mouse.x, mouse.y)
                    }
                }
            }

            Item {
                id: hueBar
                objectName: "colourHue"
                Layout.preferredWidth: 18
                Layout.preferredHeight: 216
                implicitWidth: 18
                implicitHeight: 216
                activeFocusOnTab: true
                Accessible.role: Accessible.Slider
                Accessible.name: pick.roleName + " hue"
                Accessible.description: "Vertical hue strip. Arrow keys nudge."
                Keys.onPressed: function (event) {
                    const step = event.modifiers & Qt.ShiftModifier ? 0.002 : 0.02
                    if (event.key === Qt.Key_Down || event.key === Qt.Key_Right) {
                        pick.hue = Theme.wrapHue(pick.hue + step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Up || event.key === Qt.Key_Left) {
                        pick.hue = Theme.wrapHue(pick.hue - step)
                        event.accepted = true
                    } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        pick.commit()
                        event.accepted = true
                    }
                }

                Column {
                    anchors.fill: parent
                    Repeater {
                        model: 6
                        delegate: Rectangle {
                            id: hueSlice
                            required property int index
                            width: hueBar.width
                            height: hueBar.height / 6
                            gradient: Gradient {
                                orientation: Gradient.Vertical
                                GradientStop { position: 0.0; color: Qt.hsva(hueSlice.index / 6, 1, 1, 1) }
                                GradientStop { position: 1.0; color: Qt.hsva((hueSlice.index + 1) / 6, 1, 1, 1) }
                            }
                        }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.color: hueBar.activeFocus ? Theme.accent : Theme.outline
                    border.width: hueBar.activeFocus ? 2 : 1
                }
                Rectangle {
                    x: -2
                    y: Math.round(Theme.wrapHue(pick.hue) * hueBar.height) - height / 2
                    width: hueBar.width + 4
                    height: 4
                    radius: 1
                    color: Theme.textPrimary
                    border.color: Theme.windowBase
                    border.width: 1
                }
                MouseArea {
                    anchors.fill: parent
                    preventStealing: true
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPressed: function (mouse) {
                        hueBar.forceActiveFocus()
                        pick.pickHue(mouse.y)
                    }
                    onPositionChanged: function (mouse) {
                        if (pressed)
                            pick.pickHue(mouse.y)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s2

            HudField {
                id: hexField
                objectName: "colourHex"
                Layout.preferredWidth: 108
                font.family: Theme.fontMono
                maximumLength: 7
                accessibleName: pick.roleName + " hex colour"
                tooltip: "Paste #RRGGBB. Hue, saturation and brightness follow."
                validator: RegularExpressionValidator { regularExpression: /^#?[0-9A-Fa-f]{0,6}$/ }
                releaseFocusOnEnter: false
                onEditingFinished: {
                    const col = Theme.parseHex(text)
                    if (!col) {
                        text = pick.currentHex
                        return
                    }
                    pick.syncFrom(col)
                }
                Keys.onReturnPressed: pick.commit()
                Keys.onEnterPressed: pick.commit()
                Binding {
                    target: hexField
                    property: "text"
                    value: pick.currentHex
                    when: !hexField.activeFocus
                }
            }

            Rectangle {
                Layout.preferredWidth: Theme.controlHeight
                Layout.preferredHeight: Theme.controlHeight
                radius: 2
                color: pick._original
                border.color: Theme.outline
                Accessible.name: "Previous " + pick.roleName
                Accessible.description: Theme.colorToHex(pick._original)
            }
            Rectangle {
                Layout.preferredWidth: Theme.controlHeight
                Layout.preferredHeight: Theme.controlHeight
                radius: 2
                color: pick.currentColor
                border.color: Theme.accent
                Accessible.name: "New " + pick.roleName
                Accessible.description: pick.currentHex
            }
            Item { Layout.fillWidth: true }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignRight
            spacing: Theme.s2
            HudButton {
                objectName: "colourCancel"
                text: "CANCEL"
                accessibleDescription: "Close without changing " + pick.roleName
                onClicked: pick.reject()
            }
            HudButton {
                objectName: "colourApply"
                text: "APPLY"
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                accessibleDescription: "Set " + pick.roleName + " to " + pick.currentHex
                onClicked: pick.commit()
            }
        }
    }

    Window {
        id: sampleLoupe
        visible: pick.dropping
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        width: 108
        height: 36
        x: (pick.screenPicker ? pick.screenPicker.cursorX : 0) + 20
        y: (pick.screenPicker ? pick.screenPicker.cursorY : 0) + 20
        color: "transparent"
        title: ""
        Rectangle {
            anchors.fill: parent
            color: Theme.surface
            border.color: Theme.accent
            border.width: 1
            radius: 2
            Row {
                anchors.fill: parent
                anchors.margins: 4
                spacing: 8
                Rectangle {
                    width: 28
                    height: 28
                    radius: 2
                    color: pick.currentColor
                    border.color: Theme.outline
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: pick.currentHex
                    color: Theme.textPrimary
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontSm
                }
            }
        }
    }
}
