# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    pyqtSignal,
    Qt,
    QScrollArea,
    QLabel,
    QDialog,
    QTabWidget,
    QWidget,
    QFormLayout,
    QVBoxLayout,
    QCheckBox,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
    QObject,
    QFrame,
)

from krita import Krita
from dataclasses import dataclass

from .i18n import i18n, i18n_reset

import os
import json
import typing

VERSION = "1.0.1"

C = dict[str, dict[str, str | bool]]

_global_config: C | None = None


@dataclass
class ToggleItem:
    input: QCheckBox
    extra: QLabel | None
    section: str


@dataclass
class InputItem:
    input: QLineEdit
    label: QLabel | None
    extra: QLabel | None
    section: str
    escape: bool


@dataclass
class NumberItem:
    input: QSpinBox
    label: QLabel | None
    section: str
    clamp: tuple[int, int]
    extra: QLabel | None


class Signals(QObject):
    configSaved = pyqtSignal()


signals = Signals()


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n("UI Tweaks"))
        self.setMinimumWidth(400)
        self.setMinimumHeight(400)

        self._config: C = readConfig()

        self._translated: dict[str, QLineEdit] = {}

        for k in self._config.get("translated", {}).keys():
            self._translated[k] = InputItem(
                input=QLineEdit(),
                escape=True,
                section="",
                label=QLabel(self._unescape(k)),
                extra=None,
            )

        self._appearance: dict[str, ToggleItem | NumberItem] = {
            "tab_max_chars": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Max characters to show")),
                clamp=(10, 100),
                section=i18n("Tabs"),
                extra=None,
            ),
            "tab_height": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab height")),
                clamp=(20, 50),
                section=i18n("Tabs"),
                extra=None,
            ),
            "tab_font_size": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab font size")),
                clamp=(8, 20),
                section=i18n("Tabs"),
                extra=None,
            ),
            "tab_font_bold": ToggleItem(
                input=QCheckBox(i18n("Tab font bold")),
                section=i18n("Tabs"),
                extra=None,
            ),
            "tab_hide_filesize": ToggleItem(
                input=QCheckBox(i18n("Hide the file size")),
                section=i18n("Tabs"),
                extra=None,
            ),
            "tab_ellipsis": ToggleItem(
                input=QCheckBox(
                    i18n("Show ellipsis (…) when tab text is truncated")
                ),
                section=i18n("Tabs"),
                extra=None,
            ),
        }

        self._toggle: dict[str, ToggleItem] = {
            "split_panes": ToggleItem(
                input=QCheckBox(i18n("Enable split panes")),
                section=i18n("Split Panes"),
                extra=None,
            ),
            "restore_layout": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Restore split pane layout when Krita restarts (experimental)"
                    )
                ),
                section=i18n("Split Panes"),
                extra=QLabel(
                    i18n(
                        "<b>Will disable Krita's default session restore mechanism.</b>"
                    )
                ),
            ),
            "toolbar_icons": ToggleItem(
                input=QCheckBox(i18n("Highlight active tool in toolbars")),
                section=i18n("Tools"),
                extra=None,
            ),
            "shared_tool": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Do not change the active tool when switching documents"
                    )
                ),
                section=i18n("Tools"),
                extra=None,
            ),
            "hide_floating_message": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Permanently hide the floating message that appears at the top-left of the canvas."
                    ),
                ),
                section=i18n("Tools"),
                extra=QLabel(i18n("<b>Requires restart.</b>")),
            ),
            "toggle_docking": ToggleItem(
                input=QCheckBox(i18n("Toggle docking on and off")),
                section=i18n("Dockers"),
                extra=None,
            ),
        }

        self.tabs = QTabWidget()
        self.optionsTab = self._setupOptionsTab()
        self.translateTab = self._setupTranslateTab()
        self.appearanceTab = self._setupAppearanceTab()
        self.aboutTab = self._setupAboutTab()

        self.tabs.addTab(self.optionsTab, i18n("Options"))
        self.tabs.addTab(self.appearanceTab, i18n("Appearance"))
        self.tabs.addTab(self.translateTab, i18n("Translate"))
        self.tabs.addTab(self.aboutTab, i18n("About"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def _unescape(self, val: str) -> str:
        return val.replace("&&", "&")

    def _escape(self, val: str) -> str:
        return val.replace("&", "&&")

    def _getFormValue(
        self, item: ToggleItem | InputItem | NumberItem
    ) -> typing.Any:
        t = type(item)
        if t == ToggleItem:
            return item.input.isChecked()
        elif t == InputItem:
            val = item.input.text().strip()
            return self._escape(val) if item.escape else val
        elif t == NumberItem:
            return item.input.value()

    def _renderFormItem(
        self,
        form: QWidget,
        key: tuple[str, str],
        item: ToggleItem | InputItem | NumberItem,
    ) -> QWidget | None:
        t = type(item)
        if t == ToggleItem:
            item.input.setChecked(typing.cast(bool, getOpt(*key)))
            form.addRow(item.input)
        elif t == InputItem:
            val = getOpt(*key)
            if item.escape:
                val = self._unescape(val)
            item.input.setText("" if val == item.label.text() else val)
            block = QWidget()
            v = QVBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 16)
            v.addWidget(item.label)
            v.addWidget(item.input)
            form.addRow(block)
        elif t == NumberItem:
            item.input.setRange(item.clamp[0], item.clamp[1])
            item.input.setValue(getOpt(*key))
            form.addRow(item.label, item.input)
        if item.extra:
            item.extra.setTextFormat(Qt.TextFormat.RichText)
            item.extra.setEnabled(False)
            item.extra.setContentsMargins(20, 0, 0, 0)
            form.addRow(item.extra)

    def _renderTabForm(self, configKey: str, formItems):
        tab = QWidget()
        form = QFormLayout(tab)
        section = ""
        for _, (key, item) in enumerate(formItems.items()):
            if item.section and item.section != section:
                if len(section) > 0:
                    line = QFrame()
                    line.setFrameShape(QFrame.Shape.HLine)
                    line.setFrameShadow(QFrame.Shadow.Sunken)
                    form.addRow(line)
                section = item.section
                label = QLabel(section)
                font = label.font()
                font.setBold(True)
                label.setFont(font)
                form.addRow(label)

            self._renderFormItem(form, (configKey, key), item)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tab)
        return scroll

    def _setupOptionsTab(self):
        return self._renderTabForm("toggle", self._toggle)

    def _setupTranslateTab(self):
        return self._renderTabForm("translated", self._translated)

    def _setupAppearanceTab(self):
        return self._renderTabForm("appearance", self._appearance)

    def _setupAboutTab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        label = QLabel(
            "<br>".join(
                [
                    f"<b>Krita UI Tweaks {VERSION}</b>",
                    f"Repository and more info here:",
                    f"<a href='https://github.com/vurentjie/krita_ui_tweaks/README.md'>https://github.com/vurentjie/krita_ui_tweaks/README.md</a>",
                ]
            )
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        form.addRow(label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tab)
        return scroll

    def onAccepted(self):
        global _global_config
        config = readConfig()

        for _, (k, v) in enumerate(self._translated.items()):
            config["translated"][k] = self._getFormValue(v)

        for _, (k, v) in enumerate(self._appearance.items()):
            config["appearance"][k] = self._getFormValue(v)

        for _, (k, v) in enumerate(self._toggle.items()):
            checked = self._getFormValue(v)
            config["toggle"][k] = checked
            if k == "restore_layout" and checked:
                Krita.instance().writeSetting("", "sessionOnStartup", "0")

        writeConfig(config)
        _global_config = config
        i18n_reset()
        signals.configSaved.emit()


def defaultConfig() -> C:
    config: C = {
        "appearance": {
            "tab_max_chars": 30,
            "tab_height": 30,
            "tab_font_size": 12,
            "tab_font_bold": True,
            "tab_hide_filesize": False,
            "tab_ellipsis": True,
        },
        "translated": {
            "Duplicate Tab": "Duplicate Tab",
            "Split && Move Left": "Split && Move Left",
            "Split && Move Right": "Split && Move Right",
            "Split && Move Above": "Split && Move Above",
            "Split && Move Below": "Split && Move Below",
            "Split && Duplicate Left": "Split && Duplicate Left",
            "Split && Duplicate Right": "Split && Duplicate Right",
            "Split && Duplicate Above": "Split && Duplicate Above",
            "Split && Duplicate Below": "Split && Duplicate Below",
            "Close Tabs To Right": "Close Tabs To Right",
            "Close Tabs To Left": "Close Tabs To Left",
            "Close Other Tabs": "Close Other Tabs",
            "Close Split Pane": "Close Split Pane",
            "Reset Layout": "Reset Layout",
            "Reset Sizes": "Reset Sizes",
            "Options": "Options",
            "Toggle docking": "Toggle docking",
            "Docking enabled": "Docking enabled",
            "Docking disabled": "Docking disabled",
            "Goto next tab": "Goto next tab",
            "Goto previous tab": "Goto previous tab",
        },
        "toggle": {
            "split_panes": True,
            "restore_layout": False,
            "toolbar_icons": True,
            "shared_tool": True,
            "hide_floating_message": False,
            "toggle_docking": True,
        },
    }
    return config


def getOpt(*args: str):
    global _global_config
    if _global_config is None:
        _global_config = readConfig()
    val = _global_config
    numArgs = len(args)
    for i, a in enumerate(args):
        val = typing.cast(dict[str, str | bool], val).get(a, None)
        if not isinstance(val, dict) and i < numArgs - 1:
            val = None
            break
    return val


def setOpt(*args: typing.Any):
    listArgs = list(args)
    val = listArgs.pop()
    key = str, listArgs.pop()

    global _global_config
    if _global_config is None:
        _global_config = readConfig()

    item = _global_config
    numArgs = len(listArgs)

    for i, a in enumerate(listArgs):
        item = typing.cast(dict[str, str | bool], item).get(a, None)
        if not isinstance(item, dict) and i < numArgs - 1:
            item = None
            break

    if item is not None:
        item[key] = (
            val  # pyright: ignore [reportIndexIssue, reportArgumentType]
        )
        writeConfig(_global_config)


def readConfig():
    app = Krita.instance()
    defaults = defaultConfig()
    try:
        config = json.loads(app.readSetting("krita_ui_tweaks", "options", ""))
        assert isinstance(config, dict)
        config = typing.cast(C, config)
        for section in defaults.keys():
            if not isinstance(config.get(section, None), dict):
                config[section] = defaults[section]
            else:
                for _, (k, v) in enumerate(defaults[section].items()):
                    s = config[section]
                    curr = s.get(k, None)
                    if curr is None or type(curr) != type(v):
                        s[k] = v
    except:
        config = defaults
    return config


def writeConfig(config: C):
    app = Krita.instance()
    app.writeSetting("krita_ui_tweaks", "options", json.dumps(config))


def showOptions():
    dlg = SettingsDialog()
    if dlg.exec() == QDialog.Accepted:
        dlg.onAccepted()
