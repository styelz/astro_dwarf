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
    objectName: "sessionsRoot"
    function revealTemplates(ids) {
        const created = []
        if (Array.isArray(ids)) {
            for (let i = 0; i < ids.length; i++) {
                const id = String(ids[i] || "").trim()
                if (id)
                    created.push(id)
            }
        } else {
            String(ids || "").split(",").forEach(part => {
                const id = String(part || "").trim()
                if (id)
                    created.push(id)
            })
        }
        sessionsTabs.currentIndex = 1
        Qt.callLater(() => templatesPage.revealCreated(created))
    }

    Flickable {
        id: sessionsFlick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: Math.max(height, sessionsColumn.implicitHeight)
        interactive: contentHeight > height + Theme.px(1)
        ScrollBar.vertical: HiddenBar {}
        ScrollBar.horizontal: HiddenBar {}
    ColumnLayout {
        id: sessionsColumn
        width: sessionsFlick.width
        height: Math.max(implicitHeight, sessionsFlick.height)
        spacing: Theme.px(10)
        PageHeader {
            title: "SESSIONS"
            subtitle: {
                const planned = backend.sessions.filter(item => item.status === "planned").length
                const running = backend.sessions.filter(item => item.status === "running").length
                return planned + " planned · " + (running > 0 ? running + " running · " : "") + backend.templates.length + " template" + (backend.templates.length === 1 ? "" : "s")
            }
            HudButton { text: "IMPORT STELLARIUM"; busy: backend.uiBusy === "stellarium"; busyText: "IMPORTING…"; busyMs: 0; enabled: backend.uiBusy === ""; onClicked: root.harvestStellarium("import") }
            HudButton { text: "IMPORT TELESCOPIUS"; busy: backend.uiBusy === "telescopius"; busyText: backend.uiBusy === "telescopius" ? "IMPORTING…" : "OPENING…"; enabled: backend.uiBusy === ""; onClicked: telescopiusDialog.open() }
            HudButton { text: "+ MANUAL SESSION"; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: sessionDialog.openForDate(Qt.formatDate(new Date(), "yyyy-MM-dd")) }
        }
        RowLayout {
            id: sessionsTabs
            objectName: "sessionsTabs"
            property int currentIndex: 0
            Layout.fillWidth: true
            Layout.preferredHeight: Theme.controlHeight
            Layout.maximumHeight: Theme.controlHeight
            spacing: Theme.s2

            function selectTab(index) {
                sessionsTabs.currentIndex = index
            }

            HudButton {
                id: scheduledTab
                objectName: "sessions-tab-scheduled"
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.controlHeight
                text: "SCHEDULED  ·  " + backend.sessions.length
                font.pixelSize: Theme.fontMd
                font.letterSpacing: Theme.tracking2
                buttonColor: sessionsTabs.currentIndex === 0 ? Theme.fillActive : Theme.inputBg
                foregroundColor: sessionsTabs.currentIndex === 0 ? Theme.accent : Theme.textSecondary
                Accessible.name: "Scheduled"
                accessibleDescription: (sessionsTabs.currentIndex === 0 ? "Current list. " : "") + "Show scheduled sessions"
                onClicked: sessionsTabs.selectTab(0)
                Keys.onLeftPressed: {
                    templatesTab.forceActiveFocus()
                    sessionsTabs.selectTab(1)
                }
                Keys.onRightPressed: {
                    templatesTab.forceActiveFocus()
                    sessionsTabs.selectTab(1)
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Theme.px(1)
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: Theme.px(2)
                    width: sessionsTabs.currentIndex === 0 ? parent.width - Theme.px(24) : 0
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                }
            }
            HudButton {
                id: templatesTab
                objectName: "sessions-tab-templates"
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.controlHeight
                text: "TEMPLATES  ·  " + backend.templates.length
                font.pixelSize: Theme.fontMd
                font.letterSpacing: Theme.tracking2
                buttonColor: sessionsTabs.currentIndex === 1 ? Theme.fillActive : Theme.inputBg
                foregroundColor: sessionsTabs.currentIndex === 1 ? Theme.accent : Theme.textSecondary
                Accessible.name: "Templates"
                accessibleDescription: (sessionsTabs.currentIndex === 1 ? "Current list. " : "") + "Show session templates"
                onClicked: sessionsTabs.selectTab(1)
                Keys.onLeftPressed: {
                    scheduledTab.forceActiveFocus()
                    sessionsTabs.selectTab(0)
                }
                Keys.onRightPressed: {
                    scheduledTab.forceActiveFocus()
                    sessionsTabs.selectTab(0)
                }
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Theme.px(1)
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: Theme.px(2)
                    width: sessionsTabs.currentIndex === 1 ? parent.width - Theme.px(24) : 0
                    color: Theme.accent
                    Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                }
            }
        }
        StackLayout {
            currentIndex: sessionsTabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: Theme.px(280)
            Layout.preferredHeight: 0
            Item {
                id: scheduledPage
                property var selectedIds: ({})
                property string selectionAnchorId: ""
                property var expandedGroups: ({})
                readonly property int selectedCount: Util.idSetCount(selectedIds)
                readonly property var clusteredSessions: Util.clusterSessions(backend.sessions)
                readonly property var visibleSessions: Util.visibleClusteredSessions(clusteredSessions, expandedGroups)
                readonly property var mosaicGroupKeys: Util.mosaicGroupKeys(clusteredSessions)
                readonly property int groupedCount: mosaicGroupKeys.length
                readonly property int expandedGroupCount: Util.expandedKeyCount(expandedGroups, mosaicGroupKeys)
                readonly property bool canExpandAll: groupedCount > 0 && expandedGroupCount < groupedCount
                readonly property bool canCollapseAll: expandedGroupCount > 0
                function groupKey(item) {
                    return String((item && item.group_key) || "")
                }
                function toggleGroup(item) {
                    const key = scheduledPage.groupKey(item)
                    if (!key || !(item && item.is_grouped))
                        return
                    const next = Object.assign({}, expandedGroups)
                    if (next[key])
                        delete next[key]
                    else
                        next[key] = true
                    expandedGroups = next
                }
                function expandAllGroups() {
                    expandedGroups = Util.mosaicGroupKeyMap(clusteredSessions)
                }
                function collapseAllGroups() {
                    expandedGroups = ({})
                }
                function groupMembers(item) {
                    if (item && item.group_members && item.group_members.length)
                        return item.group_members
                    const key = scheduledPage.groupKey(item)
                    const result = []
                    if (!key || !(item && item.is_grouped)) {
                        if (item)
                            result.push(item)
                        return result
                    }
                    const list = scheduledPage.clusteredSessions
                    for (let i = 0; i < list.length; i++) {
                        if (list[i] && String(list[i].group_key || "") === key)
                            result.push(list[i])
                    }
                    return result
                }
                function groupChecked(item) {
                    const members = scheduledPage.groupMembers(item)
                    if (!members.length)
                        return false
                    for (let i = 0; i < members.length; i++) {
                        if (!Util.idSetHas(selectedIds, members[i].id))
                            return false
                    }
                    return true
                }
                function rowHighlighted(item) {
                    if (item && item.group_collapsed) {
                        const members = scheduledPage.groupMembers(item)
                        for (let i = 0; i < members.length; i++) {
                            if (Util.idSetHas(selectedIds, members[i].id))
                                return true
                        }
                        return false
                    }
                    return Util.idSetHas(selectedIds, item && item.id)
                }
                function selectClick(id, shift) {
                    const list = scheduledPage.visibleSessions
                    let item = null
                    for (let i = 0; i < list.length; i++) {
                        if (list[i] && list[i].id === id) {
                            item = list[i]
                            break
                        }
                    }
                    if (!shift && item && item.group_collapsed) {
                        const members = scheduledPage.groupMembers(item)
                        const allOn = scheduledPage.groupChecked(item)
                        const next = Object.assign({}, selectedIds)
                        for (let i = 0; i < members.length; i++) {
                            const memberId = members[i] && members[i].id
                            if (!memberId)
                                continue
                            if (allOn)
                                delete next[memberId]
                            else
                                next[memberId] = true
                        }
                        selectedIds = next
                        selectionAnchorId = id
                        return
                    }
                    const result = Util.clickSelect(selectedIds, scheduledPage.clusteredSessions, id, shift, selectionAnchorId)
                    selectedIds = result.map
                    selectionAnchorId = result.anchor
                }
                function editItem(item) {
                    sessionDialog.openExisting(item)
                }
                function resetItem(item) {
                    const members = item && item.group_collapsed ? scheduledPage.groupMembers(item) : [item]
                    for (let i = 0; i < members.length; i++) {
                        if (members[i] && Util.canReset(members[i].status))
                            backend.resetSession(members[i].id)
                    }
                }
                function canResetItem(item) {
                    const members = item && item.group_collapsed ? scheduledPage.groupMembers(item) : [item]
                    for (let i = 0; i < members.length; i++) {
                        if (members[i] && Util.canReset(members[i].status))
                            return true
                    }
                    return false
                }
                property var contextSession: ({})
                function openSessionMenu(session) {
                    contextSession = session || ({})
                    sessionMenu.popup()
                }
                readonly property int rowInset: Theme.px(12)
                readonly property int colGap: Theme.px(12)
                readonly property int gripWidth: Theme.px(28)
                readonly property int startWidth: Theme.px(148)
                readonly property int deviceWidth: Theme.px(118)
                readonly property int durationWidth: Theme.px(72)
                readonly property int statusWidth: Theme.px(92)
                readonly property int actionsWidth: Theme.px(228)
                Connections {
                    target: backend
                    function onSessionsChanged() {
                        scheduledPage.selectedIds = Util.pruneIdSet(scheduledPage.selectedIds, backend.sessions)
                    }
                }
                EmptyHint { visible: backend.sessions.length === 0; glyph: "✦"; text: "No scheduled sessions yet. Create one manually or import a Stellarium / Telescopius target list."; anchors.centerIn: parent }
                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.s1
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
                    Item {
                        Layout.fillWidth: true
                        Layout.leftMargin: scheduledPage.rowInset
                        Layout.rightMargin: scheduledPage.rowInset
                        Layout.preferredHeight: Theme.px(18)
                        RowLayout {
                            anchors.fill: parent
                            spacing: scheduledPage.colGap
                            Item { Layout.preferredWidth: scheduledPage.gripWidth; Layout.maximumWidth: scheduledPage.gripWidth }
                            Text { text: "SESSION"; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4; font.bold: true; Layout.fillWidth: true }
                            Text { text: "START"; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.startWidth; Layout.maximumWidth: scheduledPage.startWidth }
                            Text { text: "DEVICE"; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.deviceWidth; Layout.maximumWidth: scheduledPage.deviceWidth }
                            Text { text: "LENGTH"; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.durationWidth; Layout.maximumWidth: scheduledPage.durationWidth; horizontalAlignment: Text.AlignRight; Layout.fillWidth: false }
                            Text { text: "STATUS"; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: 1.4; font.bold: true; Layout.preferredWidth: scheduledPage.statusWidth; Layout.maximumWidth: scheduledPage.statusWidth; horizontalAlignment: Text.AlignHCenter }
                            Item { Layout.preferredWidth: scheduledPage.actionsWidth; Layout.maximumWidth: scheduledPage.actionsWidth }
                        }
                        TapHandler {
                            acceptedButtons: Qt.RightButton
                            onTapped: scheduledExpandMenu.popup()
                        }
                        ExpandCollapseMenu {
                            id: scheduledExpandMenu
                            expandObjectName: "scheduled-header-expand-all"
                            collapseObjectName: "scheduled-header-collapse-all"
                            canExpandAll: scheduledPage.canExpandAll
                            canCollapseAll: scheduledPage.canCollapseAll
                            onExpandAllRequested: scheduledPage.expandAllGroups()
                            onCollapseAllRequested: scheduledPage.collapseAllGroups()
                        }
                    }
                    SessionInsertDrop {
                        id: scheduledInsert
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        targetList: scheduledList
                        rowHeight: Theme.px(76)
                        headerHeight: Theme.px(30)
                        ListView {
                            id: scheduledList
                            anchors.fill: parent
                            clip: true
                            spacing: Theme.px(6)
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: HiddenBar {}
                            ScrollBar.horizontal: HiddenBar {}
                            model: scheduledPage.visibleSessions
                            delegate: Column {
                                id: scheduledWrap
                                required property var modelData
                                required property int index
                                objectName: modelData && modelData.is_grouped ? "session-group-" + modelData.group_id : ""
                                width: ListView.view.width
                                spacing: 0
                                height: (showHeader ? Theme.px(30) : 0) + Theme.px(76)
                                readonly property bool collapsedGroup: !!(modelData && modelData.group_collapsed)
                                readonly property bool showHeader: {
                                    if (!modelData.is_grouped || scheduledWrap.collapsedGroup)
                                        return false
                                    if (index <= 0)
                                        return true
                                    const prev = scheduledPage.visibleSessions[index - 1]
                                    return !prev || String(prev.group_key || "") !== String(modelData.group_key || "")
                                }
                                readonly property color groupTone: modelData.is_grouped ? Util.groupTone(modelData.group_id) : (modelData.device_color || Theme.accent)
                                opacity: DragCoordinator.active && Util.sameSessionGroup(DragCoordinator.data, modelData) ? 0.35 : 1
                                Item {
                                    id: groupHeader
                                    objectName: scheduledWrap.showHeader ? "session-group-" + scheduledWrap.modelData.group_id : ""
                                    width: parent.width
                                    height: scheduledWrap.showHeader ? Theme.px(30) : 0
                                    visible: scheduledWrap.showHeader
                                    activeFocusOnTab: visible
                                    Accessible.role: Accessible.Button
                                    Accessible.name: "Collapse " + String(scheduledWrap.modelData.group_title || scheduledWrap.modelData.display_title || "mosaic")
                                    Keys.onPressed: function (event) {
                                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                                            scheduledPage.toggleGroup(scheduledWrap.modelData)
                                            event.accepted = true
                                        }
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        visible: groupHeader.activeFocus
                                        color: "transparent"
                                        border.color: Theme.accent
                                        border.width: Theme.focusStroke
                                    }
                                    TapHandler {
                                        acceptedButtons: Qt.LeftButton
                                        onTapped: scheduledPage.toggleGroup(scheduledWrap.modelData)
                                    }
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: scheduledPage.openSessionMenu(scheduledWrap.modelData)
                                    }
                                    HoverHandler { id: groupHeaderHover }
                                    HudToolTip {
                                        visible: groupHeaderHover.hovered
                                        text: "Collapse mosaic panes"
                                    }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: scheduledPage.rowInset
                                        anchors.rightMargin: scheduledPage.rowInset
                                        spacing: Theme.s2
                                        Rectangle {
                                            Layout.preferredWidth: Theme.s1
                                            Layout.preferredHeight: Theme.px(14)
                                            Layout.alignment: Qt.AlignVCenter
                                            color: scheduledWrap.groupTone
                                        }
                                        Text {
                                            text: "▾"
                                            color: scheduledWrap.groupTone
                                            font.pixelSize: Theme.fontSm
                                            Layout.fillWidth: false
                                        }
                                        Text {
                                            text: String(scheduledWrap.modelData.group_title || scheduledWrap.modelData.display_title || "").toUpperCase()
                                            color: scheduledWrap.groupTone
                                            font.pixelSize: Theme.fontPx(11)
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
                                            font.pixelSize: Theme.fontSm
                                            font.family: Theme.fontMono
                                            Layout.fillWidth: false
                                        }
                                    }
                                }
                                HudPanel {
                                    id: scheduledRow
                                    objectName: "session-" + scheduledWrap.modelData.id
                                    readonly property var modelData: scheduledWrap.modelData
                                    readonly property var actionSession: modelData.group_action || modelData
                                    width: parent.width
                                    height: Theme.px(76)
                                    readonly property color groupTone: scheduledWrap.groupTone
                                    fill: scheduledPage.rowHighlighted(modelData) ? Theme.hsl(0.036, 0.640, 0.196, 0.753) : (modelData.is_grouped ? Util.groupFill(modelData.group_id) : Theme.panelFill)
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
                                            onEditRequested: session => scheduledPage.editItem(scheduledRow.modelData)
                                        }
                                    },
                                    Item {
                                        id: groupExpand
                                        visible: scheduledWrap.collapsedGroup
                                        z: 40
                                        objectName: scheduledWrap.collapsedGroup
                                                   ? "session-expand-" + String(scheduledRow.modelData.id || "")
                                                   : ""
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.bottom: parent.bottom
                                        anchors.leftMargin: scheduledPage.rowInset + scheduledPage.gripWidth + scheduledPage.colGap
                                        anchors.rightMargin: scheduledPage.rowInset + scheduledPage.startWidth + scheduledPage.deviceWidth + scheduledPage.durationWidth + scheduledPage.statusWidth + scheduledPage.actionsWidth + scheduledPage.colGap * 5
                                        activeFocusOnTab: visible
                                        Accessible.role: Accessible.Button
                                        Accessible.name: "Expand " + String(scheduledRow.modelData.group_title || scheduledRow.modelData.display_title || "mosaic")
                                        signal clicked()
                                        onClicked: scheduledPage.toggleGroup(scheduledRow.modelData)
                                        Keys.onPressed: function (event) {
                                            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                                                groupExpand.clicked()
                                                event.accepted = true
                                            }
                                        }
                                        Rectangle {
                                            anchors.fill: parent
                                            visible: groupExpand.activeFocus
                                            color: "transparent"
                                            border.color: Theme.accent
                                            border.width: Theme.focusStroke
                                        }
                                        TapHandler {
                                            acceptedButtons: Qt.LeftButton
                                            grabPermissions: PointerHandler.CanTakeOverFromAnything
                                            onTapped: groupExpand.clicked()
                                        }
                                        HoverHandler { id: groupExpandHover }
                                        HudToolTip {
                                            visible: groupExpandHover.hovered
                                            text: "Expand mosaic panes"
                                        }
                                    },
                                    SelectBox {
                                        id: scheduledSelect
                                        anchors.left: parent.left
                                        anchors.leftMargin: scheduledPage.rowInset + Math.round((scheduledPage.gripWidth - width) / 2) + 2
                                        anchors.verticalCenter: parent.verticalCenter
                                        checked: scheduledWrap.collapsedGroup
                                                 ? scheduledPage.groupChecked(scheduledRow.modelData)
                                                 : Util.idSetHas(scheduledPage.selectedIds, scheduledRow.modelData.id)
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
                                            width: Theme.s1
                                            height: parent.height - Theme.s2
                                            anchors.verticalCenter: parent.verticalCenter
                                            color: scheduledRow.groupTone
                                        }
                                    }
                                    Item {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        Layout.minimumWidth: Theme.px(140)
                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            spacing: Theme.px(3)
                                            Row {
                                                width: parent.width
                                                spacing: Theme.px(6)
                                                Text {
                                                    visible: scheduledWrap.collapsedGroup
                                                    text: "▸"
                                                    color: scheduledRow.groupTone
                                                    font.pixelSize: Theme.fontSm
                                                    anchors.verticalCenter: parent.verticalCenter
                                                }
                                                Text {
                                                    width: parent.width - (scheduledWrap.collapsedGroup ? Theme.s5 : 0)
                                                    text: scheduledWrap.collapsedGroup
                                                          ? (scheduledRow.modelData.group_title || scheduledRow.modelData.display_title || scheduledRow.modelData.target_name)
                                                          : (scheduledRow.modelData.pane_name || scheduledRow.modelData.target_name)
                                                    color: Theme.textPrimary
                                                    font.pixelSize: Theme.fontPx(15)
                                                    font.bold: true
                                                    elide: Text.ElideRight
                                                }
                                            }
                                            Text {
                                                width: parent.width
                                                text: {
                                                    if (scheduledWrap.collapsedGroup) {
                                                        const action = scheduledRow.actionSession
                                                        if (action && action.status === "running") {
                                                            const step = Util.sessionStepLabel(action, backend.localNow.epoch_ms)
                                                            if (step)
                                                                return step
                                                        }
                                                        return scheduledRow.modelData.group_summary || ""
                                                    }
                                                    if (scheduledRow.modelData.status === "running") {
                                                        const step = Util.sessionStepLabel(scheduledRow.modelData, backend.localNow.epoch_ms)
                                                        if (step)
                                                            return step
                                                    }
                                                    const pos = scheduledRow.modelData.pane_position || ""
                                                    const summary = scheduledRow.modelData.summary || ""
                                                    if (pos && summary)
                                                        return pos + " · " + summary
                                                    return pos || scheduledRow.modelData.subtitle || summary
                                                }
                                                color: Theme.textSecondary
                                                font.pixelSize: Theme.fontPx(11)
                                                elide: Text.ElideRight
                                                visible: text !== "" && text !== (scheduledRow.modelData.pane_name || scheduledRow.modelData.target_name)
                                            }
                                        }
                                    }
                                    Text {
                                        text: scheduledWrap.collapsedGroup
                                              ? ((scheduledRow.modelData.group_start_date || scheduledRow.modelData.start_date) + "  " + (scheduledRow.modelData.group_start_time || scheduledRow.modelData.start_time))
                                              : (scheduledRow.modelData.start_date + "  " + scheduledRow.modelData.start_time)
                                        color: Theme.textPrimary
                                        font.family: Theme.fontMono
                                        font.pixelSize: Theme.fontBase
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
                                            spacing: Theme.s2
                                            Rectangle {
                                                width: Theme.px(7)
                                                height: Theme.px(7)
                                                radius: Theme.s1
                                                anchors.verticalCenter: parent.verticalCenter
                                                color: scheduledRow.modelData.device_color || Theme.accent
                                            }
                                            Text {
                                                width: parent.width - Theme.px(15)
                                                text: scheduledRow.modelData.device_name
                                                color: Theme.textPrimary
                                                elide: Text.ElideRight
                                                font.pixelSize: Theme.fontBase
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                        }
                                    }
                                    Text {
                                        text: scheduledWrap.collapsedGroup
                                              ? (scheduledRow.modelData.group_duration_text || scheduledRow.modelData.duration_text)
                                              : scheduledRow.modelData.duration_text
                                        color: Theme.textSecondary
                                        font.family: Theme.fontMono
                                        font.pixelSize: Theme.fontBase
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
                                            status: scheduledWrap.collapsedGroup
                                                    ? (scheduledRow.modelData.group_status || scheduledRow.modelData.status)
                                                    : scheduledRow.modelData.status
                                            implicitWidth: Theme.px(86)
                                            implicitHeight: Theme.px(22)
                                        }
                                    }
                                    RowLayout {
                                        Layout.preferredWidth: scheduledPage.actionsWidth
                                        Layout.maximumWidth: scheduledPage.actionsWidth
                                        Layout.minimumWidth: scheduledPage.actionsWidth
                                        Layout.fillWidth: false
                                        Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                        spacing: Theme.px(6)
                                        HudButton {
                                            text: "EDIT"
                                            implicitHeight: Theme.px(30)
                                            Layout.preferredWidth: Theme.px(68)
                                            enabled: (scheduledWrap.collapsedGroup
                                                      ? scheduledRow.modelData.group_status
                                                      : scheduledRow.modelData.status) !== "running"
                                            busyText: "OPENING…"
                                            onClicked: scheduledPage.editItem(scheduledRow.modelData)
                                        }
                                        HudButton {
                                            text: "RESET"
                                            implicitHeight: Theme.px(30)
                                            Layout.preferredWidth: Theme.px(76)
                                            opacity: scheduledPage.canResetItem(scheduledRow.modelData) ? 1 : 0
                                            enabled: scheduledPage.canResetItem(scheduledRow.modelData)
                                            busyText: "RESETTING…"
                                            onClicked: scheduledPage.resetItem(scheduledRow.modelData)
                                        }
                                        HudButton {
                                            text: scheduledRow.actionSession.status === "running" ? "STOP" : "RUN"
                                            implicitHeight: Theme.px(30)
                                            Layout.preferredWidth: Theme.px(68)
                                            enabled: scheduledRow.actionSession.status !== "running" || !root.sessionStopping(scheduledRow.actionSession)
                                            busy: root.sessionStopping(scheduledRow.actionSession)
                                            busyText: scheduledRow.actionSession.status === "running" ? "STOPPING…" : "STARTING…"
                                            busyMs: scheduledRow.actionSession.status === "running" ? 0 : 1400
                                            buttonColor: scheduledRow.actionSession.status === "running" ? Theme.fillDanger : Theme.surfaceHigh
                                            foregroundColor: scheduledRow.actionSession.status === "running" ? Theme.danger : Theme.textPrimary
                                            onClicked: scheduledRow.actionSession.status === "running"
                                                ? backend.stopSession(scheduledRow.actionSession.id)
                                                : backend.runNow(scheduledRow.actionSession.id)
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
                    showExpandCollapse: true
                    canExpandAll: scheduledPage.canExpandAll
                    canCollapseAll: scheduledPage.canCollapseAll
                    onEditRequested: session => scheduledPage.editItem(session)
                    onEditSelectedRequested: sessionDialog.openSelected(Util.itemsByIds(backend.sessions, scheduledPage.selectedIds))
                    onDuplicateRequested: (session, mode) => duplicateSessionDialog.openFor(session, mode)
                    onSelectAllRequested: scheduledPage.selectedIds = Util.idSetAll(backend.sessions, true)
                    onUnselectAllRequested: {
                        scheduledPage.selectedIds = ({})
                        scheduledPage.selectionAnchorId = ""
                    }
                    onExpandAllRequested: scheduledPage.expandAllGroups()
                    onCollapseAllRequested: scheduledPage.collapseAllGroups()
                }
            }
            Item {
                id: templatesPage
                property var selectedIds: ({})
                property var flashIds: ({})
                property string selectionAnchorId: ""
                readonly property int selectedCount: Util.idSetCount(selectedIds)
                function selectClick(id, shift) {
                    const result = Util.clickSelect(selectedIds, backend.templates, id, shift, selectionAnchorId)
                    selectedIds = result.map
                    selectionAnchorId = result.anchor
                }
                function confirmDelete(id) {
                    if (id && Util.idSetHas(selectedIds, id) && selectedCount > 1)
                        root.confirmBulkDelete("deleteTemplates", selectedIds, "template")
                    else
                        root.confirmBulkDelete("deleteTemplates", id, "template")
                }
                function revealCreated(ids) {
                    const wanted = {}
                    const list = backend.templates
                    let firstIndex = -1
                    for (let i = 0; i < list.length; i++) {
                        const item = list[i]
                        const members = item.member_ids || [item.id]
                        let match = false
                        for (let n = 0; n < ids.length; n++) {
                            if (item.id === ids[n] || members.indexOf(ids[n]) >= 0) {
                                match = true
                                break
                            }
                        }
                        if (!match)
                            continue
                        wanted[item.id] = true
                        if (firstIndex < 0)
                            firstIndex = i
                    }
                    templatesPage.flashIds = wanted
                    flashClear.restart()
                    if (firstIndex >= 0)
                        templatesView.positionViewAtIndex(firstIndex, GridView.Contain)
                }
                Timer {
                    id: flashClear
                    interval: Theme.slow * 2 + Theme.normal
                    repeat: false
                    onTriggered: templatesPage.flashIds = ({})
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
                    spacing: Theme.s1
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
                    id: templatesView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    cellWidth: 360
                    cellHeight: 228
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                    model: backend.templates
                    delegate: HudPanel {
                        id: templateCard
                        objectName: "template-" + modelData.id
                        required property var modelData
                        width: Theme.px(344)
                        height: Theme.px(212)
                        title: modelData.name
                        readonly property bool grouped: Util.isGrouped(modelData)
                        readonly property bool flashing: Util.idSetHas(templatesPage.flashIds, modelData.id)
                        readonly property color groupTone: Util.sessionTone(modelData)
                        readonly property color restFill: Util.idSetHas(templatesPage.selectedIds, modelData.id) ? Theme.hsl(0.036, 0.640, 0.196, 0.753) : (grouped ? Util.groupFill(modelData.group_id) : Theme.panelFill)
                        property real flashLevel: 0
                        titleColor: grouped ? groupTone : Theme.accent
                        hot: flashing
                        fill: Qt.rgba(
                            restFill.r + (Theme.fillActive.r - restFill.r) * flashLevel,
                            restFill.g + (Theme.fillActive.g - restFill.g) * flashLevel,
                            restFill.b + (Theme.fillActive.b - restFill.b) * flashLevel,
                            restFill.a
                        )
                        onFlashingChanged: {
                            if (!flashing)
                                flashLevel = 0
                        }
                        overlay: [
                            Rectangle {
                                visible: templateCard.grouped
                                width: Theme.s1
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.topMargin: Theme.px(10)
                                anchors.bottomMargin: Theme.px(10)
                                color: templateCard.groupTone
                            },
                            SequentialAnimation {
                                running: templateCard.flashing
                                loops: 1
                                NumberAnimation { target: templateCard; property: "flashLevel"; from: 0; to: 1; duration: Theme.slow }
                                NumberAnimation { target: templateCard; property: "flashLevel"; from: 1; to: 0; duration: Theme.slow }
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
                                anchors.bottomMargin: Theme.px(52)
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
                                anchors.margins: Theme.s2
                                checked: Util.idSetHas(templatesPage.selectedIds, templateCard.modelData.id)
                                revealed: templateHover.hovered || templatesPage.selectedCount > 0
                                onToggled: (shiftHeld) => templatesPage.selectClick(templateCard.modelData.id, shiftHeld)
                            },
                            RowLayout {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.margins: Theme.s3
                                HudButton { text: "EDIT"; busyText: "OPENING…"; onClicked: sessionDialog.openTemplate(templateCard.modelData) }
                                HudButton { text: "SCHEDULE"; Layout.fillWidth: true; busyText: "OPENING…"; buttonColor: Theme.fillActive; foregroundColor: Theme.accent; onClicked: scheduleTemplateDialog.openFor(templateCard.modelData) }
                                HudButton { text: "DELETE"; busyText: "DELETING…"; onClicked: root.confirmBulkDelete("deleteTemplates", templateCard.modelData.id, "template") }
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
                                    text: templatesPage.selectedCount > 1 && Util.idSetHas(templatesPage.selectedIds, templateCard.modelData.id) ? "Delete selected" : "Delete"
                                    glyph: "\uE74D"
                                    destructive: true
                                    onTriggered: templatesPage.confirmDelete(templateCard.modelData.id)
                                }
                            }
                        ]
                        Text {
                            visible: !!modelData.target_name && modelData.target_name !== modelData.name
                            text: modelData.target_name
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontPx(14)
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            visible: !!(modelData.coords_text || modelData.duration_text)
                            text: {
                                const coords = modelData.coords_text || ""
                                const length = modelData.duration_text || ""
                                if (coords && length)
                                    return coords + "  ·  " + length
                                return coords || length
                            }
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontMd
                            font.family: Theme.fontMono
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Theme.px(14)
                            rowSpacing: Theme.px(2)
                            Text { text: "CAPTURE"; color: Theme.muted; font.pixelSize: Theme.fontPx(9); font.letterSpacing: 1.1; font.bold: true }
                            Text { text: "CAMERA"; color: Theme.muted; font.pixelSize: Theme.fontPx(9); font.letterSpacing: 1.1; font.bold: true }
                            Text {
                                text: (modelData.capture_text || modelData.summary || "") + (modelData.gain_text ? "  " + modelData.gain_text : "")
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontMd
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: modelData.camera_text || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontMd
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text { text: "MOSAIC"; color: Theme.muted; font.pixelSize: Theme.fontPx(9); font.letterSpacing: 1.1; font.bold: true }
                            Text { text: "WORKFLOW"; color: Theme.muted; font.pixelSize: Theme.fontPx(9); font.letterSpacing: 1.1; font.bold: true }
                            Text {
                                text: modelData.mosaic_text || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontMd
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: modelData.workflow_text || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontMd
                                font.family: Theme.fontMono
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }
                        Text {
                            visible: !!(modelData.notes)
                            text: modelData.notes
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontPx(11)
                            wrapMode: Text.Wrap
                            maximumLineCount: 3
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Item { Layout.fillWidth: true; Layout.preferredHeight: Theme.px(34) }
                    }
                }
                }
            }
        }
    }
    }
}
