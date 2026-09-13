import QtQuick
import ".."

HudMenu {
    id: mediaContextMenu
    property var itemData: ({})
    property var selectionItems: []
    property var selectedMap: ({})
    readonly property string itemId: String((itemData && itemData.id) || "")
    readonly property string fileName: String((itemData && (itemData.file_name || itemData.target)) || "")
    readonly property string localPath: String((itemData && itemData.local_path) || "")
    readonly property int selectedCount: Util.idSetCount(selectedMap)
    readonly property bool onDevice: backend.mediaSource !== "local"
    readonly property bool albumLocked: !!backend.mediaLocked && mediaContextMenu.onDevice
    readonly property bool mediaBusy: backend.mediaBusy !== ""
    readonly property bool scopeOnline: !!(backend.selectedDevice && backend.selectedDevice.connected)
    signal openRequested(var item)
    signal downloadRequested(var item)
    signal deleteRequested(var item)
    signal selectAllRequested()
    signal unselectAllRequested()

    HudMenuItem {
        text: "Open"
        glyph: "\uE8A7"
        enabled: mediaContextMenu.itemId !== ""
        onTriggered: mediaContextMenu.openRequested(mediaContextMenu.itemData)
    }
    HudMenuItem {
        text: "Download"
        glyph: "\uE896"
        enabled: mediaContextMenu.onDevice && !mediaContextMenu.albumLocked && !mediaContextMenu.mediaBusy && mediaContextMenu.scopeOnline && mediaContextMenu.itemId !== ""
        onTriggered: mediaContextMenu.downloadRequested(mediaContextMenu.itemData)
    }
    HudMenuItem {
        text: mediaContextMenu.localPath ? "Reveal file" : "Open album folder"
        glyph: "\uE838"
        onTriggered: {
            if (mediaContextMenu.localPath)
                backend.revealMediaFile(mediaContextMenu.localPath)
            else
                backend.openAlbumFolder()
        }
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Copy file name"
        glyph: "\uE8C8"
        enabled: mediaContextMenu.fileName !== ""
        onTriggered: backend.copyText(mediaContextMenu.fileName)
    }
    HudMenuItem {
        text: "Copy local path"
        glyph: "\uE8C8"
        enabled: mediaContextMenu.localPath !== ""
        onTriggered: backend.copyText(mediaContextMenu.localPath)
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Select all"
        glyph: "\uE8A5"
        enabled: (mediaContextMenu.selectionItems || []).length > 0
        onTriggered: mediaContextMenu.selectAllRequested()
    }
    HudMenuItem {
        text: "Unselect all"
        glyph: "\uE711"
        enabled: mediaContextMenu.selectedCount > 0
        onTriggered: mediaContextMenu.unselectAllRequested()
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Delete"
        glyph: "\uE74D"
        destructive: true
        enabled: !mediaContextMenu.albumLocked && !mediaContextMenu.mediaBusy && mediaContextMenu.itemId !== "" && (!mediaContextMenu.onDevice || mediaContextMenu.scopeOnline)
        onTriggered: mediaContextMenu.deleteRequested(mediaContextMenu.itemData)
    }
}
