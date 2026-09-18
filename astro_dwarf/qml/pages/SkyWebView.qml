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
    signal contextMenuRequested(real x, real y)
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
            if (status === "locked" || status === "view")
                map.readSelectedTarget()
            if (typeof callback === "function")
                callback(result)
        })
    }
    function readSelectedTarget(callback) {
        map.runJavaScript(backend.skyWebHarvestScript, result => {
            const target = map.parseHarvest(result)
            map.hasSelectedTarget = !!target
            if (target) {
                map.selectedTarget = target
                map.selectedKey = target.name + "|" + Number(target.ra_hours).toFixed(5) + "|"
                                  + Number(target.dec_degrees).toFixed(5)
                backend.setSkyMapTarget(target.name, Number(target.ra_hours), Number(target.dec_degrees))
            }
            if (typeof callback === "function")
                callback(result)
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
    function applyFovOverlay() {
        if (!map.pageReady)
            return
        map.readSelectedTarget(raw => {
            const script = backend.skyWebFovScript(
                map.overlayPayload(raw),
                map.mosaicColumns,
                map.mosaicRows,
                map.mosaicOverlap,
                String(Theme.accent),
                map.mosaicPa
            )
            map.runJavaScript(script, result => {
                const status = String(result || "")
                const overlayFov = (backend.previewStacking || backend.previewResult)
                    ? backend.skyFovText
                    : ((map.mosaicColumns > 1 || map.mosaicRows > 1)
                        ? backend.mosaicFovText
                        : backend.skyFovText)
                if (status === "panes" || status === "center" || status === "grid" || status === "hidden")
                    map.overlayKey = [
                        map.mosaicColumns,
                        map.mosaicRows,
                        map.mosaicOverlap,
                        map.mosaicPa,
                        overlayFov,
                        backend.mosaicSouthUp ? "S" : "N",
                        String(Theme.accent),
                        map.liveOverlay ? "live" : "off",
                        Number((backend.mosaicPreview && backend.mosaicPreview.live_pane) || 0),
                        Object.keys(backend.skyMosaicPaneUrls || {}).join(","),
                        status
                    ].join("|")
                if (map.liveOverlay)
                    map.applyLiveOverlay()
                map.applyMosaicPaneImages()
            })
        })
    }
    function applyLiveOverlay() {
        if (!map.pageReady)
            return
        if (!map.liveOverlay) {
            map.runJavaScript(backend.skyWebLiveScript("", false, map.liveOpacity, 0))
            return
        }
        map.runJavaScript(backend.skyWebLiveScript(
            backend.skyLiveFrameDataUrl(map.liveCamera),
            true,
            map.liveOpacity,
            Number((backend.mosaicPreview && backend.mosaicPreview.live_pane) || 0)
        ))
    }
    function applyMosaicPaneImages() {
        if (!map.pageReady)
            return
        map.runJavaScript(backend.skyWebPaneScript(backend.skyMosaicPaneUrls))
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
    function viewsClose(a, b) {
        const yaw = Number(a && a.yaw)
        const pitch = Number(a && a.pitch)
        const otherYaw = Number(b && b.yaw)
        const otherPitch = Number(b && b.pitch)
        if (isFinite(yaw) && isFinite(pitch) && isFinite(otherYaw) && isFinite(otherPitch)) {
            const dYaw = Math.min(
                Math.abs(yaw - otherYaw),
                Math.abs(Math.abs(yaw - otherYaw) - 2 * Math.PI)
            )
            if (dYaw < 0.05 && Math.abs(pitch - otherPitch) < 0.05)
                return true
        }
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
        return sep < 2.5
    }
    function restoreSavedView() {
        if (!map.pageReady || map.viewRestored || !map.savedViewReady)
            return
        if (!map.hasSavedView()) {
            map.viewRestored = true
            map.persistView = true
            return
        }
        if (map.appliedSiteKey !== backend.skyWebSiteScript)
            return
        if (!map.restoreStartedAt)
            map.restoreStartedAt = Date.now()
        map.runJavaScript(backend.skyWebViewScript(map.savedView))
    }
    function pollView() {
        if (!map.pageReady)
            return
        map.runJavaScript(backend.skyWebViewPollScript, result => {
            const text = String(result || "").trim()
            if (!text || text === "undefined" || text === "null")
                return
            try {
                const data = JSON.parse(text)
                if (!isFinite(Number(data.ra_hours)) || !isFinite(Number(data.dec_degrees)))
                    return
                map.liveView = data
                map.runJavaScript(backend.skyWebViewPosScript(Number(data.ra_hours), Number(data.dec_degrees)))
                if (map.holdView)
                    return
                if (!map.savedViewReady)
                    return
                if (!map.hasSavedView()) {
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
                if (map.persistView)
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
    onPageReadyChanged: {
        if (!map.pageReady) {
            map.hasSelectedTarget = false
            map.selectedTarget = ({})
            map.selectedKey = ""
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
        running: map.documentReady && !map.initialLoadFailed
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
        running: map.pageReady && map.appliedSiteKey !== backend.skyWebSiteScript
        onTriggered: map.applyObservingSite()
    }

    Timer {
        interval: 700
        repeat: true
        running: map.pageReady
        onTriggered: map.applyFovOverlay()
    }

    Timer {
        interval: 120
        repeat: true
        running: map.pageReady && map.liveOverlay
        onTriggered: map.applyLiveOverlay()
    }

    Timer {
        interval: 80
        repeat: true
        running: map.pageReady
        onTriggered: {
            map.pollContextMenu()
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
        running: map.pageReady && map.savedViewReady && !map.viewRestored && map.hasSavedView() && !map.holdView
        onTriggered: map.restoreSavedView()
    }

    Timer {
        interval: 120
        repeat: true
        running: map.pageReady
        onTriggered: map.pollView()
    }
}
