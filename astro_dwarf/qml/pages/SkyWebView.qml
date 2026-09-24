import QtQuick
import ".."

Item {
    id: map
    anchors.fill: parent
    property string appliedSiteKey: ""
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
    readonly property string appReadyScript: "(function(){try{var stel=window._stel;if(!stel||!stel.core||!stel.observer)return\"loading\";var app=document.getElementById(\"app\");if(!app||!app.__vue_app__)return\"loading\";return\"ok\"}catch(e){return\"loading\"}})()"
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
        map.runJavaScript(backend.skyWebPinTargetScript(payload || ({})))
    }
    function runJavaScript(script, callback) {
        const view = map.engineItem
        if (!view || typeof view.runJavaScript !== "function")
            return
        view.runJavaScript(script, callback)
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
    function setView(raHours, decDegrees) {
        if (!map.pageReady)
            return "loading"
        map.beginViewHold()
        map.runJavaScript(backend.skyWebCenterViewScript(Number(raHours), Number(decDegrees)))
        return "ok"
    }
    function lockTarget(payload, callback) {
        if (!map.pageReady) {
            if (typeof callback === "function")
                callback(JSON.stringify({status: "loading"}))
            return
        }
        map.beginViewHold()
        map.runJavaScript(backend.skyWebLockTargetScript(payload || ({})), result => {
            const text = String(result || "").trim()
            let status = ""
            try {
                const data = JSON.parse(text)
                status = String((data && data.status) || "")
            } catch (err) {
            }
            if (status === "locked" || status === "view") {
                map.readSelectedTarget(raw => {
                    if (!map.parseHarvest(raw))
                        map.applyCoordinateTarget(payload || ({}))
                })
            }
            if (typeof callback === "function")
                callback(result)
        })
    }
    function readSelectedTarget(callback) {
        map.runJavaScript(backend.skyWebHarvestScript, result => {
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
    function applyObservingSite() {
        if (!map.pageReady)
            return
        const script = backend.skyWebSiteScript
        map.runJavaScript(script, result => {
            if (String(result) !== "ok")
                return
            map.appliedSiteKey = script
            if (!map.viewRestored)
                map.restoreSavedView()
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
        const viewPart = grid && isFinite(ra) && isFinite(dec)
            ? ra.toFixed(3) + "," + dec.toFixed(2)
            : ""
        const overlayFov = grid ? backend.mosaicFovText : backend.skyFovText
        return [
            map.selectedKey,
            viewPart,
            map.mosaicColumns,
            map.mosaicRows,
            Number(map.mosaicOverlap).toFixed(3),
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
        map.readSelectedTarget(raw => {
            if (!map.shown)
                return
            const script = backend.skyWebFovScript(
                map.overlayPayload(raw),
                map.mosaicColumns,
                map.mosaicRows,
                map.mosaicOverlap,
                String(Theme.fov),
                map.mosaicPa
            )
            map.runJavaScript(script, result => {
                const status = String(result || "")
                if (status === "panes" || status === "center" || status === "grid" || status === "hidden") {
                    map.fovEngineReady = true
                    map.fovPushKey = map.fovInputKey()
                    map.overlayKey = map.fovPushKey + "|" + status
                }
                if (map.liveOverlay)
                    map.applyLiveOverlay()
                map.applyMosaicPaneImages()
            })
        })
    }
    function applyLiveOverlay() {
        if (!map.pageReady || !map.shown)
            return
        if (!map.liveOverlay) {
            if (map.liveInjectedKey === "off")
                return
            map.liveInjectedKey = "off"
            map.runJavaScript(backend.skyWebLiveScript("", false, map.liveOpacity, 0))
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
        map.runJavaScript(backend.skyWebLiveScript(url, true, map.liveOpacity, pane))
    }
    function applyMosaicPaneImages() {
        if (!map.pageReady || !map.shown)
            return
        const key = Object.keys(backend.skyMosaicPaneUrls || {}).join(",")
        if (key === map.paneInjectedKey)
            return
        map.paneInjectedKey = key
        map.runJavaScript(backend.skyWebPaneScript(backend.skyMosaicPaneUrls))
    }
    function pauseSkyEngine() {
        map.runJavaScript("(function(){var c=window.__astroDwarfFovCtl;if(!c)return \"\";c.paused=true;if(c.raf){cancelAnimationFrame(c.raf);c.raf=0}if(c.timer){clearTimeout(c.timer);c.timer=0}return \"ok\"})()")
    }
    function resumeSkyEngine() {
        map.runJavaScript("(function(){var c=window.__astroDwarfFovCtl;if(!c)return \"\";c.paused=false;if(typeof c.tick===\"function\")c.tick();return \"ok\"})()")
    }
    function pointingMoved(previous, data) {
        const ra = Number(data && data.ra_hours)
        const dec = Number(data && data.dec_degrees)
        const prevRa = Number(previous && previous.ra_hours)
        const prevDec = Number(previous && previous.dec_degrees)
        if (!isFinite(prevRa) || !isFinite(prevDec))
            return true
        if (Math.abs(prevRa - ra) > 0.0008 || Math.abs(prevDec - dec) > 0.008)
            return true
        const fov = Number(data && data.fov)
        const prevFov = Number(previous && previous.fov)
        if (isFinite(fov) && isFinite(prevFov) && Math.abs(fov - prevFov) > 0.05)
            return true
        const az = Number(data && data.az)
        const prevAz = Number(previous && previous.az)
        if (isFinite(az) && isFinite(prevAz) && Math.abs(az - prevAz) > 0.6)
            return true
        const alt = Number(data && data.alt)
        const prevAlt = Number(previous && previous.alt)
        if (isFinite(alt) && isFinite(prevAlt) && Math.abs(alt - prevAlt) > 0.6)
            return true
        return false
    }
    function handleHostTitle(title) {
        const text = String(title || "")
        const marker = "astro-dwarf-host:"
        if (text.indexOf(marker) !== 0)
            return
        const parts = text.slice(marker.length).split("\t")
        if (parts[0] !== "menu")
            return
        map.contextMenuRequested(Number(parts[1]) || 0, Number(parts[2]) || 0)
        const token = JSON.stringify(text)
        map.runJavaScript("(function(){var t=" + token
            + ";if(document.title===t){var h=window.__astroDwarfHostTitle;document.title=h==null?\"\":String(h)}return\"\"})()")
    }
    function pollContextMenu() {
        map.runJavaScript(backend.skyWebContextPollScript, result => {
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
        map.runJavaScript(backend.skyWebDismissPollScript, result => {
            if (String(result || "").trim() === "dismiss")
                map.menuDismissRequested()
        })
    }
    function pollTrackRequest() {
        map.runJavaScript(backend.skyWebDblclickPollScript, result => {
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
        let place = false
        if (isFinite(ra) && isFinite(dec) && isFinite(otherRa) && isFinite(otherDec)) {
            const d1 = dec * Math.PI / 180
            const d2 = otherDec * Math.PI / 180
            const r1 = ra * Math.PI / 12
            const r2 = otherRa * Math.PI / 12
            const sep = Math.acos(Math.max(-1, Math.min(1,
                Math.sin(d1) * Math.sin(d2) + Math.cos(d1) * Math.cos(d2) * Math.cos(r1 - r2)
            ))) * 180 / Math.PI
            place = sep < 2.5
        } else {
            const yaw = Number(a && a.yaw)
            const pitch = Number(a && a.pitch)
            const otherYaw = Number(b && b.yaw)
            const otherPitch = Number(b && b.pitch)
            if (!isFinite(yaw) || !isFinite(pitch) || !isFinite(otherYaw) || !isFinite(otherPitch))
                return false
            const dYaw = Math.min(
                Math.abs(yaw - otherYaw),
                Math.abs(Math.abs(yaw - otherYaw) - 2 * Math.PI)
            )
            place = dYaw < 0.05 && Math.abs(pitch - otherPitch) < 0.05
        }
        return place && map.fovClose(a, b)
    }
    function restoreSavedView() {
        if (!map.pageReady || map.viewRestored || !map.savedViewReady)
            return
        if (!map.hasSavedView())
            return
        if (map.appliedSiteKey !== backend.skyWebSiteScript)
            return
        if (!map.restoreStartedAt)
            map.restoreStartedAt = Date.now()
        map.runJavaScript(backend.skyWebViewScript(map.savedView))
    }
    function pollView() {
        if (!map.pageReady || !map.shown)
            return
        map.runJavaScript(backend.skyWebViewPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            try {
                const data = JSON.parse(text)
                if (!isFinite(Number(data.ra_hours)) || !isFinite(Number(data.dec_degrees)))
                    return
                const moved = map.pointingMoved(map.liveView, data)
                if (moved)
                    map.liveView = data
                if (map.holdView)
                    return
                if (!map.savedViewReady)
                    return
                if (map.appliedSiteKey !== backend.skyWebSiteScript)
                    return
                if (!map.hasSavedView()) {
                    const fov = Number(data.fov)
                    const home = Number(backend.skyMapFovDeg)
                    if (!(fov > 0) || Math.abs(fov - home) > Math.max(0.6, home * 0.04)) {
                        map.runJavaScript(backend.skyWebViewScript({fov: home}))
                        return
                    }
                    map.viewRestored = true
                    map.persistView = true
                    map.viewChanged(data)
                    return
                }
                if (!map.viewRestored) {
                    if (map.viewMatchesSaved(data)) {
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
                if (map.persistView && moved)
                    map.viewChanged(data)
            } catch (err) {
            }
        })
    }
    function pollLiveOpacity() {
        map.runJavaScript(backend.skyWebOpacityPollScript, result => {
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
        map.runJavaScript(backend.skyWebBootScript)
    }
    function probeAppReady() {
        if (map.initialLoadDone || map.initialLoadFailed || !map.documentReady)
            return
        map.applyBootFixes()
        map.runJavaScript(map.appReadyScript, result => {
            if (String(result) === "ok")
                map.markInitialReady()
        })
    }
    function handleLoadState(state) {
        if (state === "started") {
            if (map.initialLoadDone)
                return
            map.pageReady = false
            map.documentReady = false
            map.appliedSiteKey = ""
            map.overlayKey = ""
            map.fovPushKey = ""
            map.fovEngineReady = false
            map.paneInjectedKey = ""
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
            map.viewRestored = false
            map.persistView = false
            map.restoreStartedAt = 0
            map.restoreHoldView = ({})
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
    onShownChanged: {
        if (!map.pageReady)
            return
        if (map.shown) {
            map.fovPushKey = ""
            map.resumeSkyEngine()
            map.applyFovOverlay()
            map.pollView()
        } else {
            map.pauseSkyEngine()
        }
    }
    onPageReadyChanged: {
        if (!map.pageReady) {
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
            map.liveInjectedKey = ""
            map.fovPushKey = ""
            map.fovEngineReady = false
            map.paneInjectedKey = ""
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
        source: Qt.resolvedUrl(Qt.platform.os === "linux" ? "SkyWebEngineItem.qml" : "SkyWebNativeItem.qml")
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
        function onContextMenuAt(x, y) {
            map.contextMenuRequested(Number(x) || 0, Number(y) || 0)
        }
    }

    Timer {
        id: revealDelay
        interval: 600
        repeat: false
        onTriggered: {
            map.initialLoadDone = true
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
        interval: 1200
        repeat: true
        running: map.pageReady && map.shown && map.appliedSiteKey !== backend.skyWebSiteScript
        onTriggered: map.applyObservingSite()
    }

    Timer {
        interval: 1000
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.readSelectedTarget()
    }

    Timer {
        interval: 1000
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.applyFovOverlay()
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
        interval: 300
        repeat: true
        running: map.pageReady && map.shown
        onTriggered: map.pollView()
    }
}
