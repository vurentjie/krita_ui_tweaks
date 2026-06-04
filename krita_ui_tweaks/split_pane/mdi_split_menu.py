from ..pyqt import (
    Qt,
    QWidget,
    QToolButton,
    QPalette,
    QColor,
    QMenu,
    QAction,
    QPoint,
    QTimer,
    QStyle,
    QStylePainter,
    QStyleOption,
    QStyleOptionToolButton,
    QSize,
    QPaintEvent,
    QIcon,
    QPixmap,
    QTransform,
    QMessageBox,
)

from ..options import (
    getOpt,
    showOptions,
)

from ..i18n import i18n

from krita import View, Document
from typing import Any, TYPE_CHECKING
from types import SimpleNamespace
from builtins import reversed
from dataclasses import dataclass, replace, fields

import typing
import re
import math
import json
import os
import time


@dataclass
class MenuData:
    text: str
    callback: typing.Callable[..., Any] | QMenu
    visible: bool = True
    enabled: bool = True
    separator: bool = False


if TYPE_CHECKING:
    from .mdi_split_pane import MdiSplitPane
    from .mdi_controller import MdiController


class MdiMenuButton(QToolButton):

    DARK_ICON = None
    LIGHT_ICON = None

    def __init__(self, parent: QWidget, controller: "MdiController"):
        super().__init__(parent)
        self._controller = controller
        self._helper = controller._helper
        self._menu: QMenu | None = None
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(True)
        self.refreshIcon()
        self.updateHeight()
        self.clicked.connect(lambda: self.showMenu())

    def refreshIcon(self):
        self.setIcon(
            self.darkMenuIcon()
            if self._helper.useDarkIcons()
            else self.lightMenuIcon()
        )

    def updateHeight(self):
        self.setFixedSize(40, getOpt("tab_behaviour", "tab_height"))

    def pane(self) -> "MdiSplitPane|None":
        from .mdi_split_pane import MdiSplitPane

        w = self.parentWidget()
        while w is not None:
            pane = self._helper.isAlive(w, MdiSplitPane)
            if pane is not None:
                return pane
            w = w.parentWidget()

    def showMenu(self, tabIndex: int = -1, tabPos: QPoint = QPoint()):
        self._menu = self._helper.isAlive(self._menu, QMenu)
        if self._menu is None:
            self._menu = QMenu(self)
            self._menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

            textColor = self._menu.palette().color(QPalette.ColorRole.Text)
            textColor.setAlpha(50)
            color = textColor.name(QColor.NameFormat.HexArgb)

            self._menu.setStyleSheet(f"""
                QMenu {{ padding-top: 10px; border: 0; padding-bottom: 10px; }}
                QMenu::separator {{ height:1px; margin: 10px 0; background: {color}; }}
            """)

        splitPane = self.pane()

        if not splitPane:
            return

        split = splitPane.parentSplit()
        tabs = splitPane.tabs()

        if split is None or tabs is None:
            return

        self._controller.setActiveSplitPane(splitPane)

        showMenuBtn = not getOpt("tab_behaviour", "tab_hide_menu_btn")
        tabCount = tabs.count()
        hasTwoTabs = tabCount > 1
        locked = self._controller.isLayoutLocked()
        tabSelected = tabIndex >= 0
        unlocked = not locked

        currentLayout = self._controller.currentLayoutName()
        saveCurrentLayoutEntry = (
            i18n("Save Current Layout") + f" ({currentLayout})"
        )
        lockLayoutEntry = (
            i18n("Lock Layout") if unlocked else i18n("Unlock Layout")
        )

        tabEntryVisible = tabSelected
        otherEntryVisible = not tabSelected or not showMenuBtn
        
        windowSubMenu = None

        if tabEntryVisible:
            components = self._controller._plugin.getValidatedComponents()

            windowSubMenu = QMenu(i18n("Open in window…"), self)
            sortedInstances = sorted(
                components, key=lambda obj: obj["created"]
            )

            winPrefix = i18n("Window")
            view = splitPane.viewAt(tabIndex)

            for k, v in enumerate(sortedInstances):
                if v != self._controller._componentGroup:
                    c = v["controller"]
                    action = QAction(f"{winPrefix} {k + 1}", self)
                    action.triggered.connect(
                        lambda _, view=view, controller=c: controller.openExternalView(
                            view
                        )
                    )
                    action.setEnabled(True)
                    windowSubMenu.addAction(action)

            def newWindow(_, view=view):
                app = self._helper.getApp()
                currWindows = app.windows()
                app.action("view_newwindow").trigger()
                for w in app.windows():
                    if w not in currWindows:
                        w.activate()
                        w.addView(view.document())
                        self._helper.focusQwin(w.qwindow())
                        break

            action = QAction(i18n("+ New window"), self)
            action.triggered.connect(newWindow)
            action.setEnabled(True)
            windowSubMenu.addAction(action)

        actions: list[MenuData] = [
            # fmt: off
            # label, callback, visible, enabled, separator

            MenuData(i18n("Duplicate Tab"), lambda s=splitPane, i=tabIndex: s.duplicateTab(i), tabEntryVisible, True, True),
            
            MenuData(i18n("Split and Move Left"),  lambda s=split, i=tabIndex: s.makeSplitLeft(s, i),  tabEntryVisible, hasTwoTabs and unlocked),
            MenuData(i18n("Split and Move Right"), lambda s=split, i=tabIndex: s.makeSplitRight(s, i), tabEntryVisible, hasTwoTabs and unlocked),
            MenuData(i18n("Split and Move Above"), lambda s=split, i=tabIndex: s.makeSplitAbove(s, i), tabEntryVisible, hasTwoTabs and unlocked),
            MenuData(i18n("Split and Move Below"), lambda s=split, i=tabIndex: s.makeSplitBelow(s, i), tabEntryVisible, hasTwoTabs and unlocked, True),
            
            MenuData(i18n("Split and Duplicate Left"),  lambda s=split, i=tabIndex: s.makeSplitLeft (s, i, True), tabEntryVisible, unlocked),
            MenuData(i18n("Split and Duplicate Right"), lambda s=split, i=tabIndex: s.makeSplitRight(s, i, True), tabEntryVisible, unlocked),
            MenuData(i18n("Split and Duplicate Above"), lambda s=split, i=tabIndex: s.makeSplitAbove(s, i, True), tabEntryVisible, unlocked),
            MenuData(i18n("Split and Duplicate Below"), lambda s=split, i=tabIndex: s.makeSplitBelow(s, i, True), tabEntryVisible, unlocked, True),
            
            MenuData(i18n("Close Tab"),           lambda s=splitPane, i=tabIndex: s.closeSubWindow(i),   tabEntryVisible),
            MenuData(i18n("Close Tabs To Right"), lambda s=splitPane, i=tabIndex: s.closeTabsToRight(i), tabEntryVisible, hasTwoTabs and tabIndex < tabCount - 1 ),
            MenuData(i18n("Close Tabs To Left"),  lambda s=splitPane, i=tabIndex: s.closeTabsToLeft(i),  tabEntryVisible, tabIndex > 0 ),
            MenuData(i18n("Close Other Tabs"),    lambda s=splitPane, i=tabIndex: s.closeOtherTabs(i),   tabEntryVisible, hasTwoTabs, True),
            
            MenuData(i18n("Close Split Pane"), lambda s=split: s.close(), otherEntryVisible, unlocked, True),
            
            MenuData(i18n("Reset Layout"),   lambda c=self._controller: c.slotResetLayout(),    otherEntryVisible, True, False),
            MenuData(i18n("Equalize Layout"),lambda c=self._controller: c.slotEqualizeLayout(), otherEntryVisible, True, True),
            
            MenuData(i18n("Save Layout As…"), lambda c=self._controller: c.saveLayoutFile(""), otherEntryVisible, True, False),
            MenuData(saveCurrentLayoutEntry,  lambda c=self._controller: c.saveCurrentLayout(), otherEntryVisible and currentLayout, True, False),
            MenuData(i18n("Open Layout"),     lambda c=self._controller: c.openLayoutFile(), otherEntryVisible, True, False),
            MenuData(lockLayoutEntry,         lambda c=self._controller, u=unlocked: c.setLayoutLocked(u), otherEntryVisible, True, True),
            
            MenuData(i18n("Open tab in window…"), windowSubMenu, tabEntryVisible, True, True),
            
            MenuData(i18n("Options"), lambda: showOptions(self._controller), otherEntryVisible, True, True),
            # fmt: on
        ]

        self._menu.clear()

        for a in actions:
            if a.visible:
                if isinstance(a.callback, QMenu):
                    self._menu.addMenu(a.callback)
                else:
                    action = self._menu.addAction(a.text)
                    action.setEnabled(a.enabled)

                    if a.callback:
                        action.triggered.connect(
                            lambda _=None, cb=a.callback: cb()
                        )

                if a.separator:
                    self._menu.addSeparator()

        self._menu.adjustSize()

        btnPos = self.mapToGlobal(self.rect().bottomRight())

        if not tabSelected and showMenuBtn:
            self._menu.exec(
                QPoint(btnPos.x() - self._menu.width(), btnPos.y())
            )
        else:
            self._menu.exec(QPoint(tabPos.x(), btnPos.y()))

    def paintEvent(self, event: QPaintEvent):
        painter = QStylePainter(self)
        opt = QStyleOption()
        opt.initFrom(self)

        painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt)

        rect = event.rect()
        bgColor = (
            self.parentWidget().palette().color(QPalette.ColorRole.Window)
        )
        painter.fillRect(rect, bgColor)

        btnOpt = QStyleOptionToolButton()
        self.initStyleOption(btnOpt)
        painter.drawControl(QStyle.ControlElement.CE_ToolButtonLabel, btnOpt)

    def sizeHint(self) -> QSize:
        return QSize(40, getOpt("tab_behaviour", "tab_height"))

    def darkMenuIcon(self) -> QIcon:
        if not MdiMenuButton.DARK_ICON:
            MdiMenuButton.DARK_ICON = QIcon(
                QPixmap(":/dark_hamburger_menu_dots.svg").transformed(
                    QTransform().rotate(90),
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return MdiMenuButton.DARK_ICON

    def lightMenuIcon(self) -> QIcon:
        if not MdiMenuButton.LIGHT_ICON:
            MdiMenuButton.LIGHT_ICON = QIcon(
                QPixmap(":/light_hamburger_menu_dots.svg").transformed(
                    QTransform().rotate(90),
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return MdiMenuButton.LIGHT_ICON

