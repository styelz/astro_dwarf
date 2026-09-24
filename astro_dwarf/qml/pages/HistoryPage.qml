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
    id: historyPage
    objectName: "historyRoot"
    property string query: ""
    property string pendingQuery: ""
    property int outcomeFilter: 0
    property var expandedIds: ({})
    property var expandedGroups: ({})
    property var selectedIds: ({})
    property string selectionAnchorId: ""
    property bool showAllDevices: false
    property string dismissedSuggestionKey: ""
    property string scopedDeviceId: ""
    property int deviceCount: 0
    readonly property int selectedCount: Util.idSetCount(selectedIds)
    // Leading gutter shared by the expand chevron and the floating select box.
    readonly property int gutterWidth: 24
    readonly property bool viewingAllDevices: historyPage.showAllDevices || historyPage.deviceCount < 2
    readonly property string durationSuggestionKey: {
        const hint = backend.durationSuggestion || ({})
        return String(hint.run_count || 0) + "\t" + String(hint.change_text || "") + "\t" + String(historyPage.scopedDeviceId || "")
    }
    readonly property bool durationBannerVisible: {
        const hint = backend.durationSuggestion || ({})
        return !!(hint.available) && historyPage.durationSuggestionKey !== historyPage.dismissedSuggestionKey
    }
    function matchesDeviceScope(item) {
        return historyPage.viewingAllDevices || !!(item && item.device_id === historyPage.scopedDeviceId)
    }
    function syncScopedDevice() {
        const id = String(backend.selectedDeviceId || "")
        if (historyPage.scopedDeviceId !== id)
            historyPage.scopedDeviceId = id
    }
    function syncDeviceCount() {
        const n = (backend.devices || []).length
        if (historyPage.deviceCount !== n)
            historyPage.deviceCount = n
    }
    function selectClick(id, shift) {
        const result = Util.clickSelect(selectedIds, filteredHistory, id, shift, selectionAnchorId)
        selectedIds = result.map
        selectionAnchorId = result.anchor
    }
    function selectRow(item, shift) {
        if (item && item.group_collapsed && item.group_members && item.group_members.length) {
            const members = item.group_members
            let allOn = true
            for (let i = 0; i < members.length; i++) {
                if (!Util.idSetHas(historyPage.selectedIds, members[i].id)) {
                    allOn = false
                    break
                }
            }
            const next = Object.assign({}, historyPage.selectedIds)
            for (let i = 0; i < members.length; i++) {
                const id = members[i] && members[i].id
                if (!id)
                    continue
                if (allOn)
                    delete next[id]
                else
                    next[id] = true
            }
            historyPage.selectedIds = next
            historyPage.selectionAnchorId = String((members[0] && members[0].id) || "")
            return
        }
        historyPage.selectClick(item && item.id, shift)
    }
    function rowSelected(item) {
        if (item && item.group_collapsed && item.group_members) {
            const members = item.group_members
            if (!members.length)
                return false
            for (let i = 0; i < members.length; i++) {
                if (!Util.idSetHas(historyPage.selectedIds, members[i].id))
                    return false
            }
            return true
        }
        return Util.idSetHas(historyPage.selectedIds, item && item.id)
    }
    function rowDeleteTarget(item) {
        if (item && item.group_collapsed && item.group_member_ids && item.group_member_ids.length)
            return item.group_member_ids
        return item && item.id
    }
    function toggleGroup(item) {
        const key = Util.sessionGroupKey(item)
        if (!key)
            return
        const next = Object.assign({}, historyPage.expandedGroups)
        if (next[key])
            delete next[key]
        else
            next[key] = true
        historyPage.expandedGroups = next
    }
    function toggleRow(item) {
        if (item && item.group_collapsed)
            historyPage.toggleGroup(item)
        else
            historyPage.toggleExpanded(item && item.id)
    }
    function clearSelection() {
        historyPage.selectedIds = ({})
        historyPage.selectionAnchorId = ""
    }
    readonly property var scopedHistory: {
        const items = backend.history || []
        const out = []
        for (let i = 0; i < items.length; i++) {
            if (historyPage.matchesDeviceScope(items[i]))
                out.push(items[i])
        }
        return out
    }
    readonly property var filteredHistory: {
        const items = historyPage.scopedHistory
        const q = historyPage.query.trim().toLowerCase()
        const out = []
        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            if (historyPage.outcomeFilter === 1 && !item.ok)
                continue
            if (historyPage.outcomeFilter === 2 && item.ok)
                continue
            if (q) {
                const hay = [item.date, item.target_name, item.device_name, item.outcome, item.summary, item.notes, item.filter_text, item.gain_text, item.camera_text, item.workflow_text, item.mosaic_text, item.coords_text].join(" ").toLowerCase()
                if (hay.indexOf(q) < 0)
                    continue
            }
            out.push(item)
        }
        return out
    }
    readonly property var clusteredHistory: Util.clusterSessions(historyPage.filteredHistory)
    readonly property var visibleHistory: Util.visibleClusteredHistory(historyPage.filteredHistory, historyPage.expandedGroups)
    readonly property var mosaicGroupKeys: Util.mosaicGroupKeys(historyPage.clusteredHistory)
    readonly property int groupedCount: mosaicGroupKeys.length
    readonly property int expandedGroupCount: Util.expandedKeyCount(historyPage.expandedGroups, historyPage.mosaicGroupKeys)
    readonly property int filteredCount: filteredHistory.length
    readonly property int filteredOk: filteredHistory.filter(item => item.ok).length
    readonly property int filteredFailed: filteredCount - filteredOk
    readonly property int filteredPlannedFrames: filteredHistory.reduce((sum, item) => sum + (item.planned_frames || item.frame_count || 0), 0)
    readonly property int filteredCapturedFrames: filteredHistory.reduce((sum, item) => sum + (item.captured_frames || 0), 0)
    readonly property int filteredSeconds: filteredHistory.reduce((sum, item) => sum + (item.actual_duration_seconds || 0), 0)
    readonly property int filteredPlannedSeconds: filteredHistory.reduce((sum, item) => sum + (item.planned_duration_seconds || 0), 0)
    function formatHours(seconds) {
        const hours = Math.max(0, seconds) / 3600
        return hours >= 10 ? hours.toFixed(0) + "h" : hours.toFixed(1) + "h"
    }
    readonly property int expandedVisibleCount: Util.idSetVisibleCount(historyPage.expandedIds, historyPage.filteredHistory)
    readonly property bool canExpandAll: historyPage.groupedCount > 0
                                         ? historyPage.expandedGroupCount < historyPage.groupedCount
                                         : (historyPage.filteredCount > 0 && historyPage.expandedVisibleCount < historyPage.filteredCount)
    readonly property bool canCollapseAll: historyPage.groupedCount > 0
                                           ? historyPage.expandedGroupCount > 0
                                           : historyPage.expandedVisibleCount > 0
    function toggleExpanded(id) {
        historyPage.expandedIds = Util.idSetToggle(historyPage.expandedIds, id)
    }
    function expandAll() {
        if (historyPage.groupedCount > 0)
            historyPage.expandedGroups = Util.mosaicGroupKeyMap(historyPage.clusteredHistory)
        else
            historyPage.expandedIds = Util.idSetAll(historyPage.filteredHistory, true)
    }
    function collapseAll() {
        if (historyPage.groupedCount > 0)
            historyPage.expandedGroups = ({})
        else
            historyPage.expandedIds = ({})
    }
    Component.onCompleted: {
        historyPage.syncScopedDevice()
        historyPage.syncDeviceCount()
    }
    Connections {
        target: backend
        function onHistoryChanged() {
            historyPage.selectedIds = Util.pruneIdSet(historyPage.selectedIds, backend.history)
            historyPage.expandedIds = Util.pruneIdSet(historyPage.expandedIds, backend.history)
            const keys = Util.mosaicGroupKeys(Util.clusterSessions(historyPage.filteredHistory))
            const next = {}
            const expanded = historyPage.expandedGroups || {}
            for (let i = 0; i < keys.length; i++) {
                if (expanded[keys[i]])
                    next[keys[i]] = true
            }
            historyPage.expandedGroups = next
        }
        function onSelectedDeviceChanged() {
            historyPage.syncScopedDevice()
        }
        function onDevicesChanged() {
            historyPage.syncDeviceCount()
        }
    }

    Timer {
        id: searchDebounce
        interval: 300
        repeat: false
        onTriggered: historyPage.query = historyPage.pendingQuery
    }

    Flickable {
        id: historyFlick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: Math.max(height, historyColumn.implicitHeight)
        interactive: contentHeight > height + Theme.px(1)
        ScrollBar.vertical: HiddenBar {}
        ScrollBar.horizontal: HiddenBar {}
    ColumnLayout {
        id: historyColumn
        width: historyFlick.width
        height: Math.max(implicitHeight, historyFlick.height)
        spacing: Theme.px(10)
        PageHeader {
            id: historyHeader
            readonly property bool tight: width < Theme.px(760)
            title: "HISTORY"
            subtitle: {
                const n = historyPage.scopedHistory.length
                const scope = historyPage.viewingAllDevices
                    ? ((backend.devices || []).length > 1 ? "all telescopes" : "")
                    : (backend.selectedDevice.name || "this telescope")
                if (n === 0)
                    return scope
                        ? "Completed runs for " + scope + " appear here with timing, frames and outcome"
                        : "Completed runs appear here with timing, frames and outcome"
                return n + " recorded run" + (n === 1 ? "" : "s")
                    + (scope ? "  ·  " + scope : "")
                    + "  ·  click a row for timing, frames and outcome details"
            }
            HudButton {
                visible: (backend.devices || []).length > 1
                text: historyHeader.tight ? "ALL" : "ALL DEVICES"
                Accessible.name: "All devices"
                buttonColor: historyPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                foregroundColor: historyPage.showAllDevices ? Theme.accent : Theme.textSecondary
                onClicked: historyPage.showAllDevices = true
            }
            HudButton {
                visible: (backend.devices || []).length > 1
                text: historyHeader.tight ? "THIS" : "THIS DEVICE"
                Accessible.name: "This device"
                buttonColor: !historyPage.showAllDevices ? Theme.fillActive : Theme.surfaceHigh
                foregroundColor: !historyPage.showAllDevices ? Theme.accent : Theme.textSecondary
                onClicked: historyPage.showAllDevices = false
            }
            HudButton {
                text: "CLEAR HISTORY"
                enabled: historyPage.scopedHistory.length > 0
                busyText: "CLEARING…"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: {
                    confirmDialog.headingText = "CLEAR HISTORY"
                    confirmDialog.confirmLabel = "CLEAR ALL"
                    if (historyPage.showAllDevices && (backend.devices || []).length > 1) {
                        confirmDialog.kind = "clearHistory"
                        confirmDialog.summary = "Delete every recorded run on all telescopes? This cannot be undone."
                    } else {
                        const name = (backend.selectedDevice && backend.selectedDevice.name) || "this telescope"
                        confirmDialog.kind = "clearHistoryDevice"
                        confirmDialog.pendingIds = [backend.selectedDeviceId]
                        confirmDialog.summary = "Delete every recorded run for " + name + "? This cannot be undone."
                    }
                    confirmDialog.open()
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Repeater {
                model: [
                    [historyPage.filteredOk + " · " + historyPage.filteredFailed, "PASSED · FAILED", "◈",
                        historyPage.filteredCount === 0 ? Theme.textSecondary : (historyPage.filteredFailed === 0 ? Theme.success : (historyPage.filteredOk > 0 ? Theme.warning : Theme.danger)),
                        historyPage.filteredCount + " session" + (historyPage.filteredCount === 1 ? "" : "s")],
                    [String(historyPage.filteredCapturedFrames) + " / " + String(historyPage.filteredPlannedFrames), "CAPTURED / PLANNED", "▦",
                        historyPage.filteredCapturedFrames > 0 ? Theme.accent : Theme.textSecondary,
                        "frames"],
                    [historyPage.filteredCount ? Math.round(100 * historyPage.filteredOk / historyPage.filteredCount) + "%" : "—", "SUCCESS", "✓",
                        historyPage.filteredCount === 0 ? Theme.textSecondary : (historyPage.filteredOk === historyPage.filteredCount ? Theme.success : (historyPage.filteredOk * 2 >= historyPage.filteredCount ? Theme.warning : Theme.danger)),
                        historyPage.filteredOk + " passed"],
                    [historyPage.formatHours(historyPage.filteredSeconds) + " / " + historyPage.formatHours(historyPage.filteredPlannedSeconds), "ACTUAL / PLANNED", "◷", Theme.notice,
                        "imaging time"]
                ]
                delegate: HudPanel {
                    id: statTile
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(108)
                    overlay: [
                        Text {
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.s3
                            text: statTile.modelData[2]
                            color: statTile.modelData[3]
                            opacity: 0.35
                            font.pixelSize: Theme.fontXl
                        }
                    ]
                    Text { text: modelData[0]; color: modelData[3]; font.pixelSize: Theme.fontXl; font.bold: true; font.family: Theme.fontMono; wrapMode: Text.NoWrap; elide: Text.ElideRight; Layout.fillWidth: true }
                    Text { text: modelData[1]; color: Theme.textSecondary; font.pixelSize: Theme.fontSm; font.letterSpacing: Theme.tracking2 }
                    Text { visible: !!(modelData[4]); text: modelData[4] || ""; color: Theme.muted; font.pixelSize: Theme.fontSm }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            HudField {
                Layout.fillWidth: true
                placeholderText: "Search target, device, or outcome"
                accessibleName: "Search history"
                onTextChanged: {
                    historyPage.pendingQuery = text
                    searchDebounce.restart()
                }
            }
            HudCombo {
                Layout.preferredWidth: Theme.px(160)
                accessibleName: "Filter by outcome"
                model: ["All outcomes", "Completed", "Failed"]
                currentIndex: historyPage.outcomeFilter
                onActivated: historyPage.outcomeFilter = currentIndex
            }
        }
        HudPanel {
            visible: historyPage.durationBannerVisible
            Layout.fillWidth: true
            title: "◷  DURATION PROFILE"
            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.s1
                    Text {
                        Layout.fillWidth: true
                        text: (backend.durationSuggestion && backend.durationSuggestion.summary) || ""
                        color: Theme.warning
                        wrapMode: Text.Wrap
                        font.pixelSize: Theme.fontMd
                    }
                    Text {
                        visible: !!(backend.durationSuggestion && backend.durationSuggestion.note)
                        Layout.fillWidth: true
                        text: (backend.durationSuggestion && backend.durationSuggestion.note) || ""
                        color: Theme.textSecondary
                        wrapMode: Text.Wrap
                        font.pixelSize: Theme.fontSm
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (backend.durationSuggestion && backend.durationSuggestion.change_text) || ""
                        color: Theme.textPrimary
                        wrapMode: Text.Wrap
                        font.pixelSize: Theme.fontMd
                        font.family: Theme.fontMono
                    }
                }
                HudButton {
                    text: "APPLY TO PROFILE"
                    busyText: "APPLYING…"
                    tooltip: "Writes the selected telescope's timing profile from completed runs"
                    buttonColor: Theme.fillActive
                    foregroundColor: Theme.accent
                    onClicked: backend.applyDurationSuggestion()
                }
                HudButton {
                    text: "DISMISS"
                    tooltip: "Hide until this suggestion changes"
                    onClicked: historyPage.dismissedSuggestionKey = historyPage.durationSuggestionKey
                }
            }
        }
        SelectionBar {
            selectedCount: historyPage.filteredHistory.filter(item => Util.idSetHas(historyPage.selectedIds, item.id)).length
            totalCount: historyPage.filteredCount
            noun: "run"
            allowEdit: false
            onSelectAllRequested: historyPage.selectedIds = Util.idSetAll(historyPage.filteredHistory, true)
            onClearRequested: historyPage.clearSelection()
            onDeleteRequested: {
                const chosen = {}
                const items = historyPage.filteredHistory
                for (let i = 0; i < items.length; i++) {
                    const id = items[i] && items[i].id
                    if (id && Util.idSetHas(historyPage.selectedIds, id))
                        chosen[id] = true
                }
                root.confirmBulkDelete("deleteHistory", chosen, "run")
            }
        }
        HudPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: Theme.px(240)
            Layout.preferredHeight: 0
            EmptyHint {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: Theme.px(40)
                visible: historyPage.filteredCount === 0
                glyph: historyPage.scopedHistory.length === 0 ? "◷" : "⌕"
                text: historyPage.scopedHistory.length === 0
                    ? ((backend.history || []).length === 0
                        ? "No completed runs yet. History appears after a session finishes."
                        : "No completed runs for this telescope.")
                    : "No runs match this search."
            }
            ColumnLayout {
                visible: historyPage.filteredCount > 0
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: 0
                spacing: 0
                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(32)
                    Row {
                        anchors.fill: parent
                        Item { width: historyPage.gutterWidth; height: parent.height }
                        Repeater {
                            model: [
                                {label: "DATE", w: 0.12}, {label: "TARGET", w: 0.22}, {label: "DEVICE", w: 0.12},
                                {label: "FRAMES", w: 0.11}, {label: "PLANNED", w: 0.10}, {label: "ACTUAL", w: 0.10},
                                {label: "OUTCOME", w: 0.23}
                            ]
                            Text {
                                required property var modelData
                                width: (parent.width - historyPage.gutterWidth) * modelData.w
                                height: parent.height
                                text: modelData.label
                                color: Theme.accent
                                font.pixelSize: Theme.fontSm
                                font.bold: true
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                                leftPadding: Theme.px(6)
                            }
                        }
                    }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: historyExpandMenu.popup()
                    }
                    ExpandCollapseMenu {
                        id: historyExpandMenu
                        expandObjectName: "history-header-expand-all"
                        collapseObjectName: "history-header-collapse-all"
                        canExpandAll: historyPage.canExpandAll
                        canCollapseAll: historyPage.canCollapseAll
                        onExpandAllRequested: historyPage.expandAll()
                        onCollapseAllRequested: historyPage.collapseAll()
                    }
                }
                Rectangle { Layout.fillWidth: true; height: Theme.px(1); color: Theme.outline }
                ListView {
                    id: historyList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: 0
                    clip: true
                    spacing: 0
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                    model: historyPage.visibleHistory
                    delegate: Rectangle {
                        id: historyRow
                        objectName: !!(modelData && modelData.group_collapsed)
                                     ? "history-group-" + (modelData.group_id || modelData.id)
                                     : "history-" + modelData.id
                        required property var modelData
                        required property int index
                        readonly property bool collapsedGroup: !!(modelData && modelData.group_collapsed)
                        readonly property bool expanded: !historyRow.collapsedGroup && Util.idSetHas(historyPage.expandedIds, modelData.id)
                        readonly property bool showHeader: {
                            if (!modelData || !modelData.is_grouped || historyRow.collapsedGroup)
                                return false
                            if (index <= 0)
                                return true
                            const prev = historyPage.visibleHistory[index - 1]
                            return !prev || String(prev.group_key || "") !== String(modelData.group_key || "")
                        }
                        width: ListView.view.width
                        height: rowBody.implicitHeight
                        readonly property color outcomeTone: modelData.ok ? Theme.success : Theme.danger
                        readonly property real deltaSeconds: Number(modelData.delta_seconds || 0)
                        readonly property color deltaTone: Math.abs(deltaSeconds) < 60 ? Theme.textSecondary : (deltaSeconds > 0 ? Theme.warning : Theme.notice)
                        color: expanded || historyPage.rowSelected(modelData) ? Theme.hsl(0.036, 0.640, 0.196, 0.133) : (rowHover.hovered ? Theme.hsl(0.068, 0.517, 0.114, 0.094) : (index % 2 ? Theme.hsl(0.062, 0.524, 0.082, 0.078) : "transparent"))
                        border.color: expanded || historyRow.showHeader ? Theme.outline : "transparent"
                        Behavior on color { ColorAnimation { duration: Theme.quick } }
                        HoverHandler { id: rowHover }
                        Rectangle { x: 0; y: 0; width: Theme.px(2); height: parent.height; color: historyRow.outcomeTone; opacity: historyRow.expanded ? 1 : 0.55 }
                        Column {
                            id: rowBody
                            width: parent.width
                            Item {
                                visible: historyRow.showHeader
                                width: parent.width
                                height: visible ? Theme.px(26) : 0
                                Accessible.role: Accessible.Button
                                Accessible.name: "Collapse " + String(historyRow.modelData.group_title || historyRow.modelData.target_name || "mosaic")
                                TapHandler {
                                    onTapped: historyPage.toggleGroup(historyRow.modelData)
                                }
                                Text {
                                    anchors.fill: parent
                                    anchors.leftMargin: historyPage.gutterWidth + 4
                                    text: "▾  " + String(historyRow.modelData.group_title || historyRow.modelData.target_name || "Mosaic")
                                          + "  ·  " + String(historyRow.modelData.pane_count || 0)
                                          + (Number(historyRow.modelData.pane_count || 0) === 1 ? " pane" : " panes")
                                    color: Theme.accent
                                    font.pixelSize: Theme.fontSm
                                    font.bold: true
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                            }
                            Item {
                                width: parent.width
                                height: Theme.px(42)
                                activeFocusOnTab: true
                                Accessible.role: Accessible.Button
                                Accessible.name: (historyRow.modelData.date || "") + " " + (historyRow.modelData.target_name || "") + " " + (historyRow.modelData.outcome || "")
                                Accessible.onPressAction: historyPage.toggleRow(historyRow.modelData)
                                Keys.onPressed: function (event) {
                                    if (event.key === Qt.Key_Space && (event.modifiers & Qt.ShiftModifier)) {
                                        historyPage.selectRow(historyRow.modelData, true)
                                        event.accepted = true
                                        return
                                    }
                                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                                        historyPage.toggleRow(historyRow.modelData)
                                        event.accepted = true
                                    }
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    visible: parent.activeFocus
                                    color: "transparent"
                                    border.color: Theme.accent
                                    border.width: Theme.focusStroke
                                    z: 4
                                }
                                Row {
                                    anchors.fill: parent
                                    Item {
                                        width: historyPage.gutterWidth
                                        height: parent.height
                                        z: 2
                                        Text {
                                            anchors.fill: parent
                                            anchors.leftMargin: Theme.px(2)
                                            text: historyRow.collapsedGroup ? "▸" : (historyRow.expanded ? "▾" : "▸")
                                            color: Theme.accent
                                            font.pixelSize: Theme.fontSm
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                            opacity: historySelect.shown ? 0 : 1
                                            Behavior on opacity { NumberAnimation { duration: Theme.quick } }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            acceptedButtons: Qt.LeftButton
                                            preventStealing: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: historyPage.toggleRow(historyRow.modelData)
                                        }
                                        SelectBox {
                                            id: historySelect
                                            anchors.centerIn: parent
                                            anchors.horizontalCenterOffset: 1
                                            checked: historyPage.rowSelected(historyRow.modelData)
                                            revealed: rowHover.hovered || historyPage.selectedCount > 0
                                            onToggled: (shiftHeld) => historyPage.selectRow(historyRow.modelData, shiftHeld)
                                        }
                                    }
                                    Repeater {
                                        model: [
                                            {text: historyRow.modelData.date, w: 0.12, color: Theme.textPrimary, mono: true},
                                            {text: historyRow.collapsedGroup
                                                   ? ((historyRow.modelData.group_title || historyRow.modelData.target_name || "")
                                                      + (historyRow.modelData.group_summary ? "  ·  " + historyRow.modelData.group_summary : ""))
                                                   : historyRow.modelData.target_name, w: 0.22, color: Theme.textPrimary, bold: true},
                                            {text: historyRow.modelData.device_name, w: 0.12, color: Theme.textPrimary, dot: historyRow.modelData.device_color || Theme.accent},
                                            {text: historyRow.modelData.frame_text || String(historyRow.modelData.frame_count || 0), w: 0.11, color: Theme.textSecondary, mono: true},
                                            {text: historyRow.modelData.planned_text, w: 0.10, color: Theme.textSecondary, mono: true},
                                            {text: historyRow.modelData.actual_text, w: 0.10, color: historyRow.deltaTone, mono: true},
                                            {text: (historyRow.modelData.ok ? "✓ " : "✗ ") + historyRow.modelData.outcome, w: 0.23, color: historyRow.outcomeTone}
                                        ]
                                        Item {
                                            required property var modelData
                                            width: (parent.width - historyPage.gutterWidth) * modelData.w
                                            height: parent.height
                                            Rectangle {
                                                visible: !!parent.modelData.dot
                                                anchors.left: parent.left; anchors.leftMargin: Theme.px(6)
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: Theme.px(6); height: Theme.px(6); radius: Theme.px(3)
                                                color: parent.modelData.dot || "transparent"
                                            }
                                            Text {
                                                anchors.fill: parent
                                                text: parent.modelData.text
                                                color: parent.modelData.color
                                                font.pixelSize: Theme.fontMd
                                                font.bold: !!parent.modelData.bold
                                                font.family: parent.modelData.mono ? Theme.fontMono : Theme.fontUi
                                                elide: Text.ElideRight
                                                verticalAlignment: Text.AlignVCenter
                                                leftPadding: parent.modelData.dot ? Theme.s4 : Theme.px(6)
                                                rightPadding: Theme.px(6)
                                            }
                                        }
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    anchors.leftMargin: historyPage.gutterWidth
                                    acceptedButtons: Qt.LeftButton
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: mouse => {
                                        if (mouse.modifiers & Qt.ShiftModifier) {
                                            historyPage.selectRow(historyRow.modelData, true)
                                            return
                                        }
                                        historyPage.toggleRow(historyRow.modelData)
                                    }
                                }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: historyMenu.popup()
                                }
                                HudMenu {
                                    id: historyMenu
                                    HudMenuItem {
                                        text: "Run again"
                                        glyph: "\uE768"
                                        enabled: !!historyRow.modelData.has_session
                                        onTriggered: backend.runNow(historyRow.modelData.session_id)
                                    }
                                    HudMenuSeparator {}
                                    HudMenuItem {
                                        text: "Copy target name"
                                        glyph: "\uE8C8"
                                        enabled: !!historyRow.modelData.target_name
                                        onTriggered: backend.copyText(String(historyRow.modelData.target_name))
                                    }
                                    HudMenuItem {
                                        text: "Copy outcome"
                                        glyph: "\uE8C8"
                                        enabled: !!historyRow.modelData.outcome
                                        onTriggered: backend.copyText(String(historyRow.modelData.outcome))
                                    }
                                    HudMenuSeparator {}
                                    HudMenuItem {
                                        objectName: "history-expand-all"
                                        text: "Expand all"
                                        glyph: "\uE70D"
                                        enabled: historyPage.canExpandAll
                                        onTriggered: historyPage.expandAll()
                                    }
                                    HudMenuItem {
                                        objectName: "history-collapse-all"
                                        text: "Collapse all"
                                        glyph: "\uE70E"
                                        enabled: historyPage.canCollapseAll
                                        onTriggered: historyPage.collapseAll()
                                    }
                                    HudMenuSeparator {}
                                    HudMenuItem {
                                        text: "Select all"
                                        glyph: "\uE8A5"
                                        enabled: historyPage.filteredCount > 0
                                        onTriggered: historyPage.selectedIds = Util.idSetAll(historyPage.filteredHistory, true)
                                    }
                                    HudMenuItem {
                                        text: "Unselect all"
                                        glyph: "\uE711"
                                        enabled: historyPage.selectedCount > 0
                                        onTriggered: historyPage.clearSelection()
                                    }
                                    HudMenuSeparator {}
                                    HudMenuItem {
                                        text: "Remove"
                                        glyph: "\uE74D"
                                        destructive: true
                                        onTriggered: root.confirmBulkDelete("deleteHistory", historyPage.rowDeleteTarget(historyRow.modelData), "run")
                                    }
                                }
                            }
                            Item {
                                visible: historyRow.expanded && !historyRow.collapsedGroup
                                width: parent.width
                                height: visible ? detailCol.implicitHeight + Theme.s4 : 0
                                ColumnLayout {
                                    id: detailCol
                                    x: historyPage.gutterWidth + 6
                                    width: parent.width - x - 8
                                    y: Theme.s1
                                    spacing: Theme.s2
                                    Text {
                                        visible: !!(historyRow.modelData.summary)
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.summary
                                        color: Theme.textPrimary
                                        font.pixelSize: Theme.fontMd
                                        elide: Text.ElideRight
                                    }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 4
                                        columnSpacing: Theme.s4
                                        rowSpacing: Theme.s1
                                        Text { text: "SCHEDULED"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "STARTED"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "ENDED"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "VARIANCE"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.scheduled_text; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.started_text; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.ended_text; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text {
                                            text: (historyRow.deltaSeconds > 60 ? "▲ " : historyRow.deltaSeconds < -60 ? "▼ " : "● ") + historyRow.modelData.delta_text
                                            color: Math.abs(historyRow.deltaSeconds) < 60 ? Theme.success : historyRow.deltaTone
                                            font.pixelSize: Theme.fontMd
                                            font.family: Theme.fontMono
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                            Layout.minimumWidth: 0
                                        }
                                        Text { text: "FRAMES"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "CAPTURED"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "PLANNED TIME"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "ACTUAL TIME"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: String(historyRow.modelData.planned_frames || historyRow.modelData.frame_count || 0) + " planned"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: String(historyRow.modelData.captured_frames || 0) + " captured"; color: historyRow.modelData.ok ? Theme.success : Theme.textPrimary; font.pixelSize: Theme.fontMd; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.planned_text; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.actual_text; color: historyRow.deltaTone; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "FILTER"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "GAIN"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "CAMERA"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "EXPOSURE"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.filter_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.gain_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.camera_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.exposure_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "MOSAIC"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "WORKFLOW"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: "TARGET"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.columnSpan: 2 }
                                        Text { text: historyRow.modelData.mosaic_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.workflow_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0 }
                                        Text { text: historyRow.modelData.coords_text || "—"; color: Theme.textPrimary; font.pixelSize: Theme.fontMd; font.family: Theme.fontMono; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.columnSpan: 2 }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.outcome
                                        color: historyRow.modelData.ok ? Theme.success : Theme.danger
                                        wrapMode: Text.Wrap
                                        font.pixelSize: Theme.fontMd
                                    }
                                    Text {
                                        visible: !!(historyRow.modelData.step_text)
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.step_text
                                        color: Theme.textSecondary
                                        wrapMode: Text.Wrap
                                        font.pixelSize: Theme.fontSm
                                        font.family: Theme.fontMono
                                    }
                                    Text {
                                        visible: !!(historyRow.modelData.notes)
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.notes
                                        color: Theme.textSecondary
                                        wrapMode: Text.Wrap
                                        font.pixelSize: Theme.fontSm
                                    }
                                    RowLayout {
                                        HudButton {
                                            text: "RUN AGAIN"
                                            enabled: !!historyRow.modelData.has_session
                                            busyText: "STARTING…"
                                            buttonColor: Theme.fillActive
                                            foregroundColor: Theme.accent
                                            onClicked: backend.runNow(historyRow.modelData.session_id)
                                        }
                                        HudButton {
                                            text: "REMOVE"
                                            busyText: "REMOVING…"
                                            buttonColor: Theme.fillDanger
                                            foregroundColor: Theme.danger
                                            onClicked: root.confirmBulkDelete("deleteHistory", historyPage.rowDeleteTarget(historyRow.modelData), "run")
                                        }
                                        Item { Layout.fillWidth: true }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    }
}
