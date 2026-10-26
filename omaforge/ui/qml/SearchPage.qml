import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Format.js" as Fmt

ColumnLayout {
    id: page
    spacing: 0
    signal showDetails(var addon)
    property var disabledProviders: ({})
    property string lastQuery: ""
    // The width the window has for this page. The narrow layouts follow this, not the page's
    // own width, which can't shrink below what the wide layout needs.
    property real room: width

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

    // One line when wide; when narrow the source toggles and the sort go on a second line.
    GridLayout {
        id: bar
        readonly property bool roomy: page.room - 32 >= 160 + sources.implicitWidth + 170 + searchBtn.implicitWidth + 3 * columnSpacing
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        columns: roomy ? 4 : 2
        columnSpacing: 8
        rowSpacing: 8
        Field {
            id: query
            objectName: "searchQuery"
            Layout.row: 0
            Layout.column: 0
            Layout.fillWidth: true
            Layout.minimumWidth: 120
            placeholderText: "Search addons for " + (backend.client.label || "this client") + ", or paste a GitHub repo"
            onAccepted: page.run()
        }
        RowLayout {
            id: sources
            Layout.row: bar.roomy ? 0 : 1
            Layout.column: bar.roomy ? 1 : 0
            spacing: 8
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
        }
        Choice {
            id: sortBox
            objectName: "searchSort"
            Layout.row: bar.roomy ? 0 : 1
            Layout.column: bar.roomy ? 2 : 1
            Layout.fillWidth: !bar.roomy
            implicitWidth: 170
            model: Object.keys(Fmt.sorters)
            ToolTip.visible: hovered
            ToolTip.delay: 600
            ToolTip.text: "Sort results"
        }
        Btn {
            id: searchBtn
            Layout.row: 0
            Layout.column: bar.roomy ? 3 : 1
            Layout.fillWidth: !bar.roomy
            text: "Search"
            primary: true
            enabled: !backend.busy && query.text.trim() !== ""
            onClicked: page.run()
        }
    }

    Label2 {
        Layout.fillWidth: true
        Layout.leftMargin: 16
        Layout.bottomMargin: 8
        visible: page.unusable.length > 0
        dim: true
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
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
        model: {
            var results = backend.searchResults.slice()
            var by = Fmt.sorters[sortBox.currentText]
            return by ? results.sort(by) : results
        }
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: AddonRow { width: list.width; room: page.room; onDetailsRequested: page.showDetails(r) }

        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0 && !backend.busy
            dim: true
            horizontalAlignment: Text.AlignHCenter
            text: page.lastQuery ? "Nothing found for \"" + page.lastQuery + "\" on " + (backend.client.label || "this client")
                                 : "Search " + page.usable.map(function (p) { return p.label }).join(", ") + ".\nResults only show addons with a build for " + (backend.client.label || "this client") + ".\nFor the most popular addons, see Explore."
        }
    }
}
