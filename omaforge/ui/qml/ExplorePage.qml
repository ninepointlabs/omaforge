import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The top addons for the selected game, ranked by one source.
ColumnLayout {
    id: page
    spacing: 0

    readonly property var sortNames: ({
        "popular": "Most popular", "downloads": "Most downloaded", "updated": "Recently updated",
        "favorites": "Most favorited", "name": "Name"
    })
    readonly property var source: backend.exploreSources.find(function (s) { return s.name === backend.exploreProvider }) || {}
    readonly property var sorts: source.sorts || []

    function reload() {
        backend.loadExplore(backend.exploreProvider, backend.exploreSort, backend.exploreCategory)
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        spacing: 8

        Repeater {
            model: backend.exploreSources
            delegate: Btn {
                required property var modelData
                text: modelData.label
                subtle: true
                active: backend.exploreProvider === modelData.name
                onClicked: backend.loadExplore(modelData.name, backend.exploreSort, "")
            }
        }
        Item { Layout.fillWidth: true }
        Choice {
            id: category
            implicitWidth: 190
            visible: backend.exploreCategories.length > 0
            model: ["All categories"].concat(backend.exploreCategories.map(function (c) { return c.name }))
            currentIndex: {
                var i = backend.exploreCategories.findIndex(function (c) { return c.id === backend.exploreCategory })
                return i + 1
            }
            onActivated: function (i) {
                backend.loadExplore(backend.exploreProvider, backend.exploreSort, i === 0 ? "" : backend.exploreCategories[i - 1].id)
            }
        }
        Choice {
            implicitWidth: 170
            model: page.sorts.map(function (s) { return page.sortNames[s] })
            currentIndex: Math.max(0, page.sorts.indexOf(backend.exploreSort))
            onActivated: function (i) { backend.loadExplore(backend.exploreProvider, page.sorts[i], backend.exploreCategory) }
        }
    }
    Label2 {
        Layout.fillWidth: true
        Layout.leftMargin: 16
        Layout.bottomMargin: 8
        dim: true
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        text: backend.exploreProvider === "curseforge"
              ? "CurseForge ranks addons with a " + (backend.client.label || "") + " build. Most popular is CurseForge's own ranking; there are no public ratings."
              : backend.exploreProvider === "wowinterface"
                ? "WoWInterface addons whose author lists " + (backend.client.label || "this game") + " as supported. Most popular is downloads this month."
                  + (backend.client.game === "forever" ? " WoWInterface does not tell Forever and Classic Era apart." : "")
                : ""
    }
    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

    ListView {
        id: list
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: backend.exploreResults
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        delegate: AddonRow {
            required property int index
            width: list.width
            number: index + 1
        }
        footer: Item {
            width: list.width
            height: backend.exploreHasMore && list.count > 0 ? 64 : 0
            visible: height > 0
            Btn {
                anchors.centerIn: parent
                text: "Load more"
                enabled: !backend.busy
                onClicked: backend.exploreMore()
            }
        }
        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0 && !backend.busy
            dim: true
            horizontalAlignment: Text.AlignHCenter
            text: backend.exploreSources.length === 0
                  ? "No source with rankings is available.\nAdd a CurseForge API key under Settings, or enable WoWInterface."
                  : "Nothing to show."
        }
    }
}
