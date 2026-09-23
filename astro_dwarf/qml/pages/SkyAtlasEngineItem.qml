import QtQuick
import QtWebEngine

Item {
    id: root
    anchors.fill: parent
    signal loadState(string state)
    property bool shown: true
    property int abortCount: 0

    function runJavaScript(script, callback) {
        view.runJavaScript(script, callback)
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        url: backend.skyAtlasUrl
        profile: atlasProfile
        settings.webGLEnabled: true
        settings.localStorageEnabled: true
        settings.javascriptEnabled: true
        settings.javascriptCanOpenWindows: true
        settings.javascriptCanAccessClipboard: true
        settings.pluginsEnabled: true
        settings.autoLoadImages: true
        settings.localContentCanAccessRemoteUrls: true
        settings.localContentCanAccessFileUrls: true
        settings.playbackRequiresUserGesture: false
        onLoadingChanged: function(loadRequest) {
            if (!loadRequest || loadRequest.status === undefined)
                return
            if (loadRequest.status === WebEngineView.LoadStartedStatus)
                root.loadState("started")
            else if (loadRequest.status === WebEngineView.LoadSucceededStatus)
                root.loadState("succeeded")
            else if (loadRequest.status === WebEngineView.LoadFailedStatus)
                root.loadState("failed")
        }
        onNewWindowRequested: function(request) {
            request.openIn(popupSink)
        }
        // The page's contextmenu listener hands the click to the HUD menu.
        // Accepting here stops Chromium's own menu from taking the gesture.
        onContextMenuRequested: function(request) {
            request.accepted = true
        }
        onJavaScriptDialogRequested: function(request) {
            request.accepted = true
            request.dialogAccept()
        }
        onPermissionRequested: function(permission) {
            try {
                permission.deny()
            } catch (err) {
            }
        }
        onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {
            const text = String(message || "")
            if (text.indexOf("Aborted") < 0)
                return
            root.abortCount += 1
            if (root.abortCount === 8)
                root.loadState("failed")
        }
    }

    WebEngineView {
        id: popupSink
        visible: false
        width: 1
        height: 1
        profile: atlasProfile
    }

    WebEngineProfile {
        id: atlasProfile
        storageName: "aladin-atlas"
        offTheRecord: false
        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
        httpCacheType: WebEngineProfile.DiskHttpCache
    }
}
