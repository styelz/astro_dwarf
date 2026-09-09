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
    signal selectAllRequested()
    signal unselectAllRequested()
    signal editRequested(var session)

    HudMenuItem {
        text: "Edit"
        glyph: "\uE70F"
        enabled: sessionContextMenu.sessionStatus !== "running"
        onTriggered: sessionContextMenu.editRequested(sessionContextMenu.sessionData)
    }
    HudMenuItem {
        text: "Run now"
        glyph: "\uE768"
        enabled: sessionContextMenu.sessionStatus !== "running"
        onTriggered: backend.runNow(sessionContextMenu.sessionId)
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
