import QtWebView

WebView {
    id: view
    anchors.fill: parent
    url: backend.stellariumWebUrl
    signal loadState(string state)

    onLoadingChanged: function(loadRequest) {
        if (!loadRequest || loadRequest.status === undefined)
            return
        if (loadRequest.status === WebView.LoadStartedStatus)
            view.loadState("started")
        else if (loadRequest.status === WebView.LoadSucceededStatus)
            view.loadState("succeeded")
        else if (loadRequest.status === WebView.LoadFailedStatus)
            view.loadState("failed")
    }
}
