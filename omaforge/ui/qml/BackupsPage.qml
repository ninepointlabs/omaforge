import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    spacing: 0
    signal confirm(string title, string message, string confirmText, bool dangerous, var action)
    // The width the window has for this page. The narrow layouts follow this, not the page's
    // own width, which can't shrink below what the wide layout needs.
    property real room: width

    // The buttons go under the text when narrow.
    GridLayout {
        id: bar
        readonly property bool roomy: page.room - 32 >= 240 + openWtf.implicitWidth + backUp.implicitWidth + 2 * columnSpacing
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        columns: roomy ? 3 : 2
        columnSpacing: 8
        rowSpacing: 8
        Label2 {
            Layout.fillWidth: true
            Layout.columnSpan: bar.roomy ? 1 : 2
            dim: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
            text: "Snapshots of the WTF folder: SavedVariables, keybindings and client settings. "
                  + "One is taken automatically before every bulk update."
        }
        Btn { id: openWtf; text: "Open WTF folder"; subtle: true; enabled: !!backend.client.path; onClicked: backend.openPath(backend.client.path + "/WTF") }
        Btn { id: backUp; text: "Back up now"; primary: true; enabled: !backend.busy; onClicked: backend.createBackup() }
    }
    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: backend.backups
        ScrollBar.vertical: ScrollBar {}
        delegate: Rectangle {
            id: row
            required property var modelData
            width: list.width
            height: 48
            color: hover.hovered ? theme.surface : "transparent"
            HoverHandler { id: hover }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border; opacity: 0.5 }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 16
                Label2 { text: new Date(row.modelData.created * 1000).toLocaleString(Qt.locale(), "yyyy-MM-dd  HH:mm"); Layout.preferredWidth: 170 }
                Label2 { text: row.modelData.reason.replace(/-/g, " "); dim: true; Layout.fillWidth: true }
                Label2 { text: (row.modelData.size / 1e6).toFixed(1) + " MB"; dim: true }
                Btn {
                    text: "Restore"
                    enabled: !backend.busy
                    onClicked: page.confirm("Restore this backup?",
                        "The WTF folder of " + backend.client.label + " is replaced with the snapshot from "
                        + new Date(row.modelData.created * 1000).toLocaleString() + ".\n\n"
                        + "The current WTF is backed up first. Close the game before restoring.",
                        "Restore", true, function () { backend.restoreBackup(row.modelData.id) })
                }
            }
        }
        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0 && !backend.busy
            dim: true
            text: "No backups yet."
        }
    }
}
