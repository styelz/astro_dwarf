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
    property int mosaicColumns: 1
    property int mosaicRows: 1
    property real mosaicOverlap: 0.2
    property real mosaicPa: 0
    property string overlayKey: ""
    readonly property string appReadyScript: "(function(){try{var stel=window._stel;if(!stel||!stel.core||!stel.observer)return\"loading\";var app=document.getElementById(\"app\");if(!app||!app.__vue_app__)return\"loading\";return\"ok\"}catch(e){return\"loading\"}})()"
    readonly property var engineItem: engineLoader.item

    function harvestLooksSelected(raw) {
        if (raw === undefined || raw === null || raw === false)
            return false
        let data = raw
        if (typeof raw === "string") {
            const text = raw.trim()
            if (text === "" || text === "undefined" || text === "null")
                return false
            try {
                data = JSON.parse(text)
            } catch (err) {
                return false
            }
        }
        if (typeof data !== "object" || data === null)
            return false
        if (data.error)
            return false
        const ra = Number(data.ra_hours)
        const dec = Number(data.dec_degrees)
        return isFinite(ra) && isFinite(dec)
    }
    function runJavaScript(script, callback) {
        const view = map.engineItem
        if (!view || typeof view.runJavaScript !== "function")
            return
        view.runJavaScript(script, callback)
    }
    function readSelectedTarget(callback) {
        map.runJavaScript(backend.skyWebHarvestScript, result => {
            map.hasSelectedTarget = map.harvestLooksSelected(result)
            if (typeof callback === "function")
                callback(result)
        })
    }
    function applyObservingSite() {
        if (!map.pageReady)
            return
        const script = backend.skyWebSiteScript
        map.runJavaScript(script, result => {
            if (String(result) === "ok")
                map.appliedSiteKey = script
        })
    }
    function applyFovOverlay() {
        if (!map.pageReady)
            return
        map.readSelectedTarget(raw => {
            const script = backend.skyWebFovScript(
                raw,
                map.mosaicColumns,
                map.mosaicRows,
                map.mosaicOverlap,
                String(Theme.accent),
                map.mosaicPa
            )
            map.runJavaScript(script, result => {
                const status = String(result || "")
                if (status === "panes" || status === "center" || status === "grid" || status === "hidden")
                    map.overlayKey = [
                        map.mosaicColumns,
                        map.mosaicRows,
                        map.mosaicOverlap,
                        map.mosaicPa,
                        backend.mosaicFovText,
                        backend.mosaicSouthUp ? "S" : "N",
                        String(Theme.accent),
                        status
                    ].join("|")
            })
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
        map.applyFovOverlay()
        if (!map.initialLoadDone && !revealDelay.running)
            revealDelay.start()
    }
    function probeAppReady() {
        if (map.initialLoadDone || map.initialLoadFailed || !map.documentReady)
            return
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
            map.initialLoadFailed = true
        }
    }
    onMosaicColumnsChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicRowsChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicOverlapChanged: if (map.pageReady) map.applyFovOverlay()
    onMosaicPaChanged: if (map.pageReady) map.applyFovOverlay()
    onPageReadyChanged: if (!map.pageReady) map.hasSelectedTarget = false

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
        }
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
}
