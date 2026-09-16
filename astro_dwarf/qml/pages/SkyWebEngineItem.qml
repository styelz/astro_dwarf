import QtWebEngine

WebEngineView {
    id: view
    anchors.fill: parent
    url: backend.stellariumWebUrl
    signal loadState(string state)

    onLoadingChanged: function(loadRequest) {
        if (!loadRequest || loadRequest.status === undefined)
            return
        if (loadRequest.status === WebEngineView.LoadStartedStatus)
            view.loadState("started")
        else if (loadRequest.status === WebEngineView.LoadSucceededStatus)
            view.loadState("succeeded")
        else if (loadRequest.status === WebEngineView.LoadFailedStatus)
            view.loadState("failed")
    }
}
