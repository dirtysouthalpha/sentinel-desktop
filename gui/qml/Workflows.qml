import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: workflowsPage

    property color panel: "#0F1316"
    property color accent: "#8AB4C8"
    property color appBg: "#0A080F"
    property color textPri: "#e2e2e8"
    property color textSec: "#849495"
    property color textTer: "#5a6a6e"
    property color brd: Qt.rgba(1, 1, 1, 0.07)
    property color actColor: "#34D399"
    property int radMd: 14

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        Text {
            text: "WORKFLOWS"
            font.family: "Manrope"
            font.pixelSize: 11
            font.bold: true
            color: accent
        }

        GridView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            cellWidth: 260
            cellHeight: 140
            model: workflowModel

            delegate: Rectangle {
                width: 240
                height: 120
                radius: 14
                color: wfMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.04) : panel
                border.width: 1
                border.color: wfMouse.containsMouse ? accent : brd

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8

                    Text {
                        text: model.icon
                        font.pixelSize: 20
                    }

                    Text {
                        text: model.name
                        font.family: "Manrope"
                        font.pixelSize: 13
                        font.bold: true
                        color: textPri
                    }

                    Text {
                        text: model.description
                        font.family: "Manrope"
                        font.pixelSize: 10
                        color: textTer
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    }
                }

                MouseArea {
                    id: wfMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: {
                        goalInput.text = model.goal
                        contentStack.currentIndex = 0
                    }
                }
            }

            ListModel {
                id: workflowModel
                ListElement { icon: "\U0001f5a5"; name: "System Info"; description: "Get system details and running processes"; goal: "Get system info and list running processes" }
                ListElement { icon: "\U0001f310"; name: "Web Browse"; description: "Open a URL and take a screenshot"; goal: "Open a web browser and navigate to the specified URL" }
                ListElement { icon: "\U0001f4dd"; name: "Notepad"; description: "Open Notepad and type text"; goal: "Open Notepad and type the specified text" }
                ListElement { icon: "\U0001f50c"; name: "Network"; description: "Run network diagnostics"; goal: "Run network diagnostics: ping, DNS lookup, and port scan" }
                ListElement { icon: "\U0001f4bb"; name: "Terminal"; description: "Open terminal and run a command"; goal: "Open a terminal and execute a command" }
                ListElement { icon: "\U0001f50d"; name: "OCR Read"; description: "Take screenshot and read text"; goal: "Take a screenshot and read all visible text on screen" }
            }
        }
    }
}
