import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: settingsPage

    property color panel: "#0F1316"
    property color accent: "#8AB4C8"
    property color appBg: "#0A080F"
    property color textPri: "#e2e2e8"
    property color textSec: "#849495"
    property color textTer: "#5a6a6e"
    property color brd: Qt.rgba(1, 1, 1, 0.07)
    property int radMd: 14

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 20

        Component.onCompleted: {
            var providers = ["OpenAI", "Anthropic", "Google", "xAI", "DeepSeek", "OpenRouter", "Z.ai (GLM-5)", "Ollama", "Custom"]
            var p = controller.getProvider()
            var idx = providers.indexOf(p)
            providerCombo.currentIndex = idx >= 0 ? idx : 0
            apiKeyField.text = controller.getApiKey()
            modelField.text = controller.getModel()
            baseUrlField.text = controller.getBaseUrl()
            stepBudget.value = controller.getMaxSteps()
            autoSwitch.checked = controller.getAutonomous()
            dryRunSwitch.checked = controller.getDryRun()
            stealthSwitch.checked = controller.getStealthInput()
        }

        Text {
            text: "SETTINGS"
            font.family: "Manrope"
            font.pixelSize: 11
            font.bold: true
            color: accent
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 300
            radius: radMd
            color: panel
            border.width: 1
            border.color: brd

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 16

                Text {
                    text: "LLM Provider"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                ComboBox {
                    id: providerCombo
                    Layout.fillWidth: true
                    model: ["OpenAI", "Anthropic", "Google", "xAI", "DeepSeek", "OpenRouter", "Z.ai (GLM-5)", "Ollama", "Custom"]
                    currentIndex: 0
                    font.family: "Manrope"
                    font.pixelSize: 12
                }

                Text {
                    text: "API Key"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                TextField {
                    id: apiKeyField
                    Layout.fillWidth: true
                    placeholderText: "Paste your API key\u2026"
                    echoMode: TextInput.Password
                    font.family: "Manrope"
                    font.pixelSize: 12
                    color: textPri
                    placeholderTextColor: textTer
                    background: Rectangle {
                        radius: 9
                        color: appBg
                        border.width: 1
                        border.color: apiKeyField.activeFocus ? accent : brd
                    }
                    leftPadding: 12
                    rightPadding: 12
                    height: 36
                }

                Text {
                    text: "Model"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                TextField {
                    id: modelField
                    Layout.fillWidth: true
                    placeholderText: "Model name or auto-detect\u2026"
                    font.family: "Manrope"
                    font.pixelSize: 12
                    color: textPri
                    placeholderTextColor: textTer
                    background: Rectangle {
                        radius: 9
                        color: appBg
                        border.width: 1
                        border.color: modelField.activeFocus ? accent : brd
                    }
                    leftPadding: 12
                    rightPadding: 12
                    height: 36
                }

                Text {
                    text: "Base URL"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                TextField {
                    id: baseUrlField
                    Layout.fillWidth: true
                    placeholderText: "Override provider base URL (leave blank for default)"
                    font.family: "Manrope"
                    font.pixelSize: 12
                    color: textPri
                    placeholderTextColor: textTer
                    background: Rectangle {
                        radius: 9
                        color: appBg
                        border.width: 1
                        border.color: baseUrlField.activeFocus ? accent : brd
                    }
                    leftPadding: 12
                    rightPadding: 12
                    height: 36
                }

                Text {
                    text: "OpenRouter: https://openrouter.ai/api/v1\nZ.ai Max Coding: https://api.z.ai/api/coding/paas/v4"
                    font.family: "JetBrains Mono"
                    font.pixelSize: 10
                    color: textTer
                    wrapMode: Text.Wrap
                }

                Text {
                    text: "Step Budget"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                SpinBox {
                    id: stepBudget
                    from: 10
                    to: 500
                    value: 100
                    editable: true
                    font.family: "Manrope"
                    font.pixelSize: 12
                }

                Text {
                    text: "Run Mode"
                    font.family: "Manrope"
                    font.pixelSize: 13
                    font.bold: true
                    color: textPri
                }

                ColumnLayout {
                    spacing: 8

                    Switch {
                        id: autoSwitch
                        text: "Fully autonomous (no approval prompts)"
                        font.family: "Manrope"
                        font.pixelSize: 12
                        contentItem: Text {
                            text: autoSwitch.text
                            font: autoSwitch.font
                            color: textSec
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: autoSwitch.indicator.width + 8
                        }
                    }

                    Switch {
                        id: dryRunSwitch
                        text: "Dry-run (log actions, don't execute)"
                        font.family: "Manrope"
                        font.pixelSize: 12
                        contentItem: Text {
                            text: dryRunSwitch.text
                            font: dryRunSwitch.font
                            color: textSec
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: dryRunSwitch.indicator.width + 8
                        }
                    }

                    Switch {
                        id: stealthSwitch
                        text: "Stealth input (don't move mouse/keyboard)"
                        font.family: "Manrope"
                        font.pixelSize: 12
                        contentItem: Text {
                            text: stealthSwitch.text
                            font: stealthSwitch.font
                            color: textSec
                            verticalAlignment: Text.AlignVCenter
                            leftPadding: stealthSwitch.indicator.width + 8
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            radius: 9
            color: saveBtnMa.containsMouse ? Qt.lighter(accent, 1.1) : accent
            Text {
                anchors.centerIn: parent
                text: "\U0001f4be Save Settings"
                font.family: "Manrope"
                font.pixelSize: 13
                font.bold: true
                color: appBg
            }
            MouseArea {
                id: saveBtnMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    var provider = providerCombo.currentText
                    var apiKey = apiKeyField.text.trim()
                    var model = modelField.text.trim()
                    var baseUrl = baseUrlField.text.trim()
                    var steps = stepBudget.value
                    var autonomous = autoSwitch.checked
                    var dryRun = dryRunSwitch.checked
                    var stealth = stealthSwitch.checked

                    controller.saveSettings(provider, apiKey, model, baseUrl, steps, autonomous, dryRun, stealth)
                    settingsSavedLabel.visible = true
                    settingsSavedTimer.restart()
                }
            }
        }

        Text {
            id: settingsSavedLabel
            text: "Settings saved."
            font.family: "JetBrains Mono"
            font.pixelSize: 11
            color: accent
            visible: false
        }

        Timer {
            id: settingsSavedTimer
            interval: 2000
            onTriggered: settingsSavedLabel.visible = false
        }

        Item { Layout.fillHeight: true }
    }
}
