import QtQuick
import QtQuick.Controls.Basic

Button {
    id: b
    property bool primary: false
    property bool danger: false
    property bool subtle: false
    property bool active: false

    hoverEnabled: true
    font.family: theme.font
    font.pixelSize: 13
    topPadding: 6
    bottomPadding: 6
    leftPadding: 12
    rightPadding: 12
    focusPolicy: Qt.TabFocus

    contentItem: Text {
        text: b.text
        font: b.font
        color: b.primary ? theme.accentText : b.danger ? theme.red : b.active ? theme.accent : theme.foreground
        opacity: b.enabled ? 1 : 0.4
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        implicitHeight: 30
        implicitWidth: 30
        color: b.primary ? (b.down ? Qt.darker(theme.accent, 1.2) : b.hovered ? Qt.lighter(theme.accent, 1.12) : theme.accent)
             : b.down ? theme.border : (b.hovered && b.enabled) ? theme.raised : b.subtle ? "transparent" : theme.surface
        border.width: b.primary || (b.subtle && !b.visualFocus) ? 0 : 1
        border.color: b.visualFocus ? theme.accent : b.active ? theme.accent : theme.border
        opacity: b.enabled || !b.primary ? 1 : 0.5
    }
}
