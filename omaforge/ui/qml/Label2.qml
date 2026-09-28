import QtQuick

// Text in the theme font; `dim` for secondary text.
Text {
    property bool dim: false
    font.family: theme.font
    font.pixelSize: 13
    color: dim ? theme.dim : theme.foreground
    elide: Text.ElideRight
    textFormat: Text.PlainText
}
