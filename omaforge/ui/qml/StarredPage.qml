import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// The addons you starred, installed or not. Stars are shared by all game versions;
// Install puts an addon into the selected one.
ColumnLayout {
    id: page
    spacing: 0
    signal showDetails(var addon)
    property string filter: ""
    property bool notInstalledOnly: false
    // The width the window has for this page. The narrow layouts follow this, not the page's
    // own width, which can't shrink below what the wide layout needs.
    property real room: width

    readonly property var shown: {
        var q = filter.toLowerCase()
        var list = backend.starred.filter(function (a) {
            return (!notInstalledOnly || !a.installed)
                && (!q || a.name.toLowerCase().indexOf(q) >= 0 || a.author.toLowerCase().indexOf(q) >= 0
                    || a.provider.indexOf(q) >= 0)
        })
        if (sortBox.currentIndex === 1)
            list.sort(function (a, b) { return a.name.toLowerCase() < b.name.toLowerCase() ? -1 : 1 })
        return list
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.margins: 16
        Layout.bottomMargin: 8
        spacing: 8
        Field {
            objectName: "starredFilter"
            Layout.fillWidth: true
            Layout.minimumWidth: 60
            placeholderText: page.room < 700 ? "Filter" : "Filter starred addons"
            onTextChanged: page.filter = text
            Keys.onEscapePressed: text = ""
        }
        Btn {
            objectName: "starredNotInstalled"
            text: "Not installed"
            subtle: true
            active: page.notInstalledOnly
            onClicked: page.notInstalledOnly = !page.notInstalledOnly
            ToolTip.visible: hovered
            ToolTip.delay: 600
            ToolTip.text: page.notInstalledOnly ? "Show installed addons too"
                                                : "Hide what's installed in " + (backend.client.label || "this client")
        }
        Choice {
            id: sortBox
            objectName: "starredSort"
            implicitWidth: 170
            model: ["Recently starred", "Name"]
            ToolTip.visible: hovered
            ToolTip.delay: 600
            ToolTip.text: "Sort starred addons"
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
        text: "Stars are shared by all your game versions. Install adds to " + (backend.client.label || "the selected one") + "."
    }
    Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

    ListView {
        id: list
        objectName: "starredList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: page.shown
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}
        // Taking a star off rebuilds this list; stay where you were in it.
        property real keepY: -1
        onModelChanged: {
            if (keepY < 0) return
            var y = keepY
            keepY = -1
            Qt.callLater(function () { list.contentY = Math.max(0, Math.min(y, list.contentHeight - list.height)) })
        }
        delegate: AddonRow {
            width: list.width
            room: page.room
            onDetailsRequested: page.showDetails(r)
            onStarToggling: list.keepY = list.contentY
        }

        Label2 {
            anchors.centerIn: parent
            visible: list.count === 0
            dim: true
            horizontalAlignment: Text.AlignHCenter
            text: backend.starred.length === 0
                  ? "Nothing starred yet.\nClick the ☆ on an addon in Explore, Search or Installed to find it here later."
                  : page.filter ? "No starred addons match \"" + page.filter + "\""
                  : "Everything you starred is installed in " + (backend.client.label || "this client") + "."
        }
    }
}
