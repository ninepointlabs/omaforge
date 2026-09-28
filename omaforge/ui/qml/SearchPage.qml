import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Format.js" as Fmt

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
        Choice {
            id: sortBox
            implicitWidth: 170
            model: Object.keys(Fmt.sorters)
            ToolTip.visible: hovered
            ToolTip.delay: 600
            ToolTip.text: "Sort results"
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
        model: {
            var results = backend.searchResults.slice()
            var by = Fmt.sorters[sortBox.currentText]
            return by ? results.sort(by) : results
        }
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: AddonRow { width: list.width }

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
