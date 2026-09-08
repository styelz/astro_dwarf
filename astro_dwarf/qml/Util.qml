pragma Singleton
import QtQuick
import "."

// Pure helpers shared by pages and components.
QtObject {
    function statusColor(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return Theme.accent
        case "error": return Theme.danger
        case "done": return Theme.success
        case "skipped": return Theme.textSecondary
        default: return Theme.textPrimary
        }
    }
    function formatDuration(seconds) {
        const total = Math.max(0, Math.round(Number(seconds || 0)))
        const h = Math.floor(total / 3600)
        const m = Math.floor((total % 3600) / 60)
        if (h > 0)
            return h + "h " + String(m).padStart(2, "0") + "m"
        if (m > 0)
            return m + "m"
        return total + "s"
    }
    function canReset(status) {
        const value = String(status || "").toLowerCase()
        return value === "error" || value === "skipped" || value === "done"
    }
    function idSetCount(map) {
        return Object.keys(map || {}).length
    }
    function idSetKeys(map) {
        return Object.keys(map || {})
    }
    function idSetHas(map, id) {
        return !!(map && id && map[id])
    }
    function idSetToggle(map, id) {
        const next = Object.assign({}, map || {})
        if (!id)
            return next
        if (next[id])
            delete next[id]
        else
            next[id] = true
        return next
    }
    function itemIndexById(items, id) {
        const list = items || []
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === id)
                return i
        }
        return -1
    }
    function clickSelect(map, items, id, shift, anchorId) {
        const list = items || []
        const clicked = Util.itemIndexById(list, id)
        if (!id || clicked < 0)
            return { map: map || {}, anchor: anchorId || "" }
        const select = !Util.idSetHas(map, id)
        if (shift) {
            let start = Util.itemIndexById(list, anchorId)
            if (start < 0)
                start = clicked
            const lo = Math.min(start, clicked)
            const hi = Math.max(start, clicked)
            const next = Object.assign({}, map || {})
            for (let i = lo; i <= hi; i++) {
                const itemId = list[i] && list[i].id
                if (!itemId)
                    continue
                if (select)
                    next[itemId] = true
                else
                    delete next[itemId]
            }
            return { map: next, anchor: anchorId || id }
        }
        return { map: Util.idSetToggle(map, id), anchor: id }
    }
    function idSetAll(items, on) {
        const next = {}
        if (!on)
            return next
        const list = items || []
        for (let i = 0; i < list.length; i++) {
            const id = list[i] && list[i].id
            if (id)
                next[id] = true
        }
        return next
    }
    function pruneIdSet(map, items) {
        const alive = {}
        const list = items || []
        for (let i = 0; i < list.length; i++) {
            const id = list[i] && list[i].id
            if (id)
                alive[id] = true
        }
        const next = {}
        const keys = Object.keys(map || {})
        for (let i = 0; i < keys.length; i++) {
            if (alive[keys[i]])
                next[keys[i]] = true
        }
        return next
    }
    function toneForLevel(level) {
        switch (String(level || "").toLowerCase()) {
        case "error": return Theme.danger
        case "warning": return Theme.warning
        case "success": return Theme.success
        case "notice": return Theme.notice
        case "sdk":
        case "debug": return Theme.muted
        default: return Theme.accent
        }
    }
    function glyphForLevel(level) {
        switch (String(level || "").toLowerCase()) {
        case "error": return "✗"
        case "warning": return "⚠"
        case "success": return "✓"
        case "notice": return "◆"
        case "sdk": return "›"
        case "debug": return "·"
        default: return "●"
        }
    }
    function batteryTone(percent) {
        const value = Number(percent)
        if (isNaN(value) || value < 0)
            return "unknown"
        return value <= 10 ? "bad" : value <= 20 ? "warn" : "good"
    }
    function toneColor(tone) {
        switch (String(tone || "")) {
        case "bad": return Theme.danger
        case "warn": return Theme.warning
        case "good": return Theme.success
        default: return Theme.textSecondary
        }
    }
    function activityLabel(activity) {
        switch (String(activity || "")) {
        case "calibrate": return "CALIBRATING"
        case "goto": return "GOTO"
        case "polar": return "POLAR / EQ"
        case "autofocus": return "AUTOFOCUS"
        case "dark": return "DARK FRAMES"
        case "imaging": return "STACKING"
        case "record": return "RECORDING"
        case "burst": return "BURST"
        case "timelapse": return "TIMELAPSE"
        case "poweroff": return "POWER OFF"
        case "": return ""
        default: return String(activity).toUpperCase()
        }
    }
    function statusFill(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return Theme.fillChecked
        case "error": return Theme.fillDanger
        case "done": return Theme.fillSuccess
        default: return Theme.surfaceHigh
        }
    }
    function durationLabel(seconds) {
        const value = Math.max(0, Math.round(Number(seconds) || 0))
        const hours = Math.floor(value / 3600)
        const minutes = Math.floor((value % 3600) / 60)
        const secs = value % 60
        return hours > 0
            ? hours + "h " + String(minutes).padStart(2, "0") + "m"
            : minutes > 0 ? minutes + "m " + String(secs).padStart(2, "0") + "s" : secs + "s"
    }
    function targetCoordinates(item) {
        const target = item && item.target ? item.target : null
        if (!target || target.ra_hours === undefined || target.ra_hours === null
                || target.dec_degrees === undefined || target.dec_degrees === null)
            return ""
        return "RA " + Number(target.ra_hours).toFixed(3) + "h  DEC "
            + Number(target.dec_degrees).toFixed(3) + "°"
    }
}
