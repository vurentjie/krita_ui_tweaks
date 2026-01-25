# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    toPoint,
    getEventGlobalPos,
    getEventPos,
    pyqtSignal,
    Qt,
    QTabBar,
    QMouseEvent,
    QTimer,
    QPoint,
    QMdiSubWindow,
    QWidget,
    QEvent,
    QColor,
    QRect,
    QWheelEvent,
)

from krita import View
from typing import Any, TYPE_CHECKING

import typing

from .split_helpers import SplitData
from .split import Split
from .split_drag import SplitDrag

if TYPE_CHECKING:
    from .split_toolbar import SplitToolbar
    from .split_pane import SplitPane


class SplitTabs(QTabBar):
    tabPress = pyqtSignal(QMouseEvent, int)
    tabRelease = pyqtSignal(QMouseEvent, int)

    def __init__(self, parent: "SplitToolbar", controller: "SplitPane"):
        super().__init__(parent)
        self.setObjectName("SplitTabs")
        self._wheelAccumulator = 0
        self._controller = controller
        self._helper = controller.helper()
        self._draggable = SplitDrag(self)

        self.setExpanding(False)
        self.setMouseTracking(True)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.tabCloseRequested.connect(self.purgeTab)
        self.setMinimumHeight(0)
        self.setMinimumWidth(0)

        self.currentChanged.connect(self.onCurrentChange)

    def _sync(self, index: int):
        helper = self._helper
        uid = self.getUid(index)
        data = self._controller.getSplitData(uid)
        mdi = helper.getMdi()
        if mdi:
            subwin = mdi.activeSubWindow()
            if data and data.win != subwin:
                self._controller.syncView(split=self.split(), view=data.view)

    def exec(
        self,
        callback: typing.Callable[[int, "SplitData"], Any],
        index: int | None = None,
        view: View | None = None,
        context: dict[str, Any] | None = None,
    ):
        helper = self._helper
        win = helper.getWin()
        qwin = helper.getQwin()
        tabs = helper.getTabBar()
        mdi = helper.getMdi()
        if not (win and qwin and tabs and mdi):
            return

        title = context.get("winTitle", None) if context else None
        if isinstance(title, str):
            title = qwin.windowTitle()

        if view:
            index = self.getTabByView(view)
            if index == -1:
                return

        with self._controller.syncedCall(True) as sync:
            if not sync:
                return

            kritaIndex = tabs.currentIndex()
            currIndex = self.currentIndex()

            index = currIndex if not isinstance(index, int) else index
            uid = self.getUid(index)
            data = self._controller.getSplitData(uid)

            if uid is not None and data:
                # XXX helps a little with window title flashing
                winTitle = data.win.windowTitle()
                data.win.setWindowTitle(typing.cast(str, title))

                # XXX use setActiveSubWindow not setCurrentIndex
                # to make sure actions use the correct subwindow (in this cycle)
                mdi.setActiveSubWindow(data.win)
                callback(uid, data)

                self.setCurrentIndex(currIndex)
                tabs.setCurrentIndex(kritaIndex)
                data.win.setWindowTitle(winTitle)

    def onCurrentChange(self):
        self._sync(self.currentIndex())

    def split(self) -> "Split | None":
        from .split_toolbar import SplitToolbar

        toolbar = self._helper.isAlive(self.parent(), SplitToolbar)
        if toolbar:
            return toolbar.split()

    def topSplit(self) -> "Split | None":
        split = self._helper.isAlive(self.split(), Split)
        if split:
            return split.topSplit()

    def parentSplit(self) -> "Split | None":
        split = self.split()
        if split:
            return self._helper.isAlive(split.parent(), Split)

    def setActiveHighlight(self, active: bool = False):
        self.setProperty("class", "active" if active else "inactive")
        self._helper.refreshWidget(self)

    def prevTab(self):
        i = self.currentIndex()
        if i > 0:
            self.setCurrentIndex(i - 1)
        else:
            self.setCurrentIndex(self.count() - 1)

    def nextTab(self):
        i = self.currentIndex()
        if i < self.count() - 1:
            self.setCurrentIndex(i + 1)
        else:
            self.setCurrentIndex(0)

    def tabInserted(self, index: int):
        super().tabInserted(index)
        btn = self.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if btn:
            btn.installEventFilter(self)

    def closeTabsOther(self, index: int | None = None):
        if not isinstance(index, int):
            index = self.currentIndex()

        split = self.split()
        assert split is not None

        wins: list[QMdiSubWindow] = []
        for i in range(self.count()):
            if i != index:
                sw = self._helper.isAlive(split.getTabWindow(i), QMdiSubWindow)
                if sw:
                    wins.append(sw)
        for w in wins:
            if self._helper.isAlive(w, QMdiSubWindow):
                w.close()

    def closeTabsLeft(self, index: int | None = None):
        if not isinstance(index, int):
            index = self.currentIndex()

        split = self.split()
        assert split is not None

        wins: list[QMdiSubWindow] = []
        for i in range(index):
            sw = self._helper.isAlive(split.getTabWindow(i), QMdiSubWindow)
            if sw:
                wins.append(sw)
        for w in wins:
            if self._helper.isAlive(w, QMdiSubWindow):
                w.close()

    def closeTabsRight(self, index: int | None = None):
        if not isinstance(index, int):
            index = self.currentIndex()

        split = self.split()
        assert split is not None

        wins: list[QMdiSubWindow] = []
        for i in range(index + 1, self.count()):
            sw = self._helper.isAlive(split.getTabWindow(i), QMdiSubWindow)
            if sw:
                wins.append(sw)
        for w in wins:
            if self._helper.isAlive(w, QMdiSubWindow):
                w.close()

    def purgeAllTabs(self, closeSplit: bool = True):
        for i in range(self.count()):
            self.purgeTab(i, closeSplit=False)
        if closeSplit:
            split = self.split()
            if split:
                split.checkShouldClose()

    def purgeTab(self, index: int, closeSplit: bool = True):
        helper = self._helper
        uid = self.getUid(index)
        data = self._controller.getSplitData(uid)
        if data:
            from .split_toolbar import SplitToolbar

            toolbar = helper.isAlive(data.toolbar, SplitToolbar)
            if toolbar and toolbar == self.parent():
                win = helper.isAlive(data.win, QMdiSubWindow)
                if win:
                    win.close()
        if closeSplit:
            split = self.split()
            if split:
                split.checkShouldClose()

    def eventFilter(self, obj: QWidget, event: QEvent):
        if event.type() == QEvent.Type.Enter:
            obj.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            obj.setProperty("hover", True)
            obj.style().unpolish(obj)
            obj.style().polish(obj)
            obj.update()
            return False

        if event.type() == QEvent.Type.Leave:
            obj.setProperty("hover", False)
            obj.style().unpolish(obj)
            obj.style().polish(obj)
            return False

        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._draggable.mouseMove(event):
            super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        qwin = self._helper.getQwin()
        if not qwin:
            return
        btn = event.button()
        index = self.tabAt(toPoint(getEventPos(event)))
        if index >= 0:
            if btn == Qt.MouseButton.LeftButton:
                self._sync(index)
            elif btn == Qt.MouseButton.RightButton:
                from .split_toolbar import SplitToolbar

                parent = self._helper.isAlive(self.parent(), SplitToolbar)
                if parent:
                    parent.showMenu(event, tabIndex=index)
            self.tabPress.emit(event, index)
        else:
            self.parent().makeActiveToolbar()
        self._draggable.mousePress(event)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._draggable.mouseRelease(event)
        i = self.tabAt(toPoint(getEventPos(event)))
        if i >= 0:
            self.tabRelease.emit(event, i)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        threshold = 100
        self._wheelAccumulator += event.angleDelta().y()

        if abs(self._wheelAccumulator) >= threshold:
            direction = -1 if self._wheelAccumulator > 0 else 1
            self._wheelAccumulator = 0

            new_index = self.currentIndex() + direction
            if 0 <= new_index < self.count():
                self.setCurrentIndex(new_index)

        event.accept()

    def getUid(self, index: int | None) -> int | None:
        if index is not None:
            data = self.tabData(index)
            if isinstance(data, dict):
                return typing.cast(dict[str, int], data).get(
                    "uiTweaksId", None
                )

    def setUid(self, index: int, uid: int):
        if index >= 0 and index < self.count():
            self.setTabData(index, {"uiTweaksId": uid})

    def getTabByView(self, view: View) -> int:
        data = self._helper.getViewData(view)
        uid = data.get("uiTweaksId", None) if data else None
        if uid is not None:
            for i in range(self.count()):
                if self.getUid(i) == uid:
                    return i
        return -1

    def getTabByWindow(self, win: QMdiSubWindow) -> int:
        uid = win.property("uiTweaksId")
        if uid is not None:
            for i in range(self.count()):
                if self.getUid(i) == uid:
                    return i
        return -1

    def getWindow(self, index: int | None = None) -> QMdiSubWindow | None:
        uid = self.getUid(index)
        if uid is not None:
            data = self._controller.getSplitData(uid)
            if data is not None:
                return data.win

    def getView(self, index: int | None = None) -> View | None:
        uid = self.getUid(index)
        if uid is not None:
            data = self._controller.getSplitData(uid)
            if data is not None:
                return data.view

