import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

ApplicationWindow {
    id: root
    visible: true
    width: 1280
    height: 820
    minimumWidth: 960
    minimumHeight: 640
    title: "SENTINEL DESKTOP"
    color: "#0A080F"
    flags: Qt.Window

    property color steelAccent: "#8AB4C8"
    property color steelPanel: "#0F1316"
    property color steelAppBg: "#0A080F"
    property color steelSee: "#38BDF8"
    property color steelPlan: "#A78BFA"
    property color steelAct: "#34D399"
    property color steelTextPri: "#e2e2e8"
    property color steelTextSec: "#849495"
    property color steelTextTer: "#5a6a6e"
    property color steelBrd: Qt.rgba(1, 1, 1, 0.07)
    property color steelErr: "#ff3b3b"
    property bool paletteVisible: false

    Connections {
        target: controller
        function onLogEntry(kind, message) {
            dashboard.addLogEntry(kind, message)
        }
        function onScreenshotReady(img) {
            dashboard.setScreenshot("image://imageProvider/" + Date.now())
        }
        function onStateChanged(state) {
            stateIndicator.text = state.toUpperCase()
        }
        function onStepChanged(step, max) {
            stepLabel.text = step + "/" + max
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillHeight: true
            Layout.preferredWidth: 62
            color: steelPanel

            ColumnLayout {
                anchors.fill: parent
                anchors.topMargin: 12
                anchors.bottomMargin: 12
                spacing: 4

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    radius: 8
                    color: steelAccent
                    Text {
                        anchors.centerIn: parent
                        text: "S"
                        font.family: "Archivo"
                        font.pixelSize: 18
                        font.bold: true
                        color: steelAppBg
                    }
                }

                Item { Layout.preferredHeight: 12 }

                Repeater {
                    model: ListModel {
                        ListElement { icon: "\u2302"; label: "Dashboard"; idx: 0 }
                        ListElement { icon: "\u2606"; label: "Workflows"; idx: 1 }
                        ListElement { icon: "\u2261"; label: "Activity"; idx: 2 }
                        ListElement { icon: "\u2699"; label: "Settings"; idx: 3 }
                    }

                    delegate: Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 42
                        Layout.preferredHeight: 42
                        radius: 9
                        color: navMa.containsMouse ? Qt.rgba(1, 1, 1, 0.05) : "transparent"

                        Column {
                            anchors.centerIn: parent
                            spacing: 2
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: model.icon
                                font.pixelSize: 18
                                color: navMa.containsMouse ? steelAccent : steelTextSec
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: model.label
                                font.family: "Manrope"
                                font.pixelSize: 8
                                color: navMa.containsMouse ? steelAccent : steelTextTer
                            }
                        }

                        MouseArea {
                            id: navMa
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: contentStack.currentIndex = model.idx
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "v18"
                    font.family: "JetBrains Mono"
                    font.pixelSize: 9
                    color: steelTextTer
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: steelAppBg

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    color: steelPanel

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 24
                        anchors.rightMargin: 24
                        spacing: 16

                        Text {
                            text: "SENTINEL DESKTOP"
                            font.family: "Archivo"
                            font.pixelSize: 14
                            font.bold: true
                            color: steelAccent
                        }

                        Rectangle {
                            Layout.preferredHeight: 20
                            Layout.preferredWidth: steelBadge.implicitWidth + 16
                            radius: 4
                            color: Qt.rgba(1, 1, 1, 0.05)
                            border.width: 1
                            border.color: steelBrd
                            Text {
                                id: steelBadge
                                anchors.centerIn: parent
                                text: "Steel"
                                font.family: "JetBrains Mono"
                                font.pixelSize: 10
                                color: steelAccent
                            }
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            id: stateIndicator
                            text: "IDLE"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 10
                            font.bold: true
                            color: steelTextSec

                            Timer {
                                running: controller.state === "running"
                                repeat: true
                                interval: 800
                                onTriggered: {
                                    stateIndicator.color = stateIndicator.color === steelAct ? steelTextSec : steelAct
                                }
                            }
                        }

                        Rectangle {
                            Layout.preferredHeight: 26
                            Layout.preferredWidth: modelChip.implicitWidth + 16
                            radius: 4
                            color: Qt.rgba(1, 1, 1, 0.05)
                            border.width: 1
                            border.color: steelBrd
                            Text {
                                id: modelChip
                                anchors.centerIn: parent
                                text: "model"
                                font.family: "JetBrains Mono"
                                font.pixelSize: 10
                                color: steelTextSec
                            }
                        }

                        Rectangle {
                            Layout.preferredHeight: 26
                            Layout.preferredWidth: 26
                            radius: 4
                            color: cmdKMa.containsMouse ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.05)
                            border.width: 1
                            border.color: steelBrd
                            Text {
                                anchors.centerIn: parent
                                text: "\u2318K"
                                font.family: "JetBrains Mono"
                                font.pixelSize: 11
                                color: steelTextTer
                            }
                            MouseArea {
                                id: cmdKMa
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: paletteVisible = !paletteVisible
                            }
                        }
                    }
                }

                StackLayout {
                    id: contentStack
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: 0

                    Rectangle {
                        id: dashboard
                        color: "transparent"
                        anchors.fill: parent
                        property color dashAccent: "#8AB4C8"
                        property color dashPanel: "#0F1316"
                        property color dashBg: "#0A080F"
                        property color dashSee: "#38BDF8"
                        property color dashPlan: "#A78BFA"
                        property color dashAct: "#34D399"
                        property color dashTextPri: "#e2e2e8"
                        property color dashTextSec: "#849495"
                        property color dashTextTer: "#5a6a6e"
                        property color dashBrd: Qt.rgba(1, 1, 1, 0.07)
                        property color dashErr: "#ff3b3b"

                        function addLogEntry(kind, message) { logModel.append({"kind": kind, "message": message}); if (logModel.count > 200) logModel.remove(0) }
                        function setScreenshot(src) { liveImage.source = src }

                        Rectangle {
                            id: goalHero
                            x: 24; y: 24
                            width: dashboard.width - 48; height: 160
                            radius: 14; color: dashboard.dashPanel; border.width: 1; border.color: dashboard.dashBrd

                            ColumnLayout {
                                anchors.fill: parent; anchors.margins: 24; spacing: 12

                                RowLayout {
                                    spacing: 12
                                    Text { text: "GOAL"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: dashboard.dashAccent }
                                    Rectangle {
                                        visible: controller.state === "running"
                                        width: rp2.implicitWidth + 14; height: 22; radius: 11; color: dashboard.dashAct
                                        Text { id: rp2; anchors.centerIn: parent; text: "RUNNING"; font.family: "JetBrains Mono"; font.pixelSize: 9; font.bold: true; color: dashboard.dashBg }
                                    }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        width: 80; height: 32; radius: 9
                                        color: rma2.pressed ? Qt.lighter(dashboard.dashAct, 1.2) : rma2.containsMouse ? Qt.lighter(dashboard.dashAct, 1.1) : dashboard.dashAct
                                        Text { anchors.centerIn: parent; text: "\u25b6 Run"; font.family: "Manrope"; font.pixelSize: 12; font.bold: true; color: dashboard.dashBg }
                                        MouseArea { id: rma2; anchors.fill: parent; hoverEnabled: true; onClicked: { var g = goalText.text.trim(); if (g.length > 0) controller.run_goal(g) } }
                                    }
                                    Rectangle {
                                        width: 80; height: 32; radius: 9
                                        color: sma2.pressed ? Qt.lighter(dashboard.dashErr, 1.2) : sma2.containsMouse ? Qt.lighter(dashboard.dashErr, 1.1) : dashboard.dashErr
                                        Text { anchors.centerIn: parent; text: "\u25a0 Stop"; font.family: "Manrope"; font.pixelSize: 12; font.bold: true; color: "#fff" }
                                        MouseArea { id: sma2; anchors.fill: parent; hoverEnabled: true; onClicked: controller.stop_goal() }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true; Layout.fillHeight: true; radius: 9; color: dashboard.dashBg
                                    border.width: 1; border.color: goalText.activeFocus ? dashboard.dashAccent : dashboard.dashBrd
                                    ScrollView { anchors.fill: parent; anchors.margins: 10; clip: true
                                        TextArea {
                                            id: goalText
                                            placeholderText: "Describe what you want done\u2026   (Ctrl+Enter to run)"
                                            font.family: "Manrope"; font.pixelSize: 14
                                            color: dashboard.dashTextPri; placeholderTextColor: dashboard.dashTextTer
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

                        Rectangle {
                            id: actPanel
                            x: 24
                            y: goalHero.y + goalHero.height + 20
                            width: Math.floor((dashboard.width - 68) * 0.65)
                            height: dashboard.height - y - 24
                            radius: 14; color: dashboard.dashPanel; border.width: 1; border.color: dashboard.dashBrd
                            clip: true

                            Text { id: actLabel; x: 16; y: 16; text: "ACTIVITY"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: dashboard.dashAccent }

                            Row { id: waveform; x: 16; y: 38; spacing: 3
                                Repeater {
                                    model: Math.min(controller.max_steps, 60)
                                    Rectangle {
                                        width: 6; height: 18; radius: 3
                                        color: index < controller.step ? dashboard.dashSee : index === controller.step ? dashboard.dashAccent : Qt.rgba(1, 1, 1, 0.07)
                                        opacity: index <= controller.step ? 1.0 : 0.4
                                    }
                                }
                            }

                            Rectangle {
                                x: 16; y: 64
                                width: actPanel.width - 32; height: actPanel.height - 80
                                radius: 9; color: dashboard.dashBg; border.width: 1; border.color: dashboard.dashBrd
                                clip: true
                                ListView {
                                    id: logView
                                    x: 8; y: 8; width: parent.width - 16; height: parent.height - 16
                                    clip: true; model: logModel; spacing: 4
                                    onCountChanged: positionViewAtEnd()
                                    delegate: Rectangle {
                                        width: logView.width; height: logTxt.implicitHeight + 12; radius: 6; color: "transparent"
                                        Rectangle {
                                            width: 4; height: 4; radius: 2
                                            x: 8; anchors.verticalCenter: parent.verticalCenter
                                            color: model.kind === "see" ? dashboard.dashSee : model.kind === "plan" ? dashboard.dashPlan : model.kind === "act" ? dashboard.dashAct : model.kind === "error" ? dashboard.dashErr : dashboard.dashTextTer
                                        }
                                        Text {
                                            id: logTxt
                                            x: 20; anchors.verticalCenter: parent.verticalCenter
                                            width: parent.width - 28
                                            text: model.message; font.family: "JetBrains Mono"; font.pixelSize: 11
                                            color: model.kind === "error" ? dashboard.dashErr : model.kind === "user" ? dashboard.dashAccent : model.kind === "assistant" ? dashboard.dashAct : dashboard.dashTextSec
                                            wrapMode: Text.Wrap
                                        }
                                    }
                                }
                            }

                            ListModel { id: logModel }
                        }

                        Column {
                            id: rightCol
                            x: actPanel.x + actPanel.width + 20
                            y: actPanel.y
                            width: dashboard.width - x - 24
                            height: actPanel.height
                            spacing: 16

                            Text { text: "LIVE VIEW"; font.family: "Manrope"; font.pixelSize: 11; font.bold: true; color: dashboard.dashAccent }

                            Rectangle {
                                width: parent.width; height: 200; radius: 9; color: dashboard.dashBg
                                border.width: 2; border.color: dashboard.dashBrd
                                Image {
                                    id: liveImage
                                    x: 4; y: 4; width: parent.width - 8; height: parent.height - 8
                                    fillMode: Image.PreserveAspectFit
                                    visible: status === Image.Ready
                                }
                                Text {
                                    anchors.centerIn: parent; text: "No screenshot"
                                    font.family: "Manrope"; font.pixelSize: 10; color: dashboard.dashTextTer
                                    visible: liveImage.status !== Image.Ready
                                }
                            }

                            Rectangle {
                                width: parent.width; height: 90; radius: 14; color: dashboard.dashPanel
                                border.width: 1; border.color: dashboard.dashBrd; clip: true

                                Text { x: 12; y: 12; text: "SYSTEM"; font.family: "Manrope"; font.pixelSize: 10; font.bold: true; color: dashboard.dashAccent }

                                Column { x: 12; y: 30; spacing: 6
                                    Repeater {
                                        model: ["CPU", "RAM", "Disk"]
                                        Row {
                                            spacing: 8
                                            Text { text: modelData + ":"; font.family: "JetBrains Mono"; font.pixelSize: 10; color: dashboard.dashTextTer; width: 36 }
                                            Rectangle { y: 3; width: rightCol.width - 68; height: 6; radius: 3; color: Qt.rgba(1, 1, 1, 0.07)
                                                Rectangle { width: parent.width * 0.3; height: parent.height; radius: 3; color: dashboard.dashAccent }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Component.onCompleted: {
                            addLogEntry("system", "Sentinel Desktop v18 Steel ready. Describe a goal and press Ctrl+Enter.")
                        }
                    }

                    Workflows {}
                    Activity {}
                    Settings {}
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 28
                    color: steelPanel

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 16

                        Text {
                            text: "v18"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 9
                            color: steelTextTer
                        }

                        Text {
                            id: uptimeText
                            text: "00:00:00"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 9
                            color: steelTextTer

                            Timer {
                                running: true
                                repeat: true
                                interval: 1000
                                property int seconds: 0
                                onTriggered: {
                                    seconds++
                                    var h = Math.floor(seconds / 3600)
                                    var m = Math.floor((seconds % 3600) / 60)
                                    var s = seconds % 60
                                    uptimeText.text = (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
                                }
                            }
                        }

                        Text {
                            id: stepLabel
                            text: "0/100"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 9
                            color: steelTextTer
                        }

                        Item { Layout.fillWidth: true }

                        Text {
                            text: "\u2318K commands \u00b7 Esc\u00d73 panic"
                            font.family: "JetBrains Mono"
                            font.pixelSize: 9
                            color: steelTextTer
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        visible: paletteVisible
        anchors.fill: parent
        color: Qt.rgba(0, 0, 0, 0.6)
        z: 100

        MouseArea {
            anchors.fill: parent
            onClicked: paletteVisible = false
        }

        Rectangle {
            anchors.centerIn: parent
            width: 500
            height: 400
            radius: 14
            color: steelPanel
            border.width: 1
            border.color: steelBrd

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                TextField {
                    id: paletteSearch
                    Layout.fillWidth: true
                    placeholderText: "Search commands\u2026"
                    font.family: "Manrope"
                    font.pixelSize: 14
                    color: steelTextPri
                    placeholderTextColor: steelTextTer
                    background: Rectangle {
                        radius: 9
                        color: steelAppBg
                        border.width: 1
                        border.color: paletteSearch.activeFocus ? steelAccent : steelBrd
                    }
                    leftPadding: 12
                    height: 40
                    onVisibleChanged: if (visible) forceActiveFocus()
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: ListModel {
                        ListElement { name: "New Chat" }
                        ListElement { name: "Settings" }
                        ListElement { name: "Screenshot" }
                        ListElement { name: "Export Log" }
                        ListElement { name: "System Info" }
                        ListElement { name: "Workflows" }
                    }

                    delegate: Rectangle {
                        width: paletteList.width
                        height: 36
                        radius: 6
                        color: paletteItemMa.containsMouse ? Qt.rgba(1, 1, 1, 0.05) : "transparent"

                        Text {
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.name
                            font.family: "Manrope"
                            font.pixelSize: 13
                            color: steelTextPri
                        }

                        MouseArea {
                            id: paletteItemMa
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                paletteVisible = false
                                if (model.name === "Settings") contentStack.currentIndex = 3
                                else if (model.name === "Workflows") contentStack.currentIndex = 1
                            }
                        }
                    }
                }
            }

            id: paletteList
        }
    }

    Rectangle {
        id: approvalDialog
        visible: false
        anchors.centerIn: parent
        width: 480
        height: 220
        radius: 14
        color: steelPanel
        border.width: 1
        border.color: steelAccent
        z: 200

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            Text {
                text: "Approve action?"
                font.family: "Manrope"
                font.pixelSize: 15
                font.bold: true
                color: steelAccent
            }

            Text {
                id: approvalActionText
                text: ""
                font.family: "JetBrains Mono"
                font.pixelSize: 11
                color: steelTextPri
                wrapMode: Text.Wrap
                Layout.fillWidth: true
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Item { Layout.fillWidth: true }

                Rectangle {
                    Layout.preferredHeight: 32
                    Layout.preferredWidth: 100
                    radius: 9
                    color: approveMa.containsMouse ? Qt.lighter(steelAct, 1.1) : steelAct
                    Text {
                        anchors.centerIn: parent
                        text: "\u2713 Approve"
                        font.family: "Manrope"
                        font.pixelSize: 12
                        font.bold: true
                        color: steelAppBg
                    }
                    MouseArea {
                        id: approveMa
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            controller.respond_approval(true)
                            approvalDialog.visible = false
                        }
                    }
                }

                Rectangle {
                    Layout.preferredHeight: 32
                    Layout.preferredWidth: 100
                    radius: 9
                    color: rejectMa.containsMouse ? Qt.lighter(steelErr, 1.1) : steelErr
                    Text {
                        anchors.centerIn: parent
                        text: "\u2717 Reject"
                        font.family: "Manrope"
                        font.pixelSize: 12
                        font.bold: true
                        color: "#ffffff"
                    }
                    MouseArea {
                        id: rejectMa
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            controller.respond_approval(false)
                            approvalDialog.visible = false
                        }
                    }
                }
            }
        }

        Connections {
            target: controller
            function onApprovalNeeded(action, params) {
                approvalActionText.text = action + "\n" + params
                approvalDialog.visible = true
            }
        }
    }

    Connections {
        target: controller
        function onErrorOccurred(msg) {
            dashboard.addLogEntry("error", msg)
        }
        function onGoalFinished(summary, steps, status) {
            dashboard.addLogEntry("assistant", "Completed in " + steps + " steps: " + summary)
        }
    }
}
