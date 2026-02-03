# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    toPoint,
    getEventGlobalPos,
    Qt,
    QWidget,
    QMenu,
    QPushButton,
    QPixmap,
    QIcon,
    QTransform,
    QRect,
    QPoint,
    QPaintEvent,
    QPainter,
    QColor,
    QMouseEvent,
    QAction,
    QResizeEvent,
)

from typing import TYPE_CHECKING

import typing
import os

from ..options import (
    showOptions,
    getOpt,
)

from ..helper import Helper
from ..i18n import i18n

from .split_helpers import MenuAction
from .split_drag import SplitDrag

if TYPE_CHECKING:
    from .split import Split
    from .split_tabs import SplitTabs
    from .split_pane import SplitPane


class SplitToolbar(QWidget):
    MenuIcons = {}

    def __init__(
        self, parent: QWidget, controller: "SplitPane", split: "Split"
    ):
        from .split_tabs import SplitTabs

        super().__init__(parent)
        self.setObjectName("SplitToolbar")
        self._split: "Split" = split
        self._controller: "SplitPane" = controller
        self._helper: "Helper" = controller.helper()
        self._tabs: SplitTabs = SplitTabs(self, controller=controller)
        self._menu: QMenu | None = None
        self._menuBtn: QPushButton | None = None
        if not SplitToolbar.MenuIcons:
            pix = QPixmap(":/dark_hamburger_menu_dots.svg")
            transform = QTransform().rotate(90)
            rotated = pix.transformed(transform)
            SplitToolbar.MenuIcons["hamburger_dark"] = QIcon(rotated)

            pix = QPixmap(":/light_hamburger_menu_dots.svg")
            transform = QTransform().rotate(90)
            rotated = pix.transformed(transform)
            SplitToolbar.MenuIcons["hamburger_light"] = QIcon(rotated)

        self.showMenuBtn()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) 
        self.setMouseTracking(True)

    def globalRect(self) -> QRect:
        qwin = self._helper.getQwin()
        mdi = self._helper.getMdi()
        if qwin and mdi:
            rect = self.geometry()
            return QRect(
                mdi.mapTo(qwin, QPoint(rect.x(), rect.y())),
                rect.size(),
            )
        return QRect()
        
    def showMenuBtn(self):
        if not self._menuBtn and not getOpt(
            "tab_behaviour", "tab_hide_menu_btn"
        ):
            val = "dark" if self._helper.useDarkIcons() else "light"
            self._menuBtn = QPushButton("", self)
            self._menuBtn.setIcon(SplitToolbar.MenuIcons[f"hamburger_{val}"])
            self._menuBtn.setProperty("class", "menuButton")
            self._menuBtn.setFixedSize(38, self._tabs.height())
            self._menuBtn.clicked.connect(self.showMenu)

    def updateMenuBtn(self):
        if self._menuBtn:
            val = "dark" if self._helper.useDarkIcons() else "light"
            self._menuBtn.setIcon(SplitToolbar.MenuIcons[f"hamburger_{val}"])

    def hideMenuBtn(self):
        if self._menuBtn:
            self._menuBtn.deleteLater()
            self._menuBtn = None

    def setSplit(self, split: "Split"):
        self._split = split

    def split(self) -> "Split":
        return self._split

    def tabs(self) -> "SplitTabs":
        return self._tabs

    def showMenu(self, event: QMouseEvent, tabIndex: int | None = None):
        topSplit = self._split.topSplit()
        assert topSplit is not None

        hasTabIndex = tabIndex is not None
        hasTabs = self._tabs.count() > 1

        from .split import Split

        hasSplits = topSplit.state() == Split.STATE_SPLIT

        isLocked = self._controller.isLocked()

        layoutPath = self._controller.getLayoutPath()
        layoutName = os.path.basename(layoutPath) if layoutPath else None
        if layoutName and layoutName.endswith(".json"):
            layoutName = layoutName[:-5]

        actions: list[MenuAction] = [
            MenuAction(
                text=i18n("Duplicate Tab"),
                callback=lambda: self._controller.syncView(
                    view=self._tabs.getView(
                        self._tabs.currentIndex()
                        if tabIndex is None
                        else tabIndex
                    ),
                    split=self._split,
                    addView=True,
                ),
                separator=True,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Left"),
                callback=lambda: self._split.makeSplitLeft(tabIndex=tabIndex),
                enabled=hasTabs and not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Right"),
                callback=lambda: self._split.makeSplitRight(tabIndex=tabIndex),
                enabled=hasTabs and not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Above"),
                callback=lambda: self._split.makeSplitAbove(tabIndex=tabIndex),
                enabled=hasTabs and not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Below"),
                callback=lambda: self._split.makeSplitBelow(tabIndex=tabIndex),
                enabled=hasTabs and not isLocked,
                separator=True,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Left"),
                callback=lambda: self._split.makeSplitLeft(
                    dupe=True, tabIndex=tabIndex
                ),
                enabled=not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Right"),
                callback=lambda: self._split.makeSplitRight(
                    dupe=True, tabIndex=tabIndex
                ),
                enabled=not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Above"),
                callback=lambda: self._split.makeSplitAbove(
                    dupe=True, tabIndex=tabIndex
                ),
                enabled=not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Below"),
                callback=lambda: self._split.makeSplitBelow(
                    dupe=True, tabIndex=tabIndex
                ),
                separator=True,
                enabled=not isLocked,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Close Tabs To Right"),
                callback=lambda: self._tabs.closeTabsRight(tabIndex),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Close Tabs To Left"),
                callback=lambda: self._tabs.closeTabsLeft(tabIndex),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Close Other Tabs"),
                callback=lambda: self._tabs.closeTabsOther(tabIndex),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Close Split Pane"),
                callback=lambda: self._split.close(),
                enabled=not isLocked,
                separator=True,
            ),
            MenuAction(
                text=i18n("Reset Layout"),
                enabled=not isLocked,
                callback=lambda: self._split.resetLayout(),
            ),
            MenuAction(
                text=i18n("Reset Sizes"),
                callback=lambda: typing.cast(
                    Split, self._split.topSplit()
                ).equalize(),
                enabled=hasSplits,
                separator=True,
            ),
            MenuAction(
                text=i18n("Save Layout As…"),
                callback=lambda: self._split.saveLayout(),
            ),
            MenuAction(
                text=i18n("Save Current Layout") + f" ({layoutName})",
                callback=lambda: self._split.saveLayout(layoutPath),
                visible=layoutPath is not None,
            ),
            MenuAction(
                text=i18n("Open Layout"),
                callback=lambda: self._split.loadLayout(),
            ),
            MenuAction(
                text=i18n("Lock Layout"),
                callback=lambda: self._controller.lock(),
                visible=not isLocked,
                separator=True,
            ),
            MenuAction(
                text=i18n("Unlock Layout"),
                callback=lambda: self._controller.unlock(),
                visible=isLocked,
                separator=True,
            ),
            MenuAction(
                text=i18n("Options"),
                callback=lambda: showOptions(self._controller),
            ),
        ]

        if self._menu is None:
            self._menu = QMenu(self)
            self._menu.setProperty("class", "splitPaneMenu")
        self._menu.clear()

        for a in actions:
            if a.visible:
                action = QAction(a.text, self)
                action.triggered.connect(a.callback)
                action.setEnabled(a.enabled)
                self._menu.addAction(action)
                if a.separator:
                    self._menu.addSeparator()

        self._menu.adjustSize()

        pos = self.mapToGlobal(self.rect().bottomRight())
        if tabIndex is not None:
            tabPos = toPoint(getEventGlobalPos(event))
            self._menu.exec(QPoint(tabPos.x(), pos.y()))
        else:
            pos = QPoint(pos.x() - self._menu.width() + 1, pos.y())
            self._menu.exec(pos)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        x = self.width()
        offset = 0
        for btn in [self._menuBtn]:
            if btn:
                offset += btn.width()
                x = self.width() - offset
                y = (self.height() - btn.height()) // 2
                btn.move(x, y)
            
        self._tabs.setFixedHeight(self.height())
        self._tabs.setGeometry(0, 0, x, self.height())

    def makeActiveToolbar(self):
        from .split import Split

        if not self._helper.isAlive(self._split, Split):
            return

        controller = self._controller
        controller.setActiveToolbar(self)
        view = self._split.getActiveTabView()
        if view:
            kritaTab = controller.getIndexByView(view)
            if kritaTab != -1:
                controller.syncView(index=kritaTab, split=self._split)

