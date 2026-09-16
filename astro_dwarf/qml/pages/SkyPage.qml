import QtQuick
import QtQuick.Layouts
import QtCore
import ".."
import "../components"

Item {
    id: skyPage
    objectName: "skyPage"
    readonly property bool mapLive: root.currentPage === root.skyPageIndex
    readonly property bool targetLocked: !!(backend.skyTarget && backend.skyTarget.locked)
    readonly property bool webReady: backend.webViewAvailable && !skyPage.webFailed
    property bool webFailed: false
    property bool mapKeepAlive: false
    property bool harvestBusy: false
    property string pendingAction: ""
    property bool paTouched: false
    readonly property int defaultPa: backend.mosaicSouthUp ? 180 : 0
    Settings {
        id: skyStore
        category: "sky"
        property int mosaicColumns: 1
        property int mosaicRows: 1
        property int mosaicOverlap: 20
        property int mosaicPa: 180
        property bool mosaicPaSet: false
    }
    function clampInt(value, lo, hi, fallback) {
        const n = Number(value)
        if (!isFinite(n))
            return fallback
        return Math.max(lo, Math.min(hi, Math.round(n)))
    }
    function restoreSkySettings() {
        columnsBox.value = skyPage.clampInt(skyStore.mosaicColumns, 1, 10, 1)
        rowsBox.value = skyPage.clampInt(skyStore.mosaicRows, 1, 10, 1)
        overlapBox.value = skyPage.clampInt(skyStore.mosaicOverlap, 0, 80, 20)
        if (skyStore.mosaicPaSet) {
            paBox.value = ((skyPage.clampInt(skyStore.mosaicPa, 0, 359, skyPage.defaultPa) % 360) + 360) % 360
            skyPage.paTouched = true
        } else {
            paBox.value = skyPage.defaultPa
        }
    }
    function saveSkyGrid() {
        skyStore.mosaicColumns = columnsBox.value
        skyStore.mosaicRows = rowsBox.value
        skyStore.mosaicOverlap = overlapBox.value
    }
    function saveSkyPa() {
        skyPage.paTouched = true
        skyStore.mosaicPa = paBox.value
        skyStore.mosaicPaSet = true
    }
    readonly property bool mosaicGrid: columnsBox.value > 1 || rowsBox.value > 1
    readonly property bool mapHasTarget: !!(mapLoader.item && mapLoader.item.hasSelectedTarget)
    readonly property bool mapInitialReady: !!(mapLoader.item && mapLoader.item.initialLoadDone)
    readonly property bool mapInitialFailed: !!(mapLoader.item && mapLoader.item.initialLoadFailed)
    readonly property bool mapBooting: skyPage.webReady && root.skyToolsEnabled
                                       && (skyPage.mapLive || mapLoader.active)
                                       && !skyPage.mapInitialReady
                                       && !skyPage.mapInitialFailed
    readonly property string targetSubtitle: {
        if (!skyPage.targetLocked) {
            return skyPage.mosaicGrid
                   ? "Select a target in the sky map. Double-click to center it, then create a mosaic session from the grid."
                   : "Select a target in the sky map. Double-click to center it, then create a single session."
        }
        const target = backend.skyTarget
        return target.name + "  ·  RA " + Number(target.ra_hours).toFixed(3) + "h  DEC "
               + Number(target.dec_degrees).toFixed(3) + "°"
    }
    function sendHarvest(raw) {
        if (!skyPage.harvestBusy)
            return
        skyPage.harvestBusy = false
        harvestTimeout.stop()
        const action = skyPage.pendingAction
        skyPage.pendingAction = ""
        if (action === "mosaic")
            backend.generateStellariumMosaic(raw, columnsBox.value, rowsBox.value, overlapBox.value / 100, paBox.value)
        else if (action === "import")
            backend.importStellariumSmart(raw)
        else if (action === "push")
            backend.pushSkyToDesktop(raw)
    }
    function withSkySources(action) {
        if (backend.uiBusy !== "" || skyPage.harvestBusy)
            return
        if ((action === "mosaic" || action === "import") && !skyPage.mapHasTarget)
            return
        skyPage.pendingAction = String(action || "")
        skyPage.harvestBusy = true
        const map = mapLoader.item
        if (!map || typeof map.readSelectedTarget !== "function") {
            skyPage.sendHarvest("")
            return
        }
        map.readSelectedTarget(result => skyPage.sendHarvest(result))
        harvestTimeout.restart()
    }

    Connections {
        target: backend
        function onSelectedDeviceChanged() {
            if (!skyPage.paTouched)
                paBox.value = skyPage.defaultPa
        }
    }

    Connections {
        target: root
        function onSkyToolsEnabledChanged() {
            if (!root.skyToolsEnabled)
                skyPage.mapKeepAlive = false
            backend.setStellariumRcWatch(root.skyToolsEnabled)
        }
    }

    Component.onCompleted: {
        skyPage.restoreSkySettings()
        backend.setStellariumRcWatch(root.skyToolsEnabled)
    }
    Component.onDestruction: backend.setStellariumRcWatch(false)

    Timer {
        id: harvestTimeout
        interval: 2000
        repeat: false
        onTriggered: skyPage.sendHarvest("")
    }

    readonly property string mosaicHint: "Pane preview is a Telescopius-style camera frame (PA east of north, "
                                         + (backend.mosaicSouthUp ? "S-up" : "N-up")
                                         + " default from the selected telescope’s location)."

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.s1

        PageHeader {
            id: skyHeader
            readonly property bool tight: width < 1100
            title: "SKY"
            subtitle: skyPage.targetSubtitle
            RowLayout {
                spacing: Theme.s2
                anchors.verticalCenter: parent.verticalCenter
                implicitHeight: Theme.compactControlHeight
                FieldLabel {
                    text: "COL"
                    Layout.preferredWidth: implicitWidth
                }
                HudSpinBox {
                    id: columnsBox
                    from: 1
                    to: 10
                    value: 1
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: 72
                    Layout.preferredWidth: 72
                    accessibleName: "Mosaic columns"
                    tooltip: skyPage.mosaicHint
                    onValueModified: skyPage.saveSkyGrid()
                }
                FieldLabel {
                    text: "ROW"
                    Layout.preferredWidth: implicitWidth
                }
                HudSpinBox {
                    id: rowsBox
                    from: 1
                    to: 10
                    value: 1
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: 72
                    Layout.preferredWidth: 72
                    accessibleName: "Mosaic rows"
                    tooltip: skyPage.mosaicHint
                    onValueModified: skyPage.saveSkyGrid()
                }
                FieldLabel {
                    text: "OVL"
                    Layout.preferredWidth: implicitWidth
                }
                HudSpinBox {
                    id: overlapBox
                    from: 0
                    to: 80
                    stepSize: 5
                    value: 20
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: 78
                    Layout.preferredWidth: 78
                    accessibleName: "Mosaic overlap percent"
                    tooltip: skyPage.mosaicHint
                    textFromValue: (value, locale) => String(value) + "%"
                    valueFromText: (text, locale) => {
                        const n = parseInt(String(text).replace("%", "").trim(), 10)
                        return isNaN(n) ? overlapBox.value : n
                    }
                    onValueModified: skyPage.saveSkyGrid()
                }
                FieldLabel {
                    text: "PA"
                    Layout.preferredWidth: implicitWidth
                }
                HudSpinBox {
                    id: paBox
                    from: 0
                    to: 359
                    wrap: true
                    value: 180
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: 78
                    Layout.preferredWidth: 78
                    accessibleName: "Camera position angle east of north"
                    tooltip: "Camera position angle, east of north. 0° is N-up, 180° is S-up. Match Telescopius PA."
                    textFromValue: (value, locale) => String(value) + "°"
                    valueFromText: (text, locale) => {
                        const n = parseInt(String(text).replace("°", "").trim(), 10)
                        return isNaN(n) ? paBox.value : ((n % 360) + 360) % 360
                    }
                    onValueModified: skyPage.saveSkyPa()
                }
                HudChip {
                    label: backend.stellariumRcLive ? "RC LIVE" : "RC OFF"
                    tone: backend.stellariumRcLive ? Theme.success : Theme.textSecondary
                    dim: !backend.stellariumRcLive
                    glow: backend.stellariumRcLive
                    Layout.alignment: Qt.AlignVCenter
                }
                HudChip {
                    label: backend.mosaicSouthUp ? "S-UP" : "N-UP"
                    tone: Theme.accent
                    Layout.alignment: Qt.AlignVCenter
                }
            }
            HudButton {
                implicitHeight: Theme.compactControlHeight
                visible: backend.stellariumRcLive
                text: "PUSH"
                busy: (skyPage.harvestBusy && skyPage.pendingAction === "push") || backend.uiBusy === "stellariumPush"
                busyText: "PUSHING…"
                busyMs: 0
                enabled: backend.stellariumRcLive && backend.uiBusy === "" && !skyPage.harvestBusy
                accessibleDescription: "Send the sky map selection, site, time, and field of view to desktop Stellarium"
                tooltip: "Send the selected target, site, time, and FOV to desktop Stellarium"
                onClicked: skyPage.withSkySources("push")
            }
            HudButton {
                implicitHeight: Theme.compactControlHeight
                text: skyPage.mosaicGrid
                      ? (skyHeader.tight ? "CREATE MOSAIC" : "CREATE MOSAIC SESSION")
                      : (skyHeader.tight ? "CREATE SESSION" : "CREATE SINGLE SESSION")
                buttonColor: Theme.fillActive
                foregroundColor: Theme.accent
                busy: (skyPage.harvestBusy && (skyPage.pendingAction === "mosaic" || skyPage.pendingAction === "import"))
                      || backend.uiBusy === "stellariumMosaic" || backend.uiBusy === "stellarium"
                busyText: (skyPage.pendingAction === "mosaic" || backend.uiBusy === "stellariumMosaic")
                          ? "GENERATING…" : "CREATING…"
                busyMs: 0
                enabled: backend.uiBusy === "" && !skyPage.harvestBusy && skyPage.mapHasTarget
                hoverEnabled: true
                accessibleDescription: !skyPage.mapHasTarget
                                       ? "Select a target in the sky map first"
                                       : skyPage.mosaicGrid
                                         ? "Create an X by Y mosaic session from the sky map selection"
                                         : "Create a single session from the sky map selection"
                tooltip: !skyPage.mapHasTarget
                         ? "Select a target in the sky map first"
                         : skyPage.mosaicGrid
                           ? "Create a mosaic session from the selected target. " + skyPage.mosaicHint
                           : "Create a single session from the selected target"
                onClicked: skyPage.withSkySources(skyPage.mosaicGrid ? "mosaic" : "import")
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 220
            color: Theme.panelFill
            border.color: Theme.outline
            clip: true

            Loader {
                id: mapLoader
                // Native WebView2 / WKWebView paint above QML and ignore overlay z-order.
                // Keep the native view full-size so it can load, but park it outside the
                // window until Stellarium JS is ready. Linux uses Qt WebEngine in the
                // scene graph, so the boot overlay can cover it without parking.
                readonly property bool nativeMapOverlay: Qt.platform.os === "windows"
                                                           || Qt.platform.os === "osx"
                width: parent.width - 2
                height: parent.height - 2
                x: (!mapLoader.nativeMapOverlay || skyPage.mapInitialReady) ? 1 : -4096
                y: 1
                active: skyPage.webReady && root.skyToolsEnabled && (skyPage.mapLive || skyPage.mapKeepAlive)
                source: Qt.resolvedUrl("SkyWebView.qml")
                onLoaded: {
                    skyPage.mapKeepAlive = true
                    const map = mapLoader.item
                    if (!map)
                        return
                    map.mosaicColumns = Qt.binding(() => columnsBox.value)
                    map.mosaicRows = Qt.binding(() => rowsBox.value)
                    map.mosaicOverlap = Qt.binding(() => overlapBox.value / 100)
                    map.mosaicPa = Qt.binding(() => paBox.value)
                }
                onStatusChanged: {
                    if (status === Loader.Error)
                        skyPage.webFailed = true
                }
            }

            EmptyHint {
                visible: !skyPage.webReady || skyPage.mapInitialFailed
                anchors.centerIn: parent
                mode: "unavailable"
                glyph: "✧"
                text: "Stellarium Web is not available in this window. Open it in a browser to find a target, then come back if the map loads."
            }

            HudButton {
                visible: !skyPage.webReady
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16
                text: "OPEN STELLARIUM WEB"
                onClicked: backend.openExternalUrl(backend.stellariumWebUrl)
            }

            Rectangle {
                id: mapBootOverlay
                anchors.fill: parent
                anchors.margins: 1
                color: Theme.surface
                opacity: skyPage.mapBooting ? 1 : 0
                visible: opacity > 0
                z: 2
                Behavior on opacity { NumberAnimation { duration: Theme.normal } }

                MouseArea {
                    anchors.fill: parent
                    enabled: skyPage.mapBooting
                    hoverEnabled: enabled
                }

                EmptyHint {
                    anchors.centerIn: parent
                    mode: "loading"
                    glyph: "✧"
                    text: "Loading Stellarium Web…"
                }
            }
        }
    }
}
