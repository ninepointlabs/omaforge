import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ColumnLayout {
    id: page
    spacing: 0
    property var disabledProviders: ({})
    property string lastQuery: ""

    readonly property var usable: backend.providers.filter(function (p) { return p.available })
    readonly property var unusable: backend.providers.filter(function (p) { return !p.available })

    function focusSearch() { query.forceActiveFocus(); query.selectAll() }
    function run() {
        var chosen = page.usable.filter(function (p) { return !page.disabledProviders[p.name] })
                                .map(function (p) { return p.name })
        if (!query.text.trim() || chosen.length === 0) return
        page.lastQuery = query.text.trim()
        backend.search(query.text, chosen)
    }
    function fmt(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"
        if (n >= 1e3) return (n / 1e3).toFixed(0) + "k"
        return "" + n
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        spacing: 8
        Field {
            id: query
            Layout.fillWidth: true
            placeholderText: "Search addons for " + (backend.client.label || "this client") + ", or paste a GitHub repo"
            onAccepted: page.run()
        }
        Repeater {
            model: page.usable
            delegate: Btn {
                required property var modelData
                text: modelData.label
                subtle: true
                active: !page.disabledProviders[modelData.name]
                onClicked: {
                    var d = Object.assign({}, page.disabledProviders)
                    d[modelData.name] = !d[modelData.name]
                    page.disabledProviders = d
                }
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: active ? "Searching " + modelData.label + "; click to skip it" : "Click to search " + modelData.label
            }
        }
        Btn { text: "Search"; primary: true; enabled: !backend.busy && query.text.trim() !== ""; onClicked: page.run() }
    }

    Label2 {
        Layout.fillWidth: true
        Layout.leftMargin: 16
        Layout.bottomMargin: 8
        visible: page.unusable.length > 0
        dim: true
        font.pixelSize: 11
        text: page.unusable.map(function (p) { return p.label + ": " + p.reason }).join("   ·   ")
    }
    Repeater {
        model: Object.keys(backend.searchErrors)
        delegate: Label2 {
            required property var modelData
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.bottomMargin: 6
            color: theme.red
            font.pixelSize: 12
            text: modelData + ": " + backend.searchErrors[modelData]
            wrapMode: Text.WordWrap
        }
    }

    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: backend.searchResults
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            id: row
            required property var modelData
            readonly property var r: modelData
            width: list.width
            height: 66
            color: hover.hovered ? theme.surface : "transparent"
            HoverHandler { id: hover }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.border; opacity: 0.5 }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                spacing: 12
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    RowLayout {
                        spacing: 8
                        Layout.fillWidth: true
                        Label2 { text: row.r.name; font.pixelSize: 14; Layout.maximumWidth: row.width * 0.5 }
                        Label2 { text: row.r.author ? "by " + row.r.author : ""; dim: true; font.pixelSize: 12; Layout.fillWidth: true }
                    }
                    Label2 {
                        Layout.fillWidth: true
                        dim: true
                        font.pixelSize: 11
                        text: [row.r.provider, row.r.version, row.r.downloads ? page.fmt(row.r.downloads) + (row.r.provider === "github" ? " stars" : " downloads") : "",
                               row.r.compatible ? "" : "no build listed for this client"].filter(function (s) { return s }).join(" · ")
                              + (row.r.summary ? "  —  " + row.r.summary : "")
                    }
                }
                Btn {
                    text: "Page"
                    subtle: true
                    visible: !!row.r.url
                    onClicked: backend.openUrl(row.r.url)
                }
                Choice {
                    id: channel
                    model: ["stable", "beta", "alpha"]
                    visible: !row.r.installed
                }
                Btn {
                    Layout.preferredWidth: 100
                    text: row.r.installed ? "Installed" : "Install"
                    primary: !row.r.installed
                    enabled: !row.r.installed && !backend.busy
                    onClicked: backend.install(row.r.provider, row.r.id, channel.currentText)
                }
            }
        }

        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0 && !backend.busy
            dim: true
            horizontalAlignment: Text.AlignHCenter
            text: page.lastQuery ? "Nothing found for \"" + page.lastQuery + "\" on " + (backend.client.label || "this client")
                                 : "Search " + page.usable.map(function (p) { return p.label }).join(", ") + ".\nResults only show addons with a build for " + (backend.client.label || "this client") + "."
        }
    }
}
