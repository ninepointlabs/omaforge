import QtQuick
import QtQuick.Controls.Basic

// "⋯": the actions that don't fit when the window is narrow, as a menu.
Btn {
    id: b
    default property alias items: menu.contentData
    text: "⋯"
    subtle: true
    leftPadding: 10
    rightPadding: 10
    onClicked: menu.popup(b, b.width - menu.width, b.height)
    ToolTip.visible: hovered && !menu.visible
    ToolTip.delay: 600
    ToolTip.text: "More actions"

    Menu {
        id: menu
        font.family: theme.font
        font.pixelSize: 13
        background: Rectangle {
            implicitWidth: 180
            color: theme.surface
            border.color: theme.border
        }
    }
}
