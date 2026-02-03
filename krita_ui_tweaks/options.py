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
    QMessageBox,
    QMouseEvent,
    QObject,
    QPainter,
    QPaintEvent,
    QPen,
    QPoint,
    QPushButton,
    QRect,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from krita import Krita
from dataclasses import dataclass, fields
from types import SimpleNamespace
from typing import Any

from .i18n import i18n, i18n_reset
from .colors import ColorScheme, HasColorScheme

import os
import json
import typing
import time

VERSION = "1.1.0"


@dataclass
class ConfigVal:
    default: str | bool | int | float
    clamp: tuple[int | float, int | float] | None = None
    options: dict[str, str] | None = None


CONFIG_SECTION_TYPE = dict[str, ConfigVal]
CONFIG_DEFAULTS_TYPE = dict[str, CONFIG_SECTION_TYPE]
CONFIG_TYPE = dict[str, dict[str, int | bool | float | str]]

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
class FormItem:
    section: str | None = None
    extra: QWidget | list[QWidget] | None = None
    label: QLabel | None = None
    subtitle: QLabel | None = None
    section: str | None = None
    spaceAbove: int = 0
    spaceBelow: int = 0
    separator: bool = False


@dataclass
class ColorItem(FormItem):
    input: ColorButton | None = None


@dataclass
class ToggleItem(FormItem):
    input: QCheckBox | None = None


@dataclass
class ComboItem(FormItem):
    input: QComboBox | None = None
    options: dict[str, str] | None = None
    singleLine: bool = False


@dataclass
class SliderItem(FormItem):
    input: QSlider | None = None
    steps: int | None = None


@dataclass
class InputItem(FormItem):
    input: QLineEdit | None = None
    escape: bool | None = None


@dataclass
class NumberItem(FormItem):
    input: QSpinBox | None = None
    clamp: tuple[int | float, int | float] | None = None


FormItemType = (
    ToggleItem | NumberItem | InputItem | ColorItem | ComboItem | SliderItem
)
FormItems = dict[str, FormItemType]


def spacer(form: QFormLayout, size: int):
    spacer = QWidget()
    spacer.setFixedHeight(size)
    form.addRow(spacer)


def line(form: QFormLayout):
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    form.addRow(line)


class Signals(QObject):
    configSaved = pyqtSignal(object)


