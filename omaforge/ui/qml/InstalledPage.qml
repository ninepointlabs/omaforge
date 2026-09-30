import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    spacing: 0
    signal exportRequested()
    signal importRequested()
    signal confirm(string title, string message, string confirmText, bool dangerous, var action)
    signal showDetails(var addon)

    property string filter: ""

    readonly property var shown: {
        var q = filter.toLowerCase()
        var list = backend.addons.filter(function (a) {
            return !q || a.name.toLowerCase().indexOf(q) >= 0
                || a.folders.join(" ").toLowerCase().indexOf(q) >= 0
                || (a.provider || "unknown").indexOf(q) >= 0
        })
        return list.sort(function (a, b) {
            var ua = a.update_available && !a.pinned && !a.ignored ? 0 : 1
            var ub = b.update_available && !b.pinned && !b.ignored ? 0 : 1
            if (ua !== ub) return ua - ub
            return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1
        })
    }
    readonly property int unknownCount: backend.addons.filter(function (a) { return !a.provider }).length
    readonly property string summary: backend.addons.length + " addons"
        + (unknownCount ? " · " + unknownCount + " unknown" : "")
        + (backend.checked ? " · " + (backend.updateCount ? backend.updateCount + " to update" : "all up to date") : "")

    function focusFilter() { filterField.forceActiveFocus() }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        spacing: 8

        Field {
            id: filterField
            Layout.preferredWidth: 260
            placeholderText: "Filter addons  (Ctrl+F)"
            onTextChanged: page.filter = text
            Keys.onEscapePressed: text = ""
        }
        Item { Layout.fillWidth: true }
        Btn { text: "Import…"; subtle: true; onClicked: page.importRequested() }
        Btn { text: "Export…"; subtle: true; onClicked: page.exportRequested() }
        Btn { text: "Check for updates"; enabled: !backend.busy; onClicked: backend.checkUpdates() }
        Btn {
            text: backend.updateCount ? "Update all (" + backend.updateCount + ")" : "Update all"
            primary: true
            enabled: backend.updateCount > 0 && !backend.busy
            onClicked: backend.updateAll()
        }
    }

    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: page.shown
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        delegate: Rectangle {
            id: row
            required property var modelData
            readonly property var a: modelData
            readonly property bool canUpdate: a.update_available && !a.pinned && !a.ignored
            width: list.width
            height: 58
            color: hover.hovered ? theme.surface : "transparent"
            HoverHandler { id: hover }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.showDetails(row.a) }

            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border; opacity: 0.5 }
            Rectangle { width: 3; height: parent.height; color: theme.accent; visible: row.canUpdate }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 10000  // take whatever is left, never push the buttons out
                    Layout.minimumWidth: 120
                    spacing: 3
                    Label2 {
                        Layout.fillWidth: true
                        text: row.a.name
                        font.pixelSize: 14
                        opacity: row.a.ignored ? 0.5 : 1
                    }
                    RowLayout {
                        spacing: 10
                        Layout.fillWidth: true
                        Label2 {
                            dim: true
                            font.pixelSize: 11
                            text: (row.a.provider ? row.a.provider + (row.a.match && row.a.match !== "state" ? " · matched by " + row.a.match : "") : "unknown source")
                                  + " · " + row.a.folders.length + (row.a.folders.length === 1 ? " folder" : " folders")
                                  + (row.a.author ? " · " + row.a.author : "")
                            Layout.fillWidth: true
                            Layout.minimumWidth: 40
                            HoverHandler { id: foldersHover }
                            ToolTip.visible: foldersHover.hovered
                            ToolTip.delay: 400
                            ToolTip.text: row.a.folders.join("\n")
                        }
                        Label2 { font.pixelSize: 11; color: theme.yellow; visible: !row.a.compatible; text: "may be out of date" }
                        Label2 { font.pixelSize: 11; color: theme.red; visible: !row.a.loadable; text: "not loadable by this client" }
                        Label2 {
                            font.pixelSize: 11
                            color: theme.red
                            visible: row.a.update_error !== "" && backend.checked && !!row.a.provider && !row.a.ignored
                            text: "can't check"
                            HoverHandler { id: errHover }
                            ToolTip.visible: errHover.hovered
                            ToolTip.text: row.a.update_error
                        }
                    }
                }

                ColumnLayout {
                    spacing: 3
                    Layout.preferredWidth: 130
                    Label2 {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignRight
                        text: row.a.version || "?"
                    }
                    Label2 {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignRight
                        font.pixelSize: 11
                        color: row.a.update_available ? theme.accent : theme.dim
                        text: row.a.ignored ? "ignored"
                              : row.a.update_available ? "→ " + row.a.latest.version + (row.a.pinned ? " (pinned)" : "")
                              : row.a.latest ? "up to date" : ""
                    }
                }

                Choice {
                    visible: !!row.a.provider
                    model: ["stable", "beta", "alpha"]
                    currentIndex: Math.max(0, model.indexOf(row.a.channel))
                    onActivated: function (i) { backend.setChannel(row.a.key, model[i]) }
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: "Release channel"
                }
                Item { visible: !row.a.provider; Layout.preferredWidth: 92 }

                Btn {
                    text: row.a.pinned ? "Pinned" : "Pin"
                    subtle: true
                    active: row.a.pinned
                    Layout.preferredWidth: 74
                    onClicked: backend.setPinned(row.a.key, !row.a.pinned)
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: row.a.pinned ? "Allow updates again" : "Keep this version"
                }
                Btn {
                    text: row.a.ignored ? "Ignored" : "Ignore"
                    subtle: true
                    active: row.a.ignored
                    Layout.preferredWidth: 78
                    onClicked: backend.setIgnored(row.a.key, !row.a.ignored)
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: row.a.ignored ? "Check this addon for updates again" : "Skip this addon when checking for updates"
                }
                Btn {
                    text: "Update"
                    primary: true
                    Layout.preferredWidth: 78
                    opacity: row.canUpdate ? 1 : 0
                    enabled: row.canUpdate && !backend.busy
                    onClicked: backend.updateAddon(row.a.key)
                }
                Btn {
                    text: "Remove"
                    subtle: true
                    danger: true
                    enabled: !backend.busy
                    onClicked: page.confirm("Remove " + row.a.name + "?",
                        "This deletes " + row.a.folders.length + " folder" + (row.a.folders.length === 1 ? "" : "s")
                        + " from Interface/AddOns:\n" + row.a.folders.join(", ")
                        + "\n\nSaved settings in WTF are kept.",
                        "Remove", true, function () { backend.uninstall(row.a.key) })
                }
            }
        }

        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0 && !backend.busy
            dim: true
            horizontalAlignment: Text.AlignHCenter
            text: page.filter ? "No addons match \"" + page.filter + "\""
                              : "No addons installed yet.\nBrowse the most popular under Explore."
        }
    }
}
