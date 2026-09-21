import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtCore
import ".."

HudMenu {
    id: sessionContextMenu
    property var sessionData: ({})
    readonly property string sessionId: String((sessionData && sessionData.id) || "")
    readonly property string sessionStatus: String((sessionData && sessionData.status) || "")
    readonly property string coordinates: Util.targetCoordinates(sessionData)
    property var selectionItems: []
    property var selectedMap: ({})
    readonly property int selectedCount: Util.idSetCount(selectedMap)
    readonly property bool editSelection: !!(sessionId && Util.idSetHas(selectedMap, sessionId) && selectedCount > 1)
    signal selectAllRequested()
    signal unselectAllRequested()
    signal editRequested(var session)
    signal editSelectedRequested()
    property bool showExpandCollapse: false
    property bool canExpandAll: false
    property bool canCollapseAll: false
    signal expandAllRequested()
    signal collapseAllRequested()

    HudMenuItem {
        text: sessionContextMenu.editSelection ? "Edit selected" : "Edit"
        glyph: "\uE70F"
        enabled: sessionContextMenu.sessionStatus !== "running" || sessionContextMenu.editSelection
        onTriggered: {
            if (sessionContextMenu.editSelection)
                sessionContextMenu.editSelectedRequested()
            else
                sessionContextMenu.editRequested(sessionContextMenu.sessionData)
        }
    }
    HudMenuItem {
        text: "Run now"
        glyph: "\uE768"
        enabled: sessionContextMenu.sessionStatus !== "running"
        onTriggered: backend.runNow(sessionContextMenu.sessionId)
    }
    HudMenuItem {
        text: "Stop session"
        glyph: "\uE71A"
        destructive: true
        enabled: sessionContextMenu.sessionStatus === "running"
        onTriggered: backend.stopSession(sessionContextMenu.sessionId)
    }
    HudMenuItem {
        text: "Skip"
        glyph: "\uE769"
        enabled: sessionContextMenu.sessionStatus === "planned"
        onTriggered: backend.skipSession(sessionContextMenu.sessionId)
    }
    HudMenuItem {
        text: "Reset"
        glyph: "\uE72C"
        enabled: Util.canReset(sessionContextMenu.sessionStatus)
        onTriggered: backend.resetSession(sessionContextMenu.sessionId)
    }
    HudMenuItem {
        text: "Duplicate"
        glyph: "\uE8C8"
        onTriggered: backend.duplicateSession(sessionContextMenu.sessionId)
    }
    MoveDeviceMenu {
        sessionIds: {
            const keys = Util.idSetKeys(sessionContextMenu.selectedMap)
            if (sessionContextMenu.sessionId && Util.idSetHas(sessionContextMenu.selectedMap, sessionContextMenu.sessionId) && keys.length > 1)
                return keys
            return sessionContextMenu.sessionId ? [sessionContextMenu.sessionId] : []
        }
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Copy target name"
        glyph: "\uE8C8"
        enabled: !!(sessionContextMenu.sessionData && sessionContextMenu.sessionData.target_name)
        onTriggered: backend.copyText(String(sessionContextMenu.sessionData.target_name))
    }
    HudMenuItem {
        text: "Copy RA / Dec"
        glyph: "\uE8C8"
        enabled: sessionContextMenu.coordinates !== ""
        onTriggered: backend.copyText(sessionContextMenu.coordinates)
    }
    HudMenuSeparator {
        visible: sessionContextMenu.showExpandCollapse
        height: visible ? implicitHeight : 0
    }
    HudMenuItem {
        objectName: "session-expand-all"
        text: "Expand all"
        glyph: "\uE70D"
        visible: sessionContextMenu.showExpandCollapse
        enabled: sessionContextMenu.canExpandAll
        accessibleDescription: "Expand every mosaic session group on this list"
        onTriggered: sessionContextMenu.expandAllRequested()
    }
    HudMenuItem {
        objectName: "session-collapse-all"
        text: "Collapse all"
        glyph: "\uE70E"
        visible: sessionContextMenu.showExpandCollapse
        enabled: sessionContextMenu.canCollapseAll
        accessibleDescription: "Collapse every mosaic session group on this list"
        onTriggered: sessionContextMenu.collapseAllRequested()
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Select all"
        glyph: "\uE8A5"
        enabled: (sessionContextMenu.selectionItems || []).length > 0
        onTriggered: sessionContextMenu.selectAllRequested()
    }
    HudMenuItem {
        text: "Unselect all"
        glyph: "\uE711"
        enabled: Util.idSetCount(sessionContextMenu.selectedMap) > 0
        onTriggered: sessionContextMenu.unselectAllRequested()
    }
    HudMenuSeparator {}
    HudMenuItem {
        text: "Delete"
        glyph: "\uE74D"
        destructive: true
        enabled: sessionContextMenu.sessionStatus !== "running"
        onTriggered: backend.deleteSession(sessionContextMenu.sessionId)
    }
}
