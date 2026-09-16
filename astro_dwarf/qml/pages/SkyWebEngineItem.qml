import QtQuick
import QtCore
import QtWebEngine

Item {
    id: root
    anchors.fill: parent
    signal loadState(string state)

    function runJavaScript(script, callback) {
        view.runJavaScript(script, callback)
    }

    WebEngineView {
        id: view
        anchors.fill: parent
        url: backend.stellariumWebUrl
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
        persistentStoragePath: StandardPaths.writableLocation(StandardPaths.AppDataLocation) + "/webengine"
        cachePath: StandardPaths.writableLocation(StandardPaths.CacheLocation) + "/webengine"
        Component.onCompleted: {
            try {
                userScripts.collection = [{
                    name: "astro-dwarf-sky-boot",
                    injectionPoint: WebEngineScript.DocumentReady,
                    worldId: WebEngineScript.MainWorld,
                    sourceCode: backend.skyWebBootScript,
                    runsOnSubFrames: false
                }]
            } catch (err) {
            }
        }
    }
}
