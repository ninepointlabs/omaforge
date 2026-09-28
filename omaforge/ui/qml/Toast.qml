import QtQuick

Rectangle {
    id: t
    property string kind: "info"
    property string message: ""

    function show(kind, message) {
        t.kind = kind
        t.message = message
        t.visible = true
        hide.interval = kind === "error" ? 12000 : 5000
        hide.restart()
    }

    visible: false
    width: Math.min(560, parent.width - 40)
    height: text.implicitHeight + 24
    color: theme.surface
    border.width: 1
    border.color: kind === "error" ? theme.red : theme.accent

    Rectangle {
        width: 3
        height: parent.height
        color: t.kind === "error" ? theme.red : theme.accent
    }
    Label2 {
        id: text
        anchors.fill: parent
        anchors.margins: 12
        anchors.leftMargin: 16
        text: t.message
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        maximumLineCount: 6
    }
    MouseArea { anchors.fill: parent; onClicked: t.visible = false }
    Timer { id: hide; onTriggered: t.visible = false }
}
