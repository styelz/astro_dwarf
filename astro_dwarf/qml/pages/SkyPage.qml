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
    property var pendingLockTarget: null
    property string pendingAction: ""
    property bool applyingPa: false
    readonly property int defaultPa: backend.mosaicSouthUp ? 180 : 0
    Settings {
        id: skyStore
        category: "sky"
        property int mosaicColumns: 1
        property int mosaicRows: 1
        property int mosaicOverlap: 20
        property int mosaicPa: 180
        property bool mosaicPaSet: false
        property bool liveFovOverlay: false
        property real liveFovOpacity: 0.65
        property bool dblclickTrack: false
        property bool viewSaved: false
        property real viewRaHours: 0
        property real viewDecDegrees: 0
        property real viewFov: 0
        property real viewYaw: 0
        property real viewPitch: 0
        property real viewRoll: 0
    }
    function clampInt(value, lo, hi, fallback) {
        const n = Number(value)
        if (!isFinite(n))
            return fallback
        return Math.max(lo, Math.min(hi, Math.round(n)))
    }
    function clampOpacity(value) {
        const n = Number(value)
        if (!isFinite(n))
            return 0.65
        return Math.max(0, Math.min(1, Math.round(n * 100) / 100))
    }
    function restoreSkySettings() {
        columnsBox.value = skyPage.clampInt(skyStore.mosaicColumns, 1, 10, 1)
        rowsBox.value = skyPage.clampInt(skyStore.mosaicRows, 1, 10, 1)
        overlapBox.value = skyPage.clampInt(skyStore.mosaicOverlap, 0, 80, 20)
        const stored = backend.selectedDevice.mosaic_pa
        const hasDevicePa = stored !== undefined && stored !== null && stored !== ""
        if (!hasDevicePa && skyStore.mosaicPaSet) {
            backend.setMosaicPa(((skyPage.clampInt(skyStore.mosaicPa, 0, 359, skyPage.defaultPa) % 360) + 360) % 360)
            skyStore.mosaicPaSet = false
        }
        skyPage.applyDevicePa()
        backend.setSkyMosaicGrid(columnsBox.value, rowsBox.value, overlapBox.value / 100)
    }
    function saveSkyGrid() {
        skyStore.mosaicColumns = columnsBox.value
        skyStore.mosaicRows = rowsBox.value
        skyStore.mosaicOverlap = overlapBox.value
        backend.setSkyMosaicGrid(columnsBox.value, rowsBox.value, overlapBox.value / 100)
    }
    function applyDevicePa() {
        const next = ((skyPage.clampInt(backend.mosaicPa, 0, 359, skyPage.defaultPa) % 360) + 360) % 360
        if (paBox.value === next)
            return
        skyPage.applyingPa = true
        paBox.value = next
        skyPage.applyingPa = false
    }
    function saveSkyPa() {
        if (skyPage.applyingPa)
            return
        backend.setMosaicPa(paBox.value)
    }
    function saveSkyView(data) {
        if (!data)
            return
        const ra = Number(data.ra_hours)
        const dec = Number(data.dec_degrees)
        const fov = Number(data.fov)
        if (!isFinite(ra) || !isFinite(dec))
            return
        skyStore.viewRaHours = ra
        skyStore.viewDecDegrees = dec
        skyStore.viewFov = isFinite(fov) ? fov : 0
        const yaw = Number(data.yaw)
        const pitch = Number(data.pitch)
        const roll = Number(data.roll)
        skyStore.viewYaw = isFinite(yaw) ? yaw : skyStore.viewYaw
        skyStore.viewPitch = isFinite(pitch) ? pitch : skyStore.viewPitch
        skyStore.viewRoll = isFinite(roll) ? roll : skyStore.viewRoll
        skyStore.viewSaved = true
        if (typeof skyStore.sync === "function")
            skyStore.sync()
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
        const fov = backend.mosaicFovText
        const live = (mapLoader.item && mapLoader.item.selectedKey)
                     ? mapLoader.item.selectedTarget
                     : null
        const target = (live && isFinite(Number(live.ra_hours)) && isFinite(Number(live.dec_degrees)))
                       ? live
                       : (skyPage.targetLocked ? backend.skyTarget : null)
        if (!target) {
            const liveView = (mapLoader.item && mapLoader.item.liveView) || {}
            const ra = Number(isFinite(Number(liveView.ra_hours)) ? liveView.ra_hours : skyStore.viewRaHours)
            const dec = Number(isFinite(Number(liveView.dec_degrees)) ? liveView.dec_degrees : skyStore.viewDecDegrees)
            if (isFinite(ra) && isFinite(dec) && (isFinite(Number(liveView.ra_hours)) || skyStore.viewSaved)) {
                const decText = (dec >= 0 ? "+" : "") + dec.toFixed(3) + "°"
                return "FOV centre  ·  RA " + ra.toFixed(3) + "h  DEC " + decText + "  ·  " + fov
            }
            const clickHint = skyStore.dblclickTrack
                ? "Select a target. Double-click to GOTO it and start tracking."
                : (skyPage.mosaicGrid
                   ? "Select a target in the sky map. Double-click to center it, then press STACK on Control to capture every pane."
                   : "Select a target in the sky map. Double-click to center it, then create a single session.")
            return clickHint + "  ·  " + fov
        }
        const name = String(target.name || "").trim()
        const dec = Number(target.dec_degrees)
        const decText = (dec >= 0 ? "+" : "") + dec.toFixed(3) + "°"
        return (name ? name + "  ·  " : "")
               + "RA " + Number(target.ra_hours).toFixed(3) + "h  DEC " + decText
               + "  ·  " + fov
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
        else if (action === "track")
            backend.trackSkyTarget(raw)
    }
    property double lastSkyMenuAt: 0
    function openSkyMenu(x, y) {
        const now = Date.now()
        if (now - skyPage.lastSkyMenuAt < 250)
            return
        skyPage.lastSkyMenuAt = now
        if (x === undefined || y === undefined)
            skyMenu.popup()
        else
            skyMenu.popup(mapLoader, x, y)
    }
    function lockToTrackedTarget() {
        const tracked = backend.trackedSkyTarget || ({})
        if (!tracked.available)
            return
        if (!root.skyToolsEnabled || !skyPage.webReady)
            return
        skyPage.mapKeepAlive = true
        if (root.currentPage !== root.skyPageIndex)
            root.goToPage(root.skyPageIndex)
        backend.lockSkyToTrackedTarget()
    }
    function queueSkyLock(payload) {
        if (!payload)
            return
        const ra = Number(payload.ra_hours)
        const dec = Number(payload.dec_degrees)
        skyPage.pendingLockTarget = {
            name: String(payload.name || ""),
            ra_hours: isFinite(ra) ? ra : undefined,
            dec_degrees: isFinite(dec) ? dec : undefined,
            aliases: payload.aliases || []
        }
        skyPage.applyPendingLock()
    }
    function applyPendingLock() {
        const target = skyPage.pendingLockTarget
        const map = mapLoader.item
        if (!target || !map || !map.pageReady || typeof map.lockTarget !== "function")
            return
        map.lockTarget(target, result => {
            let status = ""
            try {
                const data = JSON.parse(String(result || ""))
                status = String((data && data.status) || "")
            } catch (err) {
            }
            if (status === "loading")
                return
            skyPage.pendingLockTarget = null
            if (status === "locked" || status === "view")
                map.applyFovOverlay()
            else if (status === "missing" || status === "error")
                backend.reportSkyLockResult(status, String(target.name || ""))
        })
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
            skyPage.applyDevicePa()
        }
        function onSkyLockRequested(payload) {
            skyPage.queueSkyLock(payload)
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

    readonly property string mosaicHint: "Pane preview is a Telescopius-style camera frame for "
                                         + backend.mosaicFovText
                                         + " (PA east of north; default "
                                         + skyPage.defaultPa + "° "
                                         + (backend.mosaicSouthUp ? "S-up" : "N-up")
                                         + " from this telescope, or its stored camera offset)."

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
                    tooltip: "Camera position angle, east of north, stored on this telescope. 0° is N-up, 180° is S-up. Use a measured offset such as 184° if the cameras are not square south-up."
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
                HudChip {
                    visible: !skyHeader.tight
                    label: backend.mosaicFovText
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
                           ? "Create scheduled mosaic pane sessions from the selected target. Or press STACK on Control to capture the grid now. " + skyPage.mosaicHint
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
                readonly property bool nativeMapVisible: !mapLoader.nativeMapOverlay
                    || (skyPage.mapLive && skyPage.mapInitialReady && !root.appModalOpen)
                width: parent.width - 2
                height: parent.height - 2
                x: mapLoader.nativeMapVisible ? 1 : -4096
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
                    map.liveOverlay = Qt.binding(() => skyStore.liveFovOverlay)
                    map.liveOpacity = Qt.binding(() => skyPage.clampOpacity(skyStore.liveFovOpacity))
                    map.savedView = Qt.binding(() => skyStore.viewSaved ? ({
                        ra_hours: skyStore.viewRaHours,
                        dec_degrees: skyStore.viewDecDegrees,
                        fov: skyStore.viewFov,
                        yaw: skyStore.viewYaw,
                        pitch: skyStore.viewPitch,
                        roll: skyStore.viewRoll
                    }) : ({}))
                    map.savedViewReady = true
                    skyPage.applyPendingLock()
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
                text: backend.skyWebBlockedByGpu
                      ? "Stellarium Web cannot run inside this window. This session has no OpenGL, which is typical on Hyper-V. Open it in a browser, then import the target here."
                      : "Stellarium Web is not available in this window. Open it in a browser to find a target, then come back if the map loads."
            }

            HudButton {
                visible: !skyPage.webReady
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 16
                text: "OPEN STELLARIUM WEB"
                onClicked: backend.openExternalUrl(backend.stellariumWebUrl)
            }

            Connections {
                target: mapLoader.item
                function onContextMenuRequested(x, y) {
                    skyPage.openSkyMenu(x, y)
                }
                function onTrackRequested() {
                    if (!skyStore.dblclickTrack)
                        return
                    skyPage.withSkySources("track")
                }
                function onLiveOpacityNudged(opacity) {
                    skyStore.liveFovOpacity = skyPage.clampOpacity(opacity)
                }
                function onViewChanged(data) {
                    skyPage.saveSkyView(data)
                }
                function onPageReadyChanged() {
                    skyPage.applyPendingLock()
                }
            }

            TapHandler {
                acceptedButtons: Qt.RightButton
                grabPermissions: PointerHandler.CanTakeOverFromAnything | PointerHandler.ApprovesTakeOverByAnything
                enabled: skyPage.mapInitialReady && !skyPage.mapBooting
                onTapped: skyPage.openSkyMenu()
            }

            SkyContextMenu {
                id: skyMenu
                overlayEnabled: skyStore.liveFovOverlay
                overlayOpacity: skyPage.clampOpacity(skyStore.liveFovOpacity)
                dblclickTrack: skyStore.dblclickTrack
                hasTarget: skyPage.mapHasTarget
                trackEnabled: !!(backend.selectedDevice && backend.selectedDevice.connected)
                              && root.scopePending === ""
                              && !root.scopeImaging
                              && root.scopeTelemetry.goto_state !== "running"
                              && root.scopeTelemetry.goto_state !== "solving"
                              && root.scopeTelemetry.goto_state !== "stopping"
                              && (root.scopeActivity === "" || root.scopeActivity === "goto"
                                  || !!root.scopeTelemetry.tracking_active)
                onOverlayToggled: {
                    skyStore.liveFovOverlay = !skyStore.liveFovOverlay
                    if (skyStore.liveFovOverlay && !backend.previewActive && backend.selectedDevice.connected)
                        backend.startPreview(backend.selectedDeviceId)
                }
                onPreviewToggled: {
                    if (backend.previewActive || backend.previewHeld || backend.previewResult)
                        backend.stopPreview()
                    else if (backend.selectedDevice.connected)
                        backend.startPreview(backend.selectedDeviceId)
                }
                onDblclickTrackToggled: skyStore.dblclickTrack = !skyStore.dblclickTrack
                onTrackSelected: skyPage.withSkySources("track")
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
