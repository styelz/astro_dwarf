import QtQuick
import ".."

Item {
    id: map
    anchors.fill: parent
    property string appliedSiteKey: ""
    property bool homeDone: false
    property bool homePending: false
    property bool pageReady: false
    property bool documentReady: false
    property bool initialLoadDone: false
    property bool initialLoadFailed: false
    property bool hasSelectedTarget: false
    property var selectedTarget: ({})
    property string selectedKey: ""
    property int mosaicColumns: 1
    property int mosaicRows: 1
    property real mosaicOverlap: 0.2
    property real mosaicPa: 0
    property bool liveOverlay: false
    property real liveOpacity: 0.65
    property var savedView: ({})
    property bool savedViewReady: false
    property var liveView: ({})
    property bool viewRestored: false
    property bool persistView: false
    property bool holdView: false
    property double restoreStartedAt: 0
    property var restoreHoldView: ({})
    signal liveOpacityNudged(real opacity)
    signal viewChanged(var data)
    readonly property string liveCamera: (backend.previewStacking || backend.previewResult)
        ? "tele"
        : (backend.selectedDevice.camera === "wide" ? "wide" : "tele")
    onLiveCameraChanged: if (map.pageReady) map.applyFovOverlay()
    property string overlayKey: ""
    property string fovPushKey: ""
    property bool fovEngineReady: false
    property string liveInjectedKey: ""
    property string paneInjectedKey: ""
    property bool shown: true
    signal contextMenuRequested(real x, real y)
    signal menuDismissRequested()
    signal trackRequested()
    readonly property var engineItem: engineLoader.item

    function harvestLooksSelected(raw) {
        return !!map.parseHarvest(raw)
    }
    function parseHarvest(raw) {
        if (raw === undefined || raw === null || raw === false)
            return null
        let data = raw
        if (typeof raw === "string") {
            const text = raw.trim()
            if (text === "" || text === "undefined" || text === "null")
                return null
            try {
                data = JSON.parse(text)
            } catch (err) {
                return null
            }
        }
        if (typeof data !== "object" || data === null)
            return null
        if (data.error)
            return null
        const ra = Number(data.ra_hours)
        const dec = Number(data.dec_degrees)
        if (!isFinite(ra) || !isFinite(dec))
            return null
        return {
            name: String(data.name || "").trim(),
            ra_hours: ra,
            dec_degrees: dec
        }
    }
    function applyCoordinateTarget(payload) {
        const data = payload || ({})
        const ra = Number(data.ra_hours)
        const dec = Number(data.dec_degrees)
        if (!isFinite(ra) || !isFinite(dec))
            return false
        const name = String(data.name || "").trim() || ("RA " + ra.toFixed(3) + "h  DEC "
                     + (dec >= 0 ? "+" : "") + dec.toFixed(3) + "°")
        map.hasSelectedTarget = true
        map.selectedTarget = { name: name, ra_hours: ra, dec_degrees: dec }
        map.selectedKey = name + "|" + ra.toFixed(5) + "|" + dec.toFixed(5)
        backend.setSkyMapTarget(name, ra, dec)
        return true
    }
    function coordinateHarvest(result) {
        if (map.parseHarvest(result))
            return result
        const selected = map.selectedTarget || ({})
        const ra = Number(selected.ra_hours)
        const dec = Number(selected.dec_degrees)
        if (!map.hasSelectedTarget || !isFinite(ra) || !isFinite(dec))
            return result
        return JSON.stringify({
            name: String(selected.name || "").trim() || "FOV centre",
            ra_hours: ra,
            dec_degrees: dec
        })
    }
    function pinCoordinateTarget(payload) {
        map.runJavaScript(backend.skyAtlasPinTargetScript(payload || ({})))
    }
    function runJavaScript(script, callback) {
        const view = map.engineItem
        if (!view || typeof view.runJavaScript !== "function")
            return
        view.runJavaScript(script, callback)
    }
    function setView(raHours, decDegrees) {
        map.beginViewHold()
        map.runJavaScript(backend.skyAtlasViewPosScript(Number(raHours), Number(decDegrees)))
        return "ok"
    }
    function beginViewHold() {
        map.holdView = true
        map.viewRestored = true
        map.persistView = false
        viewHoldTimer.restart()
    }
    function endViewHold() {
        map.holdView = false
        map.persistView = true
    }
    function lockTarget(payload, callback) {
        if (!map.pageReady) {
            if (typeof callback === "function")
                callback(JSON.stringify({status: "loading"}))
            return
        }
        map.beginViewHold()
        map.runJavaScript(backend.skyAtlasLockTargetScript(payload || ({})), result => {
            const text = String(result || "").trim()
            let status = ""
            try {
                const data = JSON.parse(text)
                status = String((data && data.status) || "")
            } catch (err) {
            }
            if (status === "locked" || status === "view")
                map.readSelectedTarget()
            if (typeof callback === "function")
                callback(result)
        })
    }
    function readSelectedTarget(callback) {
        map.runJavaScript(backend.skyAtlasHarvestScript, result => {
            const target = map.parseHarvest(result)
            const previous = map.selectedKey
            if (target) {
                const key = target.name + "|" + Number(target.ra_hours).toFixed(5) + "|"
                            + Number(target.dec_degrees).toFixed(5)
                if (key !== map.selectedKey) {
                    map.hasSelectedTarget = true
                    map.selectedTarget = target
                    map.selectedKey = key
                    backend.setSkyMapTarget(target.name, Number(target.ra_hours), Number(target.dec_degrees))
                }
            }
            if (typeof callback === "function")
                callback(map.coordinateHarvest(result))
            else if (map.selectedKey !== previous)
                map.applyFovOverlay()
        })
    }
    function viewForOverlay() {
        const live = map.liveView || {}
        if (isFinite(Number(live.ra_hours)) && isFinite(Number(live.dec_degrees)))
            return live
        const saved = map.savedView || {}
        if (isFinite(Number(saved.ra_hours)) && isFinite(Number(saved.dec_degrees)))
            return saved
        return ({})
    }
    function overlayPayload(raw) {
        let data = {}
        if (typeof raw === "string") {
            const text = raw.trim()
            if (text && text !== "undefined" && text !== "null") {
                try { data = JSON.parse(text) || {} } catch (err) { data = {} }
            }
        } else if (raw && typeof raw === "object") {
            data = raw
        }
        if (data.error)
            data = {}
        const view = map.viewForOverlay()
        const ra = Number(view.ra_hours)
        const dec = Number(view.dec_degrees)
        if (isFinite(ra) && isFinite(dec)) {
            data = Object.assign({}, data, {
                view_ra_hours: ra,
                view_dec_degrees: dec
            })
        }
        return data
    }
    function fovInputKey() {
        const grid = map.mosaicColumns > 1 || map.mosaicRows > 1
        const view = grid ? map.viewForOverlay() : ({})
        const ra = Number(view.ra_hours)
        const dec = Number(view.dec_degrees)
        const viewPart = grid && !map.selectedKey && isFinite(ra) && isFinite(dec)
            ? ra.toFixed(3) + "," + dec.toFixed(2)
            : ""
        const capturing = String((backend.mosaicPreview && backend.mosaicPreview.phase) || "") !== ""
        const overlayFov = (grid && capturing) ? backend.mosaicFovText : backend.skyFovText
        return [
            map.selectedKey,
            viewPart,
            map.mosaicColumns,
            map.mosaicRows,
            Number(map.mosaicOverlap).toFixed(3),
            backend.mosaicMode,
            backend.deviceMosaicHorizontal,
            backend.deviceMosaicVertical,
            Number(map.mosaicPa).toFixed(1),
            overlayFov,
            backend.mosaicPaChip,
            backend.mosaicPaSource,
            String(Theme.fov),
            map.liveOverlay ? "live" : "off",
            Number((backend.mosaicPreview && backend.mosaicPreview.live_pane) || 0),
            Object.keys(backend.skyMosaicPaneUrls || {}).join(",")
        ].join("|")
    }
    function applyFovOverlay() {
        if (!map.pageReady || !map.shown)
            return
        const key = map.fovInputKey()
        if (map.fovEngineReady && key === map.fovPushKey)
            return
        const sent = key
        const payload = map.overlayPayload(map.selectedTarget || ({}))
        const script = map.fovEngineReady
            ? backend.skyAtlasFovUpdateScript(
                payload, map.mosaicColumns, map.mosaicRows, map.mosaicOverlap, String(Theme.fov), map.mosaicPa)
            : backend.skyAtlasFovScript(
                payload, map.mosaicColumns, map.mosaicRows, map.mosaicOverlap, String(Theme.fov), map.mosaicPa)
        map.runJavaScript(script, result => {
            if (map.fovInputKey() !== sent)
                return
            const status = String(result || "")
            if (status === "panes" || status === "center" || status === "grid" || status === "hidden") {
                map.fovEngineReady = true
                map.fovPushKey = sent
                map.overlayKey = sent + "|" + status
            }
            if (map.liveOverlay)
                map.applyLiveOverlay()
            map.applyMosaicPaneImages()
        })
    }
    function applyLiveOverlay() {
        if (!map.pageReady || !map.shown)
            return
        if (!map.liveOverlay) {
            if (map.liveInjectedKey === "off")
                return
            map.liveInjectedKey = "off"
            map.runJavaScript(backend.skyAtlasLiveScript("", false, map.liveOpacity, 0))
            return
        }
        const pane = Number((backend.mosaicPreview && backend.mosaicPreview.live_pane) || 0)
        // Opacity is applied in the page. Keeping it out of this key avoids
        // re-encoding the live frame and rebuilding every pane on each wheel notch.
        const key = [
            backend.skyLiveFrameRevision(map.liveCamera),
            pane
        ].join("|")
        if (key === map.liveInjectedKey)
            return
        const url = backend.skyLiveFrameDataUrl(map.liveCamera)
        if (!url)
            return
        map.liveInjectedKey = key
        map.runJavaScript(backend.skyAtlasLiveScript(url, true, map.liveOpacity, pane))
    }
    function applyMosaicPaneImages() {
        if (!map.pageReady || !map.shown)
            return
        const key = Object.keys(backend.skyMosaicPaneUrls || {}).join(",")
        if (key === map.paneInjectedKey)
            return
        map.paneInjectedKey = key
        map.runJavaScript(backend.skyAtlasPaneScript(backend.skyMosaicPaneUrls))
    }
    function openAtlasMenu(x, y) {
        if (!map.pageReady)
            return
        map.runJavaScript(backend.skyAtlasOpenMenuScript(Number(x) || 0, Number(y) || 0))
    }
    function handleHostTitle(title) {
        const text = String(title || "")
        const marker = "astro-dwarf-host:"
        if (text.indexOf(marker) !== 0)
            return
        const parts = text.slice(marker.length).split(/[\t| ]+/)
        if (parts[0] !== "menu")
            return
        map.contextMenuRequested(Number(parts[1]) || 0, Number(parts[2]) || 0)
        const token = JSON.stringify(text)
        map.runJavaScript("(function(){var t=" + token
            + ";if(document.title===t){var h=window.__astroDwarfHostTitle;document.title=h==null?\"\":String(h)}return\"\"})()")
    }
    function pollContextMenu() {
        map.runJavaScript(backend.skyAtlasContextPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            try {
                const data = JSON.parse(text)
                map.contextMenuRequested(Number(data.x) || 0, Number(data.y) || 0)
            } catch (err) {
            }
        })
    }
    function pollMenuDismiss() {
        map.runJavaScript(backend.skyAtlasDismissPollScript, result => {
            if (String(result || "").trim() === "dismiss")
                map.menuDismissRequested()
        })
    }
    function pollTrackRequest() {
        map.runJavaScript(backend.skyAtlasDblclickPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            map.trackRequested()
        })
    }
    function hasSavedView() {
        const view = map.savedView || {}
        return isFinite(Number(view.ra_hours)) && isFinite(Number(view.dec_degrees))
    }
    function viewMatchesSaved(data) {
        return map.viewsClose(data, map.savedView)
    }
    function fovClose(a, b) {
        const fov = Number(a && a.fov)
        const other = Number(b && b.fov)
        if (!(fov > 0) || !(other > 0))
            return true
        const scale = Math.max(fov, other)
        return Math.abs(fov - other) <= Math.max(0.6, scale * 0.04)
    }
    function viewsClose(a, b) {
        const ra = Number(a && a.ra_hours)
        const dec = Number(a && a.dec_degrees)
        const otherRa = Number(b && b.ra_hours)
        const otherDec = Number(b && b.dec_degrees)
        if (!isFinite(ra) || !isFinite(dec) || !isFinite(otherRa) || !isFinite(otherDec))
            return false
        const d1 = dec * Math.PI / 180
        const d2 = otherDec * Math.PI / 180
        const r1 = ra * Math.PI / 12
        const r2 = otherRa * Math.PI / 12
        const sep = Math.acos(Math.max(-1, Math.min(1,
            Math.sin(d1) * Math.sin(d2) + Math.cos(d1) * Math.cos(d2) * Math.cos(r1 - r2)
        ))) * 180 / Math.PI
        return sep < 2.5 && map.fovClose(a, b)
    }
    function applyObservingSite() {
        if (!map.pageReady)
            return
        const script = backend.skyAtlasSiteScript
        map.runJavaScript(script, result => {
            if (String(result) !== "ok")
                return
            map.appliedSiteKey = script
            if (!map.hasSavedView() && !map.homeDone)
                map.maybeHome()
            else if (map.viewRestored)
                map.runJavaScript(backend.skyAtlasBootScript)
        })
    }
    function maybeHome() {
        if (map.homeDone || map.homePending || map.hasSavedView() || map.holdView)
            return
        map.homePending = true
        map.runJavaScript(backend.skyAtlasHomeScript, result => {
            map.homePending = false
            const status = String(result || "")
            if (status === "no-site" || status === "error")
                map.homeDone = true
        })
    }
    function restoreSavedView() {
        if (!map.pageReady || map.viewRestored || !map.savedViewReady)
            return
        if (!map.hasSavedView()) {
            map.maybeHome()
            return
        }
        if (!map.restoreStartedAt)
            map.restoreStartedAt = Date.now()
        map.runJavaScript(backend.skyAtlasViewScript(map.savedView))
    }
    function pollView() {
        if (!map.pageReady || !map.shown)
            return
        map.runJavaScript(backend.skyAtlasViewPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            try {
                const data = JSON.parse(text)
                if (!isFinite(Number(data.ra_hours)) || !isFinite(Number(data.dec_degrees)))
                    return
                map.liveView = data
                if (map.holdView)
                    return
                if (!map.savedViewReady)
                    return
                if (!map.hasSavedView()) {
                    const fov = Number(data.fov)
                    const home = Number(backend.skyMapFovDeg)
                    const ready = fov > 0 && Math.abs(fov - home) <= Math.max(0.6, home * 0.04)
                    if (!ready && !map.homeDone) {
                        if (!map.holdView)
                            map.maybeHome()
                        return
                    }
                    map.homeDone = true
                    map.viewRestored = true
                    map.persistView = true
                    map.viewChanged(data)
                    return
                }
                if (!map.viewRestored) {
                    if (data.user_moved) {
                        map.viewRestored = true
                        map.persistView = true
                    } else if (map.viewMatchesSaved(data)) {
                        map.viewRestored = true
                        map.persistView = true
                    } else if (map.restoreStartedAt && Date.now() - map.restoreStartedAt > 12000) {
                        map.viewRestored = true
                        map.persistView = false
                        map.restoreHoldView = data
                    } else {
                        map.restoreSavedView()
                    }
                }
                if (map.viewRestored && !map.persistView && !map.viewsClose(data, map.restoreHoldView))
                    map.persistView = true
                if (map.persistView)
                    map.viewChanged(data)
            } catch (err) {
            }
        })
    }
    function pollLiveOpacity() {
        map.runJavaScript(backend.skyAtlasOpacityPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            try {
                const data = JSON.parse(text)
                const opacity = Number(data.opacity)
                if (!isFinite(opacity))
                    return
                map.liveOpacityNudged(opacity)
            } catch (err) {
            }
        })
    }
    function markInitialReady() {
        if (map.initialLoadFailed)
            return
        appReadyPoll.stop()
        bootTimeout.stop()
        map.documentReady = true
        map.pageReady = true
        map.initialLoadFailed = false
        map.applyObservingSite()
        map.pollView()
        map.applyFovOverlay()
        if (!map.initialLoadDone && !revealDelay.running)
            revealDelay.start()
    }
    function applyBootFixes() {
        map.runJavaScript(backend.skyAtlasBootScript)
    }
    function probeAppReady() {
        if (map.initialLoadDone || map.initialLoadFailed || !map.documentReady)
            return
        map.applyBootFixes()
        map.runJavaScript(backend.skyAtlasReadyScript, result => {
            if (String(result) === "ok")
                map.markInitialReady()
        })
    }
    function handleLoadState(state) {
        if (state === "started") {
            if (map.initialLoadDone || map.pageReady)
                return
            map.pageReady = false
            map.documentReady = false
            map.overlayKey = ""
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
            map.viewRestored = false
            map.persistView = false
            map.restoreStartedAt = 0
            map.restoreHoldView = ({})
            map.appliedSiteKey = ""
            map.homeDone = false
            map.homePending = false
            revealDelay.stop()
            return
        }
        if (state === "succeeded") {
            map.documentReady = true
            if (map.initialLoadDone) {
                map.pageReady = true
                map.applyFovOverlay()
                return
            }
            map.pageReady = false
            map.probeAppReady()
            return
        }
        if (state === "failed" && !map.initialLoadDone) {
            appReadyPoll.stop()
            bootTimeout.stop()
            revealDelay.stop()
            map.pageReady = false
            map.documentReady = false
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
            map.initialLoadFailed = true
        }
    }
    onMosaicColumnsChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicRowsChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicOverlapChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicPaChanged: if (map.pageReady) map.applyFovOverlay()
    onLiveOverlayChanged: if (map.pageReady) map.applyLiveOverlay()
    onLiveOpacityChanged: if (map.pageReady && map.liveOverlay) map.applyLiveOverlay()
    onPageReadyChanged: {
        if (!map.pageReady) {
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
            map.liveInjectedKey = ""
            return
        }
        if (map.liveOverlay)
            map.applyLiveOverlay()
    }

    Connections {
        target: backend
        function onSelectedDeviceChanged() {
            if (!map.pageReady)
                return
            map.applyObservingSite()
            map.applyFovOverlay()
            if (!map.viewRestored)
                map.restoreSavedView()
        }
        function onPreviewStackingChanged() {
            if (!map.pageReady)
                return
            map.applyFovOverlay()
            if (map.liveOverlay)
                map.applyLiveOverlay()
        }
        function onPreviewResultChanged() {
            if (!map.pageReady)
                return
            map.applyFovOverlay()
            if (map.liveOverlay)
                map.applyLiveOverlay()
        }
        function onMosaicPreviewChanged() {
            if (!map.pageReady)
                return
            map.applyFovOverlay()
            if (map.liveOverlay)
                map.applyLiveOverlay()
            map.applyMosaicPaneImages()
        }
    }

    Loader {
        id: engineLoader
        anchors.fill: parent
        source: Qt.resolvedUrl(Qt.platform.os === "linux" ? "SkyAtlasEngineItem.qml" : "SkyAtlasNativeItem.qml")
        onLoaded: {
            if (item)
                item.shown = Qt.binding(() => map.shown)
        }
        onStatusChanged: {
            if (status === Loader.Error && !map.initialLoadDone)
                map.initialLoadFailed = true
        }
    }

    Connections {
        target: map.engineItem
        function onLoadState(state) {
            map.handleLoadState(state)
        }
        function onHostTitle(title) {
            map.handleHostTitle(title)
        }
    }

    Timer {
        id: revealDelay
        interval: 600
        repeat: false
        onTriggered: {
            map.initialLoadDone = true
            map.pageReady = true
            map.applyFovOverlay()
            map.restoreSavedView()
        }
    }

    Timer {
        interval: 400
        repeat: true
        running: map.documentReady && map.shown && !map.initialLoadDone && !map.initialLoadFailed
        onTriggered: map.applyBootFixes()
    }

    Timer {
        id: appReadyPoll
        interval: 250
        repeat: true
        running: map.documentReady && !map.initialLoadDone && !map.initialLoadFailed
        onTriggered: map.probeAppReady()
    }

    Timer {
        id: bootTimeout
        interval: 15000
        repeat: false
        running: map.documentReady && !map.initialLoadDone && !map.initialLoadFailed
        onTriggered: map.markInitialReady()
    }

    Timer {
        interval: 1000
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.applyFovOverlay()
    }

    Timer {
        interval: 1000
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.readSelectedTarget()
    }

    Timer {
        interval: 250
        repeat: true
        running: map.pageReady && map.shown && map.liveOverlay
        onTriggered: map.applyLiveOverlay()
    }

    Timer {
        interval: 200
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: {
            map.pollContextMenu()
            map.pollMenuDismiss()
            map.pollTrackRequest()
            map.pollLiveOpacity()
        }
    }

    Timer {
        id: viewHoldTimer
        interval: 2500
        repeat: false
        onTriggered: map.endViewHold()
    }

    Timer {
        interval: 400
        repeat: true
        running: map.pageReady && map.shown && map.savedViewReady && !map.viewRestored && map.hasSavedView() && !map.holdView
        onTriggered: map.restoreSavedView()
    }

    Timer {
        interval: 800
        repeat: true
        running: map.pageReady && map.shown && map.appliedSiteKey !== backend.skyAtlasSiteScript
        onTriggered: map.applyObservingSite()
    }

    Timer {
        interval: 300
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.pollView()
    }
}
