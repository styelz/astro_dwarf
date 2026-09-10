import QtQuick
import ".."

// Timestamp field. Wheel over a part (year, month, day, hour, minute) nudges that
// part; minutes move in 5-minute steps to match the calendar snap.
HudField {
    id: field
    property int minuteStep: 5
    placeholderText: "yyyy-MM-ddTHH:mm"
    font.family: Theme.fontMono
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
}