signals = Signals()


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        controller: HasColorScheme | None = None,
        pos: QRect | None = None,
        tabIndex: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(i18n("UI Tweaks"))
        self.setMinimumWidth(400)
        self.setMinimumHeight(800)

        if isinstance(pos, QRect):
            self.setGeometry(pos)

        self._controller = controller
        self._helper = self._controller.helper()
        self.setupLayout()

        if isinstance(tabIndex, int):
            self.tabs.setCurrentIndex(tabIndex)

    def setupLayout(self):
        self._config: CONFIG_DEFAULTS_TYPE = readConfig()

        val = "dark" if self._helper.useDarkIcons() else "light"
        self._resetIcon = QIcon(f":/{val}_reload-preset.svg")

        sections = SimpleNamespace(
            tabAppearance=i18n("Tab Appearance"),
            tabDragging=i18n("Tab Dragging"),
            splitPanes=i18n("Split Panes"),
            fitMode=i18n("Fit To View"),
            scalingMode=i18n("Scaling mode"),
            tools=i18n("Tools"),
            dockers=i18n("Dockers"),
            colors=i18n("Colors"),
        )
        defaults = defaultConfig()

        self._translated: FormItems = {}

        for k in self._config.get("translated", {}).keys():
            self._translated[k] = InputItem(
                input=QLineEdit(),
                escape=True,
                section="",
                label=QLabel(self._unescape(k)),
            )

        self._tabBehaviour: FormItems = {
            "tab_max_chars": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Max characters to show")),
                clamp=defaults["tab_behaviour"]["tab_max_chars"].clamp,
                section=sections.tabAppearance,
            ),
            "tab_height": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab height")),
                clamp=defaults["tab_behaviour"]["tab_height"].clamp,
                section=sections.tabAppearance,
            ),
            "tab_font_size": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Tab font size")),
                clamp=defaults["tab_behaviour"]["tab_font_size"].clamp,
                section=sections.tabAppearance,
            ),
            "tab_font_bold": ToggleItem(
                input=QCheckBox(i18n("Tab font bold")),
                section=sections.tabAppearance,
            ),
            "tab_hide_filesize": ToggleItem(
                input=QCheckBox(i18n("Hide the file size")),
                section=sections.tabAppearance,
            ),
            "tab_ellipsis": ToggleItem(
                input=QCheckBox(
                    i18n("Show ellipsis (…) when tab text is truncated")
                ),
                section=sections.tabAppearance,
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
            "tab_krita_style": ToggleItem(
                input=QCheckBox(
                    i18n("Use Krita's default style for tabs")
                ),
                section=sections.tabAppearance,
            ),
            "tab_drag_middle_btn": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Splits can be created by dragging with the middle button"
                    )
                ),
                section=sections.tabDragging,
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
                spaceBelow=10,
            ),
            "tab_drag_deadzone": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Drag deadzone")),
                clamp=defaults["tab_behaviour"]["tab_drag_deadzone"].clamp,
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
            "toolbar_icons": ToggleItem(
                input=QCheckBox(i18n("Highlight active tool in toolbars")),
                section=sections.tools,
            ),
            "shared_tool": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Do not change the active tool when switching documents"
                    )
                ),
                section=sections.tools,
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
            ),
        }

        self._resize: FormItems = {
            "split_handle_size": NumberItem(
                input=QSpinBox(),
                label=QLabel(i18n("Split handle size")),
                clamp=defaults["resize"]["split_handle_size"].clamp,
                section="",
                separator=True,
                extra=QLabel(i18n("<b>Requires restart</b>")),
            ),
            "restore_fit_mode": ToggleItem(
                input=QCheckBox(),
                label=QLabel(
                    i18n(
                        "Restore position when toggling <i>'Fit to View'</i>, <i>'Fit to Width'</i> or <i>'Fit to Height'</i>"
                    ),
                ),
                section=sections.fitMode,
                spaceBelow=10,
            ),
            
            "scaling_mode_per_view": ToggleItem(
                input=QCheckBox(i18n("Scaling mode is enabled per view instead of globally")),
                section=sections.scalingMode,
            ),
            "default_scaling_mode": ComboItem(
                input=QComboBox(),
                label=QLabel(i18n("Default scaling mode")),
                singleLine=True,
                options=defaults["resize"]["default_scaling_mode"].options,
                section=sections.scalingMode,
                extra=QLabel(
                    i18n(
                        "<b>Default scaling mode will be set when Krita starts up.</b>"
                    )
                ),
                spaceBelow=10,
            ),
            "scaling_contained_only": ToggleItem(
                subtitle=QLabel(i18n("<b>Only apply scaling when:</b>")),
                input=QCheckBox(i18n("Canvas is contained in the viewport")),
                section=sections.scalingMode,
            ),
            "scaling_contained_partial": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Canvas is smaller than the viewport (but partially out of view)"
                    )
                ),
                section=sections.scalingMode,
            ),
            "scaling_contained_shorter": ToggleItem(
                input=QCheckBox(
                    i18n(
                        "Canvas is either shorter or narrower than the viewport"
                    )
                ),
                section=sections.scalingMode,
            ),
        }

        colorLabels: dict[str, str] = {
            "bar": i18n("Tab bar background *"),
            "tab": i18n("Tab background *"),
            "tabSelected": i18n("Tab selected background"),
            "tabActive": i18n("Tab active background"),
            "tabSeparator": i18n("Tab separator *"),
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
        for i, k in enumerate(colorLabels.keys()):
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
                subtitle=QLabel(i18n("Marked colors (*) are not applied when using Krita's default style for tabs") + "<br>") if i == 0 else None, 
                label=QLabel(colorLabels[k]),
                section=sections.colors,
            )

        self.tabs = QTabWidget()
        self.optionsTab = self._setupOptionsTab()
        self.resizeTab = self._setupResizeTab()
        self.translateTab = self._setupTranslateTab()
        self.behaviourTab = self._setupBehaviourTab()
        self.colorsTab = self._setupColorsTab()
        self.aboutTab = self._setupAboutTab()

        self.tabs.addTab(self.optionsTab, i18n("Options"))
        self.tabs.addTab(self.resizeTab, i18n("Resizing"))
        self.tabs.addTab(self.behaviourTab, i18n("Tabs"))
        self.tabs.addTab(self.colorsTab, i18n("Colors"))
        self.tabs.addTab(self.translateTab, i18n("Translate"))
        self.tabs.addTab(self.aboutTab, i18n("About"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        if not self.layout():
            layout = QVBoxLayout(self)
        else:
            layout = self.layout()

        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

        restore = QPushButton(i18n(" Restore Defaults "), self)
        restore.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        restore.setFixedWidth(restore.sizeHint().width())
        restore.clicked.connect(self.onRestore)
        self.adjustSize()
        restore.move(10, buttons.y())

    def _unescape(self, val: str) -> str:
        return val.replace("&&", "&")

    def _escape(self, val: str) -> str:
        return val.replace("&", "&&")

    def _getFormValue(self, item: FormItemType) -> typing.Any:
        t = type(item)
        assert item.input is not None
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
        elif t in (ColorItem, NumberItem, SliderItem):
            return item.input.value()

    def _renderFormItem(
        self, form: QFormLayout, key: tuple[str, str], item: FormItemType
    ) -> QWidget | None:
        t = type(item)
        assert item.input is not None

        itemSection = key[0]
        itemKey = key[1]

        def resetable(
            widget: QWidget | QHBoxLayout,
            callback: Any = None,
            item=item,
            itemKey=itemKey,
            itemSection=itemSection,
        ):
            reset = QPushButton()
            reset.setIcon(self._resetIcon)
            reset.setToolTip(i18n("Reset to default"))
            if callback is None:

                def cb(key=key, item=item):
                    t = type(item)
                    default = getDefaultOpt(itemSection, itemKey)
                    assert item.input is not None
                    if t == ToggleItem:
                        item.input.setChecked(default)
                    elif t == InputItem:
                        val = item.input.text()
                        if itemSection == "translated":
                            item.input.setText("")
                        else:
                            item.input.setText(default)
                    elif t in (NumberItem, SliderItem):
                        item.input.setValue(default)
                    elif t == ComboItem:
                        index = item.input.findData(default)
                        if index != -1:
                            item.input.setCurrentIndex(index)

                reset.clicked.connect(cb)
            else:
                reset.clicked.connect(callback)
            reset.setFixedWidth(30)

            if isinstance(widget, QHBoxLayout):
                widget.addWidget(reset)
                return widget
            else:
                block = QWidget()
                row = QHBoxLayout(block)
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(widget)
                row.addWidget(reset)
                return block

        if item.spaceAbove:
            spacer(form, item.spaceAbove)
        if item.subtitle:
            item.subtitle.setTextFormat(Qt.TextFormat.RichText)
            form.addRow(item.subtitle)

        if t == ToggleItem:
            item.input.setChecked(typing.cast(bool, getOpt(*key)))

            if item.label:
                item.input.setText("")
                item.input.setStyleSheet("QCheckBox { padding-right: 1px; }")
                item.input.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
                )
                item.input.setFixedSize(item.input.sizeHint())
                item.label.setTextFormat(Qt.TextFormat.RichText)
                block = QWidget()

                v = QHBoxLayout(block)
                v.setSpacing(0)
                v.setContentsMargins(0, 0, 0, 0)
                v.addWidget(item.input)
                v.addWidget(item.label)

                row = resetable(block)
                form.addRow(row)

            else:
                row = resetable(item.input)
                form.addRow(row)

        elif t == InputItem:
            item = typing.cast(InputItem, item)
            assert item.input is not None
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
            row = resetable(item.input)
            v.addWidget(row)
            form.addRow(block)

        elif t == NumberItem:
            item = typing.cast(NumberItem, item)
            assert item.input is not None
            assert item.label is not None
            assert item.clamp is not None
            item.input.setRange(item.clamp[0], item.clamp[1])
            item.input.setFixedWidth(100)
            item.input.setValue(getOpt(*key))
            item.label.setTextFormat(Qt.TextFormat.RichText)
            block = QWidget()
            v = QHBoxLayout(block)
            v.setSpacing(0)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(item.label)
            v.addWidget(item.input)
            row = resetable(block)
            form.addRow(row)
        elif t == SliderItem:
            item = typing.cast(SliderItem, item)
            assert item.input is not None
            assert item.label is not None
            assert item.steps is not None
            item.input.setRange(0, item.steps)
            item.input.setValue(getOpt(*key))
            item.input.setFixedWidth(200)
            item.label.setTextFormat(Qt.TextFormat.RichText)
            block = QWidget()
            v = QHBoxLayout(block)
            v.setSpacing(0)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(item.label)
            v.addWidget(item.input)
            row = resetable(block)
            form.addRow(row)
        elif t == ComboItem:
            item = typing.cast(ComboItem, item)
            val = typing.cast(str, getOpt(*key))
            assert item.input is not None
            assert item.label is not None
            assert item.options is not None
            index = 0
            for i, (k, t) in enumerate(item.options.items()):
                if val == k:
                    index = i
                item.input.addItem(t, k)
            item.input.setCurrentIndex(index)
            item.label.setTextFormat(Qt.TextFormat.RichText)

            if item.singleLine:
                block = QWidget()
                v = QHBoxLayout(block)
                v.setSpacing(0)
                v.setContentsMargins(0, 0, 0, 0)
                v.addWidget(item.label)
                v.addWidget(item.input)
                row = resetable(block)
                form.addRow(row)
            else:
                block = QWidget()
                v = QVBoxLayout(block)
                v.setContentsMargins(0, 0, 0, 0)
                v.addWidget(item.label)
                row = resetable(item.input)
                v.addWidget(row)
                form.addRow(row)

        elif t == ColorItem:
            item = typing.cast(ColorItem, item)
            assert item.input is not None

            block = QWidget()
            v = QHBoxLayout(block)
            v.setContentsMargins(0, 0, 0, 0)
            v.addWidget(item.input)
            v.addWidget(item.label)
            row = resetable(block, item.input.reset)
            form.addRow(row)

        if item.extra:
            if not isinstance(item.extra, list):
                item.extra = [item.extra]

            field = QHBoxLayout()
            for extra in item.extra:
                if isinstance(extra, QLabel):
                    extra.setTextFormat(Qt.TextFormat.RichText)
                    extra.setEnabled(False)
                field.addWidget(extra)
                field.setContentsMargins(20 if t == ToggleItem else 0, 0, 0, 0)
            form.addRow(field)

        if item.spaceBelow:
            spacer(form, item.spaceBelow)

    def _renderTabForm(self, configKey: str, formItems):
        tab = QWidget()
        form = QFormLayout(tab)
        section = ""
        for index, (key, item) in enumerate(formItems.items()):
            if item.section != section:
                section = item.section
                if index > 0 and (item.separator or len(section) > 0):
                    spacer(form, 3)
                    line(form)
                    spacer(form, 3)
                if item.section:
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

    def _setupResizeTab(self):
        return self._renderTabForm("resize", self._resize)

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
        updated = {}

        def checkVal(section, key, item) -> Any:
            old = config[section].get(key, None)
            new = self._getFormValue(item)
            if old != new:
                updated[section] = updated.get(section, {})
                updated[section][key] = True
            return new

        for k, v in self._translated.items():
            config["translated"][k] = checkVal("translated", k, v)

        for k, v in self._tabBehaviour.items():
            config["tab_behaviour"][k] = checkVal("tab_behaviour", k, v)

        for k, v in self._toggle.items():
            val = checkVal("toggle", k, v)
            config["toggle"][k] = val
            if k == "restore_layout" and val:
                Krita.instance().writeSetting("", "sessionOnStartup", "0")

        for k, v in self._resize.items():
            val = checkVal("resize", k, v)
            config["resize"][k] = val
            if k == "restore_layout" and val:
                Krita.instance().writeSetting("", "sessionOnStartup", "0")

        schemeColors = self._controller.colors()
        colorsChanged = False
        configColors = self._config.get("colors", {})

        for k, v in self._colors.items():
            color = self._getFormValue(v)
            currColor = configColors.get(k, "")
            resetColor = getattr(schemeColors, k, None)
            newColor = "" if color == resetColor else color
            if newColor != currColor:
                updated["colors"] = updated.get("colors", {})
                updated["colors"][k] = True
                colorsChanged = True
            config["colors"][k] = newColor

        writeConfig(config)
        _global_config = config
        i18n_reset()
        signals.configSaved.emit(updated)

    def onRestore(self):
        choice = QMessageBox.question(
            None,
            "Krita",
            i18n("Restore all settings to the defaults.")
            + "\n\n"
            + i18n("Are you sure?"),
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.No,
        )

        if choice == QMessageBox.StandardButton.Yes:

            defaults = defaultConfig()
            config = {}

            config = typing.cast(CONFIG_TYPE, config)
            for section in defaults.keys():
                if not isinstance(config.get(section, None), dict):
                    config[section] = {}

                for k, v in defaults[section].items():
                    s = config[section]
                    curr = s.get(k, None)
                    if curr is None or type(curr) != type(v.default):
                        s[k] = v.default
                    if v.clamp:
                        s[k] = max(s[k], v.clamp[0])
                        s[k] = min(s[k], v.clamp[1])
                    if v.options and s[k] not in v.options:
                        s[k] = v.default

            writeConfig(config)

            global _global_config
            _global_config = None

            controller = self._controller
            pos = self.geometry()
            tabIndex = self.tabs.currentIndex()
            self.close()
            showOptions(controller=controller, pos=pos, tabIndex=tabIndex)


def defaultConfig() -> CONFIG_DEFAULTS_TYPE:
    config: CONFIG_DEFAULTS_TYPE = {
        "tab_behaviour": {
            "tab_hide_menu_btn": ConfigVal(default=False),
            "tab_max_chars": ConfigVal(default=30, clamp=(10, 100)),
            "tab_height": ConfigVal(default=30, clamp=(20, 50)),
            "tab_font_size": ConfigVal(default=12, clamp=(8, 20)),
            "tab_font_bold": ConfigVal(default=True),
            "tab_hide_filesize": ConfigVal(default=False),
            "tab_ellipsis": ConfigVal(default=True),
            "tab_krita_style": ConfigVal(default=True),
            "tab_drag_middle_btn": ConfigVal(default=True),
            "tab_drag_left_btn": ConfigVal(default=True),
            "tab_drag_deadzone": ConfigVal(default=10, clamp=(10, 50)),
        },
        "translated": {
            "Duplicate Tab": ConfigVal(default="Duplicate Tab"),
            "Split && Move Left": ConfigVal(default="Split && Move Left"),
            "Split && Move Right": ConfigVal(default="Split && Move Right"),
            "Split && Move Above": ConfigVal(default="Split && Move Above"),
            "Split && Move Below": ConfigVal(default="Split && Move Below"),
            "Split && Duplicate Left": ConfigVal(
                default="Split && Duplicate Left"
            ),
            "Split && Duplicate Right": ConfigVal(
                default="Split && Duplicate Right"
            ),
            "Split && Duplicate Above": ConfigVal(
                default="Split && Duplicate Above"
            ),
            "Split && Duplicate Below": ConfigVal(
                default="Split && Duplicate Below"
            ),
            "Close Tabs To Right": ConfigVal(default="Close Tabs To Right"),
            "Close Tabs To Left": ConfigVal(default="Close Tabs To Left"),
            "Close Other Tabs": ConfigVal(default="Close Other Tabs"),
            "Close Split Pane": ConfigVal(default="Close Split Pane"),
            "Reset Layout": ConfigVal(default="Reset Layout"),
            "Reset Sizes": ConfigVal(default="Reset Sizes"),
            "Options": ConfigVal(default="Options"),
            "Toggle docking": ConfigVal(default="Toggle docking"),
            "Docking enabled": ConfigVal(default="Docking enabled"),
            "Docking disabled": ConfigVal(default="Docking disabled"),
            "Goto next tab": ConfigVal(default="Goto next tab"),
            "Goto previous tab": ConfigVal(default="Goto previous tab"),
            "Save Layout As…": ConfigVal(default="Save Layout As…"),
            "Save Current Layout": ConfigVal(default="Save Current Layout"),
            "Open Layout": ConfigVal(default="Open Layout"),
            "Unlock Layout": ConfigVal(default="Unlock Layout"),
            "Lock Layout": ConfigVal(default="Lock Layout"),
        },
        "toggle": {
            "split_panes": ConfigVal(default=True),
            "restore_layout": ConfigVal(default=False),
            "toolbar_icons": ConfigVal(default=True),
            "shared_tool": ConfigVal(default=True),
            "hide_floating_message": ConfigVal(default=False),
            "toggle_docking": ConfigVal(default=True),
        },
        "resize": {
            "scaling_mode_per_view": ConfigVal(default=False),
            "default_scaling_mode": ConfigVal(
                default="none",
                options={
                    "none": i18n("None"),
                    "anchored": i18n("Scaling Mode Anchored"),
                    "contained": i18n("Scaling Mode Contained"),
                    "expanded": i18n("Scaling Mode Expanded"),
                },
            ),
            "split_handle_size": ConfigVal(default=8, clamp=(4, 12)),
            "restore_fit_mode": ConfigVal(default=True),
            "scaling_contained_only": ConfigVal(default=False),
            "scaling_contained_partial": ConfigVal(default=False),
            "scaling_contained_shorter": ConfigVal(default=False),
        },
        "colors": {
            "bar": ConfigVal(default=""),
            "tab": ConfigVal(default=""),
            "tabSeparator": ConfigVal(default=""),
            "tabSelected": ConfigVal(default=""),
            "tabActive": ConfigVal(default=""),
            "tabClose": ConfigVal(default=""),
            "splitHandle": ConfigVal(default=""),
            "dropZone": ConfigVal(default=""),
            "dragTab": ConfigVal(default=""),
        },
    }
    return config


def getDefaultOpt(section, item) -> Any:
    defaults = defaultConfig()
    if not defaults:
        return

    items = defaults.get(section, None)
    if isinstance(items, dict):
        cfg = items.get(item, None)
        if isinstance(cfg, ConfigVal):
            return cfg.default


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
    defaults = defaultConfig()
    try:
        app = Krita.instance()
        config = json.loads(app.readSetting("krita_ui_tweaks", "options", ""))
    except:
        config = {}

    assert isinstance(config, dict)
    config = typing.cast(CONFIG_TYPE, config)
    for section in defaults.keys():
        if not isinstance(config.get(section, None), dict):
            config[section] = {}

        for k, v in defaults[section].items():
            s = config[section]
            curr = s.get(k, None)
            if curr is None or type(curr) != type(v.default):
                s[k] = v.default
            if v.clamp:
                s[k] = max(s[k], v.clamp[0])
                s[k] = min(s[k], v.clamp[1])
            if v.options and s[k] not in v.options:
                s[k] = v.default

    return config


def writeConfig(config: CONFIG_TYPE):
    app = Krita.instance()
    app.writeSetting("krita_ui_tweaks", "options", json.dumps(config))


def showOptions(
    controller: HasColorScheme,
    pos: QRect | None = None,
    tabIndex: int | None = None,
):
    dlg = SettingsDialog(controller=controller, pos=pos, tabIndex=tabIndex)
    if dlg.exec() == QDialog.Accepted:
        dlg.onAccepted()
