import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "Format.js" as Fmt

// One addon's description, screenshots and links over the page.
// Esc or a click outside closes it; a screenshot opens full size on top.
Popup {
    id: pop
    property var item: ({})  // the row that was clicked: a remote addon, or an installed one (it has a key)
    property int shot: -1  // index of the screenshot shown full size

    readonly property bool local: item.key !== undefined
    readonly property string provider: item.provider || ""
    readonly property string addonId: (local ? item.source_id : item.id) || ""
    readonly property var d: backend.details
    readonly property var a: d.addon || item
    readonly property var shots: d.screenshots || []
    readonly property var links: {
        var l = Object.assign({}, d.links || {})
        if (!Object.keys(l).length && item.url) l["Website"] = item.url
        return l
    }
    readonly property bool installed: local || backend.addons.some(function (x) {
        return x.key === pop.provider + ":" + pop.addonId || (!!x.links && x.links[pop.provider] === pop.addonId)
    })
    readonly property var facts: {
        var f = []
        if (local) {
            f.push(["Installed", item.version || "?"])
            if (a.version && a.version !== item.version) f.push(["Latest", a.version])
        } else if (a.version) {
            f.push(["Latest", a.version])
        }
        if (a.updated) f.push(["Updated", Fmt.age(a.updated)])
        if (d.created) f.push(["Created", new Date(d.created * 1000).toLocaleDateString(Qt.locale(), Locale.ShortFormat)])
        if (a.categories && a.categories.length) f.push(["Categories", a.categories.join(", ")])
        if (d.game_versions && d.game_versions.length) f.push(["Game versions", d.game_versions.slice(0, 8).join(", ")])
        var folders = local ? item.folders : a.folders
        if (folders && folders.length) f.push([folders.length === 1 ? "Folder" : "Folders", folders.join(", ")])
        f.push(["Source", provider ? provider + (local && item.match && item.match !== "state" ? ", matched by " + item.match : "")
                                   : "unknown: omaforge can't tell where this addon comes from"])
        return f
    }

    function show(addon) {
        item = addon
        shot = -1
        if (provider && addonId) backend.loadDetails(provider, addonId)
        else backend.closeDetails()
        body.contentY = 0
        open()
    }
    onClosed: { shot = -1; backend.closeDetails() }
    onShotChanged: {
        if (shot >= 0 && !viewer.opened) viewer.open()
        if (shot < 0 && viewer.opened) viewer.close()
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(860, parent ? parent.width - 80 : 860)
    height: Math.min(760, parent ? parent.height - 60 : 760)
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.45) }
    background: Rectangle { color: theme.background; border.color: theme.accent; border.width: 1 }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 20
            Layout.bottomMargin: 14
            spacing: 14
            Rectangle {
                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
                Layout.alignment: Qt.AlignTop
                color: theme.raised
                clip: true
                Image {
                    id: icon
                    anchors.fill: parent
                    source: pop.a.icon || ""
                    sourceSize.width: 112
                    sourceSize.height: 112
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                }
                Label2 {
                    anchors.centerIn: parent
                    visible: icon.status !== Image.Ready
                    text: (pop.a.name || "").replace(/[^A-Za-z0-9]/g, "").substring(0, 1).toUpperCase()
                    color: theme.dim
                    font.pixelSize: 22
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Label2 { Layout.fillWidth: true; text: pop.a.name || ""; font.pixelSize: 18; font.bold: true }
                Label2 { Layout.fillWidth: true; dim: true; visible: text !== ""; text: pop.a.author ? "by " + pop.a.author : "" }
                Label2 {
                    Layout.fillWidth: true
                    font.pixelSize: 11
                    opacity: 0.8
                    visible: text !== ""
                    text: Fmt.stats(pop.a)
                }
            }
            Btn {
                Layout.alignment: Qt.AlignTop
                text: "✕"
                subtle: true
                onClicked: pop.close()
                ToolTip.visible: hovered
                ToolTip.delay: 600
                ToolTip.text: "Close (Esc)"
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }

        Flickable {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: content.implicitHeight + 36
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            ColumnLayout {
                id: content
                x: 20
                y: 16
                width: body.width - 40
                spacing: 16

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Repeater {
                        model: pop.facts
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            spacing: 12
                            Label2 { text: modelData[0]; dim: true; font.pixelSize: 12; Layout.preferredWidth: 110; Layout.alignment: Qt.AlignTop }
                            Label2 {
                                text: modelData[1]
                                font.pixelSize: 12
                                Layout.fillWidth: true
                                wrapMode: Text.Wrap
                                elide: Text.ElideNone
                            }
                        }
                    }
                }

                ListView {
                    id: strip
                    Layout.fillWidth: true
                    Layout.preferredHeight: 124
                    visible: count > 0
                    orientation: ListView.Horizontal
                    spacing: 10
                    clip: true
                    model: pop.shots
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.horizontal: ScrollBar { policy: strip.contentWidth > strip.width ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                    delegate: Rectangle {
                        id: thumb
                        required property var modelData
                        required property int index
                        width: 200
                        height: 112
                        color: theme.raised
                        border.width: 1
                        border.color: thumbHover.hovered ? theme.accent : theme.border
                        Image {
                            id: thumbImage
                            anchors.fill: parent
                            anchors.margins: 1
                            source: thumb.modelData.thumbnail || thumb.modelData.url
                            sourceSize.width: 400
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                        }
                        Label2 {
                            anchors.centerIn: parent
                            visible: thumbImage.status !== Image.Ready
                            dim: true
                            font.pixelSize: 11
                            text: thumbImage.status === Image.Error ? "No preview" : "Loading…"
                        }
                        HoverHandler { id: thumbHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: pop.shot = thumb.index }
                        ToolTip.visible: thumbHover.hovered && !!thumb.modelData.title
                        ToolTip.delay: 500
                        ToolTip.text: thumb.modelData.title || ""
                    }
                }

                Label2 {
                    Layout.fillWidth: true
                    visible: text !== ""
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    color: pop.d.error ? theme.red : theme.dim
                    text: pop.d.error ? "Couldn't load the details: " + pop.d.error
                          : backend.detailsLoading ? "Loading description…"
                          : pop.d.addon && !pop.d.description ? "The author didn't write a description."
                          : !pop.provider ? "Only what the addon's TOC file says is known. Search for it to link it to a source."
                          : ""
                }

                Text {
                    id: description
                    Layout.fillWidth: true
                    visible: text !== ""
                    // Rich text ignores linkColor; the backend hands over the safe HTML subset only.
                    text: pop.d.description ? "<style>a { color: " + theme.accent + "; }</style>" + pop.d.description : ""
                    textFormat: Text.RichText
                    wrapMode: Text.Wrap
                    color: theme.foreground
                    font.family: theme.font
                    font.pixelSize: 13
                    lineHeight: 1.15
                    onLinkActivated: function (link) { backend.openUrl(link) }
                    HoverHandler { cursorShape: description.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                }
            }
        }

        Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: 14
            Layout.leftMargin: 20
            Layout.rightMargin: 20
            spacing: 8
            Repeater {
                model: Object.keys(pop.links)
                delegate: Btn {
                    required property string modelData
                    text: modelData
                    subtle: true
                    onClicked: backend.openUrl(pop.links[modelData])
                    ToolTip.visible: hovered
                    ToolTip.delay: 600
                    ToolTip.text: pop.links[modelData]
                }
            }
            Item { Layout.fillWidth: true }
            Label2 { dim: true; font.pixelSize: 11; text: "Esc to close" }
            Choice { id: channel; model: ["stable", "beta", "alpha"]; visible: !pop.local && !pop.installed }
            Btn {
                visible: !pop.local
                Layout.preferredWidth: 100
                text: pop.installed ? "Installed" : "Install"
                primary: !pop.installed
                enabled: !pop.installed && !backend.busy && pop.addonId !== ""
                onClicked: backend.install(pop.provider, pop.addonId, channel.currentText)
            }
        }
    }

    // A screenshot at full size. Esc or a click closes it and leaves the details open.
    Popup {
        id: viewer
        parent: Overlay.overlay
        x: 0
        y: 0
        width: parent ? parent.width : 0
        height: parent ? parent.height : 0
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Item {}
        background: Rectangle { color: Qt.rgba(0, 0, 0, 0.88) }
        onClosed: pop.shot = -1

        readonly property var current: pop.shot >= 0 && pop.shot < pop.shots.length ? pop.shots[pop.shot] : null
        function step(by) {
            if (pop.shots.length) pop.shot = (pop.shot + by + pop.shots.length) % pop.shots.length
        }

        contentItem: Item {
            focus: true
            Keys.onLeftPressed: viewer.step(-1)
            Keys.onRightPressed: viewer.step(1)

            TapHandler { onTapped: viewer.close() }
            Image {
                id: full
                anchors.fill: parent
                anchors.margins: 48
                source: viewer.current ? viewer.current.url : ""
                fillMode: Image.PreserveAspectFit
                asynchronous: true
            }
            Text {
                anchors.centerIn: parent
                visible: full.status !== Image.Ready
                color: "white"
                font.family: theme.font
                text: full.status === Image.Error ? "Couldn't load this screenshot" : "Loading…"
            }
            Text {
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottomMargin: 16
                color: "white"
                opacity: 0.8
                font.family: theme.font
                font.pixelSize: 12
                text: (viewer.current && viewer.current.title ? viewer.current.title + "  ·  " : "")
                      + (pop.shot + 1) + " / " + pop.shots.length
                      + (pop.shots.length > 1 ? "  ·  ← → to browse" : "") + "  ·  Esc to close"
            }
        }
    }
}
