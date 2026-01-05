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
    QDialogButtonBox,
    QObject,
    QFrame,
)

from dataclasses import dataclass
from .i18n import i18n, i18n_reset

import os
import json
import typing


C = dict[str, dict[str, str | bool]]

_global_config: C | None = None


@dataclass
class ToggleItem:
    checkbox: QCheckBox
    extra: QLabel | None
    section: str


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
            self._translated[k] = self._translateLineEdit(k)

        self._toggle: dict[str, list[ToggleItem]] = {
            "split_panes": ToggleItem(
                checkbox=QCheckBox(i18n("Enable split panes")),
                section=i18n("Split Panes"),
                extra=None,
            ),
            "restore_layout": ToggleItem(
                checkbox=QCheckBox(
                    i18n("Restore split pane layout when Krita restarts (experimental)")
                ),
                section=i18n("Split Panes"),
                extra=None
            ),
            "toolbar_icons": ToggleItem(
                checkbox=QCheckBox(i18n("Highlight active tool in toolbars")),
                section=i18n("Tools"),
                extra=None,
            ),
            "shared_tool": ToggleItem(
                checkbox=QCheckBox(
                    i18n(
                        "Do not change the active tool when switching documents"
                    )
                ),
                section=i18n("Tools"),
                extra=None,
            ),
            "toggle_docking": ToggleItem(
                checkbox=QCheckBox(i18n("Toggle docking on and off")),
                section=i18n("Dockers"),
                extra=None,
            ),
        }

        for _, (k, v) in enumerate(self._config.get("toggle", {}).items()):
            if k in self._toggle:
                self._toggle[k].checkbox.setChecked(typing.cast(bool, v))

        self.tabs = QTabWidget()
        self.optionsTab = self._setupOptionsTab()
        self.translateTab = self._setupTranslateTab()

        self.tabs.addTab(self.optionsTab, i18n("Options"))
        self.tabs.addTab(self.translateTab, i18n("Translate"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    def _translateLineEdit(self, key: str) -> QLineEdit:
        trans = typing.cast(dict[str, str], self._config.get("translated", {}))
        val = trans.get(key, "").replace("&&", "&")
        return QLineEdit(val)

    def _setupOptionsTab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        section = None
        for item in self._toggle.values():
            if item.section != section:
                if section is not None:
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
            form.addRow(item.checkbox)
            if item.extra:
                item.extra.setTextFormat(Qt.TextFormat.RichText)
                item.extra.setContentsMargins(20, 0, 0, 0)
                form.addRow(item.extra)
        return tab

    def _setupTranslateTab(self):
        content = QWidget()
        form = QFormLayout(content)

        for _, (text, edit) in enumerate(self._translated.items()):
            sanitized = text.replace("&&", "&")
            label = QLabel(sanitized)
            if edit.text() == sanitized:
                edit.setText("")
            block = QWidget()
            v = QVBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 16)
            v.addWidget(label)
            v.addWidget(edit)
            form.addRow(block)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def onAccepted(self):
        global _global_config
        config = readConfig()
        for _, (k, v) in enumerate(self._translated.items()):
            config["translated"][k] = v.text().strip().replace("&", "&&")

        for _, (k, v) in enumerate(self._toggle.items()):
            checked = v.checkbox.isChecked() 
            config["toggle"][k] = checked
            if k == "restore_layout" and checked:
                Krita.instance().writeSetting("", "sessionOnStartup", "0")
        
        writeConfig(config)
        _global_config = config
        i18n_reset()
        signals.configSaved.emit()


def defaultConfig() -> C:
    config: C = {
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
    
def setOpt(*args: str):
    listArgs = list(args)
    val = listArgs.pop()
    key = listArgs.pop()
    
    global _global_config
    if _global_config is None:
        _global_config = readConfig()
        
    item = _global_config
    numArgs = len(listArgs)
    print(f"{key} {val}")
    
    for i, a in enumerate(listArgs):
        print(f"{i}, {a}")
        item = typing.cast(dict[str, str | bool], item).get(a, None)
        if not isinstance(item, dict) and i < numArgs - 1:
            item = None
            break
            
    if item is not None:
        item[key] = val
        writeConfig(_global_config)

def readConfig():
    config = None
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass

    defaults = defaultConfig()

    if isinstance(config, dict):
        config = typing.cast(C, config)
        for section in ("translated", "toggle"):
            if not isinstance(config.get(section, None), dict):
                config[section] = defaults[section]
            else:
                for _, (k, v) in enumerate(defaults[section].items()):
                    s = config[section]
                    if s.get(k, None) is None:
                        s[k] = v
        return config
    else:
        return defaults


def writeConfig(config: C):
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config.json"
    )
    try:
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def showOptions():
    dlg = SettingsDialog()
    if dlg.exec() == QDialog.Accepted:
        dlg.onAccepted()
