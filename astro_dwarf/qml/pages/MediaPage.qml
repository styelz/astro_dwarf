import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import ".."
import "../components"

Item {
    id: mediaPage
    readonly property var items: backend.mediaItems || []
    readonly property var selected: backend.selectedMedia || ({})
    readonly property bool busy: backend.mediaBusy !== ""
    readonly property bool hasIp: !!(backend.selectedDevice && backend.selectedDevice.ip_address)
    readonly property bool onDevice: backend.mediaSource !== "local"
    property string loadedKey: ""
    readonly property string emptyText: {
        if (backend.mediaBusy === "list")
            return "Reading the telescope album…"
        if (backend.mediaStatus)
            return backend.mediaStatus
        if (backend.mediaSource === "local")
            return "Downloaded stacked frames and stills appear here. Open a session on the telescope and save it."
        if (!mediaPage.hasIp)
            return "Set the telescope IP in Settings, then refresh to browse sessions on this device."
        if (backend.mediaSource === "stills")
            return "No still photos found on this telescope. Capture a photo, then refresh."
        return "No astro sessions found on this telescope. Finished DSO stacks show up here."
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
    function downloadSelected() {
        if (!mediaPage.onDevice || !backend.selectedMedia.id)
            return
        backend.downloadMedia(backend.selectedDeviceId, backend.selectedMedia.id)
    }

    function showSource(source) {
        backend.setMediaSource(source)
        mediaPage.loadedKey = backend.selectedDeviceId + ":" + source
    }

    Connections {
        target: backend
        function onSelectedDeviceChanged() {
            mediaPage.loadedKey = ""
            if (root.currentPage !== root.mediaPageIndex)
                return
            mediaPage.maybeLoad()
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
        spacing: 10

        PageHeader {
            title: "MEDIA"
            subtitle: backend.mediaSource === "local"
                ? (mediaPage.items.length + " downloaded file" + (mediaPage.items.length === 1 ? "" : "s") + "  ·  local album")
                : (mediaPage.items.length + " on " + (backend.selectedDevice.name || "telescope") + (mediaPage.hasIp ? "  ·  " + backend.selectedDevice.ip_address : ""))
            HudButton {
                text: "ASTRO"
                buttonColor: backend.mediaSource === "astro" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "astro" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("astro")
            }
            HudButton {
                text: "STILLS"
                buttonColor: backend.mediaSource === "stills" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "stills" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("stills")
            }
            HudButton {
                text: "LOCAL"
                buttonColor: backend.mediaSource === "local" ? Theme.fillActive : Theme.inputBg
                foregroundColor: backend.mediaSource === "local" ? Theme.accent : Theme.textSecondary
                onClicked: mediaPage.showSource("local")
            }
            HudButton {
                text: backend.mediaBusy === "list" ? "LISTING…" : "REFRESH"
                enabled: !mediaPage.busy && (backend.mediaSource === "local" || mediaPage.hasIp)
                busy: backend.mediaBusy === "list"
                busyText: "LISTING…"
                onClicked: mediaPage.refresh()
            }
            HudButton {
                text: backend.mediaBusy === "download" ? "SAVING…" : "DOWNLOAD"
                enabled: mediaPage.onDevice && !mediaPage.busy && !!(backend.selectedMedia && backend.selectedMedia.id)
                busy: backend.mediaBusy === "download"
                busyText: "SAVING…"
                onClicked: mediaPage.downloadSelected()
            }
            HudButton {
                text: "OPEN FOLDER"
                onClicked: backend.openAlbumFolder()
            }
        }

        HudPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: backend.mediaSource === "astro" ? "ON DEVICE  ·  ASTRO SESSIONS" : (backend.mediaSource === "stills" ? "ON DEVICE  ·  STILLS" : "LOCAL ALBUM")

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                GridView {
                    id: mediaGrid
                    anchors.fill: parent
                    clip: true
                    visible: mediaPage.items.length > 0
                    cellWidth: Math.max(148, Math.floor(width / Math.max(1, Math.floor(width / 168))))
                    cellHeight: cellWidth + 36
                    model: backend.mediaItems
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: HiddenBar {}
                    delegate: Item {
                        id: tile
                        required property var modelData
                        required property int index
                        width: mediaGrid.cellWidth
                        height: mediaGrid.cellHeight
                        readonly property bool selected: backend.mediaSelectedId === String(modelData.id || "")
                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: 4
                            color: tile.selected ? Theme.fillActive : Theme.inputBg
                            border.color: tile.selected ? Theme.accent : Theme.outlineSoft
                            radius: Theme.radius
                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 4
                                Item {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Rectangle {
                                        anchors.fill: parent
                                        visible: !previewImage.visible
                                        color: Theme.surface
                                        Text {
                                            anchors.centerIn: parent
                                            text: tile.modelData.source === "stills" ? "▣" : "◈"
                                            color: Theme.muted
                                            font.pixelSize: 22
                                        }
                                    }
                                    Image {
                                        id: previewImage
                                        anchors.fill: parent
                                        fillMode: Image.PreserveAspectCrop
                                        asynchronous: true
                                        cache: true
                                        source: tile.modelData.thumbnail_url || tile.modelData.image_url || ""
                                        visible: source !== "" && status === Image.Ready
                                    }
                                    Rectangle {
                                        visible: !!tile.modelData.downloaded
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: 4
                                        width: 18
                                        height: 18
                                        radius: 2
                                        color: Theme.fillSuccess
                                        Text {
                                            anchors.centerIn: parent
                                            text: "↓"
                                            color: Theme.success
                                            font.pixelSize: 10
                                            font.bold: true
                                        }
                                    }
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tile.modelData.target || tile.modelData.file_name || "Untitled"
                                    color: Theme.textPrimary
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: tile.modelData.date || (tile.modelData.downloaded ? "SAVED LOCALLY" : (backend.mediaSource === "local" ? "" : "ON DEVICE"))
                                    color: Theme.textSecondary
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                }
                            }
                            TapHandler {
                                onTapped: {
                                    backend.selectMedia(String(tile.modelData.id || ""))
                                    mediaPage.openSelected()
                                }
                            }
                        }
                    }
                }

                EmptyHint {
                    anchors.centerIn: parent
                    visible: mediaPage.items.length === 0
                    glyph: backend.mediaSource === "local" ? "▤" : "◈"
                    text: mediaPage.emptyText
                }
            }
        }
    }

    Popup {
        id: lightbox
        modal: true
        focus: true
        padding: 0
        width: Math.min(root.width * 0.82, root.width - 48)
        height: Math.min(root.height * 0.88, root.height - 36)
        anchors.centerIn: Overlay.overlay
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: DialogFrame {}
        contentItem: ColumnLayout {
            spacing: 0
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.windowBase
                Image {
                    id: lightboxImage
                    anchors.fill: parent
                    anchors.margins: 8
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                    source: mediaPage.selected.image_url || mediaPage.selected.thumbnail_url || ""
                }
                Text {
                    anchors.centerIn: parent
                    visible: lightboxImage.source == "" || lightboxImage.status !== Image.Ready
                    text: lightboxImage.status === Image.Loading || mediaPage.busy ? "LOADING…" : "NO PREVIEW"
                    color: Theme.muted
                    font.pixelSize: 12
                    font.letterSpacing: 1.4
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: lightboxMeta.implicitHeight + 20
                color: Theme.surface
                ColumnLayout {
                    id: lightboxMeta
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: mediaPage.selected.target || mediaPage.selected.file_name || "Untitled"
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        HudButton {
                            text: "DOWNLOAD"
                            visible: mediaPage.onDevice
                            enabled: !mediaPage.busy && !!(mediaPage.selected.id)
                            busy: backend.mediaBusy === "download"
                            busyText: "SAVING…"
                            onClicked: mediaPage.downloadSelected()
                        }
                        HudButton {
                            text: mediaPage.selected.local_path ? "REVEAL" : "FOLDER"
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
                            if (mediaPage.selected.downloaded)
                                bits.push("Saved locally")
                            return bits.join("  ·  ") || (backend.mediaSource === "local" ? mediaPage.selected.file_name : "On-device session")
                        }
                        color: Theme.textSecondary
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
