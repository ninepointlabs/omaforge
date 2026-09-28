import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ScrollView {
    id: page
    signal addFolderRequested()
    contentWidth: availableWidth
    clip: true

    property var s: backend.settings
    function load() {
        s = backend.settings
        autodetect.checked = s.autodetect
        cfKey.text = s.curseforgeKey
        ghToken.text = s.githubToken
        wagoKey.text = s.wagoKey
        keep.value = s.backupsKeep
        beforeUpdate.checked = s.backupBeforeUpdate
        offline.checked = s.offline
    }
    Component.onCompleted: load()
    onVisibleChanged: if (visible) load()

    readonly property var detectedRoots: {
        var seen = {}
        var out = []
        backend.clients.forEach(function (c) { if (!seen[c.root]) { seen[c.root] = true; out.push(c.root) } })
        return out
    }

    ColumnLayout {
        width: Math.min(page.availableWidth - 32, 760)
        x: 16
        spacing: 10

        Item { height: 6 }
        SectionTitle { text: "World of Warcraft installs" }
        Label2 {
            Layout.fillWidth: true
            dim: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: "Found automatically in Lutris, Steam/Proton, Bottles, Heroic and ~/.wine prefixes. "
                  + "Add any other install folder, client folder or Wine prefix by hand."
        }
        Repeater {
            model: page.detectedRoots
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                Label2 { text: modelData; Layout.fillWidth: true; elide: Text.ElideMiddle }
                Label2 { text: page.s.roots.indexOf(modelData) >= 0 ? "added by hand" : "detected"; dim: true; font.pixelSize: 11 }
                Btn { text: "Open"; subtle: true; onClicked: backend.openPath(modelData) }
                Btn {
                    text: "Remove"
                    subtle: true
                    danger: true
                    visible: page.s.roots.indexOf(modelData) >= 0
                    onClicked: backend.removeRoot(modelData)
                }
            }
        }
        RowLayout {
            spacing: 8
            Btn { text: "Add folder…"; onClicked: page.addFolderRequested() }
            Btn { text: "Rescan"; subtle: true; onClicked: backend.rescan() }
            Check { id: autodetect; text: "Detect installs automatically" }
        }

        Item { height: 10 }
        SectionTitle { text: "Addon sources" }
        Repeater {
            model: backend.providers
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: 10
                Rectangle { width: 8; height: 8; color: modelData.available ? theme.accent : theme.border }
                Label2 { text: modelData.label; Layout.preferredWidth: 140 }
                Label2 { text: modelData.available ? "ready" : modelData.reason; dim: true; Layout.fillWidth: true }
            }
        }
        GridLayout {
            columns: 2
            columnSpacing: 12
            rowSpacing: 8
            Layout.fillWidth: true
            Label2 { text: "CurseForge API key" }
            Field { id: cfKey; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Issued to omaforge by CurseForge" }
            Label2 { text: "GitHub token" }
            Field { id: ghToken; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Optional: raises the rate limit from 60 to 5,000 requests an hour" }
            Label2 { text: "Wago API key" }
            Field { id: wagoKey; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Not supported yet" }
        }
        Label2 {
            Layout.fillWidth: true
            dim: true
            font.pixelSize: 11
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: "Keys are stored in " + page.s.configPath + ", readable only by you."
        }

        Item { height: 10 }
        SectionTitle { text: "Backups" }
        Check { id: beforeUpdate; text: "Back up WTF before updating several addons at once" }
        RowLayout {
            spacing: 10
            Label2 { text: "Keep the last" }
            SpinBox {
                id: keep
                from: 1
                to: 100
                editable: true
                font.family: theme.font
                palette.base: theme.surface
                palette.text: theme.foreground
                palette.button: theme.raised
                palette.buttonText: theme.foreground
            }
            Label2 { text: "backups per client" }
        }

        Item { height: 10 }
        SectionTitle { text: "Network" }
        Check { id: offline; text: "Offline mode: use cached addon data only" }

        Item { height: 10 }
        RowLayout {
            Btn {
                text: "Save settings"
                primary: true
                enabled: !backend.busy
                onClicked: backend.saveSettings({
                    autodetect: autodetect.checked,
                    githubToken: ghToken.text,
                    curseforgeKey: cfKey.text,
                    wagoKey: wagoKey.text,
                    backupsKeep: keep.value,
                    backupBeforeUpdate: beforeUpdate.checked,
                    offline: offline.checked
                })
            }
            Btn { text: "Revert"; subtle: true; onClicked: page.load() }
        }

        Item { height: 16 }
        SectionTitle { text: "Command line" }
        Label2 {
            Layout.fillWidth: true
            dim: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: "omaforge update --all --notify   updates every client's addons from a keybinding or timer.\n"
                  + "omaforge --help                  lists every command."
        }
        Label2 { text: "omaforge " + backend.version; dim: true; font.pixelSize: 11 }
        Item { height: 24 }
    }
}
