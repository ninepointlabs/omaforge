import QtCore
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1180
    height: 760
    minimumWidth: 640  // half of a 1280 px screen, so it can be tiled beside another window
    minimumHeight: 520
    visible: true
    title: backend.client.label ? "omaforge · " + backend.client.label : "omaforge"
    color: theme.background
    font.family: theme.font
    font.pixelSize: 13

    palette.window: theme.background
    palette.windowText: theme.foreground
    palette.base: theme.surface
    palette.alternateBase: theme.raised
    palette.text: theme.foreground
    palette.button: theme.surface
    palette.buttonText: theme.foreground
    palette.highlight: theme.accent
    palette.highlightedText: theme.accentText
    palette.placeholderText: theme.dim
    palette.toolTipBase: theme.raised
    palette.toolTipText: theme.foreground
    palette.mid: theme.border
    palette.dark: theme.border

    // 0 installed, 1 explore, 2 search, 3 backups, 4 settings
    property int pageIndex: 0
    readonly property var tabs: ["Installed", "Explore", "Search", "Backups", "Settings"]
    readonly property int settingsPage: 4
    // Below this the sidebar narrows and rows and toolbars fold their extra actions into menus.
    readonly property bool narrow: width < 1000
    readonly property real pageWidth: width - (narrow ? 190 : 240) - 1

    function stepClient(step) {
        var keys = backend.clients.map(function (c) { return c.key })
        if (keys.length > 1)
            backend.selectClient(keys[(keys.indexOf(backend.currentClient) + step + keys.length) % keys.length])
    }
    function go(i) {
        pageIndex = i
        if (i === 1) backend.ensureExplore()
        if (i === 3) backend.loadBackups()
    }

    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }
    Shortcut { sequence: "Ctrl+R"; onActivated: backend.checkUpdates() }
    Shortcut { sequence: "Ctrl+U"; onActivated: if (backend.updateCount > 0) backend.updateAll() }
    Shortcut { sequence: "Ctrl+F"; onActivated: { win.go(0); installed.focusFilter() } }
    Shortcut { sequence: "Ctrl+K"; onActivated: { win.go(2); search.focusSearch() } }
    Shortcut { sequence: "Ctrl+1"; onActivated: win.go(0) }
    Shortcut { sequence: "Ctrl+2"; onActivated: win.go(1) }
    Shortcut { sequence: "Ctrl+3"; onActivated: win.go(2) }
    Shortcut { sequence: "Ctrl+4"; onActivated: win.go(3) }
    Shortcut { sequence: "Ctrl+,"; onActivated: win.go(win.settingsPage) }
    Shortcut { sequence: "F1"; onActivated: about.open() }
    Shortcut { sequence: "Alt+Down"; onActivated: win.stepClient(1) }
    Shortcut { sequence: "Alt+Up"; onActivated: win.stepClient(-1) }

    Connections {
        target: backend
        function onToast(kind, message) { toast.show(kind, message) }
    }
    readonly property string clientKey: backend.currentClient
    onClientKeyChanged: {
        if (pageIndex === 1) backend.ensureExplore()
        if (pageIndex === 3) backend.loadBackups()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // Sidebar: one entry per detected client.
        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: win.narrow ? 190 : 240
            color: theme.surface

            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 18
                spacing: 0

                RowLayout {
                    Layout.leftMargin: 18
                    Layout.rightMargin: 18
                    Layout.bottomMargin: 22
                    spacing: 10
                    Image {
                        source: Qt.resolvedUrl("../icons/omaforge.svg")
                        sourceSize.width: 22
                        sourceSize.height: 22
                    }
                    Label2 { text: "omaforge"; font.pixelSize: 17; font.bold: true; color: theme.accent }
                }
                SectionTitle { text: "Game versions"; Layout.leftMargin: 18; Layout.bottomMargin: 8 }

                Repeater {
                    model: backend.clients
                    delegate: Rectangle {
                        id: item
                        required property var modelData
                        readonly property bool current: modelData.key === backend.currentClient
                        Layout.fillWidth: true
                        Layout.preferredHeight: 50
                        color: current ? theme.raised : hover.hovered ? Qt.lighter(theme.surface, 1.1) : "transparent"
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: backend.selectClient(item.modelData.key) }
                        Rectangle { width: 3; height: parent.height; color: theme.accent; visible: item.current }
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 18
                            anchors.rightMargin: 12
                            spacing: 2
                            Item { Layout.fillHeight: true }
                            Label2 {
                                Layout.fillWidth: true
                                text: item.modelData.label
                                color: item.current ? theme.foreground : theme.dim
                                font.pixelSize: 14
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 6
                                Label2 {
                                    Layout.fillWidth: true
                                    dim: true
                                    font.pixelSize: 11
                                    text: [item.modelData.version, item.modelData.folder].filter(function (s) { return !!s }).join("  ·  ")
                                }
                                Label2 {
                                    visible: !item.modelData.verified
                                    font.pixelSize: 11
                                    color: theme.yellow
                                    text: "unverified"
                                }
                            }
                            Item { Layout.fillHeight: true }
                        }
                        ToolTip.visible: hover.hovered
                        ToolTip.delay: 500
                        ToolTip.text: item.modelData.path + (item.modelData.notes.length ? "\n\n" + item.modelData.notes.join("\n") : "")
                    }
                }
                Label2 {
                    Layout.fillWidth: true
                    Layout.margins: 18
                    visible: backend.clients.length === 0 && !backend.busy
                    dim: true
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                    text: backend.configError ? "Installs can't be listed until the settings file is fixed."
                                              : "No World of Warcraft install found.\nAdd its folder under Settings."
                }
                Item { Layout.fillHeight: true }

                Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    spacing: 0
                    Btn { text: "Rescan"; subtle: true; onClicked: backend.rescan() }
                    Item { Layout.fillWidth: true }
                    // Narrow: About stays on F1 and in Settings.
                    Btn { objectName: "sidebarAbout"; text: "About"; subtle: true; visible: !win.narrow; leftPadding: 8; rightPadding: 8; onClicked: about.open() }
                    Btn { text: "Settings"; subtle: true; active: win.pageIndex === win.settingsPage; onClicked: win.go(win.settingsPage) }
                }
            }
        }
        Rectangle { Layout.fillHeight: true; width: 1; color: theme.border }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Header: client name and tabs; the tabs go on a line of their own when narrow.
            GridLayout {
                id: header
                readonly property bool stacked: win.pageWidth - 32 < tabRow.implicitWidth + columnSpacing + 220
                Layout.fillWidth: true
                Layout.leftMargin: 16
                Layout.rightMargin: 16
                Layout.topMargin: 14
                columns: stacked ? 1 : 2
                columnSpacing: 18
                rowSpacing: 6
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 0  // the tabs get their full width first; the title takes what's left
                    spacing: 2
                    Label2 { Layout.fillWidth: true; text: win.pageIndex === win.settingsPage ? "Settings" : (backend.client.label || "omaforge"); font.pixelSize: 20 }
                    Label2 {
                        Layout.fillWidth: true
                        dim: true
                        font.pixelSize: 11
                        visible: win.pageIndex !== win.settingsPage && !!backend.client.path
                        text: "build " + (backend.client.version || "?") + " · interface " + (backend.client.interface || "?")
                              + (win.pageIndex === 0 ? " · " + installed.summary : "")
                    }
                }
                RowLayout {
                    id: tabRow
                    spacing: 18
                    Repeater {
                        model: 4
                        delegate: Item {
                            id: tab
                            required property int index
                            implicitWidth: tabText.implicitWidth + 8
                            implicitHeight: 34
                            // Natural width, but able to shrink (eliding) rather than push past the window.
                            Layout.fillWidth: true
                            Layout.maximumWidth: implicitWidth
                            Layout.minimumWidth: 36
                            Label2 {
                                id: tabText
                                anchors.centerIn: parent
                                // Only when really squeezed: a rounding error must not elide the label.
                                width: tab.width - 8 < implicitWidth - 1 ? tab.width - 8 : implicitWidth
                                text: win.tabs[tab.index] + (tab.index === 0 && backend.updateCount ? "  " + backend.updateCount : "")
                                color: win.pageIndex === tab.index ? theme.foreground : theme.dim
                            }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: theme.accent; visible: win.pageIndex === tab.index }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: win.go(tab.index) }
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: theme.border; Layout.topMargin: 8 }

            // A settings file that can't be read: say which and what's wrong, instead of
            // "no install found", and offer only actions that keep the file.
            Rectangle {
                objectName: "configErrorBanner"
                Layout.fillWidth: true
                Layout.preferredHeight: bannerColumn.implicitHeight + 24
                visible: backend.configError !== ""
                color: theme.surface
                Rectangle { width: 3; height: parent.height; color: theme.red }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border }
                ColumnLayout {
                    id: bannerColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    spacing: 8
                    Label2 { text: "omaforge can't read a settings file"; color: theme.red; font.bold: true }
                    Label2 {
                        objectName: "configErrorText"
                        Layout.fillWidth: true
                        wrapMode: Text.WrapAnywhere
                        elide: Text.ElideNone
                        text: backend.configError
                    }
                    Label2 {
                        Layout.fillWidth: true
                        dim: true
                        wrapMode: Text.WordWrap
                        elide: Text.ElideNone
                        text: "Fix the file and press Rescan. Or set it aside: it is kept under a new name next to the original, "
                              + "and omaforge starts again from its defaults. Nothing is saved over it until then."
                    }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Btn { text: "Open file"; onClicked: backend.openPath(backend.configErrorPath) }
                        Btn { text: "Rescan"; enabled: !backend.busy; onClicked: backend.rescan() }
                        Btn { objectName: "setAsideBroken"; text: "Set it aside and use defaults"; subtle: true; danger: true; enabled: !backend.busy; onClicked: backend.setAsideBrokenFile() }
                    }
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                // The hidden pages' minimum widths would otherwise widen the shown one past the window.
                Layout.minimumWidth: 0
                currentIndex: win.pageIndex
                InstalledPage {
                    id: installed
                    room: win.pageWidth
                    onExportRequested: exportDialog.open()
                    onImportRequested: importDialog.open()
                    onConfirm: function (t, m, c, d, a) { confirm.ask(t, m, c, d, a) }
                    onShowDetails: function (a) { details.show(a) }
                }
                ExplorePage { id: explore; room: win.pageWidth; onShowDetails: function (a) { details.show(a) } }
                SearchPage { id: search; room: win.pageWidth; onShowDetails: function (a) { details.show(a) } }
                BackupsPage { room: win.pageWidth; onConfirm: function (t, m, c, d, a) { confirm.ask(t, m, c, d, a) } }
                SettingsPage { onAddFolderRequested: folderDialog.open(); onAboutRequested: about.open() }
            }

            // Status bar.
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 26
                color: theme.surface
                Rectangle { width: parent.width; height: 1; color: theme.border }
                Rectangle {
                    id: bar
                    height: 2
                    width: 80
                    color: theme.accent
                    visible: backend.busy
                    SequentialAnimation on x {
                        running: backend.busy
                        loops: Animation.Infinite
                        NumberAnimation { from: -80; to: win.width; duration: 1400; easing.type: Easing.InOutQuad }
                    }
                }
                Label2 {
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 16
                    anchors.rightMargin: 16
                    dim: true
                    font.pixelSize: 11
                    text: backend.busy ? (backend.status || "Working") + "…" : "Ctrl+R check · Ctrl+U update all · Ctrl+2 explore · Ctrl+K search · Ctrl+F filter · F1 about"
                }
            }
        }
    }

    Toast {
        id: toast
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 20
        anchors.bottomMargin: 40
    }
    Confirm { id: confirm }
    DetailsPopup { id: details; objectName: "details" }
    About { id: about; objectName: "about" }

    FileDialog {
        id: exportDialog
        title: "Export addon list"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "json"
        nameFilters: ["Addon lists (*.json)"]
        currentFolder: StandardPaths.writableLocation(StandardPaths.HomeLocation)
        onAccepted: backend.exportList(selectedFile.toString())
    }
    FileDialog {
        id: importDialog
        title: "Import addon list into " + (backend.client.label || "")
        fileMode: FileDialog.OpenFile
        nameFilters: ["Addon lists (*.json)"]
        onAccepted: backend.importList(selectedFile.toString())
    }
    FolderDialog {
        id: folderDialog
        title: "World of Warcraft folder, client folder or Wine prefix"
        onAccepted: backend.addRoot(selectedFolder.toString())
    }
}
