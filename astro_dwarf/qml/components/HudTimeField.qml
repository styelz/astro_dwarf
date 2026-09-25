import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Timestamp field. Wheel over a part (year, month, day, hour, minute) nudges that
// part; minutes move in 5-minute steps to match the calendar snap. The calendar
// button opens a date and time picker for the same value.
HudField {
    id: field
    property int minuteStep: 5
    property string deviceId: ""
    placeholderText: "yyyy-MM-ddTHH:mm"
    font.family: Theme.fontMono
    rightPadding: pickBtn.visible ? Theme.px(32) : Theme.px(10)
    readonly property bool canWheel: !!field.parseStamp(field.text)

    function parseStamp(text) {
        const raw = String(text || "").trim()
        const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
        if (!match)
            return null
        return {
            year: Number(match[1]),
            month: Number(match[2]),
            day: Number(match[3]),
            hour: Number(match[4]),
            minute: Number(match[5])
        }
    }

    function formatStamp(date) {
        function pad(value) { return String(value).padStart(2, "0") }
        return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate())
            + "T" + pad(date.getHours()) + ":" + pad(date.getMinutes())
    }

    function nowStamp() {
        if (typeof backend !== "undefined" && backend.deviceNowStamp)
            return String(backend.deviceNowStamp(field.deviceId || "") || "")
        return field.formatStamp(new Date())
    }

    function unitAt(pos) {
        if (pos <= 4)
            return "year"
        if (pos <= 7)
            return "month"
        if (pos <= 10)
            return "day"
        if (pos <= 13)
            return "hour"
        return "minute"
    }

    function unitRange(unit) {
        switch (unit) {
        case "year": return [0, 4]
        case "month": return [5, 7]
        case "day": return [8, 10]
        case "hour": return [11, 13]
        default: return [14, 16]
        }
    }

    function nudge(steps, unit) {
        const parsed = field.parseStamp(field.text)
        if (!parsed || !steps)
            return false
        const date = new Date(parsed.year, parsed.month - 1, parsed.day, parsed.hour, parsed.minute)
        if (isNaN(date.getTime()))
            return false
        const part = unit || "minute"
        if (part === "year")
            date.setFullYear(date.getFullYear() + steps)
        else if (part === "month")
            date.setMonth(date.getMonth() + steps)
        else if (part === "day")
            date.setDate(date.getDate() + steps)
        else if (part === "hour")
            date.setHours(date.getHours() + steps)
        else
            date.setMinutes(date.getMinutes() + steps * Math.max(1, field.minuteStep))
        field.text = field.formatStamp(date)
        const range = field.unitRange(part)
        field.select(range[0], range[1])
        return true
    }

    function gridOrigin() {
        const first = new Date(picker.viewYear, picker.viewMonth, 1)
        const weekday = (first.getDay() + 6) % 7
        return new Date(picker.viewYear, picker.viewMonth, 1 - weekday)
    }

    function cellDate(index) {
        const origin = field.gridOrigin()
        return new Date(origin.getFullYear(), origin.getMonth(), origin.getDate() + index)
    }

    function selectionIndex() {
        const origin = field.gridOrigin()
        const from = Date.UTC(origin.getFullYear(), origin.getMonth(), origin.getDate())
        const to = Date.UTC(picker.year, picker.month - 1, picker.day)
        const index = Math.round((to - from) / 86400000)
        return index >= 0 && index < 42 ? index : -1
    }

    function showStamp(stamp, followView) {
        const parsed = field.parseStamp(stamp)
        if (!parsed)
            return false
        picker.year = parsed.year
        picker.month = parsed.month
        picker.day = parsed.day
        picker.hour = parsed.hour
        picker.minute = parsed.minute
        if (followView) {
            picker.viewYear = parsed.year
            picker.viewMonth = parsed.month - 1
            const index = field.selectionIndex()
            picker.cursor = index >= 0 ? index : 0
        }
        return true
    }

    function writeStamp(stamp, followView) {
        if (!field.parseStamp(stamp))
            return false
        if (field.text !== stamp)
            field.text = stamp
        return field.showStamp(stamp, followView)
    }

    function chooseDay(date) {
        const next = new Date(date.getFullYear(), date.getMonth(), date.getDate(), picker.hour, picker.minute)
        picker.viewYear = next.getFullYear()
        picker.viewMonth = next.getMonth()
        field.writeStamp(field.formatStamp(next), false)
        picker.cursor = field.selectionIndex()
    }

    function shiftView(delta) {
        const date = new Date(picker.viewYear, picker.viewMonth + delta, 1)
        picker.viewYear = date.getFullYear()
        picker.viewMonth = date.getMonth()
        const index = field.selectionIndex()
        picker.cursor = index >= 0 ? index : Math.min(41, Math.max(0, picker.cursor))
    }

    function shiftClock(part, delta) {
        const date = new Date(picker.year, picker.month - 1, picker.day, picker.hour, picker.minute)
        if (isNaN(date.getTime()))
            return
        if (part === "hour")
            date.setHours(date.getHours() + delta)
        else
            date.setMinutes(date.getMinutes() + delta * Math.max(1, field.minuteStep))
        field.writeStamp(field.formatStamp(date), false)
    }

    function placePicker() {
        const overlay = Overlay.overlay
        if (!overlay)
            return false
        if (picker.parent !== overlay)
            picker.parent = overlay
        const pos = field.mapToItem(overlay, 0, field.height + Theme.px(4))
        const w = picker.width
        const h = picker.height
        let x = pos.x + field.width - w
        let y = pos.y
        x = Math.max(Theme.s2, Math.min(x, overlay.width - w - Theme.s2))
        if (y + h > overlay.height - Theme.s2)
            y = Math.max(Theme.s2, pos.y - field.height - Theme.px(4) - h)
        picker.x = x
        picker.y = y
        picker.z = 2000
        return true
    }

    function openPicker() {
        const parsed = field.parseStamp(field.text)
        field.showStamp(parsed ? field.text : field.nowStamp(), true)
        if (!field.placePicker())
            return
        picker.open()
    }

    function togglePicker() {
        if (picker.opened)
            picker.close()
        else
            field.openPicker()
    }

    onTextChanged: {
        if (picker.opened)
            field.showStamp(field.text, false)
    }
    onVisibleChanged: {
        if (!field.visible && picker.opened)
            picker.close()
    }
    onEnabledChanged: {
        if (!field.enabled && picker.opened)
            picker.close()
    }

    // Reparenting the popup onto the overlay keeps it above the dialog.
    // Destroy it with the field so a closed dialog cannot leave it up.
    Item {
        Component.onDestruction: {
            if (picker.parent !== field)
                picker.destroy()
        }
    }

    WheelHandler {
        enabled: field.enabled && !field.readOnly && field.canWheel
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        acceptedModifiers: Qt.NoModifier
        blocking: true
        onWheel: event => {
            const delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.pixelDelta.y
            if (!delta)
                return
            const pos = field.positionAt(point.position.x, field.height / 2)
            if (field.nudge(delta > 0 ? 1 : -1, field.unitAt(pos)))
                event.accepted = true
        }
    }

    component PickGlyph: Item {
        id: glyphBtn
        property string glyph: ""
        property string name: ""
        signal activated()
        width: Theme.compactControlHeight
        height: Theme.compactControlHeight
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: name
        Accessible.onPressAction: glyphBtn.activated()
        Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                event.accepted = true
                glyphBtn.activated()
            }
        }
        MouseArea {
            id: glyphClick
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: glyphBtn.activated()
        }
        Text {
            anchors.centerIn: parent
            text: glyphBtn.glyph
            font.family: Theme.fontIcon
            font.pixelSize: Theme.fontSm
            font.preferShaping: true
            color: glyphBtn.activeFocus || glyphClick.containsMouse ? Theme.accent : Theme.textSecondary
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.s1
            radius: Theme.px(2)
            color: "transparent"
            border.color: Theme.accent
            border.width: Theme.focusStroke
            visible: glyphBtn.activeFocus
        }
    }

    Item {
        id: pickBtn
        objectName: (field.objectName || "time") + "-picker-button"
        visible: field.enabled && !field.readOnly
        width: Theme.px(28)
        height: parent.height
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        z: 2
        property bool tipReady: false
        function hideTip() {
            tipReady = false
        }
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: "Pick date and time"
        Accessible.onPressAction: field.togglePicker()
        Keys.onPressed: function (event) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                event.accepted = true
                field.togglePicker()
            }
        }
        MouseArea {
            id: pickClick
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: pickBtn.tipReady = !picker.opened
            onExited: pickBtn.hideTip()
            onPressed: pickBtn.hideTip()
            onClicked: field.togglePicker()
        }
        Item {
            width: Theme.px(14)
            height: Theme.px(14)
            anchors.centerIn: parent
            Rectangle {
                anchors.fill: parent
                color: "transparent"
                border.width: 1
                border.color: pickBtn.activeFocus || pickClick.containsMouse || picker.opened ? Theme.accent : Theme.textSecondary
            }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Theme.px(4)
                color: pickBtn.activeFocus || pickClick.containsMouse || picker.opened ? Theme.accent : Theme.textSecondary
            }
            Rectangle {
                x: Theme.px(3)
                y: -Theme.px(2)
                width: Theme.px(1)
                height: Theme.px(4)
                color: pickBtn.activeFocus || pickClick.containsMouse || picker.opened ? Theme.accent : Theme.textSecondary
            }
            Rectangle {
                x: Theme.px(10)
                y: -Theme.px(2)
                width: Theme.px(1)
                height: Theme.px(4)
                color: pickBtn.activeFocus || pickClick.containsMouse || picker.opened ? Theme.accent : Theme.textSecondary
            }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: Theme.s1
            radius: Theme.px(2)
            color: "transparent"
            border.color: Theme.accent
            border.width: Theme.focusStroke
            visible: pickBtn.activeFocus
        }
        HudToolTip {
            id: pickTip
            visible: pickBtn.tipReady && pickClick.containsMouse && !picker.opened
            text: "Pick date and time"
        }
    }

    Popup {
        id: picker
        objectName: (field.objectName || "time") + "-picker"
        modal: true
        dim: false
        focus: true
        padding: Theme.s2
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        readonly property int gridWidth: Theme.px(32) * 7 + Theme.px(2) * 6
        width: gridWidth + leftPadding + rightPadding
        height: pickerColumn.implicitHeight + topPadding + bottomPadding
        palette.window: Theme.popupBg
        palette.windowText: Theme.textPrimary
        property int viewYear: 2026
        property int viewMonth: 0
        property int year: 2026
        property int month: 1
        property int day: 1
        property int hour: 0
        property int minute: 0
        property int cursor: 0
        onAboutToShow: pickBtn.hideTip()
        onOpened: field.placePicker()
        onClosed: {
            pickBtn.focus = false
            pickBtn.hideTip()
        }
        background: HudFrame {
            topLeft: Theme.notchSmall
            topRight: 0
            bottomRight: Theme.notchSmall
            bottomLeft: 0
            fillColor: Theme.popupBg
            strokeColor: Theme.accent
        }
        contentItem: Column {
            id: pickerColumn
            spacing: Theme.s2
            width: picker.gridWidth

            Row {
                width: parent.width
                height: Theme.compactControlHeight
                spacing: Theme.s1
                PickGlyph {
                    glyph: "\uE74A"
                    name: "Previous month"
                    onActivated: field.shiftView(-1)
                }
                Text {
                    width: parent.width - Theme.compactControlHeight * 2 - Theme.s1 * 2
                    height: parent.height
                    text: Qt.formatDate(new Date(picker.viewYear, picker.viewMonth, 1), "MMMM yyyy").toUpperCase()
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSm
                    font.bold: true
                    font.letterSpacing: Theme.tracking1
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                PickGlyph {
                    glyph: "\uE74B"
                    name: "Next month"
                    onActivated: field.shiftView(1)
                }
            }

            Row {
                width: parent.width
                spacing: Theme.px(2)
                Repeater {
                    model: ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
                    Text {
                        required property string modelData
                        width: Theme.px(32)
                        text: modelData
                        color: Theme.accent
                        font.pixelSize: Theme.fontXs
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }
                }
            }

            Grid {
                id: dayGrid
                columns: 7
                rowSpacing: Theme.px(2)
                columnSpacing: Theme.px(2)
                focus: true
                activeFocusOnTab: true
                Accessible.name: "Date"
                Keys.onLeftPressed: event => { picker.cursor = Math.max(0, picker.cursor - 1); event.accepted = true }
                Keys.onRightPressed: event => { picker.cursor = Math.min(41, picker.cursor + 1); event.accepted = true }
                Keys.onUpPressed: event => { picker.cursor = Math.max(0, picker.cursor - 7); event.accepted = true }
                Keys.onDownPressed: event => { picker.cursor = Math.min(41, picker.cursor + 7); event.accepted = true }
                Keys.onPressed: event => {
                    if (event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter && event.key !== Qt.Key_Space)
                        return
                    event.accepted = true
                    field.chooseDay(field.cellDate(picker.cursor))
                }
                Repeater {
                    model: 42
                    delegate: Rectangle {
                        id: dayCell
                        required property int index
                        readonly property date cell: field.cellDate(index)
                        readonly property bool inMonth: cell.getMonth() === picker.viewMonth
                        readonly property bool chosen: cell.getFullYear() === picker.year
                            && cell.getMonth() === picker.month - 1
                            && cell.getDate() === picker.day
                        readonly property bool isCursor: dayGrid.activeFocus && picker.cursor === index
                        readonly property var today: new Date()
                        readonly property bool isToday: cell.getFullYear() === today.getFullYear()
                            && cell.getMonth() === today.getMonth()
                            && cell.getDate() === today.getDate()
                        width: Theme.px(32)
                        height: Theme.px(32)
                        radius: Theme.px(2)
                        color: dayCell.chosen ? Theme.fillChecked : dayHover.containsMouse ? Theme.inputBg : "transparent"
                        border.width: dayCell.isCursor || (dayCell.isToday && !dayCell.chosen) ? Theme.focusStroke : 0
                        border.color: Theme.accent
                        Accessible.role: Accessible.Button
                        Accessible.name: Qt.formatDate(cell, "d MMMM yyyy")
                        Text {
                            anchors.centerIn: parent
                            text: dayCell.cell.getDate()
                            color: dayCell.chosen ? Theme.accent : dayCell.inMonth ? Theme.textPrimary : Theme.muted
                            font.family: Theme.fontMono
                            font.pixelSize: Theme.fontSm
                            font.bold: dayCell.chosen || dayCell.isToday
                        }
                        MouseArea {
                            id: dayHover
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: picker.cursor = dayCell.index
                            onClicked: field.chooseDay(dayCell.cell)
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Theme.outline
            }

            RowLayout {
                id: timeRow
                width: parent.width
                spacing: Theme.s1
                Text {
                    height: parent.height
                    text: "TIME"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontXs
                    font.bold: true
                    font.letterSpacing: Theme.tracking1
                    verticalAlignment: Text.AlignVCenter
                }
                PickGlyph {
                    glyph: "\uE74A"
                    name: "Earlier hour"
                    onActivated: field.shiftClock("hour", -1)
                }
                Text {
                    width: Theme.px(22)
                    height: parent.height
                    text: String(picker.hour).padStart(2, "0")
                    color: Theme.textPrimary
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontMd
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                PickGlyph {
                    glyph: "\uE74B"
                    name: "Later hour"
                    onActivated: field.shiftClock("hour", 1)
                }
                Text {
                    height: parent.height
                    text: ":"
                    color: Theme.textSecondary
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontMd
                    verticalAlignment: Text.AlignVCenter
                }
                PickGlyph {
                    glyph: "\uE74A"
                    name: "Earlier minute"
                    onActivated: field.shiftClock("minute", -1)
                }
                Text {
                    width: Theme.px(22)
                    height: parent.height
                    text: String(picker.minute).padStart(2, "0")
                    color: Theme.textPrimary
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontMd
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                PickGlyph {
                    glyph: "\uE74B"
                    name: "Later minute"
                    onActivated: field.shiftClock("minute", 1)
                }
                Item { Layout.fillWidth: true; Layout.minimumWidth: Theme.s1 }
                HudButton {
                    text: "NOW"
                    font.pixelSize: Theme.fontXs
                    font.letterSpacing: 0
                    leftPadding: Theme.s2
                    rightPadding: Theme.s2
                    implicitHeight: Theme.compactControlHeight
                    accessibleName: "Use the current time"
                    onClicked: field.writeStamp(field.nowStamp(), true)
                }
            }
        }
    }
}
