import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Format.js" as Fmt

// A remote addon in Search or Explore: icon, name, numbers, install.
Rectangle {
    id: row
    required property var modelData
    property int number: 0  // rank shown on the left in Explore; 0 hides it
    readonly property var r: modelData

    height: 74
    color: hover.hovered ? theme.surface : "transparent"
    HoverHandler { id: hover }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border; opacity: 0.5 }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 16
        spacing: 12

        Label2 {
            visible: row.number > 0
            text: row.number
            dim: true
            font.pixelSize: 15
            horizontalAlignment: Text.AlignRight
            Layout.preferredWidth: 30
        }
        Rectangle {
            Layout.preferredWidth: 44
            Layout.preferredHeight: 44
            color: theme.raised
            clip: true
            Image {
                id: icon
                anchors.fill: parent
                source: row.r.icon || ""
                sourceSize.width: 88
                sourceSize.height: 88
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: true
            }
            Label2 {
                anchors.centerIn: parent
                visible: icon.status !== Image.Ready
                text: row.r.name.replace(/[^A-Za-z0-9]/g, "").substring(0, 1).toUpperCase()
                color: theme.dim
                font.pixelSize: 18
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.preferredWidth: 10000
            Layout.minimumWidth: 120
            spacing: 3
            RowLayout {
                spacing: 8
                Layout.fillWidth: true
                Label2 { text: row.r.name; font.pixelSize: 14; Layout.maximumWidth: row.width * 0.45 }
                Label2 { text: row.r.author ? "by " + row.r.author : ""; dim: true; font.pixelSize: 12; Layout.fillWidth: true }
            }
            Label2 {
                Layout.fillWidth: true
                font.pixelSize: 11
                color: theme.foreground
                opacity: 0.8
                text: Fmt.stats(row.r) + (row.r.categories.length ? "  ·  " + row.r.categories.slice(0, 2).join(", ") : "")
            }
            Label2 {
                Layout.fillWidth: true
                dim: true
                font.pixelSize: 11
                text: (row.r.external_only ? "Not downloadable from CurseForge in other apps; installs from GitHub or WoWInterface when available.  " : "")
                      + (row.r.summary || (row.r.compatible ? "" : "No build listed for this client"))
                HoverHandler { id: noteHover }
                ToolTip.visible: noteHover.hovered && row.r.external_only
                ToolTip.delay: 400
                ToolTip.text: "The author has turned off downloads in third-party apps on CurseForge.\nomaforge looks for the same addon on GitHub or WoWInterface;\nif there is none, use Page to get it from curseforge.com."
            }
        }
        Label2 { text: row.r.provider; dim: true; font.pixelSize: 11 }
        Btn { text: "Page"; subtle: true; visible: !!row.r.url; onClicked: backend.openUrl(row.r.url) }
        Choice { id: channel; model: ["stable", "beta", "alpha"]; visible: !row.r.installed }
        Btn {
            Layout.preferredWidth: 100
            text: row.r.installed ? "Installed" : "Install"
            primary: !row.r.installed
            enabled: !row.r.installed && !backend.busy
            onClicked: backend.install(row.r.provider, row.r.id, channel.currentText)
        }
    }
}
