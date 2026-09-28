import QtQuick
import QtQuick.Controls.Basic

CheckBox {
    id: c
    font.family: theme.font
    font.pixelSize: 13
    spacing: 8
    indicator: Rectangle {
        implicitWidth: 16
        implicitHeight: 16
        x: c.leftPadding
        y: (c.height - height) / 2
        color: c.checked ? theme.accent : theme.surface
        border.width: 1
        border.color: c.checked || c.visualFocus ? theme.accent : theme.border
        Text {
            anchors.centerIn: parent
            text: "✓"
            visible: c.checked
            color: theme.accentText
            font.pixelSize: 12
            font.bold: true
        }
    }
    contentItem: Text {
        text: c.text
        font: c.font
        color: theme.foreground
        leftPadding: c.indicator.width + c.spacing
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }
}
