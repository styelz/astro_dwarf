import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Shapes
import QtQuick.Window
import QtCore
import ".."
import "../components"

Item {
    Flickable {
        id: sessionsFlick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: Math.max(height, sessionsColumn.implicitHeight)
        interactive: contentHeight > height + 1
        ScrollBar.vertical: HiddenBar {}
        ScrollBar.horizontal: HiddenBar {}
    ColumnLayout {
        id: sessionsColumn
        width: sessionsFlick.width
        height: Math.max(implicitHeight, sessionsFlick.height)
        spacing: 10
        PageHeader {
            title: "SESSIONS"
            subtitle: {
                const planned = backend.sessions.filter(item => item.status === "planned").length
                const running = backend.sessions.filter(item => item.status === "running").length
                return planned + " planned · " + (running > 0 ? running + " running · " : "") + backend.templates.length + " template" + (backend.templates.length === 1 ? "" : "s")
            }
            HudButton { text: "IMPORT STELLARIUM"; busy: backend.uiBusy === "stellarium"; busyText: "IMPORTING…"; busyMs: 0; enabled: backend.uiBusy === ""; onClicked: backend.importStellarium() }
            HudButton { text: "IMPORT TELESCOPIUS"; busy: backend.uiBusy === "telescopius"; busyText: backend.uiBusy === "telescopius" ? "IMPORTING…" : "OPENING…"; enabled: backend.uiBusy === ""; onClicked: telescopiusDialog.open() }
            HudButton { text: "+ MANUAL SESSION"; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: sessionDialog.openForDate(Qt.formatDate(new Date(), "yyyy-MM-dd")) }
        }
        TabBar {
            id: sessionsTabs
            Layout.fillWidth: true
            background: Rectangle { color: "transparent" }
            TabButton {
                text: "SCHEDULED"
                font.letterSpacing: 1.2
                contentItem: Text { text: parent.text; color: parent.checked ? Theme.accent : Theme.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                background: Rectangle { color: parent.checked ? Theme.fillChecked : Theme.inputBg; border.color: parent.checked ? Theme.accent : Theme.outline }
            }
            TabButton {
                text: "TEMPLATES"
                font.letterSpacing: 1.2
                contentItem: Text { text: parent.text; color: parent.checked ? Theme.accent : Theme.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                background: Rectangle { color: parent.checked ? Theme.fillChecked : Theme.inputBg; border.color: parent.checked ? Theme.accent : Theme.outline }
            }
        }
        StackLayout {
            currentIndex: sessionsTabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 280
            Layout.preferredHeight: 0
            Item {
                id: scheduledPage
                property var selectedIds: ({})
                property string selectionAnchorId: ""
                readonly property int selectedCount: Util.idSetCount(selectedIds)
                readonly property var clusteredSessions: Util.clusterSessions(backend.sessions)
                function selectClick(id, shift) {
                    const result = Util.clickSelect(selectedIds, scheduledPage.clusteredSessions, id, shift, selectionAnchorId)
                    selectedIds = result.map
                    selectionAnchorId = result.anchor
                }
                property var contextSession: ({})
                function openSessionMenu(session) {
                    contextSession = session || ({})
                    sessionMenu.popup()
                }
                readonly property int rowInset: 12
                readonly property int colGap: 12
                readonly property int gripWidth: 28
                readonly property int startWidth: 148
                readonly property int deviceWidth: 118
                readonly property int durationWidth: 72
                readonly property int statusWidth: 92
                readonly property int actionsWidth: 228
                Connections {
                    target: backend
                    function onSessionsChanged() {
                        scheduledPage.selectedIds = Util.pruneIdSet(scheduledPage.selectedIds, backend.sessions)
                    }
                }
                EmptyHint { visible: backend.sessions.length === 0; glyph: "✦"; text: "No scheduled sessions yet. Create one manually or import a Stellarium / Telescopius target list."; anchors.centerIn: parent }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4
                    visible: backend.sessions.length > 0
                    SelectionBar {
                        selectedCount: scheduledPage.selectedCount
                        totalCount: backend.sessions.length
                        noun: "session"
                        allowMove: true
                        sessionIds: Util.idSetKeys(scheduledPage.selectedIds)
                        onSelectAllRequested: scheduledPage.selectedIds = Util.idSetAll(backend.sessions, true)
                        onClearRequested: scheduledPage.selectedIds = ({})
                        onEditRequested: sessionDialog.openSelected(Util.itemsByIds(backend.sessions, scheduledPage.selectedIds))
                        onDeleteRequested: root.confirmBulkDelete("deleteSessions", scheduledPage.selectedIds, "session")
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: scheduledPage.rowInset
                        Layout.rightMargin: scheduledPage.rowInset
                        Layout.preferredHeight: 18
                        spacing: scheduledPage.colGap
                        Item { Layout.preferredWidth: scheduledPage.gripWidth; Layout.maximumWidth: scheduledPage.gripWidth }
                        Text { text: "SESSION"; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4; font.bold: true; Layout.fillWidth: true }
                        Text { text: "START"; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.startWidth; Layout.maximumWidth: scheduledPage.startWidth }
                        Text { text: "DEVICE"; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.deviceWidth; Layout.maximumWidth: scheduledPage.deviceWidth }
                        Text { text: "LENGTH"; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.durationWidth; Layout.maximumWidth: scheduledPage.durationWidth; horizontalAlignment: Text.AlignRight; Layout.fillWidth: false }
                        Text { text: "STATUS"; color: Theme.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.statusWidth; Layout.maximumWidth: scheduledPage.statusWidth; horizontalAlignment: Text.AlignHCenter }
                        Item { Layout.preferredWidth: scheduledPage.actionsWidth; Layout.maximumWidth: scheduledPage.actionsWidth }
                    }
                    SessionInsertDrop {
                        id: scheduledInsert
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        targetList: scheduledList
                        rowHeight: 76
                        ListView {
                            id: scheduledList
                            anchors.fill: parent
                            clip: true
                            spacing: 6
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: HiddenBar {}
                            ScrollBar.horizontal: HiddenBar {}
                            model: scheduledPage.clusteredSessions
                            delegate: Column {
                                id: scheduledWrap
                                required property var modelData
                                required property int index
                                width: ListView.view.width
                                spacing: 0
                                height: (showHeader ? 30 : 0) + 76
                                readonly property bool showHeader: {
                                    if (!modelData.is_grouped)
                                        return false
                                    if (index <= 0)
                                        return true
                                    const prev = scheduledPage.clusteredSessions[index - 1]
                                    return !prev || String(prev.group_key || "") !== String(modelData.group_key || "")
                                }
                                readonly property color groupTone: modelData.is_grouped ? Util.groupTone(modelData.group_id) : (modelData.device_color || Theme.accent)
                                opacity: DragCoordinator.active && DragCoordinator.data.id === modelData.id ? 0.35 : 1
                                Item {
                                    width: parent.width
                                    height: scheduledWrap.showHeader ? 30 : 0
                                    visible: scheduledWrap.showHeader
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: scheduledPage.rowInset
                                        anchors.rightMargin: scheduledPage.rowInset
                                        spacing: 8
                                        Rectangle {
                                            Layout.preferredWidth: 4
                                            Layout.preferredHeight: 14
                                            Layout.alignment: Qt.AlignVCenter
                                            color: scheduledWrap.groupTone
                                        }
                                        Text {
                                            text: String(scheduledWrap.modelData.group_title || scheduledWrap.modelData.display_title || "").toUpperCase()
                                            color: scheduledWrap.groupTone
                                            font.pixelSize: 11
                                            font.letterSpacing: 1.4
                                            font.bold: true
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                        Text {
                                            text: {
                                                const count = Number(scheduledWrap.modelData.pane_count || 0)
                                                const grid = scheduledWrap.modelData.grid_text || ""
                                                return count + (count === 1 ? " PANE" : " PANES") + (grid ? " · " + grid : "")
                                            }
                                            color: Theme.textSecondary
                                            font.pixelSize: 10
                                            font.family: Theme.fontMono
                                            Layout.fillWidth: false
                                        }
                                    }
                                }
                                HudPanel {
                                    id: scheduledRow
                                    readonly property var modelData: scheduledWrap.modelData
                                    width: parent.width
                                    height: 76
                                    readonly property color groupTone: scheduledWrap.groupTone
                                    fill: Util.idSetHas(scheduledPage.selectedIds, modelData.id) ? Theme.hsl(0.036, 0.640, 0.196, 0.753) : (modelData.is_grouped ? Util.groupFill(modelData.group_id) : Theme.panelFill)
                                overlay: [
                                    HoverHandler { id: scheduledHover },
                                    TapHandler {
                                        acceptedButtons: Qt.LeftButton
                                        acceptedModifiers: Qt.ShiftModifier
                                        onTapped: scheduledPage.selectClick(scheduledRow.modelData.id, true)
                                    },
                                    Item {
                                        anchors.fill: parent
                                        anchors.rightMargin: scheduledPage.rowInset + scheduledPage.actionsWidth
                                        SessionDragArea {
                                            dragItem: scheduledRow.modelData
                                            onEditRequested: session => sessionDialog.openExisting(session)
                                        }
                                    },
                                    SelectBox {
                                        id: scheduledSelect
                                        anchors.left: parent.left
                                        anchors.leftMargin: scheduledPage.rowInset + Math.round((scheduledPage.gripWidth - width) / 2) + 2
                                        anchors.verticalCenter: parent.verticalCenter
                                        checked: Util.idSetHas(scheduledPage.selectedIds, scheduledRow.modelData.id)
                                        revealed: scheduledHover.hovered || scheduledPage.selectedCount > 0
                                        onToggled: (shiftHeld) => scheduledPage.selectClick(scheduledRow.modelData.id, shiftHeld)
                                    }
                                ]
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    spacing: scheduledPage.colGap
                                    Item {
                                        Layout.preferredWidth: scheduledPage.gripWidth
                                        Layout.maximumWidth: scheduledPage.gripWidth
                                        Layout.fillHeight: true
                                        Rectangle {
                                            width: 4
                                            height: parent.height - 8
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: scheduledRow.groupTone
                                        }
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        Layout.minimumWidth: 140
                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            spacing: 3
                                            Text {
                                                width: parent.width
                                                text: scheduledRow.modelData.pane_name || scheduledRow.modelData.target_name
                                                color: Theme.textPrimary
                                                font.pixelSize: 15
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Text {
                                                width: parent.width
                                                text: {
                                                    const pos = scheduledRow.modelData.pane_position || ""
                                                    const summary = scheduledRow.modelData.summary || ""
                                                    if (pos && summary)
                                                        return pos + " · " + summary
                                                    return pos || scheduledRow.modelData.subtitle || summary
                                                }
                                                color: Theme.textSecondary
                                                font.pixelSize: 11
                                                elide: Text.ElideRight
                                                visible: text !== "" && text !== (scheduledRow.modelData.pane_name || scheduledRow.modelData.target_name)
                                            }
                                        }
                                    }
                                    Text {
                                        text: scheduledRow.modelData.start_date + "  " + scheduledRow.modelData.start_time
                                        color: Theme.textPrimary
                                        font.family: Theme.fontMono
                                        font.pixelSize: 13
                                        Layout.preferredWidth: scheduledPage.startWidth
                                        Layout.maximumWidth: scheduledPage.startWidth
                                        Layout.minimumWidth: scheduledPage.startWidth
                                        Layout.fillWidth: false
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    Item {
                                        Layout.preferredWidth: scheduledPage.deviceWidth
                                        Layout.maximumWidth: scheduledPage.deviceWidth
                                        Layout.minimumWidth: scheduledPage.deviceWidth
                                        Layout.fillHeight: true
                                        Row {
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            spacing: 8
                                            Rectangle {
                                                width: 7
                                                height: 7
                                                radius: 4
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: scheduledRow.modelData.device_color || Theme.accent
                                            }
                                            Text {
                                                width: parent.width - 15
                                                text: scheduledRow.modelData.device_name
                                                color: Theme.textPrimary
                                                elide: Text.ElideRight
                                                font.pixelSize: 13
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                        }
                                    }
                                    Text {
                                        text: scheduledRow.modelData.duration_text
                                        color: Theme.textSecondary
                                        font.family: Theme.fontMono
                                        font.pixelSize: 13
                                        horizontalAlignment: Text.AlignRight
                                        Layout.preferredWidth: scheduledPage.durationWidth
                                        Layout.maximumWidth: scheduledPage.durationWidth
                                        Layout.minimumWidth: scheduledPage.durationWidth
                                        Layout.fillWidth: false
                                        Layout.alignment: Qt.AlignVCenter
                                    }
                                    Item {
                                        Layout.preferredWidth: scheduledPage.statusWidth
                                        Layout.maximumWidth: scheduledPage.statusWidth
                                        Layout.minimumWidth: scheduledPage.statusWidth
                                        Layout.fillHeight: true
                                        StatusChip {
                                            anchors.centerIn: parent
                                            status: scheduledRow.modelData.status
                                            implicitWidth: 86
                                            implicitHeight: 22
                                        }
                                    }
                                    RowLayout {
                                        Layout.preferredWidth: scheduledPage.actionsWidth
                                        Layout.maximumWidth: scheduledPage.actionsWidth
                                        Layout.minimumWidth: scheduledPage.actionsWidth
                                        Layout.fillWidth: false
                                        Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                        spacing: 6
                                        HudButton {
                                            text: "EDIT"
                                            implicitHeight: 30
                                            Layout.preferredWidth: 68
                                            enabled: scheduledRow.modelData.status !== "running"
                                            busyText: "OPENING…"
                                            onClicked: sessionDialog.openExisting(scheduledRow.modelData)
                                        }
                                        HudButton {
                                            text: "RESET"
                                            implicitHeight: 30
                                            Layout.preferredWidth: 76
                                            opacity: Util.canReset(scheduledRow.modelData.status) ? 1 : 0
                                            enabled: Util.canReset(scheduledRow.modelData.status)
                                            busyText: "RESETTING…"
                                            onClicked: backend.resetSession(scheduledRow.modelData.id)
                                        }
                                        HudButton {
                                            text: scheduledRow.modelData.status === "running" ? "STOP" : "RUN"
                                            implicitHeight: 30
                                            Layout.preferredWidth: 68
                                            enabled: scheduledRow.modelData.status !== "running" || !root.sessionStopping(scheduledRow.modelData)
                                            busy: root.sessionStopping(scheduledRow.modelData)
                                            busyText: scheduledRow.modelData.status === "running" ? "STOPPING…" : "STARTING…"
                                            busyMs: scheduledRow.modelData.status === "running" ? 0 : 1400
                                            buttonColor: scheduledRow.modelData.status === "running" ? Theme.fillDanger : Theme.surfaceHigh
                                            foregroundColor: scheduledRow.modelData.status === "running" ? Theme.danger : Theme.textPrimary
                                            onClicked: scheduledRow.modelData.status === "running"
                                                ? backend.stopSession(scheduledRow.modelData.id)
                                                : backend.runNow(scheduledRow.modelData.id)
                                        }
                                    }
                                }
                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: scheduledPage.openSessionMenu(scheduledRow.modelData) }
                                }
                            }
                        }
                    }
                }
                SessionContextMenu {
                    id: sessionMenu
                    sessionData: scheduledPage.contextSession
                    selectionItems: backend.sessions
                    selectedMap: scheduledPage.selectedIds
                    onEditRequested: session => sessionDialog.openExisting(session)
                    onEditSelectedRequested: sessionDialog.openSelected(Util.itemsByIds(backend.sessions, scheduledPage.selectedIds))
                    onSelectAllRequested: scheduledPage.selectedIds = Util.idSetAll(backend.sessions, true)
                    onUnselectAllRequested: {
                        scheduledPage.selectedIds = ({})
                        scheduledPage.selectionAnchorId = ""
                    }
                }
            }
            Item {
                id: templatesPage
                property var selectedIds: ({})
                property string selectionAnchorId: ""
                readonly property int selectedCount: Util.idSetCount(selectedIds)
                function selectClick(id, shift) {
                    const result = Util.clickSelect(selectedIds, backend.templates, id, shift, selectionAnchorId)
                    selectedIds = result.map
                    selectionAnchorId = result.anchor
                }
                Connections {
                    target: backend
                    function onTemplatesChanged() {
                        templatesPage.selectedIds = Util.pruneIdSet(templatesPage.selectedIds, backend.templates)
                    }
                }
                EmptyHint { anchors.centerIn: parent; visible: backend.templates.length === 0; glyph: "❖"; text: "No templates yet. Save a session as a reusable template, or import Stellarium / Telescopius." }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4
                    visible: backend.templates.length > 0
                    SelectionBar {
                        selectedCount: templatesPage.selectedCount
                        totalCount: backend.templates.length
                        noun: "template"
                        onSelectAllRequested: templatesPage.selectedIds = Util.idSetAll(backend.templates, true)
                        onClearRequested: templatesPage.selectedIds = ({})
                        onEditRequested: sessionDialog.openSelected(Util.itemsByIds(backend.templates, templatesPage.selectedIds), true)
                        onDeleteRequested: root.confirmBulkDelete("deleteTemplates", templatesPage.selectedIds, "template")
                    }
                GridView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    cellWidth: 340
                    cellHeight: 170
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                    model: backend.templates
                    delegate: HudPanel {
                        id: templateCard
                        required property var modelData
                        width: 324
                        height: 156
                        title: modelData.name
                        readonly property bool grouped: Util.isGrouped(modelData)
                        readonly property color groupTone: Util.sessionTone(modelData)
                        titleColor: grouped ? groupTone : Theme.accent
                        fill: Util.idSetHas(templatesPage.selectedIds, modelData.id) ? Theme.hsl(0.036, 0.640, 0.196, 0.753) : (grouped ? Util.groupFill(modelData.group_id) : Theme.panelFill)
                        overlay: [
                            Rectangle {
                                visible: templateCard.grouped
                                width: 4
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.topMargin: 10
                                anchors.bottomMargin: 10
                                color: templateCard.groupTone
                            },
                            HoverHandler { id: templateHover },
                            TapHandler {
                                acceptedButtons: Qt.LeftButton
                                acceptedModifiers: Qt.ShiftModifier
                                onTapped: templatesPage.selectClick(templateCard.modelData.id, true)
                            },
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: templateMenu.popup()
                            },
                            Item {
                                anchors.fill: parent
                                anchors.bottomMargin: 52
                                TapHandler {
                                    acceptedButtons: Qt.LeftButton
                                    acceptedModifiers: Qt.NoModifier
                                    grabPermissions: PointerHandler.CanTakeOverFromAnything | PointerHandler.ApprovesTakeOverByAnything
                                    onDoubleTapped: sessionDialog.openTemplate(templateCard.modelData)
                                }
                            },
                            SelectBox {
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 8
                                checked: Util.idSetHas(templatesPage.selectedIds, templateCard.modelData.id)
                                revealed: templateHover.hovered || templatesPage.selectedCount > 0
                                onToggled: (shiftHeld) => templatesPage.selectClick(templateCard.modelData.id, shiftHeld)
                            },
                            RowLayout {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.margins: 12
                                HudButton { text: "EDIT"; busyText: "OPENING…"; onClicked: sessionDialog.openTemplate(templateCard.modelData) }
                                HudButton { text: "SCHEDULE"; Layout.fillWidth: true; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: scheduleTemplateDialog.openFor(templateCard.modelData) }
                                HudButton { text: "DELETE"; busyText: "DELETING…"; onClicked: backend.deleteTemplate(templateCard.modelData.id) }
                            },
                            HudMenu {
                                id: templateMenu
                                HudMenuItem {
                                    text: templatesPage.selectedCount > 1 && Util.idSetHas(templatesPage.selectedIds, templateCard.modelData.id) ? "Edit selected" : "Edit"
                                    glyph: "\uE70F"
                                    onTriggered: {
                                        if (templatesPage.selectedCount > 1 && Util.idSetHas(templatesPage.selectedIds, templateCard.modelData.id))
                                            sessionDialog.openSelected(Util.itemsByIds(backend.templates, templatesPage.selectedIds), true)
                                        else
                                            sessionDialog.openTemplate(templateCard.modelData)
                                    }
                                }
                                HudMenuItem {
                                    text: "Schedule"
                                    glyph: "\uE768"
                                    onTriggered: scheduleTemplateDialog.openFor(templateCard.modelData)
                                }
                                HudMenuSeparator {}
                                HudMenuItem {
                                    text: "Select all"
                                    glyph: "\uE8A5"
                                    enabled: backend.templates.length > 0
                                    onTriggered: templatesPage.selectedIds = Util.idSetAll(backend.templates, true)
                                }
                                HudMenuItem {
                                    text: "Unselect all"
                                    glyph: "\uE711"
                                    enabled: templatesPage.selectedCount > 0
                                    onTriggered: {
                                        templatesPage.selectedIds = ({})
                                        templatesPage.selectionAnchorId = ""
                                    }
                                }
                                HudMenuSeparator {}
                                HudMenuItem {
                                    text: "Delete"
                                    glyph: "\uE74D"
                                    destructive: true
                                    onTriggered: backend.deleteTemplate(templateCard.modelData.id)
                                }
                            }
                        ]
                        Text {
                            visible: modelData.target_name !== modelData.name
                            text: modelData.target_name
                            color: Theme.textPrimary
                            font.pixelSize: 16
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                        Text { text: modelData.summary; color: Theme.textSecondary; Layout.fillWidth: true }
                        Item { Layout.fillWidth: true; Layout.preferredHeight: 34 }
                    }
                }
                }
            }
        }
    }
    }
}
