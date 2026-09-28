import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: f
    font.family: theme.font
    font.pixelSize: 13
    color: theme.foreground
    placeholderTextColor: theme.dim
    selectionColor: theme.accent
    selectedTextColor: theme.accentText
    leftPadding: 10
    rightPadding: 10
    background: Rectangle {
        implicitHeight: 30
        implicitWidth: 200
        color: theme.surface
        border.width: 1
        border.color: f.activeFocus ? theme.accent : theme.border
    }
}
