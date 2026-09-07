import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Window
import QtCore

ApplicationWindow {
    id: root
    width: 1480
    height: 920
    minimumWidth: 1180
    minimumHeight: 760
    visible: true
    title: "ASTRO DWARF"
    color: "#05080F"
    font.family: "Segoe UI"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
    readonly property bool windowMaximized: visibility === Window.Maximized

    function dragWindow() {
        if (!root.windowMaximized)
            root.startSystemMove()
    }

    function toggleMaximized() {
        if (root.windowMaximized)
            root.showNormal()
        else
            root.showMaximized()
    }

    property color surface: "#0B1520"
    property color surfaceHigh: "#122033"
    property color outline: "#1E4A63"
    property color textPrimary: "#E8F7FF"
    property color textSecondary: "#7FA4B8"
    property color accent: "#4DE8FF"
    property color success: "#3DFFB0"
    property color danger: "#FF6B7A"
    property color warning: "#F5C542"
    property int currentPage: 0
    property real joySpeed: 1
    readonly property bool targetLocked: backend.selectedDevice.connected && backend.currentSession.status === "running"
    readonly property bool dataPage: currentPage !== 0
    readonly property bool scopeOnline: !!(backend.selectedDevice && backend.selectedDevice.connected)
    readonly property bool scopeImaging: !!(backend.selectedDevice && backend.selectedDevice.busy)
    readonly property bool scopeLinking: !!(backend.selectedDevice && (backend.selectedDevice.connecting || backend.selectedDevice.disconnecting))
    readonly property string scopePending: String((backend.selectedDevice && backend.selectedDevice.pending_action) || "")
    readonly property string scopeActivity: String((backend.selectedDevice && backend.selectedDevice.activity) || "")
    readonly property bool previewFailed: {
        const status = String(backend.previewStatus || "").toLowerCase()
        return status.indexOf("fail") >= 0 || status.indexOf("could not") >= 0
    }
    readonly property bool previewStarting: backend.previewActive && !backend.previewPlaying && !previewFailed
    readonly property bool scopeOccupied: scopeImaging || scopePending !== "" || scopeActivity !== "" || previewStarting
    readonly property bool cameraLiveEnabled: commandEnabled("set_exposure")
    readonly property bool motionEnabled: commandEnabled("joystick")

    function statusColor(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return root.accent
        case "error": return root.danger
        case "done": return root.success
        case "skipped": return root.textSecondary
        default: return root.textPrimary
        }
    }
    function canReset(status) {
        const value = String(status || "").toLowerCase()
        return value === "error" || value === "skipped" || value === "done"
    }
    function statusFill(status) {
        switch (String(status || "").toLowerCase()) {
        case "running": return "#123C52"
        case "error": return "#3A1218"
        case "done": return "#143028"
        default: return "#122033"
        }
    }
    function commandEnabled(op) {
        const pending = root.scopePending
        const activity = root.scopeActivity
        if (!root.scopeOnline || root.scopeLinking)
            return false
        if (pending === op)
            return false
        const stopFor = {
            burst: "burst_stop",
            burst_start: "burst_stop",
            record: "record_stop",
            record_start: "record_stop",
            timelapse: "timelapse_stop",
            timelapse_start: "timelapse_stop",
            calibrate: "stop_calibrate",
            autofocus: "stop_autofocus",
            infinity: "stop_autofocus",
            polar: "stop_polar"
        }
        if (op === "stop_all")
            return true
        const isStop = op === "stop_goto" || op.indexOf("stop_") === 0 || op.slice(-5) === "_stop"
        if (isStop) {
            if (op === stopFor[pending] || op === stopFor[activity])
                return true
            return op === "stop_goto" && !root.scopeOccupied
        }
        return !root.scopeOccupied
    }

    function requestDeviceAction(operation, label) {
        if (!root.commandEnabled(operation))
            return
        if (operation === "reboot" || operation === "power_down") {
            confirmDialog.kind = "device"
            confirmDialog.headingText = "CONFIRM COMMAND"
            confirmDialog.confirmLabel = "CONFIRM"
            confirmDialog.operation = operation
            confirmDialog.summary = "Run " + label + " on " + (backend.selectedDevice.name || "this telescope") + "?"
            confirmDialog.open()
            return
        }
        backend.deviceAction(backend.selectedDeviceId, operation)
    }

    function targetCoordinates(item) {
        const target = item && item.target ? item.target : null
        if (!target || target.ra_hours === undefined || target.ra_hours === null
                || target.dec_degrees === undefined || target.dec_degrees === null)
            return ""
        return "RA " + Number(target.ra_hours).toFixed(3) + "h  DEC "
            + Number(target.dec_degrees).toFixed(3) + "°"
    }

    function logLine(item) {
        return item ? item.time + "  [" + item.device + "]  " + item.message : ""
    }

    function allLogText() {
        return backend.allLogText()
    }

    function asset(name) { return Qt.resolvedUrl("assets/" + name) }
    function goToPage(idx) {
        if (idx === root.currentPage) {
            if (idx === 4 && !settingsPage.isDirty())
                settingsPage.load()
            return
        }
        if (root.currentPage === 4 && settingsPage.isDirty()) {
            settingsLeaveDialog.pendingPage = idx
            settingsLeaveDialog.open()
            return
        }
        root.currentPage = idx
        if (idx === 4)
            settingsPage.load()
    }
    function syncCombo(combo) {
        if (!combo || combo.count === 0)
            return
        for (let i = 0; i < combo.count; i++) {
            if (combo.valueAt(i) === backend.selectedDeviceId) {
                combo.currentIndex = i
                return
            }
        }
    }

    component HiddenBar: ScrollBar {
        policy: ScrollBar.AlwaysOff
        interactive: false
        visible: false
        implicitWidth: 0
        implicitHeight: 0
    }

    component HudPanel: Item {
        id: panel
        property alias title: heading.text
        property alias headerExtra: headerExtraRow.data
        property color fill: "#B3070D16"
        default property alias contents: body.data
        implicitWidth: 240
        implicitHeight: (headerRow.visible ? headerRow.implicitHeight + 8 : 0) + body.implicitHeight + 24
        clip: true

        Rectangle { anchors.fill: parent; color: panel.fill }
        Canvas {
            anchors.fill: parent
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                const w = width, h = height, n = 11
                ctx.strokeStyle = "#66E8FFFF"
                ctx.lineWidth = 1.25
                ctx.beginPath()
                ctx.moveTo(n, 1.5)
                ctx.lineTo(w - n, 1.5)
                ctx.lineTo(w - 1.5, n)
                ctx.lineTo(w - 1.5, h - n)
                ctx.lineTo(w - n, h - 1.5)
                ctx.lineTo(n, h - 1.5)
                ctx.lineTo(1.5, h - n)
                ctx.lineTo(1.5, n)
                ctx.closePath()
                ctx.stroke()
            }
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
        }
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8
            RowLayout {
                id: headerRow
                visible: heading.text.length || headerExtraRow.children.length
                Layout.fillWidth: true
                spacing: 8
                Text {
                    id: heading
                    visible: text.length
                    color: root.accent
                    font.pixelSize: 11
                    font.letterSpacing: 1.6
                    font.bold: true
                    Layout.fillWidth: true
                }
                Row {
                    id: headerExtraRow
                    spacing: 4
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                }
            }
            Flickable {
                id: panelFlick
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                contentWidth: width
                contentHeight: Math.max(height, body.implicitHeight)
                interactive: contentHeight > height + 1
                ScrollBar.vertical: HiddenBar {}
                ScrollBar.horizontal: HiddenBar {}
                Item {
                    width: panelFlick.width
                    height: Math.max(body.implicitHeight, panelFlick.height)
                    ColumnLayout {
                        id: body
                        anchors.fill: parent
                        spacing: 8
                    }
                }
            }
        }
    }

    component HudButton: Button {
        id: hudBtn
        property color buttonColor: root.surfaceHigh
        property color foregroundColor: root.textPrimary
        property string busyText: ""
        property bool busy: false
        property int busyMs: 1400
        property bool _clickBusy: false
        readonly property bool isBusy: busy || _clickBusy
        hoverEnabled: enabled
        opacity: enabled || isBusy ? 1 : 0.42
        font.pixelSize: 12
        font.letterSpacing: 0.6
        leftPadding: 12
        rightPadding: 12
        implicitHeight: 34
        Timer {
            id: clickBusyTimer
            interval: Math.max(1, hudBtn.busyMs)
            repeat: false
            onTriggered: hudBtn._clickBusy = false
        }
        onClicked: {
            if (hudBtn.busyText === "" || hudBtn.busy || hudBtn.busyMs <= 0)
                return
            hudBtn._clickBusy = true
            clickBusyTimer.restart()
        }
        background: Rectangle {
            color: !hudBtn.enabled && !hudBtn.isBusy ? "#070B12" : hudBtn.down || hudBtn.isBusy ? Qt.darker(hudBtn.buttonColor, 1.2) : hudBtn.hovered ? Qt.lighter(hudBtn.buttonColor, 1.18) : hudBtn.buttonColor
            border.color: !hudBtn.enabled && !hudBtn.isBusy ? "#152838" : hudBtn.hovered || hudBtn.down || hudBtn.isBusy ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
        contentItem: Text {
            text: (hudBtn.isBusy && hudBtn.busyText !== "") ? hudBtn.busyText : hudBtn.text
            color: hudBtn.enabled || hudBtn.isBusy ? hudBtn.foregroundColor : root.textSecondary
            font: hudBtn.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
    }

    component HudMenu: Menu {
        id: hudMenu
        popupType: Popup.Item
        implicitWidth: 232
        padding: 6
        topPadding: 6
        bottomPadding: 6
        leftPadding: 6
        rightPadding: 6
        overlap: 2
        background: Rectangle {
            color: root.surfaceHigh
            border.color: root.outline
            border.width: 1
            radius: 8
        }
    }

    component HudMenuItem: MenuItem {
        id: hudMenuItem
        property string glyph: ""
        property string trailingText: ""
        property bool destructive: false
        implicitWidth: 220
        implicitHeight: 34
        leftPadding: 8
        rightPadding: 10
        topPadding: 0
        bottomPadding: 0
        opacity: enabled ? 1 : 0.4
        font.pixelSize: 13
        background: Rectangle {
            color: hudMenuItem.highlighted || hudMenuItem.down ? "#123C52" : "transparent"
            radius: 4
        }
        contentItem: RowLayout {
            spacing: 10
            Text {
                Layout.preferredWidth: 18
                text: hudMenuItem.glyph
                color: hudMenuItem.destructive ? root.danger : root.textSecondary
                font.family: "Segoe MDL2 Assets"
                font.pixelSize: 14
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                Layout.fillWidth: true
                text: hudMenuItem.text
                color: hudMenuItem.destructive ? root.danger : root.textPrimary
                font: hudMenuItem.font
                elide: Text.ElideRight
                verticalAlignment: Text.AlignVCenter
            }
            Text {
                visible: text.length > 0
                text: hudMenuItem.trailingText
                color: root.textSecondary
                font.pixelSize: 11
                elide: Text.ElideMiddle
                Layout.maximumWidth: 92
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    component HudMenuSeparator: MenuSeparator {
        implicitHeight: 9
        contentItem: Rectangle {
            implicitHeight: 1
            color: root.outline
        }
        leftPadding: 8
        rightPadding: 8
        topPadding: 4
        bottomPadding: 4
    }

    component SessionContextMenu: HudMenu {
        id: sessionContextMenu
        property var sessionData: ({})
        readonly property string sessionId: String((sessionData && sessionData.id) || "")
        readonly property string sessionStatus: String((sessionData && sessionData.status) || "")
        readonly property string coordinates: root.targetCoordinates(sessionData)

        HudMenuItem {
            text: "Edit"
            glyph: "\uE70F"
            enabled: sessionContextMenu.sessionStatus !== "running"
            onTriggered: sessionDialog.openExisting(sessionContextMenu.sessionData)
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
            enabled: root.canReset(sessionContextMenu.sessionStatus)
            onTriggered: backend.resetSession(sessionContextMenu.sessionId)
        }
        HudMenuItem {
            text: "Duplicate"
            glyph: "\uE8C8"
            onTriggered: backend.duplicateSession(sessionContextMenu.sessionId)
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
            text: "Delete"
            glyph: "\uE74D"
            destructive: true
            enabled: sessionContextMenu.sessionStatus !== "running"
            onTriggered: backend.deleteSession(sessionContextMenu.sessionId)
        }
    }

    component HudSplitView: SplitView {
        handle: Rectangle {
            implicitWidth: 8
            implicitHeight: 8
            color: SplitHandle.pressed ? "#334DE8FF" : (SplitHandle.hovered ? "#221E4A63" : "transparent")
            Rectangle {
                anchors.centerIn: parent
                width: parent.width >= parent.height ? 22 : 2
                height: parent.width >= parent.height ? 2 : 22
                radius: 1
                color: SplitHandle.pressed ? root.accent : (SplitHandle.hovered ? root.accent : root.outline)
            }
        }
    }

    Settings {
        id: layoutSettings
        category: "controlLayout"
        property var columnsState
        property var leftState
        property var centerState
        property var rightState
        property var calendarState
    }

    function restoreSplit(view, state) {
        if (view && state)
            view.restoreState(state)
    }

    function saveLayout() {
        layoutSettings.columnsState = controlColumns.saveState()
        layoutSettings.leftState = controlLeft.saveState()
        layoutSettings.centerState = controlCenter.saveState()
        layoutSettings.rightState = controlRight.saveState()
        layoutSettings.calendarState = calendarSplit.saveState()
    }

    onClosing: saveLayout()

    Timer {
        interval: 1
        running: true
        repeat: false
        onTriggered: {
            restoreSplit(controlColumns, layoutSettings.columnsState)
            restoreSplit(controlLeft, layoutSettings.leftState)
            restoreSplit(controlCenter, layoutSettings.centerState)
            restoreSplit(controlRight, layoutSettings.rightState)
            restoreSplit(calendarSplit, layoutSettings.calendarState)
            root.maybeAskLocation()
        }
    }

    function maybeAskLocation() {
        const configured = !!backend.selectedDevice.location_configured
        if (!configured) {
            if (!locationDialog.visible)
                locationDialog.open()
            return
        }
        if (locationDialog.visible)
            locationDialog.close()
    }

    component HudField: TextField {
        id: field
        color: field.enabled ? root.textPrimary : root.textSecondary
        placeholderTextColor: root.textSecondary
        selectedTextColor: "#041018"
        selectionColor: root.accent
        opacity: field.enabled ? 1 : 0.45
        font.pixelSize: 13
        leftPadding: 10
        rightPadding: 10
        implicitHeight: 34
        background: Rectangle {
            color: field.enabled ? "#0A1524" : "#070B12"
            border.color: !field.enabled ? "#152838" : field.activeFocus ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
    }

    component HudCombo: ComboBox {
        id: combo
        implicitHeight: 34
        font.pixelSize: 13
        palette.window: "#02060C"
        palette.windowText: root.textPrimary
        palette.base: "#02060C"
        palette.text: root.textPrimary
        palette.button: "#0A1524"
        palette.buttonText: root.textPrimary
        palette.highlight: "#123C52"
        palette.highlightedText: root.accent
        opacity: combo.enabled ? 1 : 0.45
        background: Rectangle {
            color: combo.enabled ? "#0A1524" : "#070B12"
            border.color: !combo.enabled ? "#152838" : combo.hovered || combo.down ? root.accent : root.outline
            border.width: 1
            radius: 2
        }
        contentItem: Text {
            leftPadding: 10
            rightPadding: 22
            text: combo.displayText
            color: combo.enabled ? root.textPrimary : root.textSecondary
            font: combo.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            text: "▾"
            color: combo.enabled ? root.accent : root.textSecondary
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
        }
        delegate: ItemDelegate {
            width: combo.width
            height: 32
            highlighted: combo.highlightedIndex === index
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.text: root.textPrimary
            palette.highlightedText: root.accent
            contentItem: Text {
                text: combo.textAt(index)
                color: highlighted ? root.accent : root.textPrimary
                font.pixelSize: 13
                verticalAlignment: Text.AlignVCenter
                leftPadding: 10
            }
            background: Rectangle { color: highlighted ? "#123C52" : "#02060C" }
        }
        popup: Popup {
            y: combo.height + 3
            width: combo.width
            padding: 1
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.base: "#02060C"
            palette.text: root.textPrimary
            background: Rectangle { color: "#02060C"; border.color: root.accent }
            contentItem: ListView {
                clip: true
                implicitHeight: Math.min(contentHeight, 240)
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
            }
        }
    }

    component HudSearchCombo: Item {
        id: searchCombo
        property var allItems: []
        property int filterLimit: 120
        property string selectedName: ""
        property alias editText: searchField.text
        property bool listOpen: false
        property var filtered: []
        signal itemChosen(var item)
        implicitHeight: 34
        implicitWidth: 240

        function copyAllItems() {
            const items = searchCombo.allItems || []
            const out = []
            for (let i = 0; i < items.length; i++)
                out.push(items[i])
            return out
        }

        function indexOfCurrent(items) {
            const name = searchCombo.selectedName
            const text = String(searchField.text || "")
            for (let i = 0; i < items.length; i++) {
                if ((name && items[i].name === name) || items[i].name === text || items[i].label === text)
                    return i
            }
            return items.length ? 0 : -1
        }

        function revealCurrent() {
            const idx = suggestionView.currentIndex
            if (idx < 0)
                return
            suggestionView.positionViewAtIndex(idx, ListView.Center)
        }

        function openFullList() {
            const items = copyAllItems()
            const idx = searchCombo.indexOfCurrent(items)
            searchCombo.filtered = items
            searchCombo.listOpen = true
            Qt.callLater(function () {
                suggestionView.currentIndex = idx
                searchCombo.revealCurrent()
                if (searchCombo.selectedName)
                    searchField.selectAll()
            })
        }

        function refreshFilter() {
            const needle = String(searchField.text || "").toLowerCase().replace(/_/g, " ")
            if (!needle) {
                const items = copyAllItems()
                searchCombo.filtered = items
                suggestionView.currentIndex = searchCombo.indexOfCurrent(items)
                Qt.callLater(searchCombo.revealCurrent)
                return
            }
            const items = searchCombo.allItems || []
            const ranked = []
            for (let i = 0; i < items.length; i++) {
                const item = items[i]
                const hay = [item.name, item.label, item.comment].join(" ").toLowerCase().replace(/_/g, " ")
                if (hay.indexOf(needle) < 0)
                    continue
                const city = String(item.name).split("/").pop().toLowerCase().replace(/_/g, " ")
                let score = 2
                if (city === needle || String(item.name).toLowerCase() === needle)
                    score = 0
                else if (city.startsWith(needle) || String(item.name).toLowerCase().replace(/_/g, " ").startsWith(needle))
                    score = 1
                ranked.push({score: score, name: item.name, item: item})
            }
            ranked.sort(function (a, b) { return a.score - b.score || a.name.localeCompare(b.name) })
            const out = []
            for (let i = 0; i < ranked.length && i < searchCombo.filterLimit; i++)
                out.push(ranked[i].item)
            searchCombo.filtered = out
            suggestionView.currentIndex = out.length ? 0 : -1
        }

        function setFromName(name) {
            searchCombo.selectedName = name || ""
            searchCombo.listOpen = false
            let label = name || ""
            const items = searchCombo.allItems || []
            for (let i = 0; i < items.length; i++) {
                if (items[i].name === name) {
                    label = items[i].label
                    break
                }
            }
            searchField.text = label
        }

        function chooseItem(item) {
            if (!item)
                return
            searchCombo.selectedName = item.name || ""
            searchCombo.listOpen = false
            searchField.text = item.label || item.name || ""
            searchCombo.itemChosen(item)
        }

        function acceptTyped() {
            if (listOpen && suggestionView.currentIndex >= 0 && suggestionView.currentIndex < filtered.length) {
                chooseItem(filtered[suggestionView.currentIndex])
                return
            }
            backend.lookupLocation(searchField.text)
        }

        onListOpenChanged: {
            if (listOpen) {
                if (!suggestionPopup.opened)
                    suggestionPopup.open()
            } else if (suggestionPopup.opened) {
                suggestionPopup.close()
            }
        }

        HudField {
            id: searchField
            width: parent.width
            height: parent.height
            placeholderText: "Search city or timezone"
            rightPadding: 26
            Keys.priority: Keys.BeforeItem
            onTextEdited: {
                searchCombo.selectedName = ""
                searchCombo.refreshFilter()
                searchCombo.listOpen = true
            }
            onActiveFocusChanged: {
                if (activeFocus && !searchCombo.listOpen)
                    searchCombo.openFullList()
            }
            MouseArea {
                anchors.fill: parent
                anchors.rightMargin: 26
                propagateComposedEvents: true
                onPressed: function (mouse) {
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    mouse.accepted = false
                }
            }
            Keys.onPressed: function (event) {
                if (event.key === Qt.Key_Down) {
                    event.accepted = true
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    else if (suggestionView.currentIndex < filtered.length - 1)
                        suggestionView.incrementCurrentIndex()
                } else if (event.key === Qt.Key_Up) {
                    event.accepted = true
                    if (!searchCombo.listOpen)
                        searchCombo.openFullList()
                    else if (suggestionView.currentIndex > 0)
                        suggestionView.decrementCurrentIndex()
                } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                    event.accepted = true
                    searchCombo.acceptTyped()
                } else if (event.key === Qt.Key_Escape) {
                    event.accepted = true
                    searchCombo.listOpen = false
                } else if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                    searchCombo.listOpen = false
                }
            }
        }
        Text {
            text: "▾"
            color: root.accent
            z: 2
            anchors.right: searchField.right
            anchors.rightMargin: 8
            anchors.verticalCenter: searchField.verticalCenter
            MouseArea {
                anchors.fill: parent
                anchors.margins: -8
                onClicked: {
                    if (searchCombo.listOpen) {
                        searchCombo.listOpen = false
                        return
                    }
                    searchField.forceActiveFocus()
                    searchCombo.openFullList()
                }
            }
        }
        Popup {
            id: suggestionPopup
            y: searchField.height + 3
            width: Math.max(searchCombo.width, 360)
            height: Math.min(Math.max(searchCombo.filtered.length, 1), 10) * 32 + 2
            padding: 1
            modal: false
            focus: false
            closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
            palette.window: "#02060C"
            palette.windowText: root.textPrimary
            palette.base: "#02060C"
            palette.text: root.textPrimary
            background: Rectangle { color: "#02060C"; border.color: root.accent }
            onOpened: searchCombo.listOpen = true
            onClosed: searchCombo.listOpen = false
            contentItem: Item {
                ListView {
                    id: suggestionView
                    anchors.fill: parent
                    clip: true
                    visible: searchCombo.filtered.length > 0
                    boundsBehavior: Flickable.StopAtBounds
                    model: searchCombo.filtered
                    currentIndex: 0
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                    onCurrentIndexChanged: {
                        if (currentIndex >= 0)
                            positionViewAtIndex(currentIndex, ListView.Contain)
                    }
                    delegate: Rectangle {
                        width: suggestionView.width
                        height: 32
                        readonly property var item: modelData
                        readonly property int row: index
                        color: suggestionView.currentIndex === row ? "#123C52" : "#02060C"
                        Text {
                            anchors.fill: parent
                            leftPadding: 10
                            rightPadding: 10
                            text: item && (item.label || item.name) || ""
                            color: suggestionView.currentIndex === row ? root.accent : root.textPrimary
                            font.pixelSize: 13
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            onEntered: suggestionView.currentIndex = row
                            onClicked: searchCombo.chooseItem(item)
                        }
                    }
                }
                Text {
                    anchors.fill: parent
                    visible: searchCombo.filtered.length === 0
                    leftPadding: 10
                    text: "No matches"
                    color: root.textSecondary
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    component DeviceCombo: HudCombo {
        id: deviceCombo
        model: backend.devices
        textRole: "name"
        valueRole: "id"
        implicitWidth: 200
        onActivated: if (currentValue) backend.selectDevice(currentValue)
        Component.onCompleted: root.syncCombo(deviceCombo)
        Connections {
            target: backend
            function onSelectedDeviceChanged() { root.syncCombo(deviceCombo) }
            function onDevicesChanged() { root.syncCombo(deviceCombo) }
        }
    }

    component HudCheck: CheckBox {
        id: box
        font.pixelSize: 13
        contentItem: Text {
            text: box.text
            color: root.textPrimary
            font: box.font
            leftPadding: box.indicator.width + 8
            verticalAlignment: Text.AlignVCenter
        }
        indicator: Rectangle {
            implicitWidth: 18
            implicitHeight: 18
            x: box.leftPadding
            y: parent.height / 2 - height / 2
            color: box.checked ? "#123C52" : "#0A1524"
            border.color: root.accent
            Text { anchors.centerIn: parent; text: box.checked ? "✓" : ""; color: root.accent; font.pixelSize: 12 }
        }
    }

    component FieldLabel: Text {
        color: root.textSecondary
        font.pixelSize: 10
        font.letterSpacing: 1.1
        font.bold: true
        Layout.preferredWidth: 110
        Layout.alignment: Qt.AlignVCenter
    }

    component EmptyHint: Text {
        color: root.textSecondary
        font.pixelSize: 13
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
    }

    Item {
        id: shell
        anchors.fill: parent
        Image {
            anchors.fill: parent
            source: root.asset("hud-background.png")
            fillMode: Image.PreserveAspectCrop
            opacity: root.dataPage ? 0.14 : 0.42
        }
        Rectangle { anchors.fill: parent; color: root.dataPage ? "#CC030810" : "#99030810" }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            Layout.maximumHeight: 64
            Layout.fillHeight: false
            color: "#C0050A12"
            border.color: root.outline
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 10
                spacing: 14
                Item {
                    implicitWidth: brand.implicitWidth
                    implicitHeight: brand.implicitHeight
                    Column {
                        id: brand
                        Text { text: "ASTRO DWARF"; color: root.accent; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                        Text { text: "OBSERVATORY COMMAND  ·  v" + backend.appVersion; color: root.textSecondary; font.pixelSize: 10; font.letterSpacing: 1.4 }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Rectangle { width: 1; Layout.fillHeight: true; Layout.topMargin: 12; Layout.bottomMargin: 12; color: root.outline }
                DeviceCombo {}
                HudButton {
                    text: backend.selectedDevice.connected ? "DISCONNECT" : "CONNECT"
                    busy: backend.selectedDevice.connecting || backend.selectedDevice.disconnecting
                    busyText: backend.selectedDevice.connecting ? "CONNECTING…" : "DISCONNECTING…"
                    busyMs: 0
                    enabled: !busy
                    buttonColor: backend.selectedDevice.connected ? "#143028" : "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: backend.selectedDevice.connected
                        ? backend.disconnectDevice(backend.selectedDeviceId)
                        : backend.connectDevice(backend.selectedDeviceId)
                }
                HudButton {
                    text: backend.schedulerEnabled ? "SCHEDULER ON" : "SCHEDULER OFF"
                    busyText: "UPDATING…"
                    buttonColor: backend.schedulerEnabled ? "#143028" : root.surfaceHigh
                    foregroundColor: backend.schedulerEnabled ? root.success : root.textPrimary
                    onClicked: backend.setSchedulerEnabled(!backend.schedulerEnabled)
                }
                HudButton {
                    text: "STOP ALL"
                    busy: backend.selectedDevice.pending_action === "stop_all"
                    busyText: "STOPPING…"
                    busyMs: 0
                    enabled: root.commandEnabled("stop_all")
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: backend.stopDevice(backend.selectedDeviceId)
                }
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    MouseArea {
                        anchors.fill: parent
                        onPressed: root.dragWindow()
                        onDoubleClicked: root.toggleMaximized()
                    }
                }
                Column {
                    Text { text: backend.selectedDevice.status || "OFFLINE"; color: backend.selectedDevice.connected ? root.success : root.textSecondary; font.pixelSize: 11; font.bold: true; horizontalAlignment: Text.AlignRight; width: 160 }
                    Text { text: (backend.selectedDevice.name || "No device") + " · " + (backend.selectedDevice.model || ""); color: root.textSecondary; font.pixelSize: 10; horizontalAlignment: Text.AlignRight; width: 160; elide: Text.ElideRight }
                }
                Text { text: backend.clockText; color: root.accent; font.pixelSize: 22; font.family: "Cascadia Mono"; font.letterSpacing: 1 }
            }
        }

        ListView {
            Layout.fillWidth: true
            Layout.preferredHeight: backend.devices.length > 1 ? 64 : 0
            Layout.maximumHeight: backend.devices.length > 1 ? 64 : 0
            Layout.fillHeight: false
            Layout.leftMargin: 12
            Layout.rightMargin: 12
            Layout.topMargin: backend.devices.length > 1 ? 8 : 0
            visible: backend.devices.length > 1
            orientation: ListView.Horizontal
            spacing: 8
            clip: true
            model: backend.devices
            delegate: HudPanel {
                id: deviceCard
                required property var modelData
                width: 210
                height: 56
                fill: modelData.id === backend.selectedDeviceId ? "#C0123C52" : "#99070D16"
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    RowLayout {
                        anchors.fill: parent
                        spacing: 8
                        Rectangle { width: 4; Layout.fillHeight: true; color: modelData.color }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: modelData.name; color: root.textPrimary; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: modelData.model + "  ·  " + modelData.status; color: root.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        Rectangle {
                            width: 8; height: 8; radius: 4
                            color: modelData.connected ? root.success : "#526077"
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.selectDevice(deviceCard.modelData.id)
                    }
                    TapHandler {
                        acceptedButtons: Qt.RightButton
                        onTapped: deviceMenu.popup()
                    }
                    HudMenu {
                        id: deviceMenu
                        HudMenuItem {
                            text: deviceCard.modelData.connected ? "Disconnect" : "Connect"
                            glyph: deviceCard.modelData.connected ? "\uE8CD" : "\uE774"
                            enabled: !deviceCard.modelData.connecting && !deviceCard.modelData.disconnecting
                            onTriggered: {
                                backend.selectDevice(deviceCard.modelData.id)
                                if (deviceCard.modelData.connected)
                                    backend.disconnectDevice(deviceCard.modelData.id)
                                else
                                    backend.connectDevice(deviceCard.modelData.id)
                            }
                        }
                        HudMenuItem {
                            text: "Open settings"
                            glyph: "\uE713"
                            onTriggered: {
                                backend.selectDevice(deviceCard.modelData.id)
                                root.currentPage = 4
                            }
                        }
                        HudMenuSeparator {}
                        HudMenuItem {
                            text: "Copy IP address"
                            glyph: "\uE8C8"
                            trailingText: String(deviceCard.modelData.ip_address || "")
                            enabled: trailingText !== ""
                            onTriggered: backend.copyText(trailingText)
                        }
                        HudMenuSeparator {}
                        HudMenuItem {
                            text: "Remove device"
                            glyph: "\uE74D"
                            destructive: true
                            visible: backend.devices.length > 1
                            onTriggered: backend.deleteDevice(deviceCard.modelData.id)
                        }
                    }
                }
            }
        }

        StackLayout {
            id: pages
            currentIndex: root.currentPage
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 360
            Layout.margins: 10

            Item {
                id: controlPage
                HudSplitView {
                    id: controlColumns
                    anchors.fill: parent
                    orientation: Qt.Horizontal

                    HudSplitView {
                        id: controlLeft
                        orientation: Qt.Vertical
                        SplitView.preferredWidth: 268
                        SplitView.minimumWidth: 196

                        HudPanel {
                            title: "SYSTEM STATUS"
                            SplitView.preferredHeight: 168
                            SplitView.minimumHeight: 96
                            Image {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                source: root.asset("hud-radar.png")
                                fillMode: Image.PreserveAspectFit
                            }
                            Text {
                                text: backend.selectedDevice.connected ? "SCOPE ONLINE" : "LINK DOWN"
                                color: backend.selectedDevice.connected ? root.success : root.warning
                                font.pixelSize: 11
                                font.bold: true
                                Layout.fillWidth: true
                            }
                        }

                        HudPanel {
                            id: targetPanel
                            title: "TARGET"
                            SplitView.preferredHeight: 148
                            SplitView.minimumHeight: 88
                            Text {
                                text: backend.currentSession.target_name || (backend.selectedDevice.connected ? "No active lock" : "No telescope link")
                                color: root.textPrimary
                                font.pixelSize: 18
                                font.bold: true
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                            Text {
                                visible: !!(backend.currentSession.target && (backend.currentSession.target.ra_hours || backend.currentSession.target.ra_hours === 0))
                                text: backend.currentSession.target
                                    ? "RA  " + Number(backend.currentSession.target.ra_hours).toFixed(3) + "h   DEC  " + Number(backend.currentSession.target.dec_degrees).toFixed(3) + "°"
                                    : ""
                                color: root.textSecondary
                                font.pixelSize: 11
                            }
                            Text { text: backend.currentSession.current_step || (backend.selectedDevice.connected ? "Telescope ready" : "Connect to acquire a lock"); color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Text { text: backend.currentSession.duration_text ? "PLANNED  " + backend.currentSession.duration_text : "WAITING FOR SCHEDULE"; color: root.accent; font.pixelSize: 11 }
                            ProgressBar {
                                id: sessionBar
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: backend.sessionProgress
                                background: Rectangle { implicitHeight: 8; color: "#0A1524"; border.color: root.outline }
                                contentItem: Rectangle { width: sessionBar.visualPosition * parent.width; height: parent.height; color: root.accent }
                            }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                enabled: !!backend.currentSession.id
                                onTapped: targetMenu.popup()
                            }
                            HudMenu {
                                id: targetMenu
                                readonly property string coordinates: root.targetCoordinates(backend.currentSession)
                                HudMenuItem {
                                    text: "Edit session"
                                    glyph: "\uE70F"
                                    enabled: backend.currentSession.status !== "running"
                                    onTriggered: sessionDialog.openExisting(backend.currentSession)
                                }
                                HudMenuItem {
                                    text: "Copy target name"
                                    glyph: "\uE8C8"
                                    onTriggered: backend.copyText(String(backend.currentSession.target_name || ""))
                                }
                                HudMenuItem {
                                    text: "Copy RA / Dec"
                                    glyph: "\uE8C8"
                                    enabled: targetMenu.coordinates !== ""
                                    onTriggered: backend.copyText(targetMenu.coordinates)
                                }
                                HudMenuSeparator {}
                                HudMenuItem {
                                    text: "Stop all"
                                    glyph: "\uE71A"
                                    destructive: true
                                    enabled: backend.currentSession.status === "running"
                                        && root.commandEnabled("stop_all")
                                    onTriggered: backend.stopDevice(backend.selectedDeviceId)
                                }
                            }
                        }

                        Rectangle {
                            SplitView.preferredHeight: 48
                            SplitView.minimumHeight: 40
                            SplitView.maximumHeight: 64
                            color: root.targetLocked ? "#C0143C28" : (backend.selectedDevice.connected ? "#C0123C52" : "#C03A1218")
                            border.color: root.targetLocked ? root.success : (backend.selectedDevice.connected ? root.accent : root.danger)
                            Text {
                                anchors.centerIn: parent
                                text: root.targetLocked ? "TARGET LOCKED" : (backend.selectedDevice.connected ? "NO TARGET LOCK" : "LINK DOWN")
                                color: root.targetLocked ? root.success : (backend.selectedDevice.connected ? root.accent : root.danger)
                                font.bold: true
                                font.letterSpacing: 2
                            }
                        }

                        HudPanel {
                            title: "CAMERA"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 140
                            FieldLabel { text: "FOCUS" }
                            RowLayout {
                                Layout.fillWidth: true
                                HudButton {
                                    text: "NEAR"
                                    Layout.fillWidth: true
                                    busy: backend.selectedDevice.pending_action === "focus_near"
                                    busyText: "FOCUSING…"
                                    busyMs: 0
                                    enabled: root.commandEnabled("focus_near")
                                    onClicked: backend.manualFocus(backend.selectedDeviceId, 1)
                                }
                                HudButton {
                                    text: "FAR"
                                    Layout.fillWidth: true
                                    busy: backend.selectedDevice.pending_action === "focus_far"
                                    busyText: "FOCUSING…"
                                    busyMs: 0
                                    enabled: root.commandEnabled("focus_far")
                                    onClicked: backend.manualFocus(backend.selectedDeviceId, 0)
                                }
                            }
                            FieldLabel {
                                text: "FILTER"
                                visible: backend.selectedDevice.camera !== "wide"
                            }
                            HudCombo {
                                id: liveFilter
                                Layout.fillWidth: true
                                visible: backend.selectedDevice.camera !== "wide"
                                enabled: root.commandEnabled("set_ir")
                                model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                                onActivated: backend.setCameraParam(backend.selectedDeviceId, "ir", currentText)
                            }
                            FieldLabel { text: "CAMERA" }
                            HudCombo {
                                id: liveCamera
                                Layout.fillWidth: true
                                enabled: !root.scopeOccupied && !root.scopeLinking
                                model: ["Tele", "Wide"]
                                Component.onCompleted: currentIndex = backend.selectedDevice.camera === "wide" ? 1 : 0
                                onActivated: backend.setLiveCamera(backend.selectedDeviceId, currentIndex === 1 ? "wide" : "tele")
                                Connections {
                                    target: backend
                                    function onSelectedDeviceChanged() { liveCamera.currentIndex = backend.selectedDevice.camera === "wide" ? 1 : 0 }
                                }
                            }
                            FieldLabel { text: "EXPOSURE / GAIN" }
                            RowLayout {
                                Layout.fillWidth: true
                                HudField {
                                    id: liveExposure
                                    Layout.fillWidth: true
                                    enabled: root.cameraLiveEnabled
                                    placeholderText: "sec"
                                    text: "15"
                                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "exposure", text)
                                }
                                HudField {
                                    id: liveGain
                                    Layout.fillWidth: true
                                    enabled: root.commandEnabled("set_gain")
                                    placeholderText: "gain"
                                    text: "80"
                                    onEditingFinished: backend.setCameraParam(backend.selectedDeviceId, "gain", text)
                                }
                            }
                        }
                    }

                    HudSplitView {
                        id: controlCenter
                        orientation: Qt.Vertical
                        SplitView.fillWidth: true
                        SplitView.minimumWidth: 280

                        HudPanel {
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 180
                            fill: "#E005070B"
                            Item {
                                id: previewHost
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                property string previewDeviceId: backend.selectedDeviceId
                                property string statusText: backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"
                                readonly property bool previewFailed: {
                                    const s = String(backend.previewStatus || "").toLowerCase()
                                    return s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0
                                }
                                readonly property string actionLabel: {
                                    if (!backend.previewActive || backend.previewPlaying)
                                        return "STARTING CAMERA…"
                                    const s = String(backend.previewStatus || "").toLowerCase()
                                    if (s.indexOf("fail") >= 0 || s.indexOf("could not") >= 0)
                                        return "PREVIEW FAILED"
                                    if (s.indexOf("udp") >= 0)
                                        return "RETRYING UDP…"
                                    if (s.indexOf("waiting") >= 0)
                                        return "WAITING FOR STREAM…"
                                    if (s.indexOf("tcp") >= 0 || s.indexOf("opening") >= 0)
                                        return "OPENING STREAM…"
                                    if (s.indexOf("starting") >= 0)
                                        return "STARTING CAMERA…"
                                    return "STARTING PREVIEW…"
                                }

                                function startPreview() {
                                    if (!backend.selectedDevice.connected) {
                                        statusText = "Connect a telescope to start the stream"
                                        backend.uiLog("warning", "Preview needs an active telescope connection")
                                        return
                                    }
                                    statusText = "Starting live camera…"
                                    backend.startPreview(backend.selectedDeviceId)
                                }

                                function stopPreview() {
                                    backend.stopPreview()
                                    statusText = backend.selectedDevice.connected ? backend.videoUrl : "Connect a telescope to start the stream"
                                }

                                property bool chromeVisible: true
                                property bool chromeHold: false
                                readonly property bool chromeShown: !backend.previewPlaying || chromeVisible

                                function revealChrome() {
                                    chromeVisible = true
                                    if (!chromeHold)
                                        chromeIdleTimer.restart()
                                }

                                function leaveChrome() {
                                    if (chromeHold)
                                        return
                                    chromeVisible = false
                                    chromeIdleTimer.stop()
                                }

                                function beginChromeHold() {
                                    chromeVisible = true
                                    chromeHold = true
                                    chromeIdleTimer.stop()
                                    chromeHoldTimer.restart()
                                }

                                function clearChromeHold() {
                                    chromeHold = false
                                    chromeVisible = true
                                    chromeHoldTimer.stop()
                                    chromeIdleTimer.stop()
                                }

                                Timer {
                                    id: chromeHoldTimer
                                    interval: 5000
                                    repeat: false
                                    onTriggered: {
                                        previewHost.chromeHold = false
                                        if (!previewHover.hovered)
                                            previewHost.chromeVisible = false
                                        else
                                            chromeIdleTimer.restart()
                                    }
                                }
                                Timer {
                                    id: chromeIdleTimer
                                    interval: 3000
                                    repeat: false
                                    onTriggered: previewHost.chromeVisible = false
                                }

                                HoverHandler {
                                    id: previewHover
                                    enabled: backend.previewPlaying
                                    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                                    onPointChanged: previewHost.revealChrome()
                                    onHoveredChanged: {
                                        if (!hovered)
                                            previewHost.leaveChrome()
                                    }
                                }

                                Connections {
                                    target: backend
                                    function onSelectedDeviceChanged() {
                                        const deviceId = backend.selectedDeviceId
                                        if (deviceId === previewHost.previewDeviceId)
                                            return
                                        previewHost.previewDeviceId = deviceId
                                        previewHost.stopPreview()
                                    }
                                    function onPreviewStatusChanged() {
                                        if (backend.previewStatus)
                                            previewHost.statusText = backend.previewStatus
                                    }
                                    function onPreviewPlayingChanged() {
                                        if (backend.previewPlaying)
                                            previewHost.beginChromeHold()
                                        else
                                            previewHost.clearChromeHold()
                                    }
                                }

                                Image {
                                    anchors.fill: parent
                                    visible: backend.previewPlaying
                                    cache: false
                                    fillMode: Image.PreserveAspectFit
                                    source: backend.previewPlaying ? ("image://live/frame/" + backend.previewGeneration) : ""
                                }
                                Image {
                                    anchors.fill: parent
                                    visible: !backend.previewPlaying
                                    source: root.asset("hud-telescope.png")
                                    fillMode: Image.PreserveAspectFit
                                    opacity: 0.18
                                }
                                Canvas {
                                    anchors.fill: parent
                                    opacity: previewHost.chromeShown ? 0.9 : 0
                                    onPaint: {
                                        const ctx = getContext("2d")
                                        ctx.reset()
                                        const cx = width / 2, cy = height / 2, m = 18
                                        ctx.strokeStyle = "#88E8FFFF"
                                        ctx.lineWidth = 1.2
                                        ctx.beginPath()
                                        ctx.moveTo(cx - 80, cy); ctx.lineTo(cx - 16, cy)
                                        ctx.moveTo(cx + 16, cy); ctx.lineTo(cx + 80, cy)
                                        ctx.moveTo(cx, cy - 80); ctx.lineTo(cx, cy - 16)
                                        ctx.moveTo(cx, cy + 16); ctx.lineTo(cx, cy + 80)
                                        ctx.stroke()
                                        ctx.beginPath(); ctx.arc(cx, cy, 52, 0, Math.PI * 2); ctx.stroke()
                                        ctx.beginPath()
                                        ctx.moveTo(m, m + 24); ctx.lineTo(m, m); ctx.lineTo(m + 24, m)
                                        ctx.moveTo(width - m - 24, m); ctx.lineTo(width - m, m); ctx.lineTo(width - m, m + 24)
                                        ctx.moveTo(m, height - m - 24); ctx.lineTo(m, height - m); ctx.lineTo(m + 24, height - m)
                                        ctx.moveTo(width - m - 24, height - m); ctx.lineTo(width - m, height - m); ctx.lineTo(width - m, height - m - 24)
                                        ctx.stroke()
                                    }
                                    onWidthChanged: requestPaint()
                                    onHeightChanged: requestPaint()
                                }
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 8
                                    visible: !backend.previewPlaying
                                    Text { anchors.horizontalCenter: parent.horizontalCenter; text: "LIVE VIDEO"; color: root.textPrimary; font.pixelSize: 16; font.letterSpacing: 3; font.bold: true }
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        width: previewHost.width - 40
                                        wrapMode: Text.Wrap
                                        horizontalAlignment: Text.AlignHCenter
                                        text: previewHost.statusText
                                        color: root.textSecondary
                                    }
                                    HudButton {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "START PREVIEW"
                                        busyText: previewHost.actionLabel
                                        busy: backend.previewActive && !backend.previewPlaying
                                        busyMs: backend.selectedDevice.connected && !backend.previewActive ? 1800 : 0
                                        enabled: root.commandEnabled("open_camera") && (!backend.previewActive || backend.previewPlaying || previewHost.previewFailed)
                                        buttonColor: "#0E3A48"
                                        foregroundColor: root.accent
                                        onClicked: previewHost.startPreview()
                                    }
                                }
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    width: 96
                                    height: 28
                                    visible: previewHost.chromeShown
                                    color: "#C0101520"
                                    border.color: backend.previewPlaying ? root.success : root.outline
                                    Row {
                                        anchors.centerIn: parent
                                        spacing: 7
                                        Rectangle { width: 8; height: 8; radius: 4; color: backend.previewPlaying ? root.danger : (backend.previewActive ? root.warning : "#64748B"); anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: backend.previewPlaying ? "LIVE" : (backend.previewActive ? "STARTING" : "STANDBY"); color: root.textPrimary; font.pixelSize: 11; font.bold: true }
                                    }
                                }
                                HudButton {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 14
                                    visible: backend.previewActive && previewHost.chromeShown
                                    text: "STOP PREVIEW"
                                    busyText: "STOPPING…"
                                    onClicked: previewHost.stopPreview()
                                }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: previewMenu.popup()
                                }
                                HudMenu {
                                    id: previewMenu
                                    HudMenuItem {
                                        text: backend.previewActive ? "Stop preview" : "Start preview"
                                        glyph: backend.previewActive ? "\uE71A" : "\uE768"
                                        enabled: backend.previewActive
                                            || root.commandEnabled("open_camera")
                                        onTriggered: {
                                            if (backend.previewActive)
                                                previewHost.stopPreview()
                                            else
                                                previewHost.startPreview()
                                        }
                                    }
                                    HudMenuItem {
                                        text: "Copy stream URL"
                                        glyph: "\uE8C8"
                                        enabled: backend.selectedDevice.connected && backend.videoUrl !== ""
                                        onTriggered: backend.copyText(backend.videoUrl)
                                    }
                                }
                            }
                        }

                        HudPanel {
                            title: "COMMANDS"
                            SplitView.preferredHeight: 210
                            SplitView.minimumHeight: 120
                            Repeater {
                                model: [
                                    {label: "ALIGN", items: [["CALIBRATE", "calibrate"], ["AUTO FOCUS", "autofocus"], ["INFINITY", "infinity"], ["POLAR / EQ", "polar"]]},
                                    {label: "LIVE", items: [["LIGHTS ON", "lights_on"], ["LIGHTS OFF", "lights_off"], ["GO LIVE", "go_live"], ["STOP GOTO", "stop_goto"]]},
                                    {label: "CAPTURE", items: [["BURST", "burst_start"], ["STOP BURST", "burst_stop"], ["RECORD", "record_start"], ["STOP REC", "record_stop"], ["TIMELAPSE", "timelapse_start"], ["STOP TL", "timelapse_stop"]]},
                                    {label: "SYSTEM", items: [["REBOOT", "reboot"], ["POWER DOWN", "power_down"]]}
                                ]
                                delegate: ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 3
                                    Text { text: modelData.label; color: root.textSecondary; font.pixelSize: 9; font.letterSpacing: 1.2; font.bold: true }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Repeater {
                                            model: modelData.items
                                            delegate: HudButton {
                                                required property var modelData
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 26
                                                leftPadding: 4
                                                rightPadding: 4
                                                font.pixelSize: 9
                                                text: modelData[0]
                                                busyText: modelData[0] + "…"
                                                busy: backend.selectedDevice.pending_action === modelData[1]
                                                busyMs: 0
                                                enabled: root.commandEnabled(modelData[1])
                                                buttonColor: (modelData[1] === "reboot" || modelData[1] === "power_down") ? "#3A1218" : root.surfaceHigh
                                                foregroundColor: (modelData[1] === "reboot" || modelData[1] === "power_down") ? root.danger : root.textPrimary
                                                onClicked: root.requestDeviceAction(modelData[1], modelData[0])
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    HudSplitView {
                        id: controlRight
                        orientation: Qt.Vertical
                        SplitView.preferredWidth: 312
                        SplitView.minimumWidth: 220

                        HudPanel {
                            title: "SCOPE STATUS"
                            SplitView.preferredHeight: 132
                            SplitView.minimumHeight: 80
                            Repeater {
                                model: [
                                    {label: "LINK", value: backend.selectedDevice.connected ? "Connected" : "Offline"},
                                    {label: "ACTIVITY", value: backend.selectedDevice.busy ? "Imaging" : (root.targetLocked ? "On target" : "Idle")},
                                    {label: "TARGET", value: backend.currentSession.target_name || "None"},
                                    {label: "STEP", value: backend.currentSession.current_step || backend.selectedDevice.status || "—"}
                                ]
                                delegate: RowLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Text { text: modelData.label; color: root.textSecondary; font.pixelSize: 10; font.bold: true; Layout.preferredWidth: 72 }
                                    Text { text: modelData.value; color: root.textPrimary; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }

                        HudPanel {
                            title: "MOTION"
                            SplitView.preferredHeight: 188
                            SplitView.minimumHeight: 150
                            Item {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 118
                                opacity: root.motionEnabled ? 1 : 0.38
                                Item {
                                    id: analogPad
                                    anchors.centerIn: parent
                                    width: 108
                                    height: 108
                                    property real stickDx: 0
                                    property real stickDy: 0
                                    property bool moving: false
                                    readonly property real maxThrow: width / 2 - 15
                                    readonly property real deadzone: 0.15

                                    function updateStick(px, py) {
                                        let dx = px - width / 2
                                        let dy = py - height / 2
                                        const distance = Math.sqrt(dx * dx + dy * dy)
                                        const limited = Math.min(distance, maxThrow)
                                        const scale = distance > 0 ? limited / distance : 0
                                        stickDx = dx * scale
                                        stickDy = dy * scale
                                        const amount = maxThrow > 0 ? limited / maxThrow : 0
                                        if (amount <= deadzone) {
                                            if (moving)
                                                backend.stopMotors(backend.selectedDeviceId)
                                            moving = false
                                            return
                                        }
                                        let angle = Math.atan2(-dy, dx) * 180 / Math.PI
                                        if (angle < 0)
                                            angle += 360
                                        moving = true
                                        backend.joystick(backend.selectedDeviceId, angle, amount * root.joySpeed)
                                    }

                                    function releaseStick() {
                                        stickDx = 0
                                        stickDy = 0
                                        moving = false
                                        backend.stopMotors(backend.selectedDeviceId)
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: width / 2
                                        color: "#B30A1524"
                                        border.color: root.outline
                                        border.width: 2
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: 2
                                        height: parent.height - 18
                                        color: "#34597A"
                                        opacity: 0.45
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: parent.width - 18
                                        height: 2
                                        color: "#34597A"
                                        opacity: 0.45
                                    }
                                    Rectangle {
                                        anchors.centerIn: parent
                                        width: analogPad.maxThrow * 2 * analogPad.deadzone
                                        height: width
                                        radius: width / 2
                                        color: "#162B40"
                                        border.color: "#34597A"
                                    }
                                    Rectangle {
                                        id: analogKnob
                                        x: parent.width / 2 - width / 2 + analogPad.stickDx
                                        y: parent.height / 2 - height / 2 + analogPad.stickDy
                                        width: 28
                                        height: 28
                                        radius: width / 2
                                        color: analogPad.moving ? root.accent : "#8CB7D9"
                                        border.color: "#D8F4FF"
                                        border.width: 2
                                        Behavior on x { NumberAnimation { duration: stickArea.pressed ? 0 : 90 } }
                                        Behavior on y { NumberAnimation { duration: stickArea.pressed ? 0 : 90 } }
                                    }
                                    MouseArea {
                                        id: stickArea
                                        anchors.fill: parent
                                        enabled: root.motionEnabled
                                        preventStealing: true
                                        cursorShape: root.motionEnabled ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor
                                        onPressed: mouse => analogPad.updateStick(mouse.x, mouse.y)
                                        onPositionChanged: mouse => {
                                            if (pressed)
                                                analogPad.updateStick(mouse.x, mouse.y)
                                        }
                                        onReleased: analogPad.releaseStick()
                                        onCanceled: analogPad.releaseStick()
                                        onEnabledChanged: {
                                            if (!enabled && analogPad.moving)
                                                analogPad.releaseStick()
                                        }
                                    }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                opacity: root.motionEnabled ? 1 : 0.42
                                Text { text: "SPEED"; color: root.textSecondary; font.pixelSize: 10 }
                                Slider {
                                    id: speedSlider
                                    Layout.fillWidth: true
                                    enabled: root.motionEnabled
                                    from: 0.2
                                    to: 1
                                    value: 1
                                    onMoved: root.joySpeed = value
                                    background: Rectangle { x: speedSlider.leftPadding; y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 2; implicitHeight: 4; width: speedSlider.availableWidth; color: "#0A1524"; Rectangle { width: speedSlider.visualPosition * parent.width; height: parent.height; color: root.accent } }
                                    handle: Rectangle { x: speedSlider.leftPadding + speedSlider.visualPosition * (speedSlider.availableWidth - 12); y: speedSlider.topPadding + speedSlider.availableHeight / 2 - 6; width: 12; height: 12; radius: 6; color: root.accent }
                                }
                            }
                        }

                        HudPanel {
                            title: "UP NEXT"
                            SplitView.preferredHeight: 110
                            SplitView.minimumHeight: 72
                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                ListView {
                                    id: upcomingList
                                    anchors.fill: parent
                                    clip: true
                                    spacing: 4
                                    boundsBehavior: Flickable.StopAtBounds
                                    ScrollBar.vertical: HiddenBar {}
                                    ScrollBar.horizontal: HiddenBar {}
                                    model: backend.upcomingSessions
                                    delegate: Rectangle {
                                        id: upcomingRow
                                        required property var modelData
                                        width: ListView.view.width
                                        height: 36
                                        color: "#122033"
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 6
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 0
                                                Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                                Text { text: modelData.start_time + " · " + modelData.duration_text; color: root.textSecondary; font.pixelSize: 10 }
                                            }
                                        }
                                        TapHandler {
                                            acceptedButtons: Qt.RightButton
                                            onTapped: upcomingMenu.popup()
                                        }
                                        SessionContextMenu {
                                            id: upcomingMenu
                                            sessionData: upcomingRow.modelData
                                        }
                                    }
                                }
                                EmptyHint { anchors.centerIn: parent; visible: backend.upcomingSessions.length === 0; text: "No upcoming sessions" }
                            }
                        }

                        HudPanel {
                            title: "LIVE LOG"
                            SplitView.fillHeight: true
                            SplitView.minimumHeight: 80
                            headerExtra: HudButton {
                                text: backend.showDebugLogs ? "DEBUG ON" : "DEBUG"
                                implicitHeight: 22
                                implicitWidth: 78
                                font.pixelSize: 10
                                buttonColor: backend.showDebugLogs ? "#143028" : root.surfaceHigh
                                foregroundColor: backend.showDebugLogs ? root.success : root.textSecondary
                                onClicked: backend.setShowDebugLogs(!backend.showDebugLogs)
                            }
                            ListView {
                                id: logList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.preferredHeight: 0
                                clip: true
                                spacing: 2
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: HiddenBar {}
                                ScrollBar.horizontal: HiddenBar {}
                                model: backend.logModel
                                onCountChanged: positionViewAtEnd()
                                delegate: Text {
                                    required property string time
                                    required property string level
                                    required property string device
                                    required property string message
                                    width: ListView.view.width
                                    text: time + "  [" + device + "]  " + message
                                    color: level === "ERROR" ? root.danger : level === "SUCCESS" ? root.success : level === "WARNING" ? root.warning : level === "SDK" ? root.textSecondary : "#B7D4E2"
                                    font.family: "Cascadia Mono"
                                    font.pixelSize: 10
                                    wrapMode: Text.Wrap
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: {
                                            logMenu.lineText = text
                                            logMenu.popup()
                                        }
                                    }
                                }
                                HudMenu {
                                    id: logMenu
                                    property string lineText: ""
                                    HudMenuItem {
                                        text: "Copy line"
                                        glyph: "\uE8C8"
                                        onTriggered: backend.copyText(logMenu.lineText)
                                    }
                                    HudMenuItem {
                                        text: "Copy all"
                                        glyph: "\uE8C8"
                                        enabled: logList.count > 0
                                        onTriggered: backend.copyText(root.allLogText())
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: calendarPage
                property date shownMonth: new Date()
                property date selectedDate: new Date()
                function dateKey(value) {
                    return value.getFullYear() + "-" + String(value.getMonth() + 1).padStart(2, "0") + "-" + String(value.getDate()).padStart(2, "0")
                }
                function firstCellDate() {
                    const first = new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1)
                    const mondayIndex = (first.getDay() + 6) % 7
                    return new Date(first.getFullYear(), first.getMonth(), 1 - mondayIndex)
                }
                function sessionsForDay(key) {
                    return backend.sessions.filter(item => item.observing_date === key)
                }
                function chipText(item) {
                    return item.start_time + "  " + (item.pane_index < 1000000 ? "pane " + item.pane_index : item.target_name)
                }
                HudSplitView {
                    id: calendarSplit
                    anchors.fill: parent
                    orientation: Qt.Horizontal
                    ColumnLayout {
                        SplitView.fillWidth: true
                        SplitView.minimumWidth: 420
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: Qt.formatDate(calendarPage.shownMonth, "MMMM yyyy").toUpperCase(); color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2; Layout.fillWidth: true }
                            HudButton { text: "‹"; implicitWidth: 40; onClicked: calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() - 1, 1) }
                            HudButton { text: "TODAY"; onClicked: { calendarPage.shownMonth = new Date(); calendarPage.selectedDate = new Date() } }
                            HudButton { text: "›"; implicitWidth: 40; onClicked: calendarPage.shownMonth = new Date(calendarPage.shownMonth.getFullYear(), calendarPage.shownMonth.getMonth() + 1, 1) }
                            HudButton { text: "+ NEW SESSION"; busyText: "OPENING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(calendarPage.dateKey(calendarPage.selectedDate)) }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Repeater { model: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]; Text { required property string modelData; text: modelData; color: root.accent; font.pixelSize: 11; font.bold: true; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter } }
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 7
                            rows: 6
                            rowSpacing: 5
                            columnSpacing: 5
                            Repeater {
                                model: 42
                                delegate: Rectangle {
                                    id: dayCell
                                    required property int index
                                    property date cellDate: {
                                        calendarPage.shownMonth
                                        const value = calendarPage.firstCellDate()
                                        value.setDate(value.getDate() + index)
                                        return value
                                    }
                                    property string key: calendarPage.dateKey(cellDate)
                                    property var daySessions: calendarPage.sessionsForDay(key)
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    color: key === calendarPage.dateKey(calendarPage.selectedDate) ? "#C0123C52" : "#99070D16"
                                    border.color: dropArea.containsDrag ? root.accent : root.outline
                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 3
                                        Text { text: dayCell.cellDate.getDate(); color: dayCell.cellDate.getMonth() === calendarPage.shownMonth.getMonth() ? root.textPrimary : "#3E5A6A"; font.pixelSize: 11 }
                                        Repeater {
                                            model: dayCell.daySessions.slice(0, 3)
                                            delegate: Rectangle {
                                                id: sessionChip
                                                required property var modelData
                                                property string sessionId: modelData.id
                                                width: parent.width
                                                height: 22
                                                color: root.statusFill(modelData.status)
                                                border.color: root.statusColor(modelData.status)
                                                Text { anchors.fill: parent; anchors.margins: 4; text: calendarPage.chipText(modelData); color: root.textPrimary; font.pixelSize: 9; elide: Text.ElideRight }
                                                Drag.active: dragHandler.active
                                                Drag.source: sessionChip
                                                Drag.hotSpot.x: width / 2
                                                Drag.hotSpot.y: height / 2
                                                DragHandler { id: dragHandler }
                                                TapHandler { acceptedButtons: Qt.RightButton; onTapped: sessionMenu.open() }
                                                SessionContextMenu {
                                                    id: sessionMenu
                                                    sessionData: sessionChip.modelData
                                                }
                                            }
                                        }
                                        Text {
                                            visible: dayCell.daySessions.length > 3
                                            text: "+" + (dayCell.daySessions.length - 3) + " more"
                                            color: root.accent
                                            font.pixelSize: 9
                                            MouseArea {
                                                anchors.fill: parent
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: calendarPage.selectedDate = dayCell.cellDate
                                            }
                                        }
                                    }
                                    TapHandler { onTapped: calendarPage.selectedDate = dayCell.cellDate }
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: dayMenu.popup()
                                    }
                                    HudMenu {
                                        id: dayMenu
                                        HudMenuItem {
                                            text: "New session on this date"
                                            glyph: "\uE710"
                                            onTriggered: {
                                                calendarPage.selectedDate = dayCell.cellDate
                                                sessionDialog.openForDate(dayCell.key)
                                            }
                                        }
                                    }
                                    DropArea {
                                        id: dropArea
                                        anchors.fill: parent
                                        onDropped: drop => backend.moveSessionDate(drop.source.sessionId, dayCell.key)
                                    }
                                }
                            }
                        }
                    }
                    HudPanel {
                        title: Qt.formatDate(calendarPage.selectedDate, "ddd d MMM").toUpperCase()
                        SplitView.preferredWidth: 312
                        SplitView.minimumWidth: 220
                        Text {
                            text: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length + " session(s) this night"
                            color: root.textSecondary
                            font.pixelSize: 11
                        }
                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.preferredHeight: 0
                            ListView {
                                anchors.fill: parent
                                clip: true
                                spacing: 6
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: HiddenBar {}
                                ScrollBar.horizontal: HiddenBar {}
                                model: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate))
                                delegate: Rectangle {
                                    id: daySessionRow
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 64
                                    color: "#122033"
                                    border.color: root.statusColor(modelData.status)
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 2
                                        Text { text: modelData.start_time + "  " + modelData.target_name; color: root.textPrimary; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                        Text { text: modelData.subtitle + " · " + modelData.duration_text; color: root.textSecondary; font.pixelSize: 10; elide: Text.ElideRight; Layout.fillWidth: true }
                                        RowLayout {
                                            HudButton { text: "EDIT"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                            HudButton { text: "RESET"; implicitHeight: 24; visible: root.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                            HudButton { text: "RUN"; implicitHeight: 24; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
                                        }
                                    }
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: daySessionMenu.popup()
                                    }
                                    SessionContextMenu {
                                        id: daySessionMenu
                                        sessionData: daySessionRow.modelData
                                    }
                                }
                            }
                            EmptyHint {
                                anchors.centerIn: parent
                                visible: calendarPage.sessionsForDay(calendarPage.dateKey(calendarPage.selectedDate)).length === 0
                                text: "No sessions this observing night"
                            }
                        }
                    }
                }
            }

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
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "SESSIONS"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                            Text { text: "Templates, scheduled nights, Stellarium and Telescopius import"; color: root.textSecondary }
                        }
                        HudButton { text: "IMPORT STELLARIUM"; busy: backend.uiBusy === "stellarium"; busyText: "IMPORTING…"; busyMs: 0; enabled: backend.uiBusy === ""; onClicked: backend.importStellarium() }
                        HudButton { text: "IMPORT TELESCOPIUS"; busy: backend.uiBusy === "telescopius"; busyText: backend.uiBusy === "telescopius" ? "IMPORTING…" : "OPENING…"; enabled: backend.uiBusy === ""; onClicked: telescopiusDialog.open() }
                        HudButton { text: "+ MANUAL SESSION"; busyText: "OPENING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: sessionDialog.openForDate(Qt.formatDate(new Date(), "yyyy-MM-dd")) }
                    }
                    TabBar {
                        id: sessionsTabs
                        Layout.fillWidth: true
                        background: Rectangle { color: "transparent" }
                        TabButton {
                            text: "SCHEDULED"
                            font.letterSpacing: 1.2
                            contentItem: Text { text: parent.text; color: parent.checked ? root.accent : root.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                            background: Rectangle { color: parent.checked ? "#123C52" : "#0A1524"; border.color: parent.checked ? root.accent : root.outline }
                        }
                        TabButton {
                            text: "TEMPLATES"
                            font.letterSpacing: 1.2
                            contentItem: Text { text: parent.text; color: parent.checked ? root.accent : root.textSecondary; font: parent.font; horizontalAlignment: Text.AlignHCenter }
                            background: Rectangle { color: parent.checked ? "#123C52" : "#0A1524"; border.color: parent.checked ? root.accent : root.outline }
                        }
                    }
                    StackLayout {
                        currentIndex: sessionsTabs.currentIndex
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 280
                        Layout.preferredHeight: 0
                        Item {
                            EmptyHint { visible: backend.sessions.length === 0; text: "No scheduled sessions yet. Create one or import a target list."; anchors.centerIn: parent }
                            ListView {
                                anchors.fill: parent
                                clip: true
                                spacing: 8
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: HiddenBar {}
                                ScrollBar.horizontal: HiddenBar {}
                                model: backend.sessions
                                delegate: HudPanel {
                                    required property var modelData
                                    width: ListView.view.width
                                    height: 84
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Rectangle { width: 4; Layout.fillHeight: true; color: modelData.device_color || root.accent }
                                        ColumnLayout {
                                            Layout.preferredWidth: 280
                                            Text { text: modelData.target_name; color: root.textPrimary; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Text { text: modelData.subtitle; color: root.textSecondary; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true; visible: modelData.subtitle !== modelData.target_name }
                                        }
                                        Text { text: modelData.start_date + "  " + modelData.start_time; color: root.textPrimary; Layout.preferredWidth: 150 }
                                        Text { text: modelData.device_name; color: root.accent; Layout.preferredWidth: 120; elide: Text.ElideRight }
                                        Text { text: modelData.duration_text; color: root.textSecondary; Layout.preferredWidth: 80 }
                                        Rectangle {
                                            width: 86; height: 24; color: root.statusFill(modelData.status); border.color: root.statusColor(modelData.status)
                                            Text { anchors.centerIn: parent; text: modelData.status.toUpperCase(); color: root.statusColor(modelData.status); font.pixelSize: 9; font.bold: true }
                                        }
                                        HudButton { text: "EDIT"; enabled: modelData.status !== "running"; busyText: "OPENING…"; onClicked: sessionDialog.openExisting(modelData) }
                                        HudButton { text: "RESET"; visible: root.canReset(modelData.status); busyText: "RESETTING…"; onClicked: backend.resetSession(modelData.id) }
                                        HudButton { text: "RUN"; enabled: modelData.status !== "running"; busyText: "STARTING…"; onClicked: backend.runNow(modelData.id) }
                                    }
                                    TapHandler { acceptedButtons: Qt.RightButton; onTapped: scheduledMenu.popup() }
                                    SessionContextMenu {
                                        id: scheduledMenu
                                        sessionData: modelData
                                    }
                                }
                            }
                        }
                        Item {
                            EmptyHint { anchors.centerIn: parent; visible: backend.templates.length === 0; text: "No templates yet. Save a session as a reusable template, or import Stellarium / Telescopius." }
                            GridView {
                                anchors.fill: parent
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
                                    Text {
                                        visible: modelData.target_name !== modelData.name
                                        text: modelData.target_name
                                        color: root.textPrimary
                                        font.pixelSize: 16
                                        Layout.fillWidth: true
                                        wrapMode: Text.WordWrap
                                    }
                                    Text { text: modelData.summary; color: root.textSecondary; Layout.fillWidth: true }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        HudButton { text: "EDIT"; busyText: "OPENING…"; onClicked: sessionDialog.openTemplate(templateCard.modelData) }
                                        HudButton { text: "SCHEDULE"; Layout.fillWidth: true; busyText: "SCHEDULING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.scheduleTemplate(modelData.id) }
                                        HudButton { text: "DELETE"; busyText: "DELETING…"; onClicked: backend.deleteTemplate(modelData.id) }
                                    }
                                    TapHandler {
                                        acceptedButtons: Qt.RightButton
                                        onTapped: templateMenu.popup()
                                    }
                                    HudMenu {
                                        id: templateMenu
                                        HudMenuItem {
                                            text: "Edit"
                                            glyph: "\uE70F"
                                            onTriggered: sessionDialog.openTemplate(templateCard.modelData)
                                        }
                                        HudMenuItem {
                                            text: "Schedule"
                                            glyph: "\uE768"
                                            onTriggered: backend.scheduleTemplate(templateCard.modelData.id)
                                        }
                                        HudMenuSeparator {}
                                        HudMenuItem {
                                            text: "Delete"
                                            glyph: "\uE74D"
                                            destructive: true
                                            onTriggered: backend.deleteTemplate(templateCard.modelData.id)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                }
            }

            Item {
                id: historyPage
                property string query: ""
                property int outcomeFilter: 0
                property int expandedIndex: -1
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
                readonly property int filteredFrames: filteredHistory.reduce((sum, item) => sum + (item.frame_count || 0), 0)
                readonly property int filteredOk: filteredHistory.filter(item => item.ok).length
                readonly property int filteredSeconds: filteredHistory.reduce((sum, item) => sum + (item.actual_duration_seconds || 0), 0)
                function formatHours(seconds) {
                    const hours = Math.max(0, seconds) / 3600
                    return hours >= 10 ? hours.toFixed(0) + "h" : hours.toFixed(1) + "h"
                }
                function resetExpanded() { historyPage.expandedIndex = -1 }
                onQueryChanged: resetExpanded()
                onOutcomeFilterChanged: resetExpanded()
                Connections { target: backend; function onHistoryChanged() { historyPage.resetExpanded() } }

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
                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: "HISTORY"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                            Text { text: "Click a run for timing, frames and outcome details"; color: root.textSecondary }
                        }
                        HudButton {
                            text: "CLEAR HISTORY"
                            enabled: backend.history.length > 0
                            busyText: "CLEARING…"
                            buttonColor: "#3A1218"
                            foregroundColor: root.danger
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
                                ["SESSIONS", String(historyPage.filteredCount)],
                                ["FRAMES", String(historyPage.filteredFrames)],
                                ["SUCCESS", historyPage.filteredCount ? Math.round(100 * historyPage.filteredOk / historyPage.filteredCount) + "%" : "—"],
                                ["IMAGED", historyPage.formatHours(historyPage.filteredSeconds)]
                            ]
                            delegate: HudPanel {
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 90
                                Text { text: modelData[1]; color: root.accent; font.pixelSize: 28; font.bold: true }
                                Text { text: modelData[0]; color: root.textSecondary; font.pixelSize: 11; font.letterSpacing: 1.4 }
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
                    HudPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 240
                        Layout.preferredHeight: 0
                        EmptyHint {
                            Layout.alignment: Qt.AlignHCenter
                            visible: historyPage.filteredCount === 0
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
                                    Text { width: 22; height: parent.height; text: ""; color: root.accent }
                                    Repeater {
                                        model: [
                                            {label: "DATE", w: 0.12}, {label: "TARGET", w: 0.24}, {label: "DEVICE", w: 0.13},
                                            {label: "FRAMES", w: 0.08}, {label: "PLANNED", w: 0.10}, {label: "ACTUAL", w: 0.10},
                                            {label: "OUTCOME", w: 0.23}
                                        ]
                                        Text {
                                            required property var modelData
                                            width: (parent.width - 22) * modelData.w
                                            height: parent.height
                                            text: modelData.label
                                            color: root.accent
                                            font.pixelSize: 10
                                            font.bold: true
                                            verticalAlignment: Text.AlignVCenter
                                            elide: Text.ElideRight
                                            leftPadding: 6
                                        }
                                    }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: root.outline }
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
                                    color: expanded ? "#22123C52" : (index % 2 ? "#140A1520" : "transparent")
                                    border.color: expanded ? root.outline : "transparent"
                                    Column {
                                        id: rowBody
                                        width: parent.width
                                        Item {
                                            width: parent.width
                                            height: 42
                                            Row {
                                                anchors.fill: parent
                                                Text {
                                                    width: 22
                                                    height: parent.height
                                                    text: historyRow.expanded ? "▾" : "▸"
                                                    color: root.accent
                                                    font.pixelSize: 10
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                                Repeater {
                                                    model: [
                                                        {text: historyRow.modelData.date, w: 0.12, color: root.textPrimary},
                                                        {text: historyRow.modelData.target_name, w: 0.24, color: root.textPrimary},
                                                        {text: historyRow.modelData.device_name, w: 0.13, color: root.accent},
                                                        {text: String(historyRow.modelData.frame_count || 0), w: 0.08, color: root.textSecondary},
                                                        {text: historyRow.modelData.planned_text, w: 0.10, color: root.textSecondary},
                                                        {text: historyRow.modelData.actual_text, w: 0.10, color: root.textSecondary},
                                                        {text: historyRow.modelData.outcome, w: 0.23, color: historyRow.modelData.ok ? root.success : root.danger}
                                                    ]
                                                    Text {
                                                        required property var modelData
                                                        width: (parent.width - 22) * modelData.w
                                                        height: parent.height
                                                        text: modelData.text
                                                        color: modelData.color
                                                        font.pixelSize: 12
                                                        elide: Text.ElideRight
                                                        verticalAlignment: Text.AlignVCenter
                                                        leftPadding: 6
                                                        rightPadding: 6
                                                    }
                                                }
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                acceptedButtons: Qt.LeftButton
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: historyPage.expandedIndex = historyRow.expanded ? -1 : historyRow.index
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
                                                width: parent.width - 30
                                                x: 22
                                                y: 4
                                                spacing: 6
                                                Text {
                                                    visible: !!(historyRow.modelData.summary)
                                                    text: historyRow.modelData.summary
                                                    color: root.textPrimary
                                                    font.pixelSize: 12
                                                }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: 4
                                                    columnSpacing: 16
                                                    rowSpacing: 4
                                                    Text { text: "SCHEDULED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "STARTED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "ENDED"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: "VARIANCE"; color: root.textSecondary; font.pixelSize: 9; font.bold: true }
                                                    Text { text: historyRow.modelData.scheduled_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text { text: historyRow.modelData.started_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text { text: historyRow.modelData.ended_text; color: root.textPrimary; font.pixelSize: 12 }
                                                    Text {
                                                        text: historyRow.modelData.delta_text
                                                        color: Math.abs(historyRow.modelData.delta_seconds || 0) < 1 ? root.success : (historyRow.modelData.delta_seconds > 0 ? root.warning : root.success)
                                                        font.pixelSize: 12
                                                    }
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: historyRow.modelData.outcome
                                                    color: historyRow.modelData.ok ? root.success : root.danger
                                                    wrapMode: Text.Wrap
                                                    font.pixelSize: 12
                                                }
                                                Text {
                                                    visible: !!(historyRow.modelData.notes)
                                                    Layout.fillWidth: true
                                                    text: historyRow.modelData.notes
                                                    color: root.textSecondary
                                                    wrapMode: Text.Wrap
                                                    font.pixelSize: 11
                                                }
                                                RowLayout {
                                                    HudButton {
                                                        text: "RUN AGAIN"
                                                        enabled: !!historyRow.modelData.has_session
                                                        busyText: "STARTING…"
                                                        buttonColor: "#0E3A48"
                                                        foregroundColor: root.accent
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

            Item {
                id: settingsPage
                property string loadedDeviceId: ""
                property string loadedSnapshot: ""
                function currentPayload() {
                    return {
                        id: backend.selectedDeviceId, name: nameField.text, model: modelField.currentText,
                        ip_address: ipField.text, camera: cameraField.currentIndex === 1 ? "wide" : "tele",
                        ble_enabled: bleField.checked,
                        latitude: Number(latField.text), longitude: Number(lonField.text),
                        timezone_name: timezoneField.selectedName || timezoneField.editText, stellarium_url: stellariumField.text,
                        wifi_mode: ["auto", "ap", "sta"][wifiModeField.currentIndex],
                        wifi_ssid: ssidField.text, wifi_password: wifiField.text,
                        ble_password: blePasswordField.text,
                        observing_day_cutoff_hour: cutoffField.value, slew_seconds: Number(slewField.text),
                        settle_seconds: Number(settleField.text), calibration_seconds: Number(calibrationField.text),
                        autofocus_seconds: Number(autofocusField.text), infinite_focus_seconds: Number(infinityField.text),
                        polar_seconds: Number(polarField.text), readout_seconds: Number(readoutField.text),
                        pane_slew_seconds: Number(paneField.text), startup_seconds: Number(startupField.text)
                    }
                }
                function isDirty() { return JSON.stringify(currentPayload()) !== loadedSnapshot }
                function saveCurrent() {
                    backend.saveDevice(JSON.stringify(currentPayload()))
                    loadedSnapshot = JSON.stringify(currentPayload())
                }
                function load() {
                    const d = backend.selectedDevice
                    loadedDeviceId = d.id || ""
                    const hw = d.hardware || {}
                    nameField.text = d.name || ""
                    modelField.currentIndex = Math.max(0, ["Dwarf II", "Dwarf 3", "Dwarf Mini"].indexOf(d.model))
                    ipField.text = d.ip_address || ""
                    cameraField.currentIndex = d.camera === "wide" ? 1 : 0
                    bleField.checked = d.ble_enabled !== false
                    latField.text = d.latitude
                    lonField.text = d.longitude
                    timezoneField.setFromName(d.timezone_name || "")
                    stellariumField.text = d.stellarium_url || "http://localhost:8090"
                    wifiModeField.currentIndex = Math.max(0, ["auto", "ap", "sta"].indexOf(d.wifi_mode || "auto"))
                    ssidField.text = d.wifi_ssid || ""
                    wifiField.text = d.wifi_password || ""
                    blePasswordField.text = d.ble_password || "DWARF_12345678"
                    cutoffField.value = d.observing_day_cutoff_hour || 12
                    slewField.text = hw.slew_seconds || 20
                    settleField.text = hw.settle_seconds || 10
                    calibrationField.text = hw.calibration_seconds || 90
                    autofocusField.text = hw.autofocus_seconds || 45
                    infinityField.text = hw.infinite_focus_seconds || 15
                    polarField.text = hw.polar_seconds || 180
                    readoutField.text = hw.readout_seconds || 1.2
                    paneField.text = hw.pane_slew_seconds || 12
                    startupField.text = hw.startup_seconds || 8
                    loadedSnapshot = JSON.stringify(currentPayload())
                }
                Component.onCompleted: load()
                Connections {
                    target: backend
                    function onSelectedDeviceChanged() {
                        if (settingsPage.loadedDeviceId !== backend.selectedDeviceId)
                            settingsPage.load()
                        else if (!ipField.text && backend.selectedDevice.ip_address)
                            ipField.text = backend.selectedDevice.ip_address
                    }
                }

                function applyLocation(item) {
                    if (!item)
                        return
                    timezoneField.setFromName(item.name)
                    if (item.latitude !== undefined && item.latitude !== null)
                        latField.text = Number(item.latitude).toFixed(5)
                    if (item.longitude !== undefined && item.longitude !== null)
                        lonField.text = Number(item.longitude).toFixed(5)
                }

                Flickable {
                    id: settingsFlick
                    anchors.fill: parent
                    contentWidth: width
                    contentHeight: settingsColumn.implicitHeight + 24
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    flickableDirection: Flickable.VerticalFlick
                    ScrollBar.vertical: HiddenBar {}
                    ScrollBar.horizontal: HiddenBar {}
                    Column {
                        id: settingsColumn
                        width: settingsFlick.width
                        spacing: 12
                        RowLayout {
                            width: parent.width
                            ColumnLayout {
                                Layout.fillWidth: true
                                Text { text: "SETTINGS"; color: root.textPrimary; font.pixelSize: 22; font.letterSpacing: 2 }
                                Text { text: "Device, connection, and timing profiles"; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                Text { text: "Astro Dwarf v" + backend.appVersion; color: root.accent; font.pixelSize: 12; font.letterSpacing: 1 }
                            }
                            DeviceCombo {}
                            HudButton { text: "+ ADD DEVICE"; busyText: "ADDING…"; buttonColor: "#0E3A48"; foregroundColor: root.accent; onClicked: backend.addDevice() }
                            HudButton { text: "REMOVE DEVICE"; busyText: "REMOVING…"; buttonColor: "#3A1218"; foregroundColor: root.danger; onClicked: backend.deleteDevice(backend.selectedDeviceId) }
                        }
                        HudPanel {
                            title: "DEVICE"
                            width: parent.width
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "NAME" }
                                HudField { id: nameField; Layout.fillWidth: true }
                                FieldLabel { text: "MODEL" }
                                HudCombo { id: modelField; model: ["Dwarf II", "Dwarf 3", "Dwarf Mini"]; Layout.fillWidth: true }
                                FieldLabel { text: "CAMERA" }
                                HudCombo { id: cameraField; model: ["Tele", "Wide"]; Layout.fillWidth: true }
                                FieldLabel { text: "TIMEZONE" }
                                HudSearchCombo {
                                    id: timezoneField
                                    Layout.fillWidth: true
                                    allItems: backend.timezones
                                    onItemChosen: (item) => settingsPage.applyLocation(item)
                                }
                                FieldLabel { text: "LATITUDE" }
                                HudField { id: latField; Layout.fillWidth: true }
                                FieldLabel { text: "LONGITUDE" }
                                HudField { id: lonField; Layout.fillWidth: true }
                                FieldLabel { text: "STELLARIUM" }
                                HudField { id: stellariumField; Layout.fillWidth: true }
                                FieldLabel { text: "NIGHT CUTOFF" }
                                SpinBox {
                                    id: cutoffField
                                    from: 0
                                    to: 23
                                    value: 12
                                    editable: true
                                    Layout.fillWidth: true
                                    palette.text: root.textPrimary
                                    palette.base: "#0A1524"
                                    palette.button: "#122033"
                                    palette.buttonText: root.accent
                                    palette.highlight: root.accent
                                }
                            }
                        }
                        HudPanel {
                            title: "CONNECTION"
                            width: parent.width
                            Text {
                                text: "Bluetooth only finds the telescope and sets its Wi‑Fi. Commands and the live stream always use Wi‑Fi, so this computer must be on the same network afterward."
                                color: root.textSecondary
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 4
                                columnSpacing: 10
                                rowSpacing: 8
                                FieldLabel { text: "IP ADDRESS" }
                                HudField { id: ipField; Layout.fillWidth: true; placeholderText: "192.168.88.1 or LAN IP" }
                                FieldLabel { text: "CONNECTION MODE" }
                                HudCombo { id: wifiModeField; model: ["Auto", "AP hotspot", "STA station"]; Layout.fillWidth: true }
                                Text {
                                    Layout.fillWidth: true
                                    Layout.columnSpan: 4
                                    wrapMode: Text.Wrap
                                    color: root.textSecondary
                                    text: wifiModeField.currentIndex === 1
                                        ? "AP: the telescope broadcasts its own hotspot (for example DWARF3_1). Join that Wi‑Fi on this computer. The IP is usually 192.168.88.1. The hotspot name and password are set on the device."
                                        : wifiModeField.currentIndex === 2
                                            ? "STA: Bluetooth tells the telescope to join your home or public router. Enter that router's name and password. This computer must already be on the same Wi-Fi."
                                            : "Auto: keep the mode already set on the telescope. Bluetooth reads its current IP and does not switch AP or STA."
                                }
                                FieldLabel { text: "ROUTER WIFI NAME"; visible: wifiModeField.currentIndex === 2 }
                                HudField {
                                    id: ssidField
                                    Layout.fillWidth: true
                                    visible: wifiModeField.currentIndex === 2
                                    placeholderText: "Router name, not DWARF3_…"
                                }
                                FieldLabel { text: "ROUTER WIFI PASSWORD"; visible: wifiModeField.currentIndex === 2 }
                                HudField {
                                    id: wifiField
                                    echoMode: TextInput.Password
                                    Layout.fillWidth: true
                                    visible: wifiModeField.currentIndex === 2
                                }
                                FieldLabel { text: "BLUETOOTH PASSWORD" }
                                HudField {
                                    id: blePasswordField
                                    echoMode: TextInput.Password
                                    Layout.fillWidth: true
                                    placeholderText: "Factory default DWARF_12345678"
                                }
                                Item { Layout.fillWidth: true }
                                Item { Layout.fillWidth: true }
                                HudCheck {
                                    id: bleField
                                    text: "Use Bluetooth when the IP is empty or this computer cannot reach it"
                                    Layout.columnSpan: 4
                                }
                            }
                        }
                        HudPanel {
                            title: "HARDWARE DURATION PROFILE"
                            width: parent.width
                            Text { text: "These overheads size calendar blocks and remaining-time estimates."; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 6
                                columnSpacing: 8
                                rowSpacing: 6
                                FieldLabel { text: "SLEW S" }
                                HudField { id: slewField; Layout.fillWidth: true }
                                FieldLabel { text: "SETTLE S" }
                                HudField { id: settleField; Layout.fillWidth: true }
                                FieldLabel { text: "CALIBRATE S" }
                                HudField { id: calibrationField; Layout.fillWidth: true }
                                FieldLabel { text: "AUTOFOCUS S" }
                                HudField { id: autofocusField; Layout.fillWidth: true }
                                FieldLabel { text: "INFINITY S" }
                                HudField { id: infinityField; Layout.fillWidth: true }
                                FieldLabel { text: "POLAR S" }
                                HudField { id: polarField; Layout.fillWidth: true }
                                FieldLabel { text: "READOUT S" }
                                HudField { id: readoutField; Layout.fillWidth: true }
                                FieldLabel { text: "PANE SLEW S" }
                                HudField { id: paneField; Layout.fillWidth: true }
                                FieldLabel { text: "STARTUP S" }
                                HudField { id: startupField; Layout.fillWidth: true }
                            }
                            HudButton {
                                text: "SAVE DEVICE"
                                busyText: "SAVING…"
                                buttonColor: "#0E3A48"
                                foregroundColor: root.accent
                                onClicked: settingsPage.saveCurrent()
                            }
                        }
                        HudPanel {
                            title: "LEGACY IMPORT"
                            width: parent.width
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: "Import old Astro_Sessions JSON without modifying the old app."; color: root.textSecondary; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                }
                                HudButton { text: "CHOOSE FOLDER…"; busyText: "OPENING…"; onClicked: legacyDialog.open() }
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            Layout.maximumHeight: 48
            Layout.fillHeight: false
            Layout.leftMargin: 10
            Layout.rightMargin: 10
            Layout.bottomMargin: 8
            spacing: 8
            Item {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                Layout.fillHeight: false
                Image { anchors.fill: parent; source: root.asset("hud-joystick.png"); fillMode: Image.PreserveAspectFit }
            }
            Repeater {
                model: [
                    {label: "CONTROL", idx: 0},
                    {label: "CALENDAR", idx: 1},
                    {label: "SESSIONS", idx: 2},
                    {label: "HISTORY", idx: 3},
                    {label: "SETTINGS", idx: 4}
                ]
                delegate: HudButton {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    Layout.fillHeight: false
                    text: modelData.label
                    font.pixelSize: 12
                    font.letterSpacing: 1.4
                    buttonColor: root.currentPage === modelData.idx ? "#0E3A48" : "#0A1524"
                    foregroundColor: root.currentPage === modelData.idx ? root.accent : root.textSecondary
                    onClicked: root.goToPage(modelData.idx)
                }
            }
        }
        }

        Rectangle {
            anchors.fill: parent
            enabled: false
            color: "transparent"
            border.color: "#3F6E82"
            border.width: 2
            z: 2000
        }
    }

    Popup {
        id: snackbar
        property alias text: snackbarText.text
        property string level: "info"
        width: Math.min(root.width - 80, 520)
        height: 52
        x: (root.width - width) / 2
        y: root.height - height - 70
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Rectangle {
            color: "#0B1520"
            border.color: snackbar.level === "error" ? root.danger : snackbar.level === "warning" ? root.warning : root.accent
        }
        contentItem: Text { id: snackbarText; color: root.textPrimary; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap; leftPadding: 8 }
        onOpened: snackbarTimer.restart()
        Timer { id: snackbarTimer; interval: 4000; onTriggered: snackbar.close() }
    }

    Connections {
        target: backend
        function onToast(message, level) {
            snackbar.level = level
            snackbar.text = message
            snackbar.open()
        }
        function onLocationLookupReady(item) {
            if (locationDialog.visible)
                locationDialog.applyLocation(item)
            else
                settingsPage.applyLocation(item)
        }
        function onSelectedDeviceChanged() { root.maybeAskLocation() }
    }

    Dialog {
        id: locationDialog
        modal: true
        closePolicy: Popup.NoAutoClose
        anchors.centerIn: Overlay.overlay
        width: 520
        padding: 18
        height: Math.min(root.height - 60, locationColumn.implicitHeight + padding * 2)
        background: Rectangle { color: "#0B1520"; border.color: root.accent }
        function applyLocation(item) {
            if (!item)
                return
            locationTimezone.setFromName(item.name)
            if (item.latitude !== undefined && item.latitude !== null)
                locationLat.text = Number(item.latitude).toFixed(5)
            if (item.longitude !== undefined && item.longitude !== null)
                locationLon.text = Number(item.longitude).toFixed(5)
        }
        onOpened: {
            const d = backend.selectedDevice
            locationTimezone.setFromName(d.timezone_name && d.location_configured ? d.timezone_name : "")
            locationLat.text = d.location_configured ? d.latitude : ""
            locationLon.text = d.location_configured ? d.longitude : ""
        }
        contentItem: ColumnLayout {
            id: locationColumn
            spacing: 12
            Text { text: "OBSERVING LOCATION"; color: root.accent; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text {
                text: "Choose a timezone or city so Astro Dwarf can set longitude and latitude for this telescope. A location is required before connecting or running sessions."
                color: root.textPrimary
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            FieldLabel { text: "TIMEZONE / CITY" }
            HudSearchCombo {
                id: locationTimezone
                Layout.fillWidth: true
                allItems: backend.timezones
                onItemChosen: (item) => locationDialog.applyLocation(item)
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                FieldLabel { text: "LAT" }
                HudField { id: locationLat; Layout.fillWidth: true; readOnly: true }
                FieldLabel { text: "LON" }
                HudField { id: locationLon; Layout.fillWidth: true; readOnly: true }
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton {
                    text: "SAVE LOCATION"
                    enabled: locationTimezone.selectedName.length > 0 || locationTimezone.editText.length > 0
                    busyText: "SAVING…"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: backend.saveObservingLocation(JSON.stringify({
                        id: backend.selectedDeviceId,
                        timezone_name: locationTimezone.selectedName || locationTimezone.editText,
                        latitude: Number(locationLat.text),
                        longitude: Number(locationLon.text)
                    }))
                }
            }
        }
    }

    Dialog {
        id: settingsLeaveDialog
        property int pendingPage: -1
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 480
        height: 176
        padding: 16
        background: Rectangle { color: "#0B1520"; border.color: root.warning }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "UNSAVED SETTINGS"; color: root.warning; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text { text: "Save your device settings before leaving this page?"; color: root.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: settingsLeaveDialog.close() }
                HudButton {
                    text: "DISCARD"
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: {
                        const idx = settingsLeaveDialog.pendingPage
                        settingsLeaveDialog.close()
                        settingsPage.load()
                        root.currentPage = idx
                    }
                }
                HudButton {
                    text: "SAVE"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: {
                        const idx = settingsLeaveDialog.pendingPage
                        settingsPage.saveCurrent()
                        settingsLeaveDialog.close()
                        root.currentPage = idx
                    }
                }
            }
        }
    }

    Dialog {
        id: confirmDialog
        property string operation: ""
        property string summary: ""
        property string kind: "device"
        property string headingText: "CONFIRM COMMAND"
        property string confirmLabel: "CONFIRM"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 420
        height: 176
        padding: 16
        background: Rectangle { color: "#0B1520"; border.color: root.danger }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: confirmDialog.headingText; color: root.danger; font.pixelSize: 16; font.letterSpacing: 1.4 }
            Text { text: confirmDialog.summary; color: root.textPrimary; wrapMode: Text.Wrap; Layout.fillWidth: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: confirmDialog.close() }
                HudButton {
                    text: confirmDialog.confirmLabel
                    busyText: "WORKING…"
                    buttonColor: "#3A1218"
                    foregroundColor: root.danger
                    onClicked: {
                        if (confirmDialog.kind === "clearHistory")
                            backend.clearHistory()
                        else
                            backend.deviceAction(backend.selectedDeviceId, confirmDialog.operation)
                        confirmDialog.close()
                    }
                }
            }
        }
    }

    FileDialog {
        id: telescopiusDialog
        title: "Import Telescopius CSV"
        nameFilters: ["CSV files (*.csv)"]
        onAccepted: backend.importTelescopius(selectedFile)
    }
    FolderDialog {
        id: legacyDialog
        title: "Select old Astro_Sessions folder"
        onAccepted: backend.importLegacy(selectedFolder)
    }

    Dialog {
        id: sessionDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 900)
        height: Math.min(root.height - 80, 720)
        property string editingId: ""
        property bool editingTemplate: false
        padding: 0

        function fillForm(data) {
            sessionName.text = data.pane_name || data.name || ""
            targetName.text = (data.target && data.target.name) ? data.target.name : (data.target_name || "")
            const kind = data.target ? data.target.kind : "equatorial"
            targetType.currentIndex = Math.max(0, ["equatorial", "solar", "none"].indexOf(kind))
            ra.text = data.target && data.target.ra_hours != null ? data.target.ra_hours : ""
            dec.text = data.target && data.target.dec_degrees != null ? data.target.dec_degrees : ""
            exposure.text = data.camera.exposure_seconds
            gain.text = data.camera.gain
            frames.text = data.camera.frame_count
            camera.currentIndex = data.camera.camera === "wide" ? 1 : 0
            binning.currentIndex = Math.max(0, ["1", "2"].indexOf(String(data.camera.binning)))
            const ir = data.camera.ir_filter || "VIS Filter"
            irFilter.currentIndex = Math.max(0, ["VIS Filter", "Astro Filter", "Duo-Band Filter", "VIS"].indexOf(ir) % 3)
            rows.text = data.mosaic.rows
            columns.text = data.mosaic.columns
            rotation.text = data.mosaic.rotation_degrees
            hScale.text = data.mosaic.horizontal_scale
            vScale.text = data.mosaic.vertical_scale
            waitBefore.text = data.workflow.wait_before_seconds
            waitAfter.text = data.workflow.wait_after_seconds
            notes.text = data.notes || ""
            calibrate.checked = data.workflow.calibrate
            autofocus.checked = data.workflow.autofocus
            infiniteFocus.checked = data.workflow.infinite_focus
            polar.checked = data.workflow.polar_align
            doGoto.checked = data.workflow.goto
            saveTemplate.checked = false
        }
        function formPayload() {
            return {
                id: sessionDialog.editingId, name: sessionName.text, target: targetName.text,
                target_kind: targetType.currentText, ra: ra.text, dec: dec.text,
                scheduled_start: startTime.text, device_id: backend.selectedDeviceId,
                camera: camera.currentIndex === 1 ? "wide" : "tele", exposure: Number(exposure.text),
                gain: Number(gain.text), frame_count: Number(frames.text), binning: Number(binning.currentText),
                ir_filter: irFilter.currentText, rows: Number(rows.text), columns: Number(columns.text),
                rotation: Number(rotation.text), horizontal_scale: Number(hScale.text), vertical_scale: Number(vScale.text),
                wait_before: Number(waitBefore.text), wait_after: Number(waitAfter.text), notes: notes.text,
                calibrate: calibrate.checked, autofocus: autofocus.checked, infinite_focus: infiniteFocus.checked,
                polar_align: polar.checked, goto: doGoto.checked, save_template: saveTemplate.checked
            }
        }
        function openForDate(day) {
            editingId = ""
            editingTemplate = false
            sessionName.text = ""
            targetName.text = ""
            targetType.currentIndex = 0
            ra.text = ""
            dec.text = ""
            startTime.text = day + "T22:00"
            exposure.text = "15"
            gain.text = "80"
            frames.text = "120"
            binning.currentIndex = 0
            irFilter.currentIndex = 0
            camera.currentIndex = 0
            rows.text = "1"
            columns.text = "1"
            rotation.text = "0"
            hScale.text = "150"
            vScale.text = "150"
            waitBefore.text = "0"
            waitAfter.text = "10"
            notes.text = ""
            calibrate.checked = true
            autofocus.checked = true
            infiniteFocus.checked = false
            polar.checked = false
            doGoto.checked = true
            saveTemplate.checked = false
            open()
        }
        function openExisting(data) {
            editingId = data.id
            editingTemplate = false
            fillForm(data)
            startTime.text = String(data.scheduled_start).substring(0, 16)
            open()
        }
        function openTemplate(data) {
            editingId = data.id
            editingTemplate = true
            fillForm(data)
            startTime.text = ""
            open()
        }

        background: Rectangle { color: "#0B1520"; border.color: root.accent }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                Text { text: sessionDialog.editingTemplate ? "EDIT TEMPLATE" : (sessionDialog.editingId ? "EDIT SESSION" : "NEW SESSION"); color: root.accent; font.pixelSize: 20; font.letterSpacing: 2; Layout.fillWidth: true }
                HudButton { text: "×"; implicitWidth: 40; onClicked: sessionDialog.close() }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                columnSpacing: 10
                rowSpacing: 8
                FieldLabel { text: "SESSION NAME" }
                HudField { id: sessionName; Layout.fillWidth: true; Layout.columnSpan: 2 }
                FieldLabel { text: "TARGET TYPE" }
                HudCombo { id: targetType; model: ["equatorial", "solar", "none"]; Layout.fillWidth: true }
                HudField { id: targetName; placeholderText: "Target name"; Layout.fillWidth: true }
                FieldLabel { text: "RA HOURS" }
                HudField { id: ra; Layout.fillWidth: true }
                HudField { id: dec; placeholderText: "Dec degrees"; Layout.fillWidth: true }
                FieldLabel { text: "START"; visible: !sessionDialog.editingTemplate }
                HudField { id: startTime; Layout.fillWidth: true; Layout.columnSpan: 2; visible: !sessionDialog.editingTemplate }
                FieldLabel { text: "CAMERA" }
                HudCombo { id: camera; model: ["Tele", "Wide"]; Layout.fillWidth: true; Layout.columnSpan: currentIndex === 1 ? 2 : 1 }
                HudCombo {
                    id: irFilter
                    visible: camera.currentIndex === 0
                    model: ["VIS Filter", "Astro Filter", "Duo-Band Filter"]
                    Layout.fillWidth: true
                }
                FieldLabel { text: "EXPOSURE" }
                HudField { id: exposure; Layout.fillWidth: true }
                HudField { id: gain; placeholderText: "Gain"; Layout.fillWidth: true }
                FieldLabel { text: "FRAMES" }
                HudField { id: frames; Layout.fillWidth: true }
                HudCombo { id: binning; model: ["1", "2"]; Layout.fillWidth: true }
                FieldLabel { text: "MOSAIC" }
                HudField { id: rows; placeholderText: "Rows"; Layout.fillWidth: true }
                HudField { id: columns; placeholderText: "Columns"; Layout.fillWidth: true }
                FieldLabel { text: "ROTATION / SCALE" }
                HudField { id: rotation; placeholderText: "Rotation °"; Layout.fillWidth: true }
                RowLayout {
                    HudField { id: hScale; placeholderText: "H scale"; Layout.fillWidth: true }
                    HudField { id: vScale; placeholderText: "V scale"; Layout.fillWidth: true }
                }
                FieldLabel { text: "WAIT S" }
                HudField { id: waitBefore; placeholderText: "Before"; Layout.fillWidth: true }
                HudField { id: waitAfter; placeholderText: "After"; Layout.fillWidth: true }
                FieldLabel { text: "NOTES" }
                HudField { id: notes; Layout.fillWidth: true; Layout.columnSpan: 2 }
            }
            RowLayout {
                HudCheck { id: calibrate; text: "Calibrate" }
                HudCheck { id: autofocus; text: "Auto focus" }
                HudCheck { id: infiniteFocus; text: "Infinity focus" }
                HudCheck { id: polar; text: "Polar / EQ" }
                HudCheck { id: doGoto; text: "GOTO" }
                HudCheck { id: saveTemplate; text: "Save template"; visible: !sessionDialog.editingTemplate }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                HudButton { text: "CANCEL"; onClicked: sessionDialog.close() }
                HudButton {
                    text: sessionDialog.editingTemplate ? "SAVE TEMPLATE" : "SAVE SESSION"
                    busyText: "SAVING…"
                    buttonColor: "#0E3A48"
                    foregroundColor: root.accent
                    onClicked: {
                        const payload = JSON.stringify(sessionDialog.formPayload())
                        if (sessionDialog.editingTemplate)
                            backend.saveTemplate(payload)
                        else
                            backend.saveSession(payload)
                        sessionDialog.close()
                    }
                }
            }
        }
    }
}
