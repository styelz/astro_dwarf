import QtQuick
import QtWebView

Item {
    id: root
    anchors.fill: parent
    signal loadState(string state)

    function runJavaScript(script, callback) {
        if (typeof view.runJavaScript !== "function")
            return
        if (typeof callback === "function")
            view.runJavaScript(script, callback)
        else
            view.runJavaScript(script)
    }

    WebView {
        id: view
        anchors.fill: parent
        url: backend.stellariumWebUrl

        onLoadingChanged: function(loadRequest) {
            if (!loadRequest || loadRequest.status === undefined)
                return
            if (loadRequest.status === WebView.LoadStartedStatus)
                root.loadState("started")
            else if (loadRequest.status === WebView.LoadSucceededStatus)
                root.loadState("succeeded")
            else if (loadRequest.status === WebView.LoadFailedStatus)
                root.loadState("failed")
        }
    }
}
