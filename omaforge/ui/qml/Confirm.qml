import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Dialog {
    id: d
    property string message: ""
    property string confirmText: "OK"
    property bool dangerous: false
    property var action: null

    function ask(title, message, confirmText, dangerous, action) {
        d.title = title
        d.message = message
        d.confirmText = confirmText
        d.dangerous = dangerous
        d.action = action
        d.open()
    }

    modal: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(460, parent ? parent.width - 40 : 460)
    padding: 20
    background: Rectangle { color: theme.background; border.color: theme.accent; border.width: 1 }
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.45) }
    header: Label2 {
        text: d.title
        font.pixelSize: 15
        font.bold: true
        leftPadding: 20
        topPadding: 18
    }
    contentItem: Label2 {
        text: d.message
        wrapMode: Text.WordWrap
        elide: Text.ElideNone
        dim: true
    }
    footer: RowLayout {
        spacing: 8
        Item { Layout.fillWidth: true }
        Btn { text: "Cancel"; onClicked: d.reject() }
        Btn {
            text: d.confirmText
            primary: !d.dangerous
            danger: d.dangerous
            onClicked: { d.accept(); if (d.action) d.action() }
        }
        Item { width: 12 }
        Layout.bottomMargin: 16
    }
}
