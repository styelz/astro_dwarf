import QtQuick
import QtWebEngine

Item {
    id: root
    anchors.fill: parent
    signal loadState(string state)
    property bool shown: true
    property int abortCount: 0
    signal hostTitle(string title)
    signal contextMenuAt(real x, real y)

    function runJavaScript(script, callback) {
        view.runJavaScript(script, callback)
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        url: backend.stellariumWebUrl
        // Hiding the sky page recommends Discarded, which unloads the document.
        lifecycleState: WebEngineView.LifecycleState.Active
        onTitleChanged: root.hostTitle(view.title)
        profile: skyProfile
        settings.webGLEnabled: true
        settings.localStorageEnabled: true
        settings.javascriptEnabled: true
        settings.javascriptCanOpenWindows: true
        settings.javascriptCanAccessClipboard: true
        settings.pluginsEnabled: true
        settings.autoLoadImages: true
        settings.localContentCanAccessRemoteUrls: true
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
        // Stellarium's WebGL canvas often never emits a DOM contextmenu on
        // Linux once this request is accepted. The HUD menu has to open here.
        // Aladin still gets the DOM event, so its engine item stays on that path.
        onContextMenuRequested: function(request) {
            request.accepted = true
            root.contextMenuAt(Number(request.x) || 0, Number(request.y) || 0)
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
        profile: skyProfile
    }

    WebEngineProfile {
        id: skyProfile
        storageName: "stellarium-web"
        offTheRecord: false
        persistentCookiesPolicy: WebEngineProfile.ForcePersistentCookies
        httpCacheType: WebEngineProfile.DiskHttpCache
    }
}
