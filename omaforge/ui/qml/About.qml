import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Who made omaforge, its license, support and what it does with your data.
Popup {
    id: about
    property bool showLicense: false
    onOpened: showLicense = false

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(560, parent ? parent.width - 40 : 560)
    modal: true
    focus: true
    padding: 22
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    Overlay.modal: Rectangle { color: Qt.rgba(0, 0, 0, 0.45) }
    background: Rectangle { color: theme.background; border.color: theme.accent; border.width: 1 }

    contentItem: ColumnLayout {
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            Image {
                source: Qt.resolvedUrl("../icons/omaforge.svg")
                sourceSize.width: 56
                sourceSize.height: 56
                Layout.preferredWidth: 56
                Layout.preferredHeight: 56
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                Label2 { text: appInfo.name; font.pixelSize: 20; font.bold: true; color: theme.accent }
                Label2 { Layout.fillWidth: true; text: appInfo.tagline; wrapMode: Text.WordWrap; elide: Text.ElideNone }
                Label2 { text: "Version " + appInfo.version; dim: true; font.pixelSize: 11 }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 16
            rowSpacing: 8

            Label2 { text: "Made by"; dim: true; font.pixelSize: 11 }
            Label2 { text: appInfo.organization }

            Label2 { text: "Created"; dim: true; font.pixelSize: 11 }
            Label2 { text: appInfo.created }

            Label2 { text: "License"; dim: true; font.pixelSize: 11 }
            RowLayout {
                spacing: 8
                Label2 { text: appInfo.license + ", " + appInfo.copyright }
                Btn {
                    objectName: "aboutLicense"
                    text: about.showLicense ? "Hide" : "Read it"
                    subtle: true
                    onClicked: about.showLicense = !about.showLicense
                }
            }

            Label2 { text: "Support"; dim: true; font.pixelSize: 11 }
            RowLayout {
                spacing: 8
                Label2 { text: appInfo.supportEmail }
                Btn {
                    text: "Email"
                    subtle: true
                    onClicked: Qt.openUrlExternally("mailto:" + appInfo.supportEmail + "?subject="
                        + encodeURIComponent("omaforge " + appInfo.version) + "&body="
                        + encodeURIComponent("\n\n--\n" + appInfo.details))
                }
                Btn { text: "Copy"; subtle: true; onClicked: appInfo.copy(appInfo.supportEmail) }
            }

            Label2 { text: "Privacy"; dim: true; font.pixelSize: 11; Layout.alignment: Qt.AlignTop }
            Label2 {
                objectName: "aboutPrivacy"
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                text: "No accounts and no telemetry. omaforge connects only to the addon sources, CurseForge, "
                      + "WoWInterface and GitHub, to search, check for updates and download addons, and loads "
                      + "icons and screenshots from the addresses they list. To recognise installed addons it sends "
                      + "CurseForge fingerprints (hashes) of your addon folders. API keys and tokens stay in "
                      + "~/.config/omaforge/config.toml, readable only by you, and go only to the service they "
                      + "are for. Settings, install records, WTF backups and the cache stay on this computer."
            }

            Label2 { text: "Built with"; dim: true; font.pixelSize: 11 }
            Label2 {
                Layout.fillWidth: true
                dim: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
                text: "Qt " + appInfo.qtVersion + ", PySide6 " + appInfo.pysideVersion + ", Python " + appInfo.pythonVersion
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 180
            visible: about.showLicense
            color: theme.surface
            border.width: 1
            border.color: theme.border
            Flickable {
                id: licenseView
                anchors.fill: parent
                anchors.margins: 12
                clip: true
                contentHeight: licenseText.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                Label2 {
                    id: licenseText
                    objectName: "aboutLicenseText"
                    width: licenseView.width - 10
                    text: appInfo.licenseText
                    dim: true
                    font.pixelSize: 11
                    wrapMode: Text.WordWrap
                    elide: Text.ElideNone
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 8
            Item { Layout.fillWidth: true }
            Btn { text: "Copy version details"; subtle: true; onClicked: appInfo.copy(appInfo.details) }
            Btn { text: "Close"; primary: true; onClicked: about.close() }
        }
    }
}
