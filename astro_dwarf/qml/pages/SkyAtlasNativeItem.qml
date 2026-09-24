import QtQuick
import QtWebView

Item {
    id: root
    anchors.fill: parent
    property bool shown: true
    signal loadState(string state)
    signal hostTitle(string title)

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
        url: backend.skyAtlasUrl
        onTitleChanged: root.hostTitle(view.title)

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
