import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: activityPage

    property color panel: "#0F1316"
    property color accent: "#8AB4C8"
    property color appBg: "#0A080F"
    property color textPri: "#e2e2e8"
    property color textSec: "#849495"
    property color textTer: "#5a6a6e"
    property color brd: Qt.rgba(1, 1, 1, 0.07)
    property color seeColor: "#38BDF8"
    property color planColor: "#A78BFA"
    property color actColor: "#34D399"
    property int radMd: 14

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        Text {
            text: "ACTIVITY LOG"
            font.family: "Manrope"
            font.pixelSize: 11
            font.bold: true
            color: accent
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: radMd
            color: panel
            border.width: 1
            border.color: brd

            ListView {
                id: historyList
                anchors.fill: parent
                anchors.margins: 16
                clip: true
                model: historyModel
                spacing: 8

                delegate: Rectangle {
                    width: historyList.width
                    height: 48
                    radius: 9
                    color: Qt.rgba(1, 1, 1, 0.02)
                    border.width: 1
                    border.color: brd

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 12

                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: model.status === "completed" ? actColor :
                                   model.status === "error" ? "#ff3b3b" : textTer
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                text: model.goal
                                font.family: "Manrope"
                                font.pixelSize: 12
                                color: textPri
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }

                            Text {
                                text: model.steps + " steps \u00b7 " + model.duration + " \u00b7 " + model.timestamp
                                font.family: "JetBrains Mono"
                                font.pixelSize: 10
                                color: textTer
                            }
                        }
                    }
                }
            }

            ListModel {
                id: historyModel
                ListElement { goal: "Open Notepad and type Hello World"; status: "completed"; steps: 4; duration: "12s"; timestamp: "14:32" }
                ListElement { goal: "Check system info and list processes"; status: "completed"; steps: 3; duration: "8s"; timestamp: "14:28" }
                ListElement { goal: "Navigate to github.com"; status: "error"; steps: 7; duration: "23s"; timestamp: "14:15" }
            }
        }
    }
}
