# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    Qt,
    pyqtSignal,
    QObject,
    QWidget,
    QRect,
    QEvent,
    QMdiSubWindow,
    QTimer,
    QPoint,
    QRectF,
    QMessageBox,
    QFileDialog,
    QColor,
)

from krita import View, Document
from typing import Any, TYPE_CHECKING
from types import SimpleNamespace
from builtins import reversed

import typing
import re
import math
import json
import os
import time

from ..options import (
    getOpt,
)

from ..i18n import i18n

from .split_drag import SplitDragRect
from .split_handle import SplitHandle
from .split_toolbar import SplitToolbar

if TYPE_CHECKING:
    from .split_pane import SplitPane

from .split_helpers import (
    SplitData,
    SavedLayout,
    CollapsedLayout,
    SplitLayout,
    getLayoutFiles,
    almostEqual,
    almostEqualPos,
    QMDI_WIN_MIN_SIZE,
    SPLIT_MIN_SIZE,
    FitViewState,
)


class Split(QObject):
    STATE_SPLIT = 0
    STATE_COLLAPSED = 1

    resized = pyqtSignal()

    def __init__(
        self,
        parent: "Split | QWidget",
        controller: "SplitPane",
        toolbar: "SplitToolbar | None" = None,
        state: int | None = None,
        orient: Qt.Orientation = Qt.Orientation.Vertical,
        first: "Split | None" = None,
        second: "Split | None" = None,
    ):
        super().__init__(parent)
        self.setObjectName("SplitHandle")
        self._controller = controller
        self._helper = controller.helper()
        self._state: int = Split.STATE_COLLAPSED if state is None else state
        self._rect: QRect = QRect()
        self._first: "Split | None" = first
        self._second: "Split | None" = second
        self._handle: "SplitHandle | None" = None
        self._toolbar: "SplitToolbar | None" = None
        self._attachResizeCallback: typing.Callable[..., Any] | None = None
        self._resizing: bool = False
        self._closing: bool = False
        self._checkClosing: bool = False
        self._forceResizing: bool = False
        self._lastHandleRect: QRect = QRect()
        self._backing = None

        mdi = self._helper.getMdi()
        assert mdi

        if self._state == Split.STATE_COLLAPSED:
            self._toolbar = self._helper.isAlive(toolbar, SplitToolbar)
            if self._toolbar:
                self._toolbar.setSplit(self)
                self._toolbar.setParent(mdi)
            else:
                self._toolbar = SplitToolbar(
                    parent=mdi,
                    split=self,
                    controller=self._controller,
                )

            assert self._toolbar is not None
            self._toolbar.raise_()
            self._toolbar.show()
        else:
            self._handle = SplitHandle(
                self, controller=self._controller, orient=orient
            )
            assert self._first is not None
            assert self._second is not None
            self._first.setParent(self)
            self._second.setParent(self)

        self.attachEvents()
        self.destroyed.connect(self.clear)
        self._overlay = None

    def showOverlay(
        self,
        text: str | None = None,
        color: QColor | None = None,
        raiseOverlay: bool = False,
    ) -> SplitDragRect | None:
        if not self._overlay:
            qwin = self._helper.getQwin()
            rect = self.globalRect()
            if qwin:
                self._overlay = SplitDragRect(
                    qwin,
                    text=text,
                    color=QColor(0, 0, 0, 0) if color is None else color,
                )
                self._overlay.show()
                self._overlay.setGeometry(rect)
                if raiseOverlay:
                    self._overlay.raise_()

        return self._overlay

    def updateOverlay(self):
        if self._overlay:
            rect = self.globalRect()
            self._overlay.setGeometry(rect)

    def hideOverlay(self):
        if self._overlay and self._helper.isAlive(self._overlay, QWidget):
            self._overlay.deleteLater()
            self._overlay = None

    def state(self) -> int:
        return self._state

    def isChildOf(self, obj) -> bool:
        top = self
        while self._helper.isAlive(top, Split) and isinstance(
            top.parent(), Split
        ):
            top = top.parent()
            if obj == top:
                return True
        return False

    def showCanvasBacking(self):
        if not self._backing:
            rect = self.globalRect()
            app = self._helper.getApp()
            mdi = self._helper.getMdi()
            sw = mdi.activeSubWindow() if mdi else None
            if app and sw:
                color = self._helper.settingColor("", "canvasBorderColor", "")
                self._backing = SplitDragRect(sw.parent(), color=color)
                self._backing.show()
                self._backing.setGeometry(rect)

    def updateCanvasBacking(self):
        app = self._helper.getApp()
        if app and self._backing:
            color = self._helper.settingColor("", "canvasBorderColor", "")
            self._backing.setColor(color)

    def hideCanvasBacking(self):
        if self._backing:
            self._backing.deleteLater()
            self._backing = None

    def topSplit(self) -> "Split | None":
        return self._controller.topSplit()

    def defaultSplit(self, checkToolbar: bool = True) -> "Split | None":
        return self._controller.defaultSplit(checkToolbar)

    def firstMostSplit(self):
        firstMost = self
        while firstMost.state() == Split.STATE_SPLIT:
            first = firstMost.first()
            if not first:
                break
            firstMost = first
        return firstMost

    def secondMostSplit(self):
        secondMost = self
        while secondMost.state() == Split.STATE_SPLIT:
            second = secondMost.second()
            if not second:
                break
            secondMost = second
        return secondMost

    def tabs(self):
        return getattr(self._toolbar, "_tabs", None)

    def currentIndex(self) -> int:
        tabs = self.tabs()
        if tabs is not None:
            return tabs.currentIndex()
        return -1

    def currentTabText(self) -> str:
        tabs = self.tabs()
        if tabs is not None:
            return tabs.tabText(tabs.currentIndex())
        return ""

    def getSplitData(self, tabIndex: int) -> SplitData | None:
        tabs = self.tabs()
        if tabs is not None:
            uid = tabs.getUid(tabIndex)
            return self._controller.getSplitData(uid)

    def getCurrentSplitData(self) -> SplitData | None:
        return self.getSplitData(self.currentIndex())

    def toolbar(self) -> "SplitToolbar | None":
        return self._toolbar

    def controller(self) -> "SplitPane":
        return self._controller

    def attachEvents(self):
        parent = self.parent()
        if isinstance(parent, QWidget):
            parent.installEventFilter(self)
        elif isinstance(parent, Split):
            helper = self._helper

            def cb():
                if helper.isAlive(self, Split):
                    self.onResize()

            self._attachResizeCallback = lambda: cb()
            parent.resized.connect(self._attachResizeCallback)

    def detachEvents(self):
        parent = self.parent()
        if isinstance(parent, QWidget):
            parent.removeEventFilter(self)
        elif isinstance(parent, Split):
            try:
                if self._attachResizeCallback is not None:
                    parent.resized.disconnect(self._attachResizeCallback)
            except Exception:
                pass

    def eventFilter(self, obj: QObject, event: QEvent):
        if obj == self.parent():
            eventType = event.type()
            if eventType == QEvent.Type.Resize:
                self.onResize()
        return super().eventFilter(obj, event)

    def setParent(self, parent: "Split"):
        self.detachEvents()
        ret = super().setParent(parent)
        self.attachEvents()
        return ret

    def first(self) -> "Split | None":
        return self._helper.isAlive(self._first, Split)

    def second(self) -> "Split | None":
        return self._helper.isAlive(self._second, Split)

    def handle(self) -> "SplitHandle | None":
        return self._helper.isAlive(self._handle, SplitHandle)

    def level(self):
        level = 0
        top = self
        while self._helper.isAlive(top, Split) and isinstance(
            top.parent(), Split
        ):
            top = top.parent()
            level += 1
        return level

    def droppableLevel(self) -> int:
        level = 0
        top = self
        while self._helper.isAlive(top, Split):
            parent = self._helper.isAlive(top.parent(), Split)
            if not parent:
                break
            if parent.orientation() != top.orientation():
                level += 1
            top = parent
        return level

    def rect(self):
        return QRect(self._rect)

    def getRect(self) -> tuple[int, int, int, int]:
        return self._rect.getRect()

    def equalize(
        self, nested: bool = True, orient: Qt.Orientation | None = None
    ):
        if self._state == Split.STATE_SPLIT and self._helper.isAlive(
            self._handle, SplitHandle
        ):
            assert self._handle is not None
            if orient is None or orient == self._handle.orientation():
                self._handle.reset()
                self.onResize(force=True)
            if nested and self._first and self._second:
                self._first.equalize(nested=True)
                self._second.equalize(nested=True)

    def orientation(self) -> Qt.Orientation | None:
        if self._state == Split.STATE_SPLIT and self._helper.isAlive(
            self._handle, SplitHandle
        ):
            assert self._handle
            return self._handle.orientation()

    def setOrientation(self, orient: Qt.Orientation, redraw: bool = True):
        if self._state == Split.STATE_SPLIT and self._helper.isAlive(
            self._handle, SplitHandle
        ):
            assert self._handle
            if self._handle.setOrientation(orient, redraw=redraw) and redraw:
                self.equalize()
                return True

    def getTabWindow(self, index: int) -> QMdiSubWindow | None:
        from .split_tabs import SplitTabs

        tabs = self._helper.isAlive(self.tabs(), SplitTabs)
        if tabs:
            return tabs.getWindow(index)

    def getTabView(self, index: int) -> View | None:
        from .split_tabs import SplitTabs

        tabs = self._helper.isAlive(self.tabs(), SplitTabs)
        if tabs:
            return tabs.getView(index)

    def getActiveTabWindow(self) -> QMdiSubWindow | None:
        return self.getTabWindow(self.currentIndex())

    def getActiveTabView(self) -> View | None:
        return self.getTabView(self.currentIndex())

    def getOpenSubWindows(
        self, modified: bool = False
    ) -> list[tuple[QMdiSubWindow, View]]:
        windows: list[tuple[QMdiSubWindow, View]] = []
        if self._state == Split.STATE_COLLAPSED:
            tabs = self.tabs()
            if tabs:
                for i in range(tabs.count()):
                    view = self.getTabView(i)
                    win = self.getTabWindow(i)
                    doc = view.document() if view else None
                    if (
                        view
                        and win
                        and (
                            not modified
                            or (modified and doc and doc.modified())
                        )
                    ):
                        windows.append((win, view))
        elif self._state == Split.STATE_SPLIT:
            if self._first:
                windows.extend(self._first.getOpenSubWindows())
            if self._second:
                windows.extend(self._second.getOpenSubWindows())
        return windows

    def checkShouldClose(self, ts: int = 100):
        if self._checkClosing or self._controller.isLocked():
            return
        self._checkClosing = True
        helper = self._helper

        def cb():
            closeSplit = helper.isAlive(self, Split)
            if closeSplit and closeSplit.state() == Split.STATE_COLLAPSED:
                from .split_tabs import SplitTabs

                tabs = helper.isAlive(closeSplit.tabs(), SplitTabs)
                if not tabs or tabs.count() == 0:
                    if closeSplit.topSplit() != closeSplit:
                        closeSplit.close()
                    self._controller.setActiveToolbar()
            self._checkClosing = False
            self._controller._doSaveLayout()

        if ts < 0:
            cb()
        else:
            QTimer.singleShot(ts, cb)

    def close(self):
        helper = self._helper
        controller = self._controller

        if (
            self._closing
            or controller.isLocked()
            or not helper.isAlive(self, Split)
            or self._state != Split.STATE_COLLAPSED
        ):
            return

        self._closing = True

        opened = self.getOpenSubWindows()
        for o in opened:
            win = o[0]
            win.close()

        opened = self.getOpenSubWindows()
        if len(opened) > 0:
            self._closing = False
            return

        parent = self.parent()
        if isinstance(parent, Split):
            first = parent.first()
            second = parent.second()
            if not (first and second):
                return
            if (
                first
                and second
                and first._state == Split.STATE_COLLAPSED
                and second._state == Split.STATE_COLLAPSED
            ):
                keep = second if first == self else first

                assert keep._toolbar is not None
                assert parent._handle is not None

                parent._toolbar = keep._toolbar
                parent._toolbar.setSplit(parent)
                keep._toolbar = None

                first.clear(True)
                second.clear(True)

                parent._state = Split.STATE_COLLAPSED
                handle = parent._handle
                parent._handle = None
                handle.deleteLater()

                topSplit = parent.topSplit()
                if topSplit:
                    topSplit.onResize(force=True)
            else:
                keep = second if first == self else first
                keep_orient = keep.orientation()

                assert parent._handle is not None
                assert keep._first is not None
                assert keep._second is not None
                assert keep_orient is not None

                parent._handle.setOrientation(keep_orient, redraw=False)
                parent._first = keep._first
                parent._second = keep._second

                parent._first.setParent(parent)
                parent._second.setParent(parent)
                keep._first = None
                keep._second = None

                first.clear(True)
                second.clear(True)

                topSplit = parent.topSplit()
                if topSplit:
                    topSplit.onResize(force=True)
                parent.equalize()

        controller.savePreviousLayout()
        self._closing = False

    def clear(self, removeSelf: bool = False):
        helper = self._helper
        self._handle = helper.isAlive(self._handle, SplitHandle)
        self._toolbar = helper.isAlive(self._toolbar, SplitToolbar)
        self._first = helper.isAlive(self._first, Split)
        self._second = helper.isAlive(self._second, Split)
        if self._handle:
            self._handle.deleteLater()
            self._handle = None
        if self._toolbar:
            self._toolbar.tabs().purgeAllTabs(closeSplit=False)
            self._toolbar.deleteLater()
            self._toolbar = None
        if self._first:
            self._first.clear(True)
            self._first = None
        if self._second:
            self._second.clear(True)
            self._second = None
        if removeSelf and helper.isAlive(self, Split):
            self.hideOverlay()
            self.hideCanvasBacking()
            parent = self.parent()
            if parent and isinstance(parent, Split):
                if self == parent._first:
                    parent._first = None
                elif self == parent._second:
                    parent._second = None
            self.detachEvents()
            self.deleteLater()

    def isForceResizing(self):
        if self._forceResizing:
            return True
        top = self._helper.isAlive(self, Split)
        while top:
            top = self._helper.isAlive(top.parent(), Split)
            if top and top._forceResizing:
                return True
        return False

    def isResizing(self):
        return self._resizing

    def onResize(
        self,
        force: bool = True,
        refreshIcons: bool = False,
        recenterCanvas: bool = False,
    ):
        if self._resizing:
            return
        self._forceResizing = force
        self._resizing = True
        parent = self.parent()
        helper = self._helper
        old_rect = self._rect
        isFirst = False
        if isinstance(parent, QWidget):
            # this is the origin rect x=0,y=0
            self._rect = parent.rect()
        elif isinstance(parent, Split):
            first = parent._first
            second = parent._second
            handle = parent._handle
            if not handle:
                return
            px, py, pw, ph = parent.getRect()
            hx, hy, hw, hh = handle.geometry().getRect()
            if first == self:
                isFirst = True
                if handle.orientation() == Qt.Orientation.Vertical:
                    self._rect = QRect(px, py, max(0, hx - px), ph)
                else:
                    self._rect = QRect(px, py, pw, max(0, hy - py))
            elif second == self:
                if handle.orientation() == Qt.Orientation.Vertical:
                    self._rect = QRect(
                        hx + hw, py, max(0, pw - ((hx - px) + hw)), ph
                    )
                else:
                    self._rect = QRect(
                        px, hy + hh, pw, max(0, ph - ((hy - py) + hh))
                    )

        self.updateOverlay()
        self.showCanvasBacking()
        if self._backing:
            self._backing.setGeometry(self._rect)

        if self._state == Split.STATE_SPLIT:
            if not self._handle:
                return
            handleRect = self._handle.globalRect()
            if (
                old_rect != self._rect
                or handleRect != self._lastHandleRect
                or self.isForceResizing()
            ):
                self._handle.clamp()
                self._lastHandleRect = handleRect
                if self._first:
                    self._first.onResize(
                        refreshIcons=refreshIcons,
                        recenterCanvas=recenterCanvas,
                    )
                if self._second:
                    self._second.onResize(
                        refreshIcons=refreshIcons,
                        recenterCanvas=recenterCanvas,
                    )
        else:
            if self._state == Split.STATE_COLLAPSED and (
                old_rect != self._rect or self.isForceResizing()
            ):
                if self._backing:
                    self._backing.raise_()
                if self._toolbar is not None:
                    tabBarHeight = getOpt("tab_behaviour", "tab_height")
                    self._toolbar.setFixedHeight(tabBarHeight)
                    self._toolbar.setGeometry(
                        self._rect.x(),
                        self._rect.y(),
                        self._rect.width(),
                        tabBarHeight,
                    )
                    self.syncSubWindow(
                        wasResized=self._rect.size() != old_rect.size(),
                    )
                    if recenterCanvas:
                        win = helper.isAlive(
                            self.getActiveTabWindow(), QMdiSubWindow
                        )
                        view = helper.isAlive(self.getActiveTabView(), View)
                        if win and view:
                            self._helper.centerCanvas(win=win, view=view)

                    if refreshIcons:
                        self._toolbar.updateMenuBtn()

                    tabs = self.tabs()
                    if tabs:
                        tabs.setUsesScrollButtons(self._rect.width() > 100)

                self.resized.emit()

        if isFirst:
            self._controller.savePreviousLayout()

        self._helper.hideToast()
        self._forceResizing = False
        self._resizing = False

    def syncSubWindow(self, wasResized: bool = True):
        if self._state != Split.STATE_COLLAPSED:
            return

        helper = self._helper
        win = helper.isAlive(self.getActiveTabWindow(), QMdiSubWindow)
        toolbar = helper.isAlive(self._toolbar, SplitToolbar)
        if win and toolbar:
            rect = self._rect
            win.setFixedWidth(rect.width())
            win.setFixedHeight(rect.height() - toolbar.height())
            win.setGeometry(
                rect.x(),
                rect.y() + toolbar.height(),
                rect.width(),
                rect.height() - toolbar.height(),
            )

            win.raise_()
            win.show()

    def globalRect(self, withToolBar: bool = True):
        helper = self._helper
        qwin = helper.getQwin()
        mdi = helper.getMdi()
        if qwin and mdi:
            rect = QRect(
                mdi.mapTo(qwin, QPoint(self._rect.x(), self._rect.y())),
                self._rect.size(),
            )
            if not withToolBar:
                rect.setY(rect.y() + getOpt("tab_behaviour", "tab_height"))
            return rect
        return QRect()

    def splitAt(
        self, pos: QPoint
    ) -> tuple["Split | None", "Split | SplitToolbar | SplitHandle | None"]:
        if self.globalRect().contains(pos):
            if self._state == Split.STATE_SPLIT:
                assert self._handle is not None
                assert self._first is not None
                assert self._second is not None
                if self._handle.globalRect().contains(pos):
                    return (self, self._handle)
                split, element = self._first.splitAt(pos)
                if split is None:
                    split, element = self._second.splitAt(pos)
                return (split, element)
            elif self._state == Split.STATE_COLLAPSED:
                assert self._toolbar is not None
                if self._toolbar.globalRect().contains(pos):
                    return (self, self._toolbar)
                return (self, self)
        return (None, None)

    def transferTab(
        self,
        tabSplit: "Split",
        tabIndex: int | None = None,
        allTabs: bool = False,
        dupe: bool = False,
    ):
        tabs = tabSplit.tabs()
        parent = tabSplit.parent()

        if not tabs:
            return

        controller = self._controller
        enabled = controller.resizingEnabled()
        controller.setResizingEnabled(False)

        def doTab(
            tabIndex,
            tabs=tabs,
            dupe=dupe,
            split=self,
            controller=controller,
            makeCurrent=True,
        ):
            uid = tabs.getUid(tabIndex)
            data = controller.getSplitData(uid)
            if data:
                if dupe:
                    controller.syncView(
                        view=data.view, split=split, addView=True
                    )
                else:
                    kritaTab = controller.getIndexByView(data.view)
                    if kritaTab != -1:
                        controller.syncView(index=kritaTab, split=split)

        currIndex = tabSplit.currentIndex()
        if allTabs:
            for i in reversed(range(tabs.count())):
                doTab(i, dupe=False, makeCurrent=i == currIndex)
        else:
            doTab(currIndex if tabIndex is None else tabIndex)

        tabSplit.checkShouldClose(-1)
        tabSplit.checkShouldClose()

        controller.setResizingEnabled(enabled)

        def cb():
            topSplit = self.topSplit()
            if topSplit:
                topSplit.onResize(force=True, recenterCanvas=True)

        QTimer.singleShot(0, cb)

    def makeSplit(
        self,
        orient: Qt.Orientation,
        dupe: bool = False,
        swap: bool = False,
        empty: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
        handlePos: int | None = None,
        allTabs: bool = False,
    ) -> tuple["Split | None", "Split | None"]:
        tabs = self.tabs()
        if self._controller.isLocked() or not (
            self._state == Split.STATE_COLLAPSED and (tabs or empty)
        ):
            return (None, None)

        enabled = self._controller.resizingEnabled()
        self._controller.setResizingEnabled(False)

        isSelf = tabSplit == self
        toolbar = self._toolbar
        self._toolbar = None
        self._handle = SplitHandle(
            self, controller=self._controller, orient=orient, pos=handlePos
        )

        if swap:
            self._second = Split(
                self, toolbar=toolbar, controller=self._controller
            )
            self._first = Split(self, controller=self._controller)
        else:
            self._first = Split(
                self, toolbar=toolbar, controller=self._controller
            )
            self._second = Split(self, controller=self._controller)

        self._state = Split.STATE_SPLIT

        target = None
        if not empty:
            if isSelf or tabSplit is None:
                tabSplit = self._second if swap else self._first

            if tabIndex is None and not allTabs:
                tabIndex = tabSplit.currentIndex()

            target = self._first if swap else self._second
            if allTabs:
                target.transferTab(tabSplit=tabSplit, allTabs=allTabs)
            elif tabIndex is not None:
                target.transferTab(
                    tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                )

        def cb(target=target):
            topSplit = self.topSplit()
            if topSplit:
                topSplit.onResize(force=True, recenterCanvas=True)
            target = self._helper.isAlive(target, Split)
            if target:
                parent = target.parent()
                if parent:
                    parent.equalize()

        self._controller.setResizingEnabled(enabled)
        QTimer.singleShot(100, cb)

        return (self._first, self._second)

    def makeSplitBelow(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
        empty: bool = False,
        handlePos: int | None = None,
        allTabs: bool = False,
    ):
        return self.makeSplit(
            Qt.Orientation.Horizontal,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
            empty=empty,
            handlePos=handlePos,
            allTabs=allTabs,
        )

    def makeSplitAbove(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
        empty: bool = False,
        handlePos: int | None = None,
        allTabs: bool = False,
    ):
        return self.makeSplit(
            Qt.Orientation.Horizontal,
            swap=True,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
            empty=empty,
            handlePos=handlePos,
            allTabs=allTabs,
        )

    def makeSplitRight(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
        empty: bool = False,
        handlePos: int | None = None,
        allTabs: bool = False,
    ):
        return self.makeSplit(
            Qt.Orientation.Vertical,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
            empty=empty,
            handlePos=handlePos,
            allTabs=allTabs,
        )

    def makeSplitLeft(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
        empty: bool = False,
        handlePos: int | None = None,
        allTabs: bool = False,
    ):
        return self.makeSplit(
            Qt.Orientation.Vertical,
            swap=True,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
            empty=empty,
            handlePos=handlePos,
            allTabs=allTabs,
        )

    def makeSplitBetween(
        self,
        dupe: bool = False,
        tabSplit: "Split | None" = None,
        tabIndex: int | None = None,
        allTabs: bool = False,
    ):
        if (
            not self._controller.isLocked()
            and self._state == Split.STATE_SPLIT
        ):
            assert self._handle is not None
            assert self._first is not None
            assert self._second is not None

            enabled = self._controller.resizingEnabled()
            self._controller.setResizingEnabled(False)
            second = self._second
            orient = self._handle.orientation()

            split = Split(self, controller=self._controller)
            toolbar = split._toolbar
            split._toolbar = None
            split._handle = SplitHandle(
                split, controller=self._controller, orient=orient
            )
            split._first = Split(
                split, toolbar=toolbar, controller=self._controller
            )
            split._second = second
            split._second.setParent(split)
            split._state = Split.STATE_SPLIT

            self._second = split

            if tabSplit is not None:
                if allTabs:
                    split._first.transferTab(
                        tabSplit=tabSplit, allTabs=allTabs
                    )
                elif tabIndex is not None:
                    split._first.transferTab(
                        tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                    )

            def cb():
                topSplit = self.topSplit()
                if topSplit:
                    topSplit.onResize(force=True, recenterCanvas=True)

            self._controller.setResizingEnabled(enabled)
            QTimer.singleShot(0, cb)

            return split._first

    def makeSplitAtEdge(
        self,
        edge: Qt.AnchorPoint,
        dupe: bool = False,
        tabSplit: "Split | None" = None,
        tabIndex: int | None = None,
        allTabs: bool = False,
    ):
        topSplit = self.topSplit()
        if (
            not self._controller.isLocked()
            and topSplit
            and topSplit.state() == Split.STATE_SPLIT
        ):

            enabled = self._controller.resizingEnabled()
            self._controller.setResizingEnabled(False)
            sizes = topSplit.saveSplitSizes()

            first = topSplit.first()
            second = topSplit.second()
            orient = topSplit.orientation()
            assert orient is not None

            targetSplit = Split(topSplit, controller=self._controller)
            otherSplit = Split(
                topSplit,
                controller=self._controller,
                state=Split.STATE_SPLIT,
                orient=orient,
                first=first,
                second=second,
            )

            if edge in (Qt.AnchorPoint.AnchorLeft, Qt.AnchorPoint.AnchorTop):
                topSplit._first = targetSplit
                topSplit._second = otherSplit
            else:
                topSplit._second = targetSplit
                topSplit._first = otherSplit

            topSplit.setOrientation(
                Qt.Orientation.Vertical
                if edge
                in (Qt.AnchorPoint.AnchorLeft, Qt.AnchorPoint.AnchorRight)
                else Qt.Orientation.Horizontal
            )
            rect = topSplit.rect()
            h = int(rect.height() * 0.25)
            w = int(rect.width() * 0.25)
            handle = topSplit.handle()
            first = topSplit.first()
            second = topSplit.second()
            assert handle is not None
            assert first is not None
            assert second is not None

            if edge == Qt.AnchorPoint.AnchorLeft:
                handle.moveTo(w)
                second.equalize(orient=Qt.Orientation.Vertical)
            elif edge == Qt.AnchorPoint.AnchorTop:
                handle.moveTo(h)
                second.equalize(orient=Qt.Orientation.Horizontal)
            elif edge == Qt.AnchorPoint.AnchorRight:
                handle.moveTo(rect.width() - w)
                first.equalize(orient=Qt.Orientation.Vertical)
            elif edge == Qt.AnchorPoint.AnchorBottom:
                handle.moveTo(rect.height() - h)
                first.equalize(orient=Qt.Orientation.Horizontal)

            if tabSplit is not None:
                if allTabs:
                    targetSplit.transferTab(tabSplit=tabSplit, allTabs=allTabs)
                elif tabIndex is not None:
                    targetSplit.transferTab(
                        tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                    )

            second.restoreSplitSizes(sizes, orient=second.orientation())

            def cb():
                topSplit = self.topSplit()
                if topSplit:
                    topSplit.onResize(force=True, recenterCanvas=True)

            self._controller.setResizingEnabled(enabled)
            QTimer.singleShot(0, cb)

    def resetLayout(self):
        tabs = self._helper.getTabBar()
        topSplit = self.topSplit()
        if not topSplit:
            return
        split = topSplit.firstMostSplit()
        if tabs and split:
            currIndex = tabs.currentIndex()
            for i in range(tabs.count()):
                self._controller.syncView(
                    index=i, split=split, makeCurrent=i == currIndex
                )
            topSplit = split.topSplit()
            if topSplit:
                topSplit.closeEmpties()

    def saveSplitSizes(self) -> list[tuple["Split", int]]:
        if self._state == Split.STATE_SPLIT:
            assert self._first is not None
            assert self._second is not None
            return (
                [
                    (self, self.size()),
                    (self._first, self._first.size()),
                    (self._second, self._second.size()),
                ]
                + self._first.saveSplitSizes()
                + self._second.saveSplitSizes()
            )
        return []

    def size(self) -> int:
        parent = self._helper.isAlive(self.parent(), Split)
        if parent:
            return (
                self._rect.height()
                if parent.orientation() == Qt.Orientation.Horizontal
                else self._rect.width()
            )
        return 0

    def resize(self, size: int):
        parent = self._helper.isAlive(self.parent(), Split)
        if parent:
            handle = parent.handle()
            if not handle:
                return
            delta = 1 if self == parent.first() else -1
            if handle.orientation() == Qt.Orientation.Vertical:
                currSize = self._rect.width()
                handle.moveTo(handle.x() + (delta * (size - currSize)))
            else:
                currSize = self._rect.height()
                handle.moveTo(handle.y() + (delta * (size - currSize)))
            tabs = self.tabs()
            if tabs:
                self._helper.refreshWidget(tabs)

    def restoreSplitSizes(
        self,
        sizes: list[tuple["Split", int]],
        orient: Qt.Orientation | None = None,
    ):
        for data in sizes:
            split, size = data
            if self._helper.isAlive(split, Split):
                if orient is None or split.orientation() == orient:
                    split.resize(size)

    def closeEmpties(self):
        if self._controller.isLocked():
            return
        helper = self._helper
        if self._state == Split.STATE_COLLAPSED:
            tabs = self.tabs()
            if not tabs or tabs.count() == 0:
                parentSplit = helper.isAlive(self.parent(), Split)
                self.close()
                if parentSplit:
                    parentSplit.closeEmpties()
                self._controller.setActiveToolbar()
        elif self._state == Split.STATE_SPLIT:
            first = helper.isAlive(self._first, Split)
            if first:
                first.closeEmpties()
            second = helper.isAlive(self._second, Split)
            if second:
                second.closeEmpties()

    def eachCollapsedSplit(self, callback: typing.Callable[["Split"], Any]):
        helper = self._helper
        if self._state == Split.STATE_COLLAPSED:
            callback(self)
        elif self._state == Split.STATE_SPLIT:
            first = helper.isAlive(self._first, Split)
            if first:
                first.eachCollapsedSplit(callback)
            second = helper.isAlive(self._second, Split)
            if second:
                second.eachCollapsedSplit(callback)

    def getLayout(
        self, verify: bool = False
    ) -> "SavedLayout | CollapsedLayout | SplitLayout | None":
        helper = self._helper
        mdi = helper.getMdi()
        app = helper.getApp()
        qwin = helper.getQwin()
        topSplit = self.topSplit()
        if not (qwin and mdi and app and topSplit):
            return

        if verify:
            for doc in app.documents():
                fname = doc.fileName()
                if not fname or not os.path.exists(fname):
                    choice = QMessageBox.question(
                        None,
                        "Krita",
                        i18n(
                            "Some documents are not saved to disk. These will not be included."
                        )
                        + "\n\n"
                        + i18n("Do you wish to continue?"),
                        QMessageBox.StandardButton.No
                        | QMessageBox.StandardButton.Yes,
                        QMessageBox.StandardButton.No,
                    )

                    if choice == QMessageBox.StandardButton.No:
                        return
                    else:
                        break

        splitLayout = None
        isActiveSplit = self == self._controller.defaultSplit()
        if self._state == Split.STATE_COLLAPSED:
            tabs = self.tabs()
            if tabs:
                files: list[str] = []
                activeView = self.getActiveTabView()
                activeDoc = activeView.document() if activeView else None
                activeFile = activeDoc.fileName() if activeDoc else None
                activeIndex = -1
                for i in range(tabs.count()):
                    uid = tabs.getUid(i)
                    data = self._controller.getSplitData(uid)
                    if data and data.view:
                        doc = data.view.document()
                        if doc:
                            path = doc.fileName()
                            if os.path.exists(path):
                                files.append(path)
                                if path == activeFile and activeIndex == -1:
                                    activeIndex = len(files) - 1
                splitLayout = typing.cast(
                    CollapsedLayout,
                    {
                        "state": "c",
                        "files": files,
                        "active": activeIndex,
                        "isActiveSplit": isActiveSplit,
                        "splitSize": self.size(),
                    },
                )
            else:
                splitLayout = typing.cast(
                    CollapsedLayout,
                    {
                        "state": "c",
                        "files": [],
                        "active": -1,
                        "isActiveSplit": False,
                        "splitSize": self.size(),
                    },
                )

        elif self._state == Split.STATE_SPLIT:
            assert self._handle is not None
            assert self._first is not None
            assert self._second is not None
            orient = (
                "v"
                if self._handle.orientation() == Qt.Orientation.Vertical
                else "h"
            )
            first = self._first.getLayout()
            second = self._second.getLayout()
            splitLayout = typing.cast(
                SplitLayout,
                {
                    "state": orient,
                    "first": first,
                    "second": second,
                    "splitSize": self.size(),
                },
            )

        if self == topSplit:
            w, h = qwin.width(), qwin.height()
            return typing.cast(
                SavedLayout,
                {
                    "state": "s",
                    "locked": self._controller.isLocked(),
                    "layout": splitLayout,
                    "winWidth": w,
                    "winHeight": h,
                },
            )
        else:
            return splitLayout

    def restoreLayout(
        self,
        layout: "CollapsedLayout | SplitLayout",
        silent: bool = False,
        sessionRestore: bool = False,
    ):
        topSplit = self.topSplit()
        if self is not topSplit:
            if topSplit:
                topSplit.restoreLayout(layout)
            return

        helper = self._helper
        qwin = helper.getQwin()
        app = helper.getApp()
        mdi = helper.getMdi()
        if not (app and qwin and mdi):
            return

        if not isinstance(layout, dict):
            return

        if not sessionRestore:
            for doc in app.documents():
                if doc.modified():
                    if silent:
                        return

                    choice = QMessageBox.question(
                        None,
                        "Krita",
                        i18n("You have unsaved changes.")
                        + i18n(
                            "If you continue the files will be kept open in your new layout."
                        )
                        + "\n\n"
                        + i18n("Do you wish to continue?"),
                        QMessageBox.StandardButton.No
                        | QMessageBox.StandardButton.Yes,
                        QMessageBox.StandardButton.No,
                    )

                    if choice == QMessageBox.StandardButton.No:
                        return
                    else:
                        break

        assert topSplit is not None
        files, missing = getLayoutFiles(layout)

        if len(files) == 0:
            if not silent:
                _ = QMessageBox.warning(
                    None,
                    "Krita",
                    i18n(
                        "Unable to restore session.\nThese files are missing:"
                    )
                    + "\n"
                    + "\n".join(missing),
                )
            return

        self._controller.unlock(silent=True)
        self.resetLayout()

        splitTabs = self.tabs()
        splitTabs.setVisible(False)

        firstMost = self.firstMostSplit()
        w, h = qwin.width(), qwin.height()

        context = SimpleNamespace(
            files=files,
            missing={},
            handled={},
            docs=helper.docsByFile(),
            views=helper.viewsByFile(),
            currWidth=w,
            currHeight=h,
            savedWidth=w,
            savedHeight=h,
            sizes=[],
            activeSplit=None,
            activeFile=layout.get("active", None),
            splitFiles=[],
        )

        self.showOverlay()
        self._restoreSplits(layout, context)

        def closeOthers(context=context, keepOne=False):
            helper = self._helper
            mdi = helper.getMdi()
            assert mdi is not None
            for f in context.views:
                size = len(context.views[f])
                for i, v in enumerate(context.views[f]):
                    if helper.isAlive(v, View):
                        index = self._controller.getIndexByView(v)
                        if (not keepOne and index != -1) or (
                            keepOne and index > 0
                        ):
                            activeWin = mdi.subWindowList()[index]
                            if activeWin:
                                doc = v.document()
                                if (
                                    not doc.modified()
                                    or i < size - 1
                                    or context.handled.get(
                                        doc.fileName(), None
                                    )
                                ):
                                    activeWin.close()

        def completeLayout(
            context=context,
            layout=layout,
            closeOthers=closeOthers,
            splitTabs=splitTabs,
        ):
            try:
                closeOthers(keepOne=True)

                for f in context.splitFiles:
                    f[0]._restoreSplitFiles(f[1], context)

                if layout.get("locked", False):
                    self._controller.lock()

                self._controller.setLayoutPath(layout.get("path", None))

                closeOthers()
                missing = context.missing.keys()

                split = (
                    context.activeSplit
                    if context.activeSplit
                    else self.firstModeSplit()
                )

                def setActive(split=split, splitTabs=splitTabs):
                    try:
                        self.closeEmpties()
                        if split:
                            view = split.getActiveTabView()
                            kritaTab = self._controller.getIndexByView(view)
                            if kritaTab != -1:
                                self._controller.syncView(
                                    index=kritaTab, split=split
                                )
                    finally:
                        self.hideOverlay()
                        splitTabs.setVisible(True)

                QTimer.singleShot(100, setActive)

                if len(missing) > 0:

                    def cb(missing=missing):
                        _ = QMessageBox.warning(
                            None,
                            "Krita",
                            i18n("These files could not be opened:")
                            + "\n"
                            + ("\n".join(missing)),
                        )

                    QTimer.singleShot(0, cb)
            except:
                self.hideOverlay()
                splitTabs.setVisible(True)

        def restoreSizes(
            context=context,
            layout=layout,
            closeOthers=closeOthers,
            completeLayout=completeLayout,
        ):
            try:
                sizes = context.sizes
                if len(sizes) == 0:
                    self.equalize()
                else:
                    self.restoreSplitSizes(sizes)
            except:
                self.hideOverlay()
                splitTabs.setVisible(True)
            finally:
                topSplit = self.topSplit()
                if topSplit:
                    topSplit.onResize(force=True)

            QTimer.singleShot(100, completeLayout)

        QTimer.singleShot(100, restoreSizes)

    def _restoreSplitFiles(
        self,
        files: list[tuple["Split", list[str]]],
        context: SimpleNamespace,
    ):
        helper = self._helper
        controller = self._controller
        app = helper.getApp()
        assert app is not None
        assert isinstance(context, SimpleNamespace)

        activeFile = context.activeFile
        activeIndex = -1
        if isinstance(activeFile, int):
            activeIndex = activeFile
            activeFile = None
        activeView = None

        for i, f in enumerate(files):
            handled = False

            # NOTE
            # don't re-use views here,
            # it causes weird issues
            # with the canvas floating messages

            if not handled and f in context.docs:
                doc = context.docs[f]
                if helper.isAlive(doc, Document):
                    handled = True
                    controller.syncView(addView=True, document=doc, split=self)
                    if not activeView and (
                        f == activeFile or i == activeIndex
                    ):
                        activeView = self.getActiveTabView()

            if not handled:
                if os.path.exists(typing.cast(str, f)):
                    doc = app.openDocument(f)
                    if doc:
                        context.docs[f] = doc
                        handled = True
                        controller.syncView(
                            addView=True, document=doc, split=self
                        )
                        if not activeView and f == activeFile:
                            activeView = self.getActiveTabView()

            if handled:
                context.handled[f] = True
            else:
                context.missing[f] = True

        if activeView:
            kritaTab = controller.getIndexByView(activeView)
            if kritaTab != -1:
                controller.syncView(index=kritaTab, split=self)

    def _restoreSplits(
        self,
        layout: "SavedLayout | CollapsedLayout | SplitLayout | None",
        context: SimpleNamespace,
    ):
        if not layout:
            return

        helper = self._helper
        controller = self._controller
        app = helper.getApp()
        assert app is not None
        assert isinstance(context, SimpleNamespace)

        topSplit = self.topSplit()
        state = layout.get("state", None)
        if state == "s":
            layout = layout["layout"]
            state = layout.get("state", None)

        # NOTE append size here to preserve order of processing
        sz = layout.get("splitSize", None)
        if isinstance(sz, int):
            sz = (
                int(float(sz) / context.savedWidth * context.currWidth)
                if state == "v"
                else int(float(sz) / context.savedHeight * context.currHeight)
            )
            context.sizes.append((self, sz))

        if state == "c":
            layout = typing.cast(CollapsedLayout, layout)
            if layout.get("isActiveSplit", False):
                context.activeSplit = self
            context.splitFiles.append((self, layout.get("files", [])))

        elif state in ("v", "h"):
            layout = typing.cast(SplitLayout, layout)
            first, second = None, None
            if state == "v":
                first, second = self.makeSplitRight(empty=True)
            else:
                first, second = self.makeSplitBelow(empty=True)

            if first:
                first._restoreSplits(layout.get("first", {}), context)

            if second:
                second._restoreSplits(layout.get("second", {}), context)

    def saveLayout(self, path: str | None = None):
        topSplit = self.topSplit()
        if not topSplit:
            return

        layout = topSplit.getLayout(verify=True)

        if not layout:
            return

        files, _ = getLayoutFiles(layout)
        if len(files) == 0:
            return

        hasPath = path and isinstance(path, str)
        if not hasPath:
            path, _ = QFileDialog.getSaveFileName(
                None, "Save JSON", "", "JSON files (*.json);;All files (*)"
            )

        if not path:
            return

        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(layout, f, ensure_ascii=False)
                self._controller.setLayoutPath(path)
                if hasPath:
                    self._helper.showToast("Layout saved")
        except:
            _ = QMessageBox.warning(
                None,
                "Krita",
                i18n("The operation was aborted."),
            )

    def loadLayout(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "Open JSON", "", "JSON files (*.json);;All files (*)"
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    layout = json.load(f)
                    layout["path"] = path
                    self.restoreLayout(layout)
            except Exception as e:
                _ = QMessageBox.warning(
                    None,
                    "Krita",
                    i18n("The operation was aborted.")
                    + i18n("The file could not be opened.")
                    + i18n("\nError:\n")
                    + str(e),
                )

