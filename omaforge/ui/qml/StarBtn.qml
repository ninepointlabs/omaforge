import QtQuick
import QtQuick.Controls.Basic

// Stars or unstars an addon: a remote one, or an installed one with a known source.
// Also lit when a source the addon's TOC links to has the star.
Btn {
    id: star
    property var addon: ({})
    signal toggling()  // just before the star changes
    readonly property bool starred: {
        var links = addon.links || {}
        return [addon.provider + ":" + (addon.id || addon.source_id)]
            .concat(Object.keys(links).map(function (p) { return p + ":" + links[p] }))
            .some(function (k) { return !!backend.starredKeys[k] })
    }

    objectName: "star"
    text: starred ? "★" : "☆"
    subtle: true
    active: starred
    font.pixelSize: 19  // these glyphs are small for their size
    leftPadding: 0
    rightPadding: 0
    implicitWidth: 30
    Accessible.name: starred ? "Remove star" : "Star this addon"
    onClicked: {
        toggling()
        backend.setStarred(addon, !starred)
    }
    ToolTip.visible: hovered
    ToolTip.delay: 600
    ToolTip.text: starred ? "Remove star" : "Star this addon, to find it later under Starred"
}
