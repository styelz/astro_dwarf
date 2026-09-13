import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Window
import QtMultimedia
import QtCore
import ".."
import "../components"

Item {
    id: mediaPage
    objectName: "mediaPage"
    readonly property var items: backend.mediaItems || []
    readonly property var selected: backend.selectedMedia || ({})
    readonly property bool busy: backend.mediaBusy !== ""
    readonly property bool hasIp: !!(backend.selectedDevice && backend.selectedDevice.ip_address)
    readonly property bool scopeOnline: !!(backend.selectedDevice && backend.selectedDevice.connected)
    readonly property bool onDevice: backend.mediaSource !== "local"
    readonly property bool albumLocked: backend.mediaLocked && mediaPage.onDevice
    readonly property bool mediaError: {
        const s = String(backend.mediaStatus || "").toLowerCase()
        return s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0
    }
    property string loadedKey: ""
    property string boundDeviceId: ""
    property var selectedIds: ({})
    property string selectionAnchorId: ""
    readonly property int selectedCount: Util.idSetCount(selectedIds)
    readonly property var downloadTargetIds: {
        if (mediaPage.selectedCount > 0)
            return Util.idSetKeys(mediaPage.selectedIds)
        const id = String((backend.selectedMedia && backend.selectedMedia.id) || "")
        return id ? [id] : []
    }
    readonly property bool canDownload: mediaPage.onDevice && !mediaPage.albumLocked && !mediaPage.busy && mediaPage.scopeOnline && mediaPage.downloadTargetIds.length > 0
    readonly property string emptyText: {
        if (mediaPage.albumLocked)
            return backend.mediaStatus || "The telescope album isn't available while it's capturing. Wait until imaging finishes, or switch to Local."
        if (backend.mediaBusy === "list")
            return "Reading the telescope album…"
        if (backend.mediaStatus)
            return backend.mediaStatus
        if (backend.mediaSource === "local")
            return "Downloaded stacked frames and stills appear here. Open a session on the telescope and save it."
        if (!mediaPage.hasIp)
            return "Set the telescope IP in Settings, then refresh to browse sessions on this device."
        if (!mediaPage.scopeOnline)
            return "Connect this telescope to browse its album."
        if (backend.mediaSource === "stills")
            return "No photos, videos, or bursts found on this telescope. Capture, then refresh. DSO stacks are under Astro."
        return "No astro sessions found on this telescope. Finished DSO and manual stacks show up here."
    }

    onAlbumLockedChanged: {
        if (mediaPage.albumLocked) {
            mediaPage.clearSelection()
            lightbox.close()
            mediaMenu.close()
            return
        }
        mediaPage.loadedKey = ""
        mediaPage.maybeLoad()
    }
    onScopeOnlineChanged: {
        if (!mediaPage.scopeOnline)
            return
        mediaPage.loadedKey = ""
        mediaPage.maybeLoad()
    }

    function sourceKey() {
        return backend.selectedDeviceId + ":" + backend.mediaSource
    }
    function refresh() {
        mediaPage.loadedKey = mediaPage.sourceKey()
        backend.refreshMedia(backend.selectedDeviceId, false)
    }
    function maybeLoad() {
        if (root.currentPage !== root.mediaPageIndex)
            return
        if (mediaPage.albumLocked)
            return
        if (mediaPage.onDevice && !mediaPage.scopeOnline)
            return
        const key = mediaPage.sourceKey()
        if (mediaPage.loadedKey === key && backend.mediaSource === "local")
            return
        if (mediaPage.loadedKey === key && (backend.mediaItems.length > 0 || backend.mediaBusy !== "" || backend.mediaStatus !== ""))
            return
        mediaPage.loadedKey = key
        backend.refreshMedia(backend.selectedDeviceId, true)
    }
    function openSelected() {
        if (!backend.selectedMedia || !backend.selectedMedia.id)
            return
        lightbox.open()
    }
    function downloadItems(ids) {
        const chosen = Array.isArray(ids) ? ids : Util.idSetKeys(ids)
        if (mediaPage.albumLocked || !mediaPage.onDevice || !mediaPage.scopeOnline || mediaPage.busy || !chosen.length)
            return
        backend.downloadMediaItems(backend.selectedDeviceId, chosen)
    }
    function downloadSelected() {
        mediaPage.downloadItems(mediaPage.downloadTargetIds)
    }
    function downloadClickedItem(item) {
        const id = String((item && item.id) || "")
        backend.selectMedia(id)
        if (mediaPage.selectedCount > 1 && Util.idSetHas(mediaPage.selectedIds, id))
            mediaPage.downloadSelected()
        else
            mediaPage.downloadItems(id ? [id] : [])
    }
    function deleteClickedItem(item) {
        const id = String((item && item.id) || "")
        if (mediaPage.selectedCount > 1 && Util.idSetHas(mediaPage.selectedIds, id))
            mediaPage.confirmDelete(mediaPage.selectedIds)
        else
            mediaPage.confirmDelete(id ? [id] : [])
    }
    function selectClick(id, shift) {
        const result = Util.clickSelect(selectedIds, mediaPage.items, id, shift, selectionAnchorId)
        selectedIds = result.map
        selectionAnchorId = result.anchor
    }
    function confirmDelete(ids) {
        const chosen = Array.isArray(ids) ? ids : Util.idSetKeys(ids)
        if (!chosen.length)
            return
        root.confirmBulkDelete("deleteMedia", chosen, "file")
    }
    function clearSelection() {
        mediaPage.selectedIds = ({})
        mediaPage.selectionAnchorId = ""
    }
    function closeViewer() {
        lightbox.close()
    }
    function openMediaMenu(item, pos) {
        const data = item || ({})
        const id = String(data.id || "")
        if (id)
            backend.selectMedia(id)
        mediaMenu.itemData = data
        if (pos)
            mediaMenu.popup(pos)
        else
            mediaMenu.popup()
    }
    function openCurrentTile() {
        const item = mediaPage.items[mediaGrid.currentIndex]
        if (!item || !item.id)
            return
        backend.selectMedia(String(item.id))
        mediaPage.openSelected()
    }

    function showSource(source) {
        mediaPage.clearSelection()
        backend.setMediaSource(source)
        mediaPage.loadedKey = backend.selectedDeviceId + ":" + source
    }

    Connections {
        target: backend
        function onSelectedDeviceChanged() {
            if (mediaPage.boundDeviceId === backend.selectedDeviceId)
                return
            mediaPage.boundDeviceId = backend.selectedDeviceId
            mediaPage.loadedKey = ""
            mediaPage.clearSelection()
            if (root.currentPage !== root.mediaPageIndex)
                return
            mediaPage.maybeLoad()
        }
        function onMediaItemsChanged() {
            mediaPage.selectedIds = Util.pruneIdSet(mediaPage.selectedIds, mediaPage.items)
            if (lightbox.visible && !(mediaPage.selected && mediaPage.selected.id))
                lightbox.close()
        }
    }
    Connections {
        target: root
        function onCurrentPageChanged() {
            if (root.currentPage === root.mediaPageIndex)
                mediaPage.maybeLoad()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.s2

        PageHeader {
            title: "MEDIA"
            subtitle: mediaPage.albumLocked
                ? "Unavailable while the telescope is capturing"
                : (backend.mediaSource === "local"
                    ? (mediaPage.items.length + " downloaded file" + (mediaPage.items.length === 1 ? "" : "s") + "  ·  local album")
                    : (mediaPage.items.length + " on " + (backend.selectedDevice.name || "telescope") + (mediaPage.hasIp ? "  ·  " + backend.selectedDevice.ip_address : "")))
            HudButton {
                text: "ASTRO"
                accessibleDescription: backend.mediaSource === "astro" ? "On-device astro sessions, selected" : "On-device astro sessions"
                buttonColor: backend.mediaSource === "astro" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "astro" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("astro")
            }
            HudButton {
                text: "STILLS"
                accessibleDescription: backend.mediaSource === "stills" ? "On-device camera files, selected" : "On-device camera files"
                buttonColor: backend.mediaSource === "stills" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "stills" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("stills")
            }
            HudButton {
                text: "LOCAL"
                accessibleDescription: backend.mediaSource === "local" ? "Local album, selected" : "Local album"
                buttonColor: backend.mediaSource === "local" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "local" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("local")
            }
            HudButton {
                text: backend.mediaBusy === "list" ? "LISTING…" : "REFRESH"
                enabled: !mediaPage.albumLocked && !mediaPage.busy && (backend.mediaSource === "local" || mediaPage.scopeOnline)
                busy: backend.mediaBusy === "list"
                busyText: "LISTING…"
                onClicked: mediaPage.refresh()
            }
            HudButton {
                text: backend.mediaBusy === "download" ? "SAVING…" : "DOWNLOAD"
                enabled: mediaPage.canDownload
                busy: backend.mediaBusy === "download"
                busyText: "SAVING…"
                onClicked: mediaPage.downloadSelected()
            }
            HudButton {
                text: "OPEN FOLDER"
                tooltip: "Opens the local album folder on this computer"
                onClicked: backend.openAlbumFolder()
            }
        }

        HudPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: mediaPage.albumLocked
                ? "ON DEVICE  ·  UNAVAILABLE"
                : (backend.mediaSource === "astro" ? "ON DEVICE  ·  ASTRO SESSIONS" : (backend.mediaSource === "stills" ? "ON DEVICE  ·  CAMERA" : "LOCAL ALBUM"))

            SelectionBar {
                selectedCount: mediaPage.selectedCount
                totalCount: mediaPage.items.length
                noun: "file"
                allowEdit: false
                deleteEnabled: !mediaPage.busy && !mediaPage.albumLocked
                active: !mediaPage.albumLocked && mediaPage.items.length > 0
                onSelectAllRequested: mediaPage.selectedIds = Util.idSetAll(mediaPage.items, true)
                onClearRequested: mediaPage.clearSelection()
                onDeleteRequested: {
                    if (mediaPage.busy || mediaPage.albumLocked)
                        return
                    mediaPage.confirmDelete(mediaPage.selectedIds)
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridView {
                    id: mediaGrid
                    anchors.fill: parent
                    clip: true
                    visible: !mediaPage.albumLocked && mediaPage.items.length > 0
                    enabled: visible
                    focus: true
                    activeFocusOnTab: true
                    keyNavigationEnabled: true
                    highlightFollowsCurrentItem: true
                    highlightMoveDuration: 0
                    cellWidth: Math.max(148, Math.floor(width / Math.max(1, Math.floor(width / 168))))
                    cellHeight: cellWidth + 36
                    model: backend.mediaItems
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: HiddenBar {}
                    Keys.onReturnPressed: (event) => { event.accepted = true; mediaPage.openCurrentTile() }
                    Keys.onSpacePressed: (event) => { event.accepted = true; mediaPage.openCurrentTile() }
                    highlight: Rectangle {
                        color: "transparent"
                        border.color: Theme.accent
                        border.width: Theme.focusStroke
                        radius: Theme.radius
                    }
                    delegate: Item {
                        id: tile
                        required property var modelData
                        required property int index
                        width: mediaGrid.cellWidth
                        height: mediaGrid.cellHeight
                        readonly property bool selected: backend.mediaSelectedId === String(modelData.id || "")
                        readonly property bool checked: Util.idSetHas(mediaPage.selectedIds, String(modelData.id || ""))
                        HoverHandler { id: tileHover }
                        readonly property bool highlighted: tile.selected || tile.checked
                        Accessible.role: Accessible.Button
                        Accessible.name: String(tile.modelData.target || tile.modelData.file_name || "Untitled")
                        Accessible.selectable: true
                        Accessible.selected: tile.selected || tile.checked
                        Accessible.onPressAction: {
                            mediaGrid.currentIndex = tile.index
                            backend.selectMedia(String(tile.modelData.id || ""))
                            mediaPage.openSelected()
                        }
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: Theme.s1
                            color: tile.highlighted ? Theme.fillActive : Theme.inputBg
                            border.color: tile.highlighted ? Theme.accent : Theme.outlineSoft
                            radius: Theme.radius
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: Theme.s1 + 2
                                spacing: Theme.s1
                                Item {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Rectangle {
                                        anchors.fill: parent
                                        visible: !previewImage.visible
                                        color: Theme.surface
                                        Text {
                                            anchors.centerIn: parent
                                            text: Util.mediaKindGlyph(tile.modelData)
                                            color: Theme.muted
                                            font.pixelSize: Theme.fontXl
                                        }
                                    }
                                    Image {
                                        id: previewImage
                                        anchors.fill: parent
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        cache: true
                                        source: tile.modelData.thumbnail_url || (Util.isVideoMedia(tile.modelData) ? "" : (tile.modelData.image_url || ""))
                                        visible: source !== "" && status === Image.Ready
                                    }
                                    Rectangle {
                                        visible: !!Util.mediaKindLabel(tile.modelData)
                                        anchors.left: parent.left
                                        anchors.top: parent.top
                                        anchors.margins: Theme.s1
                                        color: Theme.surface
                                        border.color: Theme.outlineSoft
                                        radius: Theme.radius
                                        width: kindLabel.implicitWidth + Theme.s2
                                        height: kindLabel.implicitHeight + Theme.s1
                                        Text {
                                            id: kindLabel
                                            anchors.centerIn: parent
                                            text: Util.mediaKindLabel(tile.modelData)
                                            color: Theme.textSecondary
                                            font.pixelSize: Theme.fontXs
                                            font.bold: true
                                        }
                                    }
                                    Rectangle {
                                        visible: !!tile.modelData.downloaded
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: Theme.s1
                                        width: Theme.s5 - 2
                                        height: Theme.s5 - 2
                                        radius: Theme.radius
                                        color: Theme.fillSuccess
                                        Text {
                                            anchors.centerIn: parent
                                            text: "↓"
                                            color: Theme.success
                                            font.pixelSize: Theme.fontSm
                                            font.bold: true
                                        }
                                    }
                                    SelectBox {
                                        anchors.left: parent.left
                                        anchors.bottom: parent.bottom
                                        anchors.margins: Theme.s1 + 2
                                        checked: tile.checked
                                        revealed: tileHover.hovered || mediaPage.selectedCount > 0
                                        onToggled: (shiftHeld) => mediaPage.selectClick(String(tile.modelData.id || ""), shiftHeld)
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tile.modelData.target || tile.modelData.file_name || "Untitled"
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontSm
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tile.modelData.date || (tile.modelData.downloaded ? "SAVED LOCALLY" : (backend.mediaSource === "local" ? "" : "ON DEVICE"))
                                    color: Theme.textSecondary
                                    font.pixelSize: Theme.fontXs
                                    elide: Text.ElideRight
                                }
                            }
                            TapHandler {
                                onTapped: {
                                    mediaGrid.currentIndex = tile.index
                                    backend.selectMedia(String(tile.modelData.id || ""))
                                    mediaPage.openSelected()
                                }
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: function (eventPoint) {
                                    mediaGrid.currentIndex = tile.index
                                    mediaPage.openMediaMenu(tile.modelData, mapToItem(mediaPage, eventPoint.position.x, eventPoint.position.y))
                                }
                            }
                        }
                    }
                }

                EmptyHint {
                    anchors.centerIn: parent
                    visible: mediaPage.albumLocked || mediaPage.items.length === 0
                    mode: backend.mediaBusy === "list" ? "loading"
                          : mediaPage.albumLocked || mediaPage.mediaError || (mediaPage.onDevice && !mediaPage.scopeOnline) ? "unavailable"
                          : "empty"
                    glyph: mediaPage.albumLocked ? "⊘" : (backend.mediaSource === "local" ? "▤" : "◈")
                    text: mediaPage.emptyText
                }
            }
        }
    }

    Popup {
        id: lightbox
        objectName: "mediaLightbox"
        modal: true
        focus: true
        padding: 0
        width: Math.min(root.width * 0.82, root.width - 48)
        height: Math.min(root.height * 0.88, root.height - 36)
        anchors.centerIn: Overlay.overlay
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: DialogFrame {}
        property bool viewEnhance: true
        property bool viewDeep: false
        readonly property bool enhanceOn: lightbox.viewEnhance && Util.shouldEnhanceMedia(mediaPage.selected)
        readonly property bool isVideo: Util.isVideoMedia(mediaPage.selected)
        readonly property string selectedKey: String((mediaPage.selected && mediaPage.selected.id) || "")
        readonly property string enhanceProfile: lightbox.viewDeep ? "deep" : "std"
        function syncEnhanceFromTheme() {
            viewEnhance = Theme.enhanceImages
            viewDeep = Theme.deepCleanImages
        }
        Connections {
            target: Theme
            function onEnhanceImagesChanged() { lightbox.syncEnhanceFromTheme() }
            function onDeepCleanImagesChanged() { lightbox.syncEnhanceFromTheme() }
        }
        readonly property bool enhanceFailed: {
            backend.enhanceCacheGeneration
            return lightbox.enhanceOn && !lightbox.isVideo && !!lightbox.rawUrl && backend.mediaEnhanceFailed(lightbox.rawUrl, lightbox.enhanceProfile)
        }
        readonly property string rawUrl: {
            const item = mediaPage.selected
            if (!item)
                return ""
            if (item.local_path)
                return backend.mediaFileUrl(String(item.local_path))
            return String(item.image_url || item.thumbnail_url || "")
        }
        readonly property string posterUrl: {
            const item = mediaPage.selected
            if (!item)
                return ""
            return String(item.thumbnail_url || "")
        }
        property string heldCleanUrl: ""
        readonly property string cleanUrl: {
            lightbox.selectedKey
            lightbox.viewEnhance
            lightbox.viewDeep
            Theme.enhanceDenoise
            Theme.enhanceSkyCrush
            backend.enhanceCacheGeneration
            if (!lightbox.enhanceOn || !lightbox.rawUrl || lightbox.isVideo)
                return ""
            return backend.mediaEnhanceSource(lightbox.rawUrl, lightbox.enhanceProfile)
        }
        onSelectedKeyChanged: {
            heldCleanUrl = ""
            clipPlayer.stop()
        }
        onClosed: clipPlayer.stop()
        onOpened: {
            lightbox.syncEnhanceFromTheme()
            if (lightbox.isVideo && clipPlayer.source !== "")
                clipPlayer.play()
        }
        onEnhanceOnChanged: if (!enhanceOn) heldCleanUrl = ""
        onCleanUrlChanged: if (cleanUrl !== "") heldCleanUrl = cleanUrl
        contentItem: ColumnLayout {
            spacing: 0
            Accessible.name: mediaPage.selected.target || mediaPage.selected.file_name || "Media viewer"
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.windowBase
                Image {
                    id: rawImage
                    objectName: "rawImage"
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    visible: !lightbox.isVideo && !lightbox.enhanceOn && source !== "" && status === Image.Ready
                    source: lightbox.enhanceOn || lightbox.isVideo ? "" : lightbox.rawUrl
                }
                Image {
                    id: cleanImage
                    objectName: "cleanImage"
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    visible: !lightbox.isVideo && lightbox.enhanceOn && source !== "" && status === Image.Ready
                    source: lightbox.cleanUrl !== "" ? lightbox.cleanUrl : lightbox.heldCleanUrl
                }
                Video {
                    id: clipPlayer
                    objectName: "mediaVideo"
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    fillMode: VideoOutput.PreserveAspectFit
                    source: lightbox.isVideo ? lightbox.rawUrl : ""
                    visible: lightbox.isVideo && source !== ""
                    autoPlay: lightbox.visible && lightbox.isVideo
                    loops: 1
                }
                Image {
                    id: videoPoster
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    visible: lightbox.isVideo && source !== "" && status === Image.Ready && clipPlayer.playbackState === MediaPlayer.StoppedState
                    source: lightbox.isVideo ? lightbox.posterUrl : ""
                }
                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: Theme.s4
                    visible: rawImage.visible || cleanImage.visible || clipPlayer.visible
                    color: Theme.surface
                    border.color: Theme.outline
                    radius: Theme.radius
                    width: modeLabel.implicitWidth + Theme.s3
                    height: modeLabel.implicitHeight + Theme.s2
                    Text {
                        id: modeLabel
                        anchors.centerIn: parent
                        text: lightbox.isVideo ? "VIDEO" : (lightbox.enhanceFailed ? "ENHANCE FAILED" : (lightbox.enhanceOn ? "SMOOTHED" : "RAW"))
                        color: lightbox.enhanceOn && !lightbox.isVideo ? Theme.accent : Theme.textSecondary
                        font.pixelSize: Theme.fontSm
                        font.letterSpacing: Theme.tracking2
                        font.bold: true
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: (!rawImage.visible && !cleanImage.visible && !clipPlayer.visible && !videoPoster.visible)
                             || (lightbox.isVideo && !!clipPlayer.errorString)
                             || (lightbox.isVideo && clipPlayer.playbackState === MediaPlayer.StoppedState && !videoPoster.visible && !clipPlayer.errorString)
                    text: lightbox.isVideo ? (clipPlayer.errorString || "LOADING VIDEO…") : (lightbox.enhanceFailed ? "COULD NOT ENHANCE" : (lightbox.enhanceOn ? "SMOOTHING…" : (mediaPage.busy ? "LOADING…" : "NO PREVIEW")))
                    color: lightbox.enhanceFailed || (lightbox.isVideo && clipPlayer.errorString) ? Theme.warning : Theme.muted
                    font.pixelSize: Theme.fontMd
                    font.letterSpacing: Theme.tracking2
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Theme.s4
                    visible: lightbox.enhanceOn && lightbox.cleanUrl === "" && cleanImage.visible
                    text: lightbox.enhanceFailed ? "COULD NOT ENHANCE" : "SMOOTHING…"
                    color: lightbox.enhanceFailed ? Theme.warning : Theme.accent
                    font.pixelSize: Theme.fontSm
                    font.letterSpacing: Theme.tracking2
                }
                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: function (eventPoint) {
                        mediaPage.openMediaMenu(mediaPage.selected, mapToItem(mediaPage, eventPoint.position.x, eventPoint.position.y))
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: lightboxMeta.implicitHeight + Theme.s5
                color: Theme.surface
                ColumnLayout {
                    id: lightboxMeta
                    anchors.fill: parent
                    anchors.margins: Theme.s3
                    spacing: Theme.s1 + 2
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: mediaPage.selected.target || mediaPage.selected.file_name || "Untitled"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontLg
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        HudButton {
                            objectName: "lightboxEnhanceButton"
                            text: lightbox.viewEnhance ? "ENHANCE ON" : "ENHANCE OFF"
                            visible: Util.shouldEnhanceMedia(mediaPage.selected)
                            buttonColor: lightbox.viewEnhance ? Theme.fillActive : Theme.inputBg
                            foregroundColor: lightbox.viewEnhance ? Theme.accent : Theme.textSecondary
                            onClicked: lightbox.viewEnhance = !lightbox.viewEnhance
                        }
                        HudButton {
                            objectName: "lightboxDeepButton"
                            text: lightbox.viewDeep ? "DEEP ON" : "DEEP CLEAN"
                            visible: Util.shouldEnhanceMedia(mediaPage.selected) && lightbox.viewEnhance
                            buttonColor: lightbox.viewDeep ? Theme.fillActive : Theme.inputBg
                            foregroundColor: lightbox.viewDeep ? Theme.accent : Theme.textSecondary
                            onClicked: lightbox.viewDeep = !lightbox.viewDeep
                        }
                        HudButton {
                            text: "DOWNLOAD"
                            visible: mediaPage.onDevice
                            enabled: !mediaPage.albumLocked && !mediaPage.busy && mediaPage.scopeOnline && !!(mediaPage.selected.id)
                            busy: backend.mediaBusy === "download"
                            busyText: "SAVING…"
                            onClicked: mediaPage.downloadItems(mediaPage.selected.id ? [mediaPage.selected.id] : [])
                        }
                        HudButton {
                            objectName: "lightboxDeleteButton"
                            text: backend.mediaBusy === "delete" ? "DELETING…" : "DELETE"
                            enabled: !mediaPage.albumLocked && !mediaPage.busy && !!(mediaPage.selected.id) && (backend.mediaSource === "local" || mediaPage.scopeOnline)
                            busy: backend.mediaBusy === "delete"
                            busyText: "DELETING…"
                            buttonColor: Theme.fillDanger
                            foregroundColor: Theme.danger
                            onClicked: mediaPage.confirmDelete([mediaPage.selected.id])
                        }
                        HudButton {
                            text: mediaPage.selected.local_path ? "REVEAL" : "FOLDER"
                            tooltip: mediaPage.selected.local_path ? "Show this file on this computer" : "Opens the local album folder on this computer"
                            onClicked: {
                                if (mediaPage.selected.local_path)
                                    backend.revealMediaFile(mediaPage.selected.local_path)
                                else
                                    backend.openAlbumFolder()
                            }
                        }
                        HudButton { text: "CLOSE"; onClicked: lightbox.close() }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: {
                            const bits = []
                            if (mediaPage.selected.date)
                                bits.push(mediaPage.selected.date)
                            if (mediaPage.selected.exposure)
                                bits.push("Exposure " + mediaPage.selected.exposure + "s")
                            if (mediaPage.selected.gain)
                                bits.push("Gain " + mediaPage.selected.gain)
                            if (mediaPage.selected.ir_filter)
                                bits.push("IR " + mediaPage.selected.ir_filter)
                            if (mediaPage.selected.camera)
                                bits.push(mediaPage.selected.camera === "wide" ? "Wide" : "Tele")
                            if (mediaPage.selected.kind && mediaPage.selected.kind !== "photo" && mediaPage.selected.kind !== "astro")
                                bits.push(Util.mediaKindLabel(mediaPage.selected))
                            return bits.join("  ·  ") || (backend.mediaSource === "local" ? String(mediaPage.selected.file_name || "") : "On-device session")
                        }
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontMd
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }

    MediaContextMenu {
        id: mediaMenu
        selectionItems: mediaPage.items
        selectedMap: mediaPage.selectedIds
        onOpenRequested: item => {
            backend.selectMedia(String((item && item.id) || ""))
            mediaPage.openSelected()
        }
        onDownloadRequested: item => mediaPage.downloadClickedItem(item)
        onDeleteRequested: item => mediaPage.deleteClickedItem(item)
        onSelectAllRequested: mediaPage.selectedIds = Util.idSetAll(mediaPage.items, true)
        onUnselectAllRequested: mediaPage.clearSelection()
    }
}
