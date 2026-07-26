import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: dashboard

    readonly property color appBg: "#0A080F"
    readonly property color panel: "#0F1316"
    readonly property color accent: "#8AB4C8"
    readonly property color seeColor: "#38BDF8"
    readonly property color planColor: "#A78BFA"
    readonly property color actColor: "#34D399"
    readonly property color textPri: "#e2e2e8"
    readonly property color textSec: "#849495"
    readonly property color textTer: "#5a6a6e"
    readonly property color brd: Qt.rgba(1, 1, 1, 0.07)
    readonly property color errColor: "#ff3b3b"

    // ── Goal Hero ──────────────────────────────────────────────
    Rectangle {
        id: goalHero
        x: 24; y: 24
        width: parent.width - 48
        height: 160
        radius: 14; color: panel; border.width: 1; border.color: brd

        ColumnLayout {
            anchors.fill: parent; anchors.margins: 24; spacing: 12

            RowLayout {
                spacing: 12
                Text { text: "GOAL"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: accent }
                Rectangle {
                    visible: controller.state === "running"
                    width: rp.implicitWidth + 14; height: 22; radius: 11; color: actColor
                    Text { id: rp; anchors.centerIn: parent; text: "RUNNING"; font.family: "JetBrains Mono"; font.pixelSize: 9; font.bold: true; color: appBg }
                }
                Item { Layout.fillWidth: true }
                Rectangle {
                    width: 80; height: 32; radius: 9
                    color: rma.pressed ? Qt.lighter(actColor, 1.2) : rma.containsMouse ? Qt.lighter(actColor, 1.1) : actColor
                    Text { anchors.centerIn: parent; text: "\u25b6 Run"; font.family: "Manrope"; font.pixelSize: 12; font.bold: true; color: appBg }
                    MouseArea { id: rma; anchors.fill: parent; hoverEnabled: true; onClicked: { var g = goalText.text.trim(); if (g.length > 0) controller.run_goal(g) } }
                }
                Rectangle {
                    width: 80; height: 32; radius: 9
                    color: sma.pressed ? Qt.lighter(errColor, 1.2) : sma.containsMouse ? Qt.lighter(errColor, 1.1) : errColor
                    Text { anchors.centerIn: parent; text: "\u25a0 Stop"; font.family: "Manrope"; font.pixelSize: 12; font.bold: true; color: "#fff" }
                    MouseArea { id: sma; anchors.fill: parent; hoverEnabled: true; onClicked: controller.stop_goal() }
                }
            }

            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true; radius: 9; color: appBg
                border.width: 1; border.color: goalText.activeFocus ? accent : brd
                ScrollView { anchors.fill: parent; anchors.margins: 10; clip: true
                    TextArea {
                        id: goalText
                        placeholderText: "Describe what you want done\u2026   (Ctrl+Enter to run)"
                        font.family: "Manrope"; font.pixelSize: 14
                        color: textPri; placeholderTextColor: textTer
                        wrapMode: TextArea.Wrap; background: null; selectByMouse: true
                        Keys.onReturnPressed: {
                            if (event.modifiers & Qt.ControlModifier) {
                                var g = text.trim(); if (g.length > 0) controller.run_goal(g)
                            } else { insert(cursorPosition, "\n") }
                        }
                    }
                }
            }
        }
    }

    // ── Activity Panel (left 66%) ──────────────────────────────
    Rectangle {
        id: activityPanel
        x: 24; y: goalHero.y + goalHero.height + 20
        width: Math.floor((parent.width - 68) * 0.65)
        height: parent.height - y - 24
        radius: 14; color: panel; border.width: 1; border.color: brd
        clip: true

        ColumnLayout {
            x: 16; y: 16
            width: parent.width - 32; height: parent.height - 32
            spacing: 8

            Text { text: "ACTIVITY"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: accent }

            Row {
                spacing: 3; Layout.topMargin: 4
                Repeater {
                    model: Math.min(controller.max_steps, 60)
                    Rectangle {
                        width: 6; height: 18; radius: 3
                        color: index < controller.step ? dashboard.seeColor :
                               index === controller.step ? dashboard.accent :
                               Qt.rgba(1, 1, 1, 0.07)
                        opacity: index <= controller.step ? 1.0 : 0.4
                    }
                }
            }

            Rectangle {
                x: 0; y: 40; width: parent.width; height: parent.height - 40
                radius: 9; color: appBg
                border.width: 1; border.color: brd
                clip: true
                ListView {
                    x: 8; y: 8; width: parent.width - 16; height: parent.height - 16
                    model: logModel; spacing: 4
                    onCountChanged: positionViewAtEnd()
                    delegate: Rectangle {
                        width: logView.width; height: logText.implicitHeight + 12; radius: 6; color: "transparent"
                        Rectangle {
                            width: 4; height: 4; radius: 2
                            anchors.left: parent.left; anchors.leftMargin: 8; anchors.verticalCenter: parent.verticalCenter
                            color: model.kind === "see" ? dashboard.seeColor :
                                   model.kind === "plan" ? dashboard.planColor :
                                   model.kind === "act" ? dashboard.actColor :
                                   model.kind === "error" ? dashboard.errColor : dashboard.textTer
                        }
                        Text {
                            id: logText
                            anchors.left: parent.left; anchors.right: parent.right; anchors.margins: 20
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.message; font.family: "JetBrains Mono"; font.pixelSize: 11
                            color: model.kind === "error" ? dashboard.errColor :
                                   model.kind === "user" ? dashboard.accent :
                                   model.kind === "assistant" ? dashboard.actColor : dashboard.textSec
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }

            ListModel { id: logModel }
        }
    }

    // ── Live View + System (right column) ──────────────────────
    Column {
        id: rightCol
        x: activityPanel.x + activityPanel.width + 20
        y: activityPanel.y
        width: parent.width - x - 24
        height: activityPanel.height
        spacing: 16

        Text { text: "LIVE VIEW"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: accent }

        Rectangle {
            width: parent.width; height: 200; radius: 9; color: appBg
            border.width: 2; border.color: brd
            Image {
                id: liveImage
                x: 4; y: 4; width: parent.width - 8; height: parent.height - 8
                fillMode: Image.PreserveAspectFit
                visible: status === Image.Ready
            }
            Text {
                anchors.centerIn: parent; text: "No screenshot"
                font.family: "Manrope"; font.pixelSize: 10; color: textTer
                visible: liveImage.status !== Image.Ready
            }
        }

        Rectangle {
            width: parent.width; height: 90; radius: 14; color: panel
            border.width: 1; border.color: brd
            clip: true

            ColumnLayout {
                x: 12; y: 12
                width: parent.width - 24; height: parent.height - 24
                spacing: 6
                Text { text: "SYSTEM"; font.family: "Manrope"; font.pixelSize: 10; font.bold: true; color: accent }
                Repeater {
                    model: ["CPU", "RAM", "Disk"]
                    RowLayout {
                        spacing: 8
                        Text { text: modelData + ":"; font.family: "JetBrains Mono"; font.pixelSize: 10; color: textTer; Layout.preferredWidth: 36 }
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.07)
                            Rectangle { width: parent.width * 0.3; height: parent.height; radius: 3; color: accent }
                        }
                    }
                }
            }
        }
    }

    function addLogEntry(kind, message) {
        logModel.append({"kind": kind, "message": message})
        if (logModel.count > 200) logModel.remove(0)
    }

    function setScreenshot(imgSource) {
        liveImage.source = imgSource
    }
}
