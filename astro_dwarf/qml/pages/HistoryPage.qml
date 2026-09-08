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
    property string query: ""
    property int outcomeFilter: 0
    property int expandedIndex: -1
    property var selectedIds: ({})
    property string selectionAnchorId: ""
    readonly property int selectedCount: Util.idSetCount(selectedIds)
    // Leading gutter shared by the expand chevron and the floating select box.
    readonly property int gutterWidth: 24
    function selectClick(id, shift) {
        const result = Util.clickSelect(selectedIds, filteredHistory, id, shift, selectionAnchorId)
        selectedIds = result.map
        selectionAnchorId = result.anchor
    }
    readonly property var filteredHistory: {
        const items = backend.history || []
        const q = historyPage.query.trim().toLowerCase()
        const out = []
        for (let i = 0; i < items.length; i++) {
            const item = items[i]
            if (historyPage.outcomeFilter === 1 && !item.ok)
                continue
            if (historyPage.outcomeFilter === 2 && item.ok)
                continue
            if (q) {
                const hay = [item.date, item.target_name, item.device_name, item.outcome, item.summary, item.notes].join(" ").toLowerCase()
                if (hay.indexOf(q) < 0)
                    continue
            }
            out.push(item)
        }
        return out
    }
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
    function resetExpanded() { historyPage.expandedIndex = -1 }
    onQueryChanged: resetExpanded()
    onOutcomeFilterChanged: resetExpanded()
    Connections {
        target: backend
        function onHistoryChanged() {
            historyPage.resetExpanded()
            historyPage.selectedIds = Util.pruneIdSet(historyPage.selectedIds, backend.history)
        }
    }

    Flickable {
        id: historyFlick
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        contentWidth: width
        contentHeight: Math.max(height, historyColumn.implicitHeight)
        interactive: contentHeight > height + 1
        ScrollBar.vertical: HiddenBar {}
        ScrollBar.horizontal: HiddenBar {}
    ColumnLayout {
        id: historyColumn
        width: historyFlick.width
        height: Math.max(implicitHeight, historyFlick.height)
        spacing: 10
        PageHeader {
            title: "HISTORY"
            subtitle: backend.history.length === 0
                ? "Completed runs appear here with timing, frames and outcome"
                : backend.history.length + " recorded run" + (backend.history.length === 1 ? "" : "s") + "  ·  click a row for timing, frames and outcome details"
            HudButton {
                text: "CLEAR HISTORY"
                enabled: backend.history.length > 0
                busyText: "CLEARING…"
                buttonColor: Theme.fillDanger
                foregroundColor: Theme.danger
                onClicked: {
                    confirmDialog.kind = "clearHistory"
                    confirmDialog.headingText = "CLEAR HISTORY"
                    confirmDialog.confirmLabel = "CLEAR ALL"
                    confirmDialog.summary = "Delete every recorded run? This cannot be undone."
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
                    Layout.preferredHeight: 108
                    overlay: [
                        Text {
                            anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 12
                            text: statTile.modelData[2]
                            color: statTile.modelData[3]
                            opacity: 0.35
                            font.pixelSize: 20
                        }
                    ]
                    Text { text: modelData[0]; color: modelData[3]; font.pixelSize: 22; font.bold: true; font.family: Theme.fontMono; wrapMode: Text.NoWrap; elide: Text.ElideRight; Layout.fillWidth: true }
                    Text { text: modelData[1]; color: Theme.textSecondary; font.pixelSize: 11; font.letterSpacing: 1.4 }
                    Text { visible: !!(modelData[4]); text: modelData[4] || ""; color: Theme.muted; font.pixelSize: 10 }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            HudField {
                Layout.fillWidth: true
                placeholderText: "Search target, device, or outcome"
                onTextChanged: historyPage.query = text
            }
            HudCombo {
                Layout.preferredWidth: 160
                model: ["All outcomes", "Completed", "Failed"]
                currentIndex: historyPage.outcomeFilter
                onActivated: historyPage.outcomeFilter = currentIndex
            }
        }
        SelectionBar {
            selectedCount: historyPage.filteredHistory.filter(item => Util.idSetHas(historyPage.selectedIds, item.id)).length
            totalCount: historyPage.filteredCount
            noun: "run"
            onSelectAllRequested: historyPage.selectedIds = Util.idSetAll(historyPage.filteredHistory, true)
            onClearRequested: historyPage.selectedIds = ({})
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
            Layout.minimumHeight: 240
            Layout.preferredHeight: 0
            EmptyHint {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 40
                visible: historyPage.filteredCount === 0
                glyph: backend.history.length === 0 ? "◷" : "⌕"
                text: backend.history.length === 0
                    ? "No completed runs yet. History appears after a session finishes."
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
                    Layout.preferredHeight: 32
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
                                font.pixelSize: 10
                                font.bold: true
                                verticalAlignment: Text.AlignVCenter
                                elide: Text.ElideRight
                                leftPadding: 6
                            }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.outline }
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
                    model: historyPage.filteredHistory
                    delegate: Rectangle {
                        id: historyRow
                        required property var modelData
                        required property int index
                        readonly property bool expanded: historyPage.expandedIndex === index
                        width: ListView.view.width
                        height: rowBody.implicitHeight
                        readonly property color outcomeTone: modelData.ok ? Theme.success : Theme.danger
                        readonly property real deltaSeconds: Number(modelData.delta_seconds || 0)
                        readonly property color deltaTone: Math.abs(deltaSeconds) < 60 ? Theme.textSecondary : (deltaSeconds > 0 ? Theme.warning : Theme.notice)
                        color: expanded || Util.idSetHas(historyPage.selectedIds, modelData.id) ? Theme.hsl(0.036, 0.640, 0.196, 0.133) : (rowHover.hovered ? Theme.hsl(0.068, 0.517, 0.114, 0.094) : (index % 2 ? Theme.hsl(0.062, 0.524, 0.082, 0.078) : "transparent"))
                        border.color: expanded ? Theme.outline : "transparent"
                        Behavior on color { ColorAnimation { duration: 100 } }
                        HoverHandler { id: rowHover }
                        Rectangle { x: 0; y: 0; width: 2; height: parent.height; color: historyRow.outcomeTone; opacity: historyRow.expanded ? 1 : 0.55 }
                        Column {
                            id: rowBody
                            width: parent.width
                            Item {
                                width: parent.width
                                height: 42
                                Row {
                                    anchors.fill: parent
                                    Item {
                                        width: historyPage.gutterWidth
                                        height: parent.height
                                        z: 2
                                        Text {
                                            anchors.fill: parent
                                            anchors.leftMargin: 2
                                            text: historyRow.expanded ? "▾" : "▸"
                                            color: Theme.accent
                                            font.pixelSize: 10
                                            horizontalAlignment: Text.AlignHCenter
                                            verticalAlignment: Text.AlignVCenter
                                            opacity: historySelect.shown ? 0 : 1
                                            Behavior on opacity { NumberAnimation { duration: 90 } }
                                        }
                                        SelectBox {
                                            id: historySelect
                                            anchors.centerIn: parent
                                            anchors.horizontalCenterOffset: 1
                                            checked: Util.idSetHas(historyPage.selectedIds, historyRow.modelData.id)
                                            revealed: rowHover.hovered || historyPage.selectedCount > 0
                                            onToggled: (shiftHeld) => historyPage.selectClick(historyRow.modelData.id, shiftHeld)
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            acceptedButtons: Qt.LeftButton
                                            preventStealing: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: mouse => historyPage.selectClick(historyRow.modelData.id, !!(mouse.modifiers & Qt.ShiftModifier))
                                        }
                                    }
                                    Repeater {
                                        model: [
                                            {text: historyRow.modelData.date, w: 0.12, color: Theme.textPrimary, mono: true},
                                            {text: historyRow.modelData.target_name, w: 0.22, color: Theme.textPrimary, bold: true},
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
                                                anchors.left: parent.left; anchors.leftMargin: 6
                                                anchors.verticalCenter: parent.verticalCenter
                                                width: 6; height: 6; radius: 3
                                                color: parent.modelData.dot || "transparent"
                                            }
                                            Text {
                                                anchors.fill: parent
                                                text: parent.modelData.text
                                                color: parent.modelData.color
                                                font.pixelSize: 12
                                                font.bold: !!parent.modelData.bold
                                                font.family: parent.modelData.mono ? Theme.fontMono : Theme.fontUi
                                                elide: Text.ElideRight
                                                verticalAlignment: Text.AlignVCenter
                                                leftPadding: parent.modelData.dot ? 16 : 6
                                                rightPadding: 6
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
                                            historyPage.selectClick(historyRow.modelData.id, true)
                                            return
                                        }
                                        historyPage.expandedIndex = historyRow.expanded ? -1 : historyRow.index
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
                                        text: "Select all"
                                        glyph: "\uE8A5"
                                        enabled: historyPage.filteredCount > 0
                                        onTriggered: historyPage.selectedIds = Util.idSetAll(historyPage.filteredHistory, true)
                                    }
                                    HudMenuItem {
                                        text: "Unselect all"
                                        glyph: "\uE711"
                                        enabled: historyPage.selectedCount > 0
                                        onTriggered: {
                                            historyPage.selectedIds = ({})
                                            historyPage.selectionAnchorId = ""
                                        }
                                    }
                                    HudMenuSeparator {}
                                    HudMenuItem {
                                        text: "Remove"
                                        glyph: "\uE74D"
                                        destructive: true
                                        onTriggered: backend.deleteHistoryRecord(historyRow.modelData.id)
                                    }
                                }
                            }
                            Item {
                                visible: historyRow.expanded
                                width: parent.width
                                height: visible ? detailCol.implicitHeight + 16 : 0
                                ColumnLayout {
                                    id: detailCol
                                    x: historyPage.gutterWidth + 6
                                    width: parent.width - x - 8
                                    y: 4
                                    spacing: 6
                                    Text {
                                        visible: !!(historyRow.modelData.summary)
                                        text: historyRow.modelData.summary
                                        color: Theme.textPrimary
                                        font.pixelSize: 12
                                    }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 4
                                        columnSpacing: 16
                                        rowSpacing: 4
                                        Text { text: "SCHEDULED"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "STARTED"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "ENDED"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "VARIANCE"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: historyRow.modelData.scheduled_text; color: Theme.textPrimary; font.pixelSize: 12 }
                                        Text { text: historyRow.modelData.started_text; color: Theme.textPrimary; font.pixelSize: 12 }
                                        Text { text: historyRow.modelData.ended_text; color: Theme.textPrimary; font.pixelSize: 12 }
                                        Text {
                                            text: (historyRow.deltaSeconds > 60 ? "▲ " : historyRow.deltaSeconds < -60 ? "▼ " : "● ") + historyRow.modelData.delta_text
                                            color: Math.abs(historyRow.deltaSeconds) < 60 ? Theme.success : historyRow.deltaTone
                                            font.pixelSize: 12
                                            font.family: Theme.fontMono
                                        }
                                        Text { text: "FRAMES"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "CAPTURED"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "PLANNED TIME"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: "ACTUAL TIME"; color: Theme.textSecondary; font.pixelSize: 9; font.bold: true }
                                        Text { text: String(historyRow.modelData.planned_frames || historyRow.modelData.frame_count || 0) + " planned"; color: Theme.textPrimary; font.pixelSize: 12 }
                                        Text { text: String(historyRow.modelData.captured_frames || 0) + " captured"; color: historyRow.modelData.ok ? Theme.success : Theme.textPrimary; font.pixelSize: 12 }
                                        Text { text: historyRow.modelData.planned_text; color: Theme.textPrimary; font.pixelSize: 12; font.family: Theme.fontMono }
                                        Text { text: historyRow.modelData.actual_text; color: historyRow.deltaTone; font.pixelSize: 12; font.family: Theme.fontMono }
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.outcome
                                        color: historyRow.modelData.ok ? Theme.success : Theme.danger
                                        wrapMode: Text.Wrap
                                        font.pixelSize: 12
                                    }
                                    Text {
                                        visible: !!(historyRow.modelData.notes)
                                        Layout.fillWidth: true
                                        text: historyRow.modelData.notes
                                        color: Theme.textSecondary
                                        wrapMode: Text.Wrap
                                        font.pixelSize: 11
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
                                            onClicked: backend.deleteHistoryRecord(historyRow.modelData.id)
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
