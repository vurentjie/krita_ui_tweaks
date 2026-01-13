# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    pyqtSignal,
    Qt,
    QApplication,
    QCheckBox,
    QColor,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QMouseEvent,
    QObject,
    QPainter,
    QPaintEvent,
    QPen,
    QPoint,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from krita import Krita
from dataclasses import dataclass, fields
from types import SimpleNamespace

from .i18n import i18n, i18n_reset
from .colors import ColorScheme, HasColorScheme

import os
import json
import typing
import time

VERSION = "1.0.5"

CONFIG_SECTION_TYPE = dict[str, str | bool | int]
CONFIG_TYPE = dict[str, CONFIG_SECTION_TYPE]

_global_config: CONFIG_TYPE | None = None


class ColorButton(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(
        self,
        parent=None,
        color=QColor("white"),
        resetColor=QColor("white"),
        customColors: list[QColor] | None = [],
    ):
        super().__init__(parent)
        self._color: QColor = QColor(color)
        self._resetColor: QColor = QColor(resetColor)
        self._customColors: list[QColor] | None = customColors
        self.setFixedSize(24, 24)

    def paintEvent(self, _: QPaintEvent):
        rect = self.rect()

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(rect, self._color)

        borderColor = self._color.darker(120)
        pen = QPen(borderColor)
        pen.setWidth(1)
        p.setPen(pen)
        p.drawRect(rect.adjusted(0, 0, -1, -1))

    def reset(self):
        self.setColor(self._resetColor)

    def color(self) -> QColor:
        return self._color

    def value(self) -> str:
        return self._color.name()

    def setColor(self, color: QColor):
        if color.isValid() and color != self._color:
            self._color = QColor(color)
            self.update()
            self.colorChanged.emit(self._color)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            dlg = QColorDialog(self._color, self)

            for k, v in enumerate(self._customColors):
                dlg.setCustomColor(k, QColor(v))

            dlg.setOption(QColorDialog.ShowAlphaChannel, False)
            dlg.adjustSize()
            button_rect = self.rect()
            global_pos = self.mapToGlobal(button_rect.topRight())
            offset = QPoint(self.width() + 5, 0)
            dlg.move(global_pos + offset)
            dlg.colorSelected.connect(self.setColor)
            dlg.open()
        super().mousePressEvent(event)


@dataclass
class ColorItem:
    input: ColorButton
    label: QLabel
    extra: QWidget | list[QWidget] | None
    section: str


@dataclass
class ToggleItem:
    input: QCheckBox
    extra: QWidget | list[QWidget] | None
    section: str


@dataclass
class ComboItem:
    input: QComboBox
    label: QLabel
    options: dict[str, str]
    extra: QWidget | list[QWidget] | None
    section: str


@dataclass
class InputItem:
    input: QLineEdit
    label: QLabel | None
    extra: QWidget | list[QWidget] | None
    section: str
    escape: bool


@dataclass
class NumberItem:
    input: QSpinBox
    label: QLabel | None
    section: str
    clamp: tuple[int, int]
    extra: QWidget | list[QWidget] | None


FormItem = ToggleItem | NumberItem | InputItem | ColorItem | ComboItem
FormItems = dict[str, FormItem]


class Signals(QObject):
    configSaved = pyqtSignal(object)


signals = Signals()


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        controller: HasColorScheme | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(i18n("UI Tweaks"))
        self.setMinimumWidth(400)
        self.setMinimumHeight(600)

        self._controller = controller
        self._helper = self._controller.helper()
        self._config: CONFIG_TYPE = readConfig()

        val = "dark" if self._helper.useDarkIcons() else "light"
        self._resetIcon = QIcon(f":/{val}_reload-preset.svg")

        sections = SimpleNamespace(
            tabAppearance=i18n("Tab Appearance"),
            tabDragging=i18n("Tab Dragging"),
            splitPanes=i18n("Split Panes"),
            tools=i18n("Tools"),
            dockers=i18n("Dockers"),
            colors=i18n("Colors"),
        )

        self._translated: FormItems = {}

        for k in self._config.get("translated", {}).keys():
            self._translated[k] = InputItem(
                input=QLineEdit(),
                escape=True,
                section="",
                label=QLabel(self._unescape(k)),
                extra=None,
            )

        self._tabBehaviour: FormItems = {
            "tab_max_chars": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Max characters to show")),
                clamp=(10, 100),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_height": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab height")),
                clamp=(20, 50),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_font_size": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab font size")),
                clamp=(8, 20),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_font_bold": ToggleItem(
                input=QCheckBox(i18n("Tab font bold")),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_hide_filesize": ToggleItem(
                input=QCheckBox(i18n("Hide the file size")),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_ellipsis": ToggleItem(
                input=QCheckBox(
                    i18n("Show ellipsis (…) when tab text is truncated")
                ),
                section=sections.tabAppearance,
                extra=None,
            ),
            "tab_hide_menu_btn": ToggleItem(
                input=QCheckBox(
                    i18n("Hide the menu button in the tab toolbar (3 dots)")
                ),
                section=sections.tabAppearance,
                extra=QLabel(
                    i18n(
                        "<b>Requires restart. The menu can still be accessed by right-clicking tabs.</b>"
                    )
                ),
            ),
            "tab_drag_middle_btn": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Splits can be created by dragging with the middle button"
                    )
                ),
                section=sections.tabDragging,
                extra=None,
            ),
            "tab_drag_left_btn": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Splits can be created by dragging with the left button"
                    )
                ),
                section=sections.tabDragging,
                extra=QLabel(
                    i18n(
                        "<b>For left button: drag tabs vertically to initiate splitting</b>"
                    )
                ),
            ),
            "tab_drag_deadzone": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Drag deadzone")),
                clamp=(10, 50),
                section=sections.tabDragging,
                extra=QLabel(
                    i18n(
                        "<b>Amount of pixels to move for tab dragging to start.<br>Only applicable for left button.</b>"
                    )
                ),
            ),
        }

        self._toggle: FormItems = {
            "split_panes": ToggleItem(
                input=QCheckBox(i18n("Enable split panes")),
                section=sections.splitPanes,
                extra=None,
            ),
            "restore_layout": ToggleItem(
                input=QCheckBox(
                    i18n("Restore split pane layout when Krita restarts")
                ),
                section=sections.splitPanes,
                extra=QLabel(
                    i18n(
                        "<b>Will disable Krita's default session restore mechanism.</b>"
                    )
                ),
            ),
            "zoom_constraint_hint": ToggleItem(
                input=QCheckBox(i18n("Resize hint: scale images to viewport")),
                section=sections.splitPanes,
                extra=QLabel(
                    i18n("<b>Applies to images smaller than the viewport</b>")
                ),
            ),
            "toolbar_icons": ToggleItem(
                input=QCheckBox(i18n("Highlight active tool in toolbars")),
                section=sections.tools,
                extra=None,
            ),
            "shared_tool": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Do not change the active tool when switching documents"
                    )
                ),
                section=sections.tools,
                extra=None,
            ),
            "hide_floating_message": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Permanently hide the floating message that appears at the top-left of the canvas."
                    ),
                ),
                section=sections.tools,
                extra=QLabel(i18n("<b>Requires restart.</b>")),
            ),
            "toggle_docking": ToggleItem(
                input=QCheckBox(i18n("Toggle docking on and off")),
                section=sections.dockers,
                extra=None,
            ),
        }

        colorLabels: dict[str, str] = {
            "bar": i18n("Tab bar background"),
            "tab": i18n("Tab background"),
            "tabSelected": i18n("Tab selected background"),
            "tabActive": i18n("Tab active background"),
            "tabSeparator": i18n("Tab separator"),
            "tabClose": i18n("Close button background when hovered"),
            "splitHandle": i18n("Split drag handle"),
            "dropZone": i18n("Drop zone"),
            "dragTab": i18n("Drag tab indicator"),
        }
        schemeColors = self._controller.colors()
        configColors = self._config.get("colors", {})
        customColors = [
            getattr(schemeColors, f.name) for f in fields(schemeColors)
        ]
        # fill update the empty slots
        customColors.extend(
            [
                "#181818",
                "#282828",
                "#383838",
                "#474747",
                "#565656",
                "#646464",
                "#717171",
                "#7e7e7e",
            ]
        )

        self._colors: FormItems = {}
        for k in colorLabels.keys():
            color = configColors[k]
            resetColor = getattr(schemeColors, k, None)
            if not color:
                color = resetColor
            self._colors[k] = ColorItem(
                input=ColorButton(
                    color=color,
                    resetColor=resetColor,
                    customColors=customColors,
                ),
                label=QLabel(colorLabels[k]),
                section=sections.colors,
                extra=None,
            )

        self.tabs = QTabWidget()
        self.optionsTab = self._setupOptionsTab()
        self.translateTab = self._setupTranslateTab()
        self.behaviourTab = self._setupBehaviourTab()
        self.colorsTab = self._setupColorsTab()
        self.aboutTab = self._setupAboutTab()

        self.tabs.addTab(self.optionsTab, i18n("Options"))
        self.tabs.addTab(self.behaviourTab, i18n("Behaviour"))
        self.tabs.addTab(self.colorsTab, i18n("Colors"))
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

    def _getFormValue(self, item: FormItem) -> typing.Any:
        t = type(item)
        if t == ComboItem:
            return item.input.currentData()
        elif t == ToggleItem:
            return item.input.isChecked()
        elif t == InputItem:
            val = item.input.text().strip()
            return (
                self._escape(val)
                if typing.cast(InputItem, item).escape
                else val
            )
        elif t in (ColorItem, NumberItem):
            return item.input.value()

    def _renderFormItem(
        self, form: QWidget, key: tuple[str, str], item: FormItem
    ) -> QWidget | None:
        t = type(item)
        if t == ToggleItem:
            item.input.setChecked(typing.cast(bool, getOpt(*key)))
            form.addRow(item.input)
        elif t == InputItem:
            item = typing.cast(InputItem, item)
            assert item.label is not None
            val = getOpt(*key)
            if item.escape:
                val = self._unescape(val)
            item.input.setText("" if val == item.label.text() else val)
            block = QWidget()
            v = QVBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 16)
            item.label.setTextFormat(Qt.TextFormat.RichText)
            v.addWidget(item.label)
            v.addWidget(item.input)
            form.addRow(block)
        elif t == NumberItem:
            item = typing.cast(NumberItem, item)
            assert item.label is not None
            assert item.clamp is not None
            item.input.setRange(item.clamp[0], item.clamp[1])
            item.input.setFixedWidth(100)
            item.input.setValue(getOpt(*key))
            item.label.setTextFormat(Qt.TextFormat.RichText)
            form.addRow(item.label, item.input)
        elif t == ComboItem:
            item = typing.cast(ComboItem, item)
            val = typing.cast(str, getOpt(*key))
            assert item.input is not None
            assert item.label is not None
            index = 0
            for i, (key, text) in enumerate(item.options.items()):
                if val == key:
                    index = i
                item.input.addItem(text, key)

            # item.input.setSizeAdjustPolicy(
            #     QComboBox.SizeAdjustPolicy.AdjustToContents
            # )
            # item.input.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            item.input.setCurrentIndex(index)
            block = QWidget()
            v = QVBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 0)
            item.label.setTextFormat(Qt.TextFormat.RichText)
            v.addWidget(item.label)
            v.addWidget(item.input)
            form.addRow(block)
        elif t == ColorItem:
            item = typing.cast(ColorItem, item)
            reset = QPushButton()
            reset.setIcon(self._resetIcon)
            reset.setToolTip(i18n("Reset to default color"))
            reset.clicked.connect(item.input.reset)
            reset.setFixedWidth(30)

            block = QWidget()
            v = QHBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(item.input)
            v.addWidget(item.label)
            v.addWidget(reset)
            form.addRow(block)
        if item.extra:
            if not isinstance(item.extra, list):
                item.extra = [item.extra]

            field = QHBoxLayout()
            for extra in item.extra:
                if isinstance(extra, QLabel):
                    extra.setTextFormat(Qt.TextFormat.RichText)
                    extra.setEnabled(False)
                field.addWidget(extra)
                field.setContentsMargins(20, 0, 0, 0)
            form.addRow(field)

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

    def _setupColorsTab(self):
        return self._renderTabForm("colors", self._colors)

    def _setupTranslateTab(self):
        return self._renderTabForm("translated", self._translated)

    def _setupBehaviourTab(self):
        return self._renderTabForm("tab_behaviour", self._tabBehaviour)

    def _setupAboutTab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        label = QLabel(
            "<br>".join(
                [
                    f"<b>Krita UI Tweaks {VERSION}</b>",
                    f"Repository and more info here:",
                    f"<a href='https://github.com/vurentjie/krita_ui_tweaks'>https://github.com/vurentjie/krita_ui_tweaks</a>",
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

        for _, (k, v) in enumerate(self._tabBehaviour.items()):
            config["tab_behaviour"][k] = self._getFormValue(v)

        for _, (k, v) in enumerate(self._toggle.items()):
            val = self._getFormValue(v)
            config["toggle"][k] = val
            if k == "restore_layout" and val:
                Krita.instance().writeSetting("", "sessionOnStartup", "0")

        schemeColors = self._controller.colors()
        colorsChanged = False
        configColors = self._config.get("colors", {})

        for _, (k, v) in enumerate(self._colors.items()):
            color = self._getFormValue(v)
            currColor = configColors.get(k, "")
            resetColor = getattr(schemeColors, k, None)
            newColor = "" if color == resetColor else color
            if newColor != currColor:
                colorsChanged = True
            config["colors"][k] = newColor

        writeConfig(config)
        _global_config = config
        i18n_reset()
        signals.configSaved.emit({"colorsChanged": colorsChanged})


def defaultConfig() -> CONFIG_TYPE:
    config: CONFIG_TYPE = {
        "tab_behaviour": {
            "tab_hide_menu_btn": False,
            "tab_max_chars": 30,
            "tab_height": 30,
            "tab_font_size": 12,
            "tab_font_bold": True,
            "tab_hide_filesize": False,
            "tab_ellipsis": True,
            "tab_drag_middle_btn": True,
            "tab_drag_left_btn": True,
            "tab_drag_deadzone": 10,
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
            "Save Layout As…": "Save Layout As…",
            "Save Current Layout": "Save Current Layout",
            "Open Layout": "Open Layout",
            "Unlock Layout": "Unlock Layout",
            "Lock Layout": "Lock Layout",
        },
        "toggle": {
            "split_panes": True,
            "restore_layout": False,
            "zoom_constraint_hint": False,
            "toolbar_icons": True,
            "shared_tool": True,
            "hide_floating_message": False,
            "toggle_docking": True,
        },
        "colors": {
            # NOTE these are camelCase for convenient lookup
            "bar": "",
            "tab": "",
            "tabSeparator": "",
            "tabSelected": "",
            "tabActive": "",
            "tabClose": "",
            "splitHandle": "",
            "dropZone": "",
            "dragTab": "",
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
    key = listArgs.pop()

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
        item = typing.cast(CONFIG_SECTION_TYPE, item)
        item[key] = val
        writeConfig(_global_config)


def readConfig():
    app = Krita.instance()
    defaults = defaultConfig()
    try:
        config = json.loads(app.readSetting("krita_ui_tweaks", "options", ""))
        assert isinstance(config, dict)
        config = typing.cast(CONFIG_TYPE, config)
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


def writeConfig(config: CONFIG_TYPE):
    app = Krita.instance()
    app.writeSetting("krita_ui_tweaks", "options", json.dumps(config))


def showOptions(controller: HasColorScheme):
    dlg = SettingsDialog(controller=controller)
    if dlg.exec() == QDialog.Accepted:
        dlg.onAccepted()
