import QtQuick
import QtQuick.Layouts
import QtCore
import ".."
import "../components"

Item {
    id: skyPage
    objectName: "skyPage"
    readonly property bool mapLive: root.currentPage === root.skyPageIndex
    onMapLiveChanged: {
        if (!skyPage.mapLive && skyMenu.visible)
            skyMenu.close()
    }
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
        property bool liveFovOverlay: false
        property real liveFovOpacity: 0.65
        property bool dblclickTrack: false
        property bool viewSaved: false
        property real viewRaHours: 0
        property real viewDecDegrees: 0
        property real viewFov: 0
        property bool viewFovDegrees: false
        property real viewYaw: 0
        property real viewPitch: 0
        property real viewRoll: 0
        property int coordFormatIndex: 0
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
    function shareMapFov() {
        if (skyStore.viewFovDegrees)
            return
        // A saved field of 2π degrees or less is Stellarium's old radian zoom.
        // That painted Aladin as a few degrees and Stellarium at its widest.
        const fov = Number(skyStore.viewFov)
        if (!(fov > 6.3))
            skyStore.viewFov = backend.skyMapFovDeg
        skyStore.viewFovDegrees = true
    }
    function restoreSkySettings() {
        skyPage.shareMapFov()
        columnsBox.value = skyPage.clampInt(skyStore.mosaicColumns, 1, 10, 1)
        rowsBox.value = skyPage.clampInt(skyStore.mosaicRows, 1, 10, 1)
        overlapBox.value = skyPage.clampInt(skyStore.mosaicOverlap, 0, 80, 20)
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
        if (paBox.activeFocus)
            return
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
        const fovStored = isFinite(fov) ? fov : 0
        if (skyStore.viewSaved
                && Math.abs(skyStore.viewRaHours - ra) < 0.0008
                && Math.abs(skyStore.viewDecDegrees - dec) < 0.008
                && Math.abs(skyStore.viewFov - fovStored) < 0.05)
            return
        skyStore.viewRaHours = ra
        skyStore.viewDecDegrees = dec
        skyStore.viewFov = fovStored
        const yaw = Number(data.yaw)
        const pitch = Number(data.pitch)
        const roll = Number(data.roll)
        skyStore.viewYaw = isFinite(yaw) ? yaw : skyStore.viewYaw
        skyStore.viewPitch = isFinite(pitch) ? pitch : skyStore.viewPitch
        skyStore.viewRoll = isFinite(roll) ? roll : skyStore.viewRoll
        skyStore.viewSaved = true
        skyPage.viewPersistDirty = true
        viewPersistTimer.restart()
    }
    property bool viewPersistDirty: false
    Timer {
        id: viewPersistTimer
        interval: 1200
        repeat: false
        onTriggered: {
            if (!skyPage.viewPersistDirty)
                return
            skyPage.viewPersistDirty = false
            if (typeof skyStore.sync === "function")
                skyStore.sync()
        }
    }
    readonly property bool mosaicGrid: columnsBox.value > 1 || rowsBox.value > 1
    readonly property bool mapHasTarget: !!(mapLoader.item && mapLoader.item.hasSelectedTarget)
    readonly property bool mapInitialReady: !!(mapLoader.item && mapLoader.item.initialLoadDone)
    readonly property bool mapInitialFailed: !!(mapLoader.item && mapLoader.item.initialLoadFailed)
    readonly property bool mapBooting: skyPage.webReady && root.skyToolsEnabled
                                       && (skyPage.mapLive || mapLoader.active)
                                       && !skyPage.mapInitialReady
                                       && !skyPage.mapInitialFailed
    readonly property string overlayFovText: skyPage.mosaicGrid
                                            ? backend.mosaicFovText
                                            : backend.skyFovText
    readonly property string targetSubtitle: {
        const fov = skyPage.overlayFovText
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
                const az = Number(liveView.az)
                const alt = Number(liveView.alt)
                const horizon = (isFinite(az) && isFinite(alt))
                    ? "  ·  AZ " + Math.round(((az % 360) + 360) % 360) + "°  ALT " + (alt >= 0 ? "+" : "") + Math.round(alt) + "°"
                    : ""
                return "FOV centre  ·  RA " + ra.toFixed(3) + "h  DEC " + decText + horizon + "  ·  " + fov
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
        return "Selected target  ·  "
               + (name ? name + "  ·  " : "")
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
            backend.generateStellariumMosaic(
                raw, columnsBox.value, rowsBox.value, overlapBox.value / 100,
                backend.mosaicPaManual ? paBox.value : backend.mosaicPa)
        else if (action === "import")
            backend.importStellariumSmart(raw)
        else if (action === "push")
            backend.pushSkyToDesktop(raw)
        else if (action === "track") {
            const openControl = skyPage.trackOpensControl
            skyPage.trackOpensControl = false
            if (backend.trackSkyTarget(raw) && openControl)
                root.goToPage(root.controlPageIndex)
        }
    }
    property double lastSkyMenuAt: 0
    property real lastSkyMenuX: 0
    property real lastSkyMenuY: 0
    function openSkyMenu(x, y) {
        const now = Date.now()
        if (now - skyPage.lastSkyMenuAt < 250)
            return
        skyPage.lastSkyMenuAt = now
        if (x === undefined || y === undefined) {
            skyMenu.popup()
            return
        }
        skyPage.lastSkyMenuX = x
        skyPage.lastSkyMenuY = y
        skyMenu.popup(mapLoader, x, y)
    }
    function openAtlasMenu() {
        const map = mapLoader.item
        if (!map || typeof map.openAtlasMenu !== "function")
            return
        map.openAtlasMenu(skyPage.lastSkyMenuX, skyPage.lastSkyMenuY)
    }
    function currentMapCenter() {
        const live = (mapLoader.item && mapLoader.item.liveView) || {}
        const ra = Number(isFinite(Number(live.ra_hours)) ? live.ra_hours : skyStore.viewRaHours)
        const dec = Number(isFinite(Number(live.dec_degrees)) ? live.dec_degrees : skyStore.viewDecDegrees)
        if (isFinite(ra) && isFinite(dec) && (isFinite(Number(live.ra_hours)) || skyStore.viewSaved))
            return { ra_hours: ra, dec_degrees: dec }
        return null
    }
    readonly property var fovCenter: skyPage.currentMapCenter()
    readonly property string fovCenterText: {
        const center = skyPage.fovCenter
        if (!center)
            return ""
        const dec = Number(center.dec_degrees)
        const decText = (dec >= 0 ? "+" : "") + dec.toFixed(2) + "\u00b0"
        return Number(center.ra_hours).toFixed(2) + "h  " + decText
    }
    function useFovCenterAsTarget() {
        const center = skyPage.currentMapCenter()
        const map = mapLoader.item
        if (!center || !map || typeof map.applyCoordinateTarget !== "function")
            return
        const payload = {
            name: "FOV centre",
            ra_hours: Number(center.ra_hours),
            dec_degrees: Number(center.dec_degrees)
        }
        map.applyCoordinateTarget(payload)
        if (typeof map.pinCoordinateTarget === "function")
            map.pinCoordinateTarget(payload)
        if (typeof map.applyFovOverlay === "function")
            map.applyFovOverlay()
    }
    function openRaDecDialog() {
        skyRaDecDialog.formatIndex = skyPage.clampInt(skyStore.coordFormatIndex, 0, 3, 0)
        const center = skyPage.currentMapCenter()
        if (center)
            skyRaDecDialog.openAt(center.ra_hours, center.dec_degrees)
        else
            skyRaDecDialog.openAt(Number.NaN, Number.NaN)
    }
    function gotoRaDec(raHours, decDegrees) {
        const map = mapLoader.item
        if (!map || typeof map.setView !== "function")
            return
        if (typeof map.beginViewHold === "function")
            map.beginViewHold()
        map.setView(raHours, decDegrees)
    }
    property bool trackOpensControl: false
    function showScheduleOnSky(item) {
        if (!root.skyToolsEnabled)
            return
        const plan = backend.skyShowPlan(item) || ({})
        if (!plan.ok)
            return
        const columns = skyPage.clampInt(plan.columns, 1, 10, 1)
        const rows = skyPage.clampInt(plan.rows, 1, 10, 1)
        if (columnsBox.value !== columns)
            columnsBox.value = columns
        if (rowsBox.value !== rows)
            rowsBox.value = rows
        if (plan.mosaic) {
            const overlapPct = skyPage.clampInt(Math.round(Number(plan.overlap) * 100), 0, 80, 0)
            if (overlapBox.value !== overlapPct)
                overlapBox.value = overlapPct
            if (backend.mosaicPaManual && isFinite(Number(plan.position_angle))) {
                const pa = ((Math.round(Number(plan.position_angle)) % 360) + 360) % 360
                if (paBox.value !== pa) {
                    skyPage.applyingPa = true
                    paBox.value = pa
                    skyPage.applyingPa = false
                }
            }
        }
        skyPage.saveSkyGrid()
        skyPage.mapKeepAlive = true
        if (root.currentPage !== root.skyPageIndex)
            root.goToPage(root.skyPageIndex)
        skyPage.queueSkyLock({
            name: String(plan.name || ""),
            ra_hours: Number(plan.ra_hours),
            dec_degrees: Number(plan.dec_degrees)
        })
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
            if (status === "locked" || status === "view") {
                if (typeof map.applyCoordinateTarget === "function")
                    map.applyCoordinateTarget(target)
                if (status === "view" && typeof map.pinCoordinateTarget === "function")
                    map.pinCoordinateTarget(target)
                map.applyFovOverlay()
            } else if (status === "missing" || status === "error")
                backend.reportSkyLockResult(status, String(target.name || ""))
        })
    }
    function harnessGrid(columns, rows) {
        const nextColumns = skyPage.clampInt(columns, 1, 10, columnsBox.value)
        const nextRows = skyPage.clampInt(rows, 1, 10, rowsBox.value)
        if (columnsBox.value !== nextColumns)
            columnsBox.value = nextColumns
        if (rowsBox.value !== nextRows)
            rowsBox.value = nextRows
        skyPage.saveSkyGrid()
        return columnsBox.value + "x" + rowsBox.value
    }
    function harnessSetView(raHours, decDegrees) {
        const map = mapLoader.item
        if (!map)
            return "no-map"
        if (typeof map.setView === "function")
            return map.setView(raHours, decDegrees)
        if (typeof map.runJavaScript !== "function")
            return "no-map"
        map.runJavaScript(backend.skyWebViewPosScript(Number(raHours), Number(decDegrees)))
        return "ok"
    }
    function harnessEval(script, callback) {
        const map = mapLoader.item
        if (!map || typeof map.runJavaScript !== "function") {
            if (typeof callback === "function")
                callback("no-map")
            return "no-map"
        }
        map.runJavaScript(String(script || ""), result => {
            if (typeof callback === "function")
                callback(result)
        })
        return "pending"
    }
    function harnessMenu(action) {
        const key = String(action || "")
        if (key === "overlay")
            skyMenu.overlayToggled()
        else if (key === "preview")
            skyMenu.previewToggled()
        else if (key === "dblclick")
            skyMenu.dblclickTrackToggled()
        else if (key === "track")
            skyMenu.trackSelected()
        else if (key === "fov")
            skyPage.useFovCenterAsTarget()
        else if (key === "atlas")
            skyPage.openAtlasMenu()
        else if (key === "clipboard")
            skyMenu.clipboardGotoRequested()
        else if (key === "radec")
            skyPage.openRaDecDialog()
        else
            return "unknown"
        return key
    }
    function withSkySources(action, openControl) {
        if (backend.uiBusy !== "" || skyPage.harvestBusy)
            return
        skyPage.trackOpensControl = String(action || "") === "track" && !!openControl
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
        function onMosaicPaChanged() {
            skyPage.applyDevicePa()
        }
        function onSkyLockRequested(payload) {
            skyPage.queueSkyLock(payload)
        }
        function onAppSettingsChanged() {
            skyPage.webFailed = false
        }
    }

    function requestMapWarmup() {
        if (!root.skyToolsEnabled || !skyPage.webReady)
            return
        skyPage.mapKeepAlive = true
    }

    Connections {
        target: root
        function onSkyToolsEnabledChanged() {
            if (!root.skyToolsEnabled)
                skyPage.mapKeepAlive = false
            else
                Qt.callLater(skyPage.requestMapWarmup)
            backend.setStellariumRcWatch(root.skyToolsEnabled)
        }
    }

    Component.onCompleted: {
        skyPage.restoreSkySettings()
        backend.setStellariumRcWatch(root.skyToolsEnabled)
        Qt.callLater(skyPage.requestMapWarmup)
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
                                         + ". EQ camera-up is east of north: unset is 0° N-up in the north and 180° S-up in the south. Alt-az follows the zenith."

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.s1

        PageHeader {
            id: skyHeader
            readonly property bool tight: width < Theme.px(1100)
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
                    objectName: "skyColumns"
                    from: 1
                    to: 10
                    value: 1
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: Theme.px(72)
                    Layout.preferredWidth: Theme.px(72)
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
                    objectName: "skyRows"
                    from: 1
                    to: 10
                    value: 1
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: Theme.px(72)
                    Layout.preferredWidth: Theme.px(72)
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
                    objectName: "skyOverlap"
                    from: 0
                    to: 80
                    stepSize: 5
                    value: 20
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: Theme.px(78)
                    Layout.preferredWidth: Theme.px(78)
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
                    visible: backend.mosaicPaManual
                    Layout.preferredWidth: implicitWidth
                }
                HudSpinBox {
                    id: paBox
                    objectName: "skyPa"
                    visible: backend.mosaicPaManual
                    from: 0
                    to: 359
                    wrap: true
                    value: 0
                    implicitHeight: Theme.compactControlHeight
                    implicitWidth: Theme.px(78)
                    Layout.preferredWidth: Theme.px(78)
                    accessibleName: "Camera position angle east of north"
                    tooltip: "Equatorial camera-up, east of north. Unset is 0° N-up north of the equator and 180° S-up south of it. A stored 0° stays N-up. Alt-az hides this box and follows the zenith."
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
                    label: backend.mosaicPaChip
                    tone: Theme.accent
                    Layout.alignment: Qt.AlignVCenter
                    Accessible.name: "Camera position angle"
                    Accessible.description: backend.mosaicPaManual
                                           ? "Equatorial mosaic north-up or south-up"
                                           : "Live alt-az zenith-up camera angle"
                }
                HudChip {
                    visible: !skyHeader.tight
                    label: skyPage.overlayFovText
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
            Layout.minimumHeight: Theme.px(220)
            color: Theme.panelFill
            border.color: Theme.outline
            clip: true

            Item {
                id: mapSlot
                anchors.fill: parent
                anchors.margins: Theme.px(1)
            }

            Loader {
                id: mapLoader
                // Native WebView2 / WKWebView paint above QML and ignore overlay z-order.
                // The Sky page is 0×0 while another tab is current, so this view lives
                // on the window and keeps a real size while parked. Creating WebView2
                // at 0×0 is what previously left a black atlas after opening SKY.
                // Linux Qt WebEngine composites in the scene graph. Parking that item
                // at -4096 culls the delegated frame and leaves the SKY slot empty.
                readonly property bool nativeMapOverlay: Qt.platform.os === "windows"
                                                           || Qt.platform.os === "osx"
                parent: mapLoader.nativeMapOverlay ? root.contentItem : mapSlot
                readonly property bool nativeMapVisible: skyPage.mapLive
                    && !root.appModalOpen
                    && mapSlot.width > 1
                    && (!mapLoader.nativeMapOverlay || skyPage.mapInitialReady)
                readonly property real layoutTick: root.width + root.height + root.currentPage
                    + mapSlot.width + mapSlot.height
                width: mapLoader.nativeMapOverlay
                       ? (mapSlot.width > 1 ? mapSlot.width : Math.max(Theme.px(320), root.width - Theme.px(24)))
                       : mapSlot.width
                height: mapLoader.nativeMapOverlay
                        ? (mapSlot.height > 1 ? mapSlot.height : Math.max(Theme.px(220), root.height - Theme.px(180)))
                        : mapSlot.height
                x: {
                    void mapLoader.layoutTick
                    if (!mapLoader.nativeMapOverlay)
                        return 0
                    if (!mapLoader.nativeMapVisible)
                        return -4096
                    return mapSlot.mapToItem(root.contentItem, 0, 0).x
                }
                y: {
                    void mapLoader.layoutTick
                    if (!mapLoader.nativeMapOverlay)
                        return 0
                    if (!mapLoader.nativeMapVisible)
                        return 1
                    return mapSlot.mapToItem(root.contentItem, 0, 0).y
                }
                // Keep the map after the first visit. Destroying the Linux
                // WebEngine on every page change reloaded Stellarium and Aladin.
                active: skyPage.webReady && root.skyToolsEnabled && (
                    skyPage.mapLive || skyPage.mapKeepAlive
                ) && (
                    mapLoader.nativeMapOverlay
                    || mapSlot.width > 1
                    || skyPage.mapKeepAlive
                )
                source: Qt.resolvedUrl(backend.skyMapUsesStellariumWeb ? "SkyWebView.qml" : "SkyAtlasView.qml")
                onLoaded: {
                    skyPage.mapKeepAlive = true
                    const map = mapLoader.item
                    if (!map)
                        return
                    map.shown = Qt.binding(() => skyPage.mapLive && !root.appModalOpen)
                    map.mosaicColumns = Qt.binding(() => columnsBox.value)
                    map.mosaicRows = Qt.binding(() => rowsBox.value)
                    map.mosaicOverlap = Qt.binding(() => overlapBox.value / 100)
                    map.mosaicPa = Qt.binding(() => backend.mosaicPaManual ? paBox.value : backend.mosaicPa)
                    map.liveOverlay = Qt.binding(() => skyStore.liveFovOverlay)
                    map.liveOpacity = Qt.binding(() => skyPage.clampOpacity(skyStore.liveFovOpacity))
                    map.savedView = Qt.binding(() => skyStore.viewSaved ? ({
                        ra_hours: skyStore.viewRaHours,
                        dec_degrees: skyStore.viewDecDegrees,
                        fov: skyStore.viewFov
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
                text: backend.skyMapUsesStellariumWeb
                      ? (backend.skyWebBlockedByGpu
                         ? "Stellarium Web cannot run inside this window because OpenGL is disabled. Open it in a browser, then import the target here."
                         : "Stellarium Web is not available in this window. Open it in a browser to find a target, then come back if the map loads.")
                      : (backend.skyWebBlockedByGpu
                         ? "Aladin Lite cannot run inside this window because OpenGL is disabled. Open the atlas in a browser, then import the target here."
                         : "Aladin Lite is not available in this window. Open it in a browser to find a target, then come back if the map loads.")
            }

            HudButton {
                visible: !skyPage.webReady
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Theme.s4
                text: backend.skyMapUsesStellariumWeb ? "OPEN STELLARIUM WEB" : "OPEN ALADIN LITE"
                onClicked: backend.openExternalUrl(backend.skyMapUsesStellariumWeb
                                                   ? backend.stellariumWebUrl
                                                   : "https://aladin.cds.unistra.fr/AladinLite/")
            }

            Connections {
                target: mapLoader.item
                function onContextMenuRequested(x, y) {
                    skyPage.openSkyMenu(x, y)
                }
                function onMenuDismissRequested() {
                    if (skyMenu.opened || skyMenu.visible)
                        skyMenu.close()
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
                objectName: "skyContextMenu"
                overlayEnabled: skyStore.liveFovOverlay
                overlayOpacity: skyPage.clampOpacity(skyStore.liveFovOpacity)
                dblclickTrack: skyStore.dblclickTrack
                hasTarget: skyPage.mapHasTarget
                hasFovCenter: !!skyPage.fovCenter
                fovCenterText: skyPage.fovCenterText
                atlasMenuAvailable: !backend.skyMapUsesStellariumWeb && skyPage.webReady
                trackEnabled: !!(backend.selectedDevice && backend.selectedDevice.connected)
                              && root.scopePending === ""
                              && !root.scopeImaging
                              && !root.scopeStacking
                              && root.scopeTelemetry.goto_state !== "running"
                              && root.scopeTelemetry.goto_state !== "solving"
                              && root.scopeTelemetry.goto_state !== "stopping"
                              && (root.scopeActivity === "" || root.scopeActivity === "goto"
                                  || !!root.scopeTelemetry.tracking_active)
                onAtlasMenuRequested: skyPage.openAtlasMenu()
                onEnterRaDecRequested: Qt.callLater(skyPage.openRaDecDialog)
                onClipboardGotoRequested: {
                    skyMenu.refreshClipboard()
                    if (!skyMenu.clipboardValid)
                        return
                    const map = mapLoader.item
                    if (!map || typeof map.setView !== "function")
                        return
                    if (typeof map.beginViewHold === "function")
                        map.beginViewHold()
                    map.setView(skyMenu.clipboardRaHours, skyMenu.clipboardDecDegrees)
                }
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
                onFovTargetRequested: skyPage.useFovCenterAsTarget()
                onTrackSelected: skyPage.withSkySources("track", true)
            }

            Rectangle {
                id: mapBootOverlay
                anchors.fill: parent
                anchors.margins: Theme.px(1)
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
                    text: backend.skyMapUsesStellariumWeb ? "Loading Stellarium Web…" : "Loading Aladin Lite…"
                }
            }
        }
    }

    Connections {
        target: skyRaDecDialog
        function onFormatIndexChanged() {
            skyStore.coordFormatIndex = skyPage.clampInt(skyRaDecDialog.formatIndex, 0, 3, 0)
        }
    }
}
