pragma Singleton
import QtQuick
import "."

// Pure helpers shared by pages and components.
// Stock capture fallbacks match astro_dwarf.domain DEFAULT_* when a device
// has no saved Settings defaults yet.
QtObject {
    readonly property real stockExposureSeconds: 15
    readonly property int stockGain: 40
    readonly property int stockFrameCount: 60
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
    function clockDuration(seconds) {
        const total = Math.max(0, Math.round(Number(seconds || 0)))
        const h = Math.floor(total / 3600)
        const m = Math.floor((total % 3600) / 60)
        const s = total % 60
        return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
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
    function itemsByIds(items, map) {
        const list = items || []
        const result = []
        for (let i = 0; i < list.length; i++) {
            if (list[i] && Util.idSetHas(map, list[i].id))
                result.push(list[i])
        }
        return result
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
        case "polar_position": return "POLAR POS"
        case "autofocus": return "AUTOFOCUS"
        case "infinity": return "INFINITY"
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
    function commandTransitionLocked(op, pending, telemetry) {
        // Stop, stop-and-cancel, and a firmware state change are one-shot.
        // The pad stays dark while that command is in flight, and while the
        // telescope is still in the stopping state between the two modes.
        const operation = String(op || "")
        const inflight = String(pending || "")
        const t = telemetry || ({})
        const startForStop = {
            burst_stop: "burst_start",
            record_stop: "record_start",
            timelapse_stop: "timelapse_start",
            stop_calibrate: "calibrate",
            stop_polar: "polar",
            stop_astro: "stack",
            lights_off: "lights_on",
            indicator_off: "indicator_on"
        }
        if (inflight && startForStop[operation] === inflight)
            return true
        if (operation === "stop_autofocus" && (inflight === "autofocus" || inflight === "infinity"))
            return true
        if (operation === "stop_goto" && (inflight === "track" || inflight === "sky_track"))
            return true
        if (operation === "cancel_prime" && inflight !== "")
            return true
        if (inflight === "cancel_prime" && (
            operation === "photo"
            || operation === "burst_start" || operation === "burst_stop"
            || operation === "record_start" || operation === "record_stop"
            || operation === "timelapse_start" || operation === "timelapse_stop"
        ))
            return true
        const stateKey = {
            calibrate: "calibration_state",
            stop_calibrate: "calibration_state",
            autofocus: "autofocus_state",
            infinity: "autofocus_state",
            stop_autofocus: "autofocus_state",
            polar: "eq_state",
            stop_polar: "eq_state",
            track: "goto_state",
            sky_track: "goto_state",
            stop_goto: "goto_state",
            stack: "capture_state",
            stop_astro: "capture_state",
            photo: "photo_state",
            burst_start: "burst_state",
            burst_stop: "burst_state",
            record_start: "record_state",
            record_stop: "record_state",
            timelapse_start: "timelapse_state",
            timelapse_stop: "timelapse_state"
        }[operation] || ""
        if (stateKey && String(t[stateKey] || "") === "stopping")
            return true
        if (operation === "cancel_prime") {
            return String(t.photo_state || "") === "stopping"
                || String(t.burst_state || "") === "stopping"
                || String(t.record_state || "") === "stopping"
                || String(t.timelapse_state || "") === "stopping"
        }
        return false
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
    function clockLabel(seconds) {
        const value = Math.max(0, Math.floor(Number(seconds) || 0))
        const hours = Math.floor(value / 3600)
        const minutes = Math.floor((value % 3600) / 60)
        const secs = value % 60
        if (hours > 0)
            return hours + ":" + String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0")
        return String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0")
    }
    function sessionStepLabel(session, nowMs) {
        const step = String((session && session.current_step) || "")
        if (!session || String(session.status || "") !== "running" || !step)
            return step
        const started = Number(session.step_started_at || 0)
        if (started <= 0)
            return step
        const now = Number(nowMs || 0) / 1000
        const elapsed = Math.max(0, Math.round(now - started))
        const total = Number(session.step_wait_seconds || 0)
        if (total > 0) {
            const remaining = Math.max(0, Math.round(total - elapsed))
            return step + "  ·  " + Util.durationLabel(remaining) + " remaining"
        }
        if (elapsed < 1)
            return step
        return step + "  ·  " + Util.durationLabel(elapsed)
    }
    function idleScheduleLabel(upcoming, schedulerEnabled, nowMs) {
        const next = upcoming && upcoming.length ? upcoming[0] : null
        if (!next)
            return schedulerEnabled ? "QUEUE EMPTY" : "IDLE"
        const name = next.pane_name || next.target_name || "next session"
        const startMs = Number(next.start_epoch_ms)
        const start = isNaN(startMs) ? new Date(next.scheduled_start).getTime() : startMs
        const seconds = Math.floor((start - Number(nowMs || Date.now())) / 1000)
        if (!schedulerEnabled)
            return "NEXT  " + name + (next.start_time ? "  ·  " + next.start_time : "") + "  ·  scheduler off"
        if (seconds <= 0)
            return "WAITING  ·  " + name + "  ·  due now"
        return "WAITING  ·  " + name + "  ·  " + Util.durationLabel(seconds)
    }
    function formatCoordinates(raHours, decDegrees) {
        const ra = Number(raHours)
        const dec = Number(decDegrees)
        if (!isFinite(ra) || !isFinite(dec))
            return ""
        return "RA " + ra.toFixed(3) + "h  DEC " + (dec >= 0 ? "+" : "") + dec.toFixed(3) + "°"
    }
    // Site latitude/longitude entry: blank stays blank, a number within
    // +/-limit is tidied to 5 decimals, anything else falls back.
    function siteCoordinateText(text, limit, fallback) {
        const raw = String(text === undefined || text === null ? "" : text).trim()
        if (raw === "")
            return ""
        const n = Number(raw)
        if (!isFinite(n) || Math.abs(n) > limit)
            return String(fallback === undefined || fallback === null ? "" : fallback)
        return n.toFixed(5)
    }
    function targetCoordinates(item) {
        const target = item && item.target ? item.target : null
        if (!target || target.ra_hours === undefined || target.ra_hours === null
                || target.dec_degrees === undefined || target.dec_degrees === null)
            return ""
        return Util.formatCoordinates(target.ra_hours, target.dec_degrees)
    }
    function skyShowIsMosaic(item) {
        const data = item || ({})
        if (data.is_grouped || data.is_group)
            return true
        const mosaic = data.mosaic || ({})
        const rows = Math.max(Number(mosaic.grid_rows) || 0, Number(mosaic.rows) || 0, Number(mosaic.row) || 0)
        const columns = Math.max(Number(mosaic.grid_columns) || 0, Number(mosaic.columns) || 0, Number(mosaic.column) || 0)
        return rows > 1 || columns > 1
    }
    function skyShowHasCoordinates(item) {
        if (Util.targetCoordinates(item) !== "")
            return true
        const data = item || ({})
        const members = data.group_members || data.members || []
        for (let i = 0; i < members.length; i++) {
            if (Util.targetCoordinates(members[i]) !== "")
                return true
        }
        return false
    }
    function groupHash(groupId) {
        const text = String(groupId || "")
        let hash = 2166136261
        for (let i = 0; i < text.length; i++)
            hash = Math.imul(hash ^ text.charCodeAt(i), 16777619)
        return hash >>> 0
    }
    function groupOffset(groupId) {
        const offsets = [0.00, 0.10, 0.18, -0.08, -0.16, 0.28, -0.28, 0.38]
        return offsets[Util.groupHash(groupId) % offsets.length]
    }
    function groupTone(groupId) {
        if (!groupId)
            return Theme.accent
        return Theme.hsl(Util.groupOffset(groupId), 1.0, 0.62, 1, 1.0)
    }
    function groupFill(groupId) {
        if (!groupId)
            return Theme.panelFill
        return Theme.hsl(Util.groupOffset(groupId), 0.50, 0.10, 0.70, 0.20)
    }
    function isGrouped(item) {
        return !!(item && item.group_id && (item.is_grouped || item.is_group))
    }
    function sessionTone(item) {
        if (Util.isGrouped(item))
            return Util.groupTone(item.group_id)
        return (item && item.device_color) || Theme.accent
    }
    function shouldEnhanceMedia(item) {
        if (!item)
            return false
        if (Util.isFolderMedia(item) || Util.isVideoMedia(item) || Util.isFitsMedia(item) || Util.isTiffMedia(item))
            return false
        if (item.source === "stills")
            return false
        if (item.source === "local") {
            const name = String(item.file_name || item.target || item.id || "")
            return /_stacked/i.test(name)
        }
        return !!(item.image_url || item.thumbnail_url)
    }
    function mediaKind(item) {
        return String((item && item.kind) || "").toLowerCase()
    }
    function isFolderMedia(item) {
        return !!(item && item.is_dir)
    }
    function isVideoMedia(item) {
        if (!item || Util.isFolderMedia(item))
            return false
        if (Util.mediaKind(item) === "video")
            return true
        const name = String(item.file_name || item.file_path || item.local_path || item.id || "")
        return Util.isVideoName(name)
    }
    function isVideoName(text) {
        return /\.(mp4|mov|m4v|mkv|avi)(?:$|[?#])/i.test(String(text || ""))
    }
    function isPreviewImageName(text) {
        return /\.(jpg|jpeg|png)(?:$|[?#])/i.test(String(text || ""))
    }
    function isFitsName(text) {
        return /\.(fits|fit|fts)(?:$|[?#])/i.test(String(text || ""))
    }
    function isTiffName(text) {
        return /\.(tif|tiff)(?:$|[?#])/i.test(String(text || ""))
    }
    function isHeavyPreviewName(text) {
        return Util.isFitsName(text) || Util.isTiffName(text)
    }
    function isFitsMedia(item) {
        if (!item || Util.isFolderMedia(item))
            return false
        return Util.isFitsName(item.file_name || item.file_path || item.local_path || item.image_url || item.id || "")
    }
    function isTiffMedia(item) {
        if (!item || Util.isFolderMedia(item))
            return false
        return Util.isTiffName(item.file_name || item.file_path || item.local_path || item.image_url || item.id || "")
    }
    function albumFolderLabel(name) {
        const key = String(name || "").trim().toLowerCase().replace(/_/g, " ")
        if (key === "normal photos" || key === "photos")
            return "PHOTOS"
        if (key === "astronomy" || key === "astro")
            return "ASTRO"
        if (key === "video" || key === "videos")
            return "VIDEO"
        if (key === "burst" || key === "bursts")
            return "BURST"
        if (key === "panorama")
            return "PANO"
        if (key === "panoramas")
            return "PANOS"
        return String(name || "").toUpperCase()
    }
    function albumFolderActive(folder, path) {
        const current = String(folder || "").replace(/\\/g, "/")
        const target = String(path || "").replace(/\\/g, "/")
        if (!current || !target)
            return false
        return current === target || current.startsWith(target + "/")
    }
    function mediaClock(ms) {
        const total = Math.max(0, Math.floor(Number(ms || 0) / 1000))
        const hours = Math.floor(total / 3600)
        const minutes = Math.floor((total % 3600) / 60)
        const secs = total % 60
        if (hours > 0)
            return hours + ":" + String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0")
        return minutes + ":" + String(secs).padStart(2, "0")
    }
    function mediaKindLabel(item) {
        if (Util.isFitsMedia(item))
            return "FITS"
        if (Util.isTiffMedia(item))
            return "TIFF"
        if (Util.isFolderMedia(item) && Util.mediaKind(item) === "folder")
            return "FOLDER"
        switch (Util.mediaKind(item)) {
        case "folder": return "FOLDER"
        case "video": return "VIDEO"
        case "burst": return "BURST"
        case "panorama": return "PANO"
        case "astro": return "STACK"
        case "photo": return "PHOTO"
        default:
            return item && item.source === "stills" ? "PHOTO" : ""
        }
    }
    function mediaKindGlyph(item) {
        if (Util.isFolderMedia(item))
            return "▤"
        switch (Util.mediaKind(item)) {
        case "folder": return "▤"
        case "video": return "▶"
        case "burst": return "◫"
        case "panorama": return "▣"
        case "astro": return "◈"
        default: return item && item.source === "stills" ? "▣" : "◈"
        }
    }
    function captureDefaults(device) {
        const cap = (device && device.capture_defaults) || {}
        const exposure = Number(cap.exposure_seconds)
        const gain = Number(cap.gain)
        const frames = Number(cap.frame_count)
        return {
            exposure_seconds: Number.isFinite(exposure) && exposure > 0 ? exposure : stockExposureSeconds,
            gain: Number.isFinite(gain) && gain >= 0 ? gain : stockGain,
            frame_count: Number.isFinite(frames) && frames >= 1 ? frames : stockFrameCount
        }
    }
    function deviceById(devices, id) {
        const list = devices || []
        for (let i = 0; i < list.length; i++) {
            if (list[i] && list[i].id === id)
                return list[i]
        }
        return null
    }
    function clusterSessions(items) {
        const list = items || []
        const groups = []
        const indexByKey = {}
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item)
                continue
            const key = String(item.group_key || ("session:" + item.id))
            if (!(key in indexByKey)) {
                indexByKey[key] = groups.length
                groups.push([])
            }
            groups[indexByKey[key]].push(item)
        }
        const result = []
        for (let g = 0; g < groups.length; g++) {
            const members = groups[g]
            members.sort(function(a, b) {
                const ai = Number(a.pane_index)
                const bi = Number(b.pane_index)
                if (ai !== bi)
                    return ai - bi
                return String(a.pane_name || "").localeCompare(String(b.pane_name || ""))
            })
            for (let m = 0; m < members.length; m++)
                result.push(members[m])
        }
        return result
    }
    function mosaicGroupStatus(members) {
        const list = members || []
        let running = false
        let error = false
        let planned = 0
        let done = 0
        let skipped = 0
        for (let i = 0; i < list.length; i++) {
            const status = String((list[i] && list[i].status) || "").toLowerCase()
            if (status === "running")
                running = true
            else if (status === "error")
                error = true
            else if (status === "planned")
                planned += 1
            else if (status === "done")
                done += 1
            else if (status === "skipped")
                skipped += 1
        }
        if (running)
            return "running"
        if (error)
            return "error"
        if (planned > 0)
            return "planned"
        if (done > 0 && done === list.length)
            return "done"
        if (skipped > 0 && skipped === list.length)
            return "skipped"
        return (list[0] && list[0].status) || "planned"
    }
    function mosaicGroupSummary(members) {
        const list = members || []
        const first = list[0] || {}
        let startMs = Number(first.start_epoch_ms)
        let endMs = Number(first.end_epoch_ms)
        let startDate = first.start_date || ""
        let startTime = first.start_time || ""
        let durationSum = 0
        let action = first
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item)
                continue
            const start = Number(item.start_epoch_ms)
            const finish = Number(item.end_epoch_ms)
            if (Number.isFinite(start) && (!Number.isFinite(startMs) || start < startMs)) {
                startMs = start
                startDate = item.start_date || startDate
                startTime = item.start_time || startTime
            }
            if (Number.isFinite(finish) && (!Number.isFinite(endMs) || finish > endMs))
                endMs = finish
            durationSum += Number(item.planned_duration_seconds || 0)
            if (!action || String(item.status || "").toLowerCase() === "running")
                action = item
        }
        const span = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs > startMs
            ? (endMs - startMs) / 1000
            : durationSum
        const count = Number(first.pane_count || list.length)
        const grid = first.grid_text || ""
        return {
            group_collapsed: true,
            group_members: list,
            group_status: Util.mosaicGroupStatus(list),
            group_start_date: startDate,
            group_start_time: startTime,
            group_duration_text: Util.clockDuration(span),
            group_summary: count + (count === 1 ? " pane" : " panes") + (grid ? " · " + grid : ""),
            group_action: action
        }
    }
    function sessionDeleteIds(item) {
        if (item && item.group_collapsed && item.group_members && item.group_members.length) {
            const ids = []
            for (let i = 0; i < item.group_members.length; i++) {
                const id = item.group_members[i] && item.group_members[i].id
                if (id)
                    ids.push(String(id))
            }
            if (ids.length)
                return ids
        }
        const id = item && item.id
        return id ? [String(id)] : []
    }
    function sessionDeleteEnabled(item) {
        const members = item && item.group_collapsed && item.group_members && item.group_members.length
            ? item.group_members
            : [item]
        for (let i = 0; i < members.length; i++) {
            if (members[i] && String(members[i].status || "") !== "running")
                return true
        }
        return false
    }
    function sessionGroupKey(item) {
        if (item && item.is_grouped)
            return String(item.group_key || "")
        return ""
    }
    function sameSessionGroup(a, b) {
        if (!a || !b)
            return false
        if (String(a.id || "") && String(a.id) === String(b.id))
            return true
        const key = Util.sessionGroupKey(a)
        return !!(key && key === Util.sessionGroupKey(b))
    }
    function sessionDragPlanned(item) {
        if (!item)
            return false
        const status = String((item.group_collapsed ? (item.group_status || item.status) : item.status) || "").toLowerCase()
        return status === "planned"
    }
    function groupIndexRange(rows, index) {
        const list = rows || []
        const row = list[index]
        if (!row)
            return { start: index, end: index }
        const key = Util.sessionGroupKey(row)
        if (!key || row.group_collapsed)
            return { start: index, end: index }
        let start = index
        let end = index
        while (start > 0 && Util.sessionGroupKey(list[start - 1]) === key)
            start -= 1
        while (end + 1 < list.length && Util.sessionGroupKey(list[end + 1]) === key)
            end += 1
        return { start, end }
    }
    function snapReorderInsertIndex(rows, insertIndex, source) {
        const list = rows || []
        const count = list.length
        if (insertIndex < 0)
            return insertIndex
        let idx = Math.max(0, Math.min(insertIndex, count))
        let from = -1
        let fromEnd = -1
        for (let i = 0; i < count; i++) {
            if (!Util.sameSessionGroup(list[i], source))
                continue
            if (from < 0)
                from = i
            fromEnd = i
        }
        if (from >= 0 && idx >= from && idx <= fromEnd + 1)
            return -1
        const probe = idx < count ? idx : count - 1
        if (probe >= 0 && probe < count && !Util.sameSessionGroup(list[probe], source)) {
            const range = Util.groupIndexRange(list, probe)
            if (range.end > range.start && idx > range.start && idx <= range.end) {
                const mid = (range.start + range.end + 1) / 2
                idx = idx <= mid ? range.start : range.end + 1
            }
        }
        return idx
    }
    function reorderBeforeId(rows, insertIndex, source) {
        const list = rows || []
        const idx = Util.snapReorderInsertIndex(list, insertIndex, source)
        if (idx < 0)
            return { skip: true, beforeId: "", night: "" }
        for (let i = idx; i < list.length; i++) {
            const target = list[i]
            if (!target || Util.sameSessionGroup(target, source))
                continue
            if (String(target.device_id) !== String(source.device_id))
                continue
            if (!Util.sessionDragPlanned(target))
                continue
            return { skip: false, beforeId: String(target.id), night: String(target.observing_date || "") }
        }
        let night = ""
        const prevIdx = Math.min(idx, list.length) - 1
        const neighbor = list[prevIdx >= 0 ? prevIdx : 0]
        if (neighbor && neighbor.observing_date)
            night = String(neighbor.observing_date)
        return { skip: false, beforeId: "", night }
    }
    function mosaicGroupKeys(items) {
        const list = items || []
        const keys = []
        const seen = {}
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item || !item.is_grouped)
                continue
            const key = String(item.group_key || "")
            if (!key || seen[key])
                continue
            seen[key] = true
            keys.push(key)
        }
        return keys
    }
    function mosaicGroupKeyMap(items) {
        const keys = Util.mosaicGroupKeys(items)
        const next = {}
        for (let i = 0; i < keys.length; i++)
            next[keys[i]] = true
        return next
    }
    function expandedKeyCount(map, keys) {
        const expanded = map || {}
        const list = keys || []
        let n = 0
        for (let i = 0; i < list.length; i++) {
            if (expanded[list[i]])
                n += 1
        }
        return n
    }
    function idSetVisibleCount(map, items) {
        const list = items || []
        let n = 0
        for (let i = 0; i < list.length; i++) {
            if (Util.idSetHas(map, list[i] && list[i].id))
                n += 1
        }
        return n
    }
    function visibleClusteredSessions(items, expandedMap) {
        const clustered = Util.clusterSessions(items)
        const expanded = expandedMap || {}
        const result = []
        let i = 0
        while (i < clustered.length) {
            const item = clustered[i]
            if (!item) {
                i += 1
                continue
            }
            if (!item.is_grouped) {
                result.push(item)
                i += 1
                continue
            }
            const key = String(item.group_key || "")
            const members = []
            while (i < clustered.length && clustered[i] && String(clustered[i].group_key || "") === key) {
                members.push(clustered[i])
                i += 1
            }
            if (expanded[key]) {
                for (let m = 0; m < members.length; m++)
                    result.push(members[m])
            } else {
                result.push(Object.assign({}, members[0], Util.mosaicGroupSummary(members)))
            }
        }
        return result
    }
    function historyGroupSummary(members) {
        const list = members || []
        const first = list[0] || {}
        let ok = 0
        let captured = 0
        let planned = 0
        let plannedSec = 0
        let actualSec = 0
        const ids = []
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item)
                continue
            ids.push(item.id)
            if (item.ok)
                ok += 1
            captured += Number(item.captured_frames || 0)
            planned += Number(item.planned_frames || item.frame_count || 0)
            plannedSec += Number(item.planned_duration_seconds || 0)
            actualSec += Number(item.actual_duration_seconds || 0)
        }
        const count = list.length
        const fail = count - ok
        let outcome = first.outcome || ""
        const allOk = fail === 0 && count > 0
        if (ok && fail)
            outcome = ok + "/" + count + " completed"
        else if (allOk)
            outcome = "Completed"
        const grid = first.grid_text || ""
        const title = first.group_title || first.target_name || "Mosaic"
        return {
            group_collapsed: true,
            group_members: list,
            group_member_ids: ids,
            group_summary: count + (count === 1 ? " pane" : " panes") + (grid ? " · " + grid : ""),
            group_title: title,
            target_name: title,
            date: first.date,
            device_name: first.device_name,
            device_color: first.device_color,
            device_id: first.device_id,
            ok: allOk,
            outcome: outcome,
            frame_text: captured + "/" + planned,
            captured_frames: captured,
            planned_frames: planned,
            planned_duration_seconds: plannedSec,
            actual_duration_seconds: actualSec,
            planned_text: Util.clockDuration(plannedSec),
            actual_text: Util.clockDuration(actualSec),
            delta_seconds: actualSec - plannedSec,
            delta_text: "",
            summary: first.summary || "",
            notes: "",
            has_session: list.some(function(item) { return !!(item && item.has_session) }),
            session_id: first.session_id,
            id: first.id,
            is_grouped: true,
            group_key: first.group_key,
            group_id: first.group_id
        }
    }
    function visibleClusteredHistory(items, expandedMap) {
        const clustered = Util.clusterSessions(items)
        const expanded = expandedMap || {}
        const result = []
        let i = 0
        while (i < clustered.length) {
            const item = clustered[i]
            if (!item) {
                i += 1
                continue
            }
            if (!item.is_grouped) {
                result.push(item)
                i += 1
                continue
            }
            const key = String(item.group_key || "")
            const members = []
            while (i < clustered.length && clustered[i] && String(clustered[i].group_key || "") === key) {
                members.push(clustered[i])
                i += 1
            }
            if (expanded[key]) {
                for (let m = 0; m < members.length; m++)
                    result.push(members[m])
            } else {
                result.push(Object.assign({}, members[0], Util.historyGroupSummary(members)))
            }
        }
        return result
    }
    function calendarDayBuckets(sessions, history, showHistory, showAllDevices, deviceId) {
        const showAll = !!showAllDevices
        const scopeId = String(deviceId || "")
        function inScope(item) {
            return showAll || !!(item && item.device_id === scopeId)
        }
        const finished = {}
        const list = sessions || []
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (!item || !item.id)
                continue
            const status = String(item.status || "")
            if (status === "done" || status === "error" || status === "skipped")
                finished[item.id] = true
        }
        const byDate = {}
        function push(item) {
            const key = String((item && item.observing_date) || "")
            if (!key)
                return
            let bucket = byDate[key]
            if (!bucket) {
                bucket = []
                byDate[key] = bucket
            }
            bucket.push(item)
        }
        for (let i = 0; i < list.length; i++) {
            const item = list[i]
            if (item && inScope(item))
                push(item)
        }
        if (showHistory) {
            const rows = history || []
            for (let i = 0; i < rows.length; i++) {
                const item = rows[i]
                if (!item || !item.from_history || !item.observing_date || !Number(item.start_epoch_ms || 0))
                    continue
                if (!inScope(item))
                    continue
                if (item.session_id && finished[item.session_id])
                    continue
                push(item)
            }
        }
        const keys = Object.keys(byDate)
        for (let k = 0; k < keys.length; k++) {
            byDate[keys[k]].sort(function(a, b) {
                return Number(a.start_epoch_ms || 0) - Number(b.start_epoch_ms || 0)
            })
        }
        return byDate
    }
    function calendarEntriesForKeys(buckets, keys) {
        const map = buckets || {}
        const list = keys || []
        const items = []
        for (let i = 0; i < list.length; i++) {
            const bucket = map[list[i]]
            if (!bucket)
                continue
            for (let j = 0; j < bucket.length; j++)
                items.push(bucket[j])
        }
        items.sort(function(a, b) {
            const da = String(a.observing_date || "")
            const db = String(b.observing_date || "")
            if (da !== db)
                return da < db ? -1 : 1
            return Number(a.start_epoch_ms || 0) - Number(b.start_epoch_ms || 0)
        })
        return items
    }
    function calendarBucketCount(buckets, prefix) {
        const map = buckets || {}
        const keys = Object.keys(map)
        const head = String(prefix || "")
        let total = 0
        for (let i = 0; i < keys.length; i++) {
            if (head && String(keys[i]).indexOf(head) !== 0)
                continue
            const bucket = map[keys[i]]
            total += bucket ? bucket.length : 0
        }
        return total
    }
    function calendarPlannedCount(buckets) {
        const map = buckets || {}
        const keys = Object.keys(map)
        let planned = 0
        for (let i = 0; i < keys.length; i++) {
            const bucket = map[keys[i]] || []
            for (let j = 0; j < bucket.length; j++) {
                const item = bucket[j]
                if (item && !item.from_history && String(item.status || "") === "planned")
                    planned += 1
            }
        }
        return planned
    }
}
