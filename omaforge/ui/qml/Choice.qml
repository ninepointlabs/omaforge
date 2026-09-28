import QtQuick
import QtQuick.Controls.Basic

ComboBox {
    id: box
    font.family: theme.font
    font.pixelSize: 12
    implicitWidth: 92
    hoverEnabled: true

    contentItem: Text {
        leftPadding: 8
        text: box.displayText
        font: box.font
        color: theme.foreground
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        x: box.width - width - 8
        y: (box.height - height) / 2
        text: "▾"
        color: theme.dim
        font.pixelSize: 12
    }
    background: Rectangle {
        implicitHeight: 28
        color: box.hovered ? theme.raised : theme.surface
        border.width: 1
        border.color: box.visualFocus || box.popup.visible ? theme.accent : theme.border
    }
    delegate: ItemDelegate {
        required property var modelData
        required property int index
        width: box.width
        highlighted: box.highlightedIndex === index
        contentItem: Text {
            text: modelData
            font: box.font
            color: highlighted ? theme.accentText : theme.foreground
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: highlighted ? theme.accent : theme.surface }
    }
    popup: Popup {
        y: box.height
        width: box.width
        padding: 1
        implicitHeight: contentItem.implicitHeight + 2
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: box.popup.visible ? box.delegateModel : null
            currentIndex: box.highlightedIndex
        }
        background: Rectangle { color: theme.surface; border.color: theme.border }
    }
}
