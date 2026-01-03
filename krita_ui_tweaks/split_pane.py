# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    QWIDGETSIZE_MAX,
    pyqtSignal,
    QApplication,
    QResizeEvent,
    QPaintEvent,
    QPixmap,
    QAction,
    QMainWindow,
    QMouseEvent,
    QPushButton,
    QTransform,
    QWheelEvent,
    QMenu,
    Qt,
    QPainter,
    QPen,
    QColor,
    QTabBar,
    QObject,
    QMdiSubWindow,
    QWidget,
    QEvent,
    QMdiArea,
    QRect,
    QTimer,
    QPoint,
    QIcon,
    getEventGlobalPos,
    getEventPos,
    toPoint,
)

from krita import Window, View, Document
from dataclasses import dataclass
from contextlib import contextmanager
from typing import Any
from types import SimpleNamespace

from .component import Component
from .options import showOptions, getOpt, signals as OptionSignals
from .helper import Helper
from .i18n import i18n

import typing
import re

# TODO add this to configurable options
TAB_BAR_HEIGHT = 34
TAB_TEXT_MAX_LEN = 30


@dataclass
class MenuAction:
    text: str
    callback: typing.Callable[..., Any]
    separator: bool = False
    enabled: bool = True
    visible: bool = True


@dataclass
class ViewData:
    view: View
    win: QMdiSubWindow
    toolbar: "SplitToolbar | None"
    watcher: "SubWindowInterceptor | None"
    watcherCallback: typing.Callable[[object, Any], None] | None


class SubWindowInterceptor(QObject):
    def __init__(self, callback: typing.Callable[..., Any]):
        super().__init__()
        self._callback = callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Close:
            obj.destroyed.connect(self._callback)
        return False


class TabDragRect(QWidget):
    def __init__(
        self,
        parent: QWidget | QMainWindow,
        color: QColor | None = None,
        altColor: QColor | None = None,
        text: str | None = None,
        textColor: QColor | None = None,
    ):
        super().__init__(parent)

        self._color = QColor(10, 10, 100, 100) if color is None else color
        self._altColor = altColor
        self._text = text
        self._textColor = textColor if textColor else Qt.GlobalColor.white

    def setText(self, text: str | None):
        self._text = text
        self.update()

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        rect = self.rect()
        p.fillRect(rect, self._color)

        if self._altColor:
            stripe_width = 5
            pen = QPen(self._altColor, stripe_width * 2)
            p.setPen(pen)

            w, h = rect.width(), rect.height()
            for x in range(-h, w, stripe_width * 2):
                p.drawLine(x, 0, x + h, h)

        if self._text:
            p.setPen(self._textColor)
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine,
                self._text,
            )


class SplitTabs(QTabBar):
    tabPress = pyqtSignal(QMouseEvent, int)
    tabRelease = pyqtSignal(QMouseEvent, int)

    def __init__(self, parent: "SplitToolbar", controller: "SplitPane"):
        super().__init__(parent)
        self._wheelAccumulator = 0

        self._controller = controller
        self._helper = controller.helper()
        self._dragIndex = -1
        self._dragTimer: QTimer | None = None
        self._dragPos: QPoint | None = None
        self._dragStart = QPoint()
        self._dragPlaceHolder = None
        self._dropPlaceHolder = None
        self._dropAction: (
            typing.Literal[
                "makeSplitAtEdge",
                "makeSplitBetween",
                "makeSplitLeft",
                "makeSplitRight",
                "makeSplitAbove",
                "makeSplitBelow",
                "transferTab",
            ]
            | None
        ) = None
        self._dropSplit: Split | None = None
        self._dropEdge: Qt.AnchorPoint | None = None

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
        data = self._controller.getViewData(uid)
        mdi = helper.getMdi()
        if mdi:
            subwin = mdi.activeSubWindow()
            if data and data.win != subwin:
                self._controller.syncView(split=self.split(), view=data.view)

    def exec(
        self,
        callback: typing.Callable[[int, ViewData], Any],
        index: int | None = None,
        view: View | None = None,
    ):
        helper = self._helper
        win = helper.getWin()
        qwin = helper.getQwin()
        title = qwin.windowTitle()
        tabs = helper.getTabBar()
        mdi = helper.getMdi()
        if not (win and qwin and tabs and mdi):
            return

        if view:
            index = self.getTabByView(view)
            if index == -1:
                return

        updates = qwin.updatesEnabled()
        qwin.setUpdatesEnabled(False)
        try:
            kritaIndex = tabs.currentIndex()
            currIndex = self.currentIndex()

            index = currIndex if not isinstance(index, int) else index
            uid = self.getUid(index)
            data = self._controller.getViewData(uid)

            if uid is not None and data:
                # XXX stop the window title from flashing
                winTitle = data.win.windowTitle()
                data.win.setWindowTitle(title)
                
                # XXX make sure actions use the correct subwindow
                mdi.setActiveSubWindow(data.win)
                callback(uid, data)

                self.setCurrentIndex(currIndex)
                tabs.setCurrentIndex(kritaIndex)
                data.win.setWindowTitle(winTitle)
        finally:
            qwin.setUpdatesEnabled(updates)

    def onCurrentChange(self):
        self._sync(self.currentIndex())

    def split(self) -> "Split | None":
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

    def purgeAllTabs(self):
        for i in range(self.count()):
            self.purgeTab(i)

    def purgeTab(self, index: int):
        helper = self._helper
        uid = self.getUid(index)
        data = self._controller.getViewData(uid)
        if data:
            toolbar = helper.isAlive(data.toolbar, SplitToolbar)
            if toolbar and toolbar == self.parent():
                win = helper.isAlive(data.win, QMdiSubWindow)
                if win:
                    win.close()

        def cb():
            if helper.isAlive(self, SplitTabs) and self.count() == 0:
                split = helper.isAlive(self.split(), Split)
                if split and split.topSplit() != split:
                    split.close()
                self._controller.setActiveToolbar()

        QTimer.singleShot(10, cb)

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

    def showDragPlaceHolder(self, pos: QPoint):
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if self._dragPlaceHolder is None:
            colors = self._controller.colors()
            assert colors is not None
            bg = QColor(colors.tabActive)
            fg = QColor(colors.tabText)
            self._dragPlaceHolder = TabDragRect(
                parent=qwin,
                color=bg,
                text=self.tabText(self._dragIndex),
                textColor=fg,
            )

        self._dragPlaceHolder.show()
        self._dragPlaceHolder.raise_()
        self._dragPlaceHolder.setGeometry(
            pos.x(),
            pos.y(),
            self.tabRect(self._dragIndex).width(),
            self.height(),
        )

    def hideDragPlaceHolder(self):
        if self._dragPlaceHolder is not None:
            self._dragPlaceHolder.deleteLater()
            self._dragPlaceHolder = None

    def showDropPlaceHolder(self, rect: QRect):
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if self._dropPlaceHolder is None:
            palette = self._controller.colors()
            assert palette is not None
            color = QColor(palette.tabActive)
            color.setAlpha(50)
            altColor = QColor(palette.tabActive).darker(150)
            altColor.setAlpha(100)
            self._dropPlaceHolder = TabDragRect(
                qwin, color=color, altColor=altColor
            )

        self._dropPlaceHolder.show()
        self._dropPlaceHolder.setGeometry(rect)

    def hideDropPlaceHolder(self):
        if self._dropPlaceHolder is not None:
            self._dropPlaceHolder.deleteLater()
            self._dropPlaceHolder = None

    def handleDropZone(self):
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if self._dragIndex != -1 and isinstance(self._dragPos, QPoint):
            globalPos = self._dragPos
            pos = qwin.mapFromGlobal(globalPos)
            self.showDragPlaceHolder(pos)
            currSplit = self.split()

            if not currSplit:
                return

            topSplit = helper.isAlive(currSplit.topSplit(), Split)
            if not topSplit:
                return

            targetSplit, el = topSplit.splitAt(pos)

            self._dropAction = None
            self._dropSplit = None
            self._dropEdge = None
            isOnlyTab = self.count() == 1

            if targetSplit is None or (
                isOnlyTab and topSplit.state() == Split.STATE_COLLAPSED
            ):
                self.hideDropPlaceHolder()
            else:
                targetRect = targetSplit.globalRect(withToolBar=False)
                rx, ry, rw, rh = targetRect.getRect()

                topRect = topSplit.globalRect(withToolBar=False)
                tx, ty, tw, th = topRect.getRect()

                x = pos.x()
                y = pos.y()
                edgeThreshold = 30

                if x > tx and x < tx + edgeThreshold and th != rh:
                    self._dropEdge = Qt.AnchorPoint.AnchorLeft
                    topRect.setWidth(edgeThreshold)
                elif x > tx + tw - edgeThreshold and x < tx + tw and th != rh:
                    self._dropEdge = Qt.AnchorPoint.AnchorRight
                    topRect.setX(tx + tw - edgeThreshold)
                elif y > ty and y < ty + edgeThreshold and tw != rw:
                    self._dropEdge = Qt.AnchorPoint.AnchorTop
                    topRect.setHeight(edgeThreshold)
                elif y > ty + th - edgeThreshold and y < ty + th and tw != rw:
                    self._dropEdge = Qt.AnchorPoint.AnchorBottom
                    topRect.setY(ty + th - edgeThreshold)
                else:
                    topRect = None

                if topRect is not None:
                    self._dropSplit = topSplit
                    self._dropAction = "makeSplitAtEdge"
                    self.showDropPlaceHolder(topRect)
                    return

                if isinstance(el, SplitHandle):
                    orient = el.orientation()
                    first = targetSplit.first()
                    second = targetSplit.second()
                    if first is not None and second is not None:
                        if (
                            first.state() == Split.STATE_SPLIT
                            and second.state() == Split.STATE_SPLIT
                        ):
                            first_handle = first.handle()
                            second_handle = second.handle()
                            if (
                                first_handle is not None
                                and second_handle is not None
                                and first_handle.orientation() != orient
                                and second_handle.orientation() != orient
                            ):
                                rect = second.globalRect()
                                if orient == Qt.Orientation.Vertical:
                                    rect.translate(-30, 0)
                                    rect.setWidth(50)
                                else:
                                    rect.translate(0, -30)
                                    rect.setHeight(50)
                                self._dropSplit = targetSplit
                                self._dropAction = "makeSplitBetween"
                                self.showDropPlaceHolder(rect)
                                return

                        targetSplit = (
                            first
                            if first.state() == Split.STATE_COLLAPSED
                            else second
                        )

                if isOnlyTab and targetSplit == currSplit:
                    self.hideDropPlaceHolder()
                    return

                edgeWidth = int(rw / 2.5)
                edgeHeight = int(rh / 2.5)
                x = pos.x()
                y = pos.y()

                hasAction = False
                actions = SimpleNamespace(
                    makeSplitLeft=False,
                    makeSplitRight=False,
                    makeSplitAbove=False,
                    makeSplitBelow=False,
                    transferTab=False,
                )

                level = targetSplit.droppableLevel()
                hasToolbar = isinstance(el, SplitToolbar)

                if hasToolbar:
                    actions.transferTab = True
                    hasAction = True
                elif level < 30:
                    if x < rx + edgeWidth and x >= rx:
                        actions.makeSplitLeft = max(0, (x - rx) / rw)
                        hasAction = True

                    if x > rx + rw - edgeWidth and x <= rx + rw:
                        actions.makeSplitRight = max(0, (rx + rw - x) / rw)
                        hasAction = True

                    if y < ry + edgeHeight and y >= ry:
                        actions.makeSplitAbove = max(0, (y - ry) / rh)
                        hasAction = True

                    if y > ry + rh - edgeHeight and y <= ry + rh:
                        actions.makeSplitBelow = max(0, (ry + rh - y) / rh)
                        hasAction = True

                if not hasAction:
                    self.hideDropPlaceHolder()
                    return

                if isOnlyTab:
                    parent = helper.isAlive(currSplit.parent(), Split)
                    targetParent = helper.isAlive(targetSplit.parent(), Split)
                    if parent and targetParent:
                        first = helper.isAlive(parent.first(), Split)
                        second = helper.isAlive(parent.second(), Split)
                        orient = parent.orientation()

                        if first and second:
                            firstMost = None
                            secondMost = None
                            nextParent = helper.isAlive(parent.parent(), Split)
                            if currSplit == first:
                                firstMost = second.firstMostSplit()
                                if (
                                    nextParent
                                    and parent == nextParent.second()
                                ):
                                    nextParentFirst = nextParent.first()
                                    assert nextParentFirst is not None
                                    secondMost = (
                                        nextParentFirst.secondMostSplit()
                                    )
                            elif currSplit == second:
                                secondMost = first.secondMostSplit()
                                if nextParent and parent == nextParent.first():
                                    nextParentSecond = nextParent.second()
                                    assert nextParentSecond is not None
                                    firstMost = (
                                        nextParentSecond.firstMostSplit()
                                    )

                            if targetParent.orientation() == orient:
                                currRect = currSplit.globalRect(
                                    withToolBar=False
                                )
                                cw = currRect.width()
                                ch = currRect.height()

                                if targetSplit == firstMost:
                                    if (
                                        orient == Qt.Orientation.Vertical
                                        and rh == ch
                                    ):
                                        actions.makeSplitLeft = False
                                    elif (
                                        orient == Qt.Orientation.Horizontal
                                        and rw == cw
                                    ):
                                        actions.makeSplitAbove = False
                                elif targetSplit == secondMost:
                                    if (
                                        orient == Qt.Orientation.Vertical
                                        and rh == ch
                                    ):
                                        actions.makeSplitRight = False
                                    elif (
                                        orient == Qt.Orientation.Horizontal
                                        and rw == cw
                                    ):
                                        actions.makeSplitBelow = False

                if (
                    actions.makeSplitLeft is not False
                    and (
                        actions.makeSplitAbove is False
                        or actions.makeSplitLeft <= actions.makeSplitAbove
                    )
                    and (
                        actions.makeSplitBelow is False
                        or actions.makeSplitLeft <= actions.makeSplitBelow
                    )
                ):
                    targetRect.setWidth(edgeWidth)
                    self._dropAction = "makeSplitLeft"
                elif (
                    actions.makeSplitRight is not False
                    and (
                        actions.makeSplitAbove is False
                        or actions.makeSplitRight <= actions.makeSplitAbove
                    )
                    and (
                        actions.makeSplitBelow is False
                        or actions.makeSplitRight <= actions.makeSplitBelow
                    )
                ):
                    targetRect.translate(rw - edgeWidth, 0)
                    targetRect.setWidth(edgeWidth)
                    self._dropAction = "makeSplitRight"
                elif actions.makeSplitAbove is not False:
                    targetRect.setHeight(edgeHeight)
                    self._dropAction = "makeSplitAbove"
                elif actions.makeSplitBelow is not False:
                    targetRect.translate(0, rh - edgeHeight)
                    targetRect.setHeight(edgeHeight)
                    self._dropAction = "makeSplitBelow"
                elif actions.transferTab:
                    targetRect = targetSplit.globalRect()
                    self._dropAction = "transferTab"

                if self._dropAction:
                    self._dropSplit = targetSplit
                    self.showDropPlaceHolder(targetRect)
                else:
                    self.hideDropPlaceHolder()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragIndex != -1:
            self._dragPos = toPoint(getEventGlobalPos(event))
            if self._dragTimer is None:
                self._dragTimer = QTimer()
                self._dragTimer.timeout.connect(self.handleDropZone)
                self._dragTimer.start(50)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        qwin = self._helper.getQwin()
        if not qwin:
            return
        btn = event.button()
        index = self.tabAt(toPoint(getEventPos(event)))
        self._dropEdge = None
        self._dropAction = None
        self._dropSplit = None
        if index >= 0:
            if btn == Qt.MouseButton.LeftButton:
                self._sync(index)
            elif btn == Qt.MouseButton.MiddleButton:
                self._dragStart = getEventGlobalPos(event)
                self._dragIndex = index
                globalPos = toPoint(getEventGlobalPos(event))
                pos = qwin.mapFromGlobal(globalPos)
                self.showDragPlaceHolder(pos)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            elif btn == Qt.MouseButton.RightButton:
                parent = self._helper.isAlive(self.parent(), SplitToolbar)
                if parent:
                    parent.showMenu(event, tabIndex=index)
            self.tabPress.emit(event, index)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        helper = self._helper
        dropSplit = helper.isAlive(self._dropSplit, Split)
        if self._dragIndex != -1 and self._dropAction and dropSplit:
            if self._dropAction == "makeSplitAtEdge":
                assert self._dropEdge is not None
                dropSplit.makeSplitAtEdge(
                    tabIndex=self._dragIndex,
                    tabSplit=self.split(),
                    edge=self._dropEdge,
                )
            else:
                cb = getattr(dropSplit, self._dropAction, None)
                if cb is not None:
                    cb(tabIndex=self._dragIndex, tabSplit=self.split())
                    
            currSplit = self.split()
            if currSplit:
                currSplit.realignCanvas()

        if self._dragTimer:
            self._dragTimer.stop()
            self._dragTimer = None

        self._dragPos = None
        self._dragIndex = -1
        self._dropAction = None
        self._dropSplit = None
        self._dropEdge = None

        self.hideDragPlaceHolder()
        self.hideDropPlaceHolder()
        self.unsetCursor()

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
                    "splitWindowUid", None
                )

    def setUid(self, index: int, uid: int):
        if index >= 0 and index < self.count():
            self.setTabData(index, {"splitWindowUid": uid})

    def getTabByView(self, view: View) -> int:
        data = self._helper.getViewData(view)
        uid = data.get("splitWindowUid", None) if data else None
        if uid is not None:
            for i in range(self.count()):
                if self.getUid(i) == uid:
                    return i
        return -1

    def getTabByWindow(self, win: QMdiSubWindow) -> int:
        uid = win.property("splitWindowUid")
        if uid is not None:
            for i in range(self.count()):
                if self.getUid(i) == uid:
                    return i
        return -1

    def getWindow(self, index: int | None = None) -> QMdiSubWindow | None:
        uid = self.getUid(index)
        if uid is not None:
            data = self._controller.getViewData(uid)
            if data is not None:
                return data.win

    def getView(self, index: int | None = None) -> View | None:
        uid = self.getUid(index)
        if uid is not None:
            data = self._controller.getViewData(uid)
            if data is not None:
                return data.view


class SplitToolbar(QWidget):
    MenuIcon = None

    def __init__(
        self, parent: QWidget, controller: "SplitPane", split: "Split"
    ):
        super().__init__(parent)
        self._split: "Split" = split
        self._controller: "SplitPane" = controller
        self._helper: Helper = controller.helper()
        self._tabs: SplitTabs = SplitTabs(self, controller=controller)
        self._menu: QMenu | None = None

        if SplitToolbar.MenuIcon is None:
            pix = QPixmap(
                ":/dark_hamburger_menu_dots.svg"
                if self._helper.useDarkIcons()
                else ":/light_hamburger_menu_dots.svg"
            )
            transform = QTransform().rotate(90)
            rotated = pix.transformed(transform)
            SplitToolbar.MenuIcon = QIcon(rotated)

        self._menuBtn = QPushButton("", self)
        self._menuBtn.setIcon(SplitToolbar.MenuIcon)
        self._menuBtn.setProperty("class", "menuButton")
        self._menuBtn.setFixedSize(38, self._tabs.height())
        self._menuBtn.clicked.connect(self.showMenu)

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

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2c2c2c"))

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
        hasSplits = topSplit.state() == Split.STATE_SPLIT

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
                enabled=hasTabs,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Right"),
                callback=lambda: self._split.makeSplitRight(tabIndex=tabIndex),
                enabled=hasTabs,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Above"),
                callback=lambda: self._split.makeSplitAbove(tabIndex=tabIndex),
                enabled=hasTabs,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Move Below"),
                callback=lambda: self._split.makeSplitBelow(tabIndex=tabIndex),
                enabled=hasTabs,
                separator=True,
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Left"),
                callback=lambda: self._split.makeSplitLeft(
                    dupe=True, tabIndex=tabIndex
                ),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Right"),
                callback=lambda: self._split.makeSplitRight(
                    dupe=True, tabIndex=tabIndex
                ),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Above"),
                callback=lambda: self._split.makeSplitAbove(
                    dupe=True, tabIndex=tabIndex
                ),
                visible=hasTabIndex,
            ),
            MenuAction(
                text=i18n("Split && Duplicate Below"),
                callback=lambda: self._split.makeSplitBelow(
                    dupe=True, tabIndex=tabIndex
                ),
                separator=True,
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
                separator=True,
            ),
            MenuAction(
                text=i18n("Reset Layout"),
                callback=lambda: self._split.resetLayout(),
            ),
            MenuAction(
                text=i18n("Equalize Sizes"),
                callback=lambda: typing.cast(
                    Split, self._split.topSplit()
                ).equalize(),
                enabled=hasSplits,
                separator=True,
            ),
            MenuAction(
                text=i18n("Options"),
                callback=showOptions,
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
        x = self.width() - self._menuBtn.width()
        y = (self.height() - self._menuBtn.height()) // 2
        self._menuBtn.move(x, y)

        self._tabs.setFixedHeight(self.height())
        self._tabs.setGeometry(0, 0, x, self.height())


class SplitHandle(QWidget):
    SIZE = 10

    def __init__(
        self,
        split: "Split",
        helper: Helper,
        orient: Qt.Orientation | None = None,
    ):
        super().__init__(helper.getMdi())
        self._helper: Helper = helper
        self._split: "Split" = split
        self._lastMousePos: QPoint = QPoint()
        self._dragging: bool = False
        self._dragDelta: int = 0
        self._dragTimer: QTimer | None = None
        self._orient: Qt.Orientation = (
            orient
            if isinstance(orient, Qt.Orientation)
            else Qt.Orientation.Vertical
        )
        self.setCursor(
            self._orient == Qt.Orientation.Vertical
            and Qt.CursorShape.SizeHorCursor
            or Qt.CursorShape.SizeVerCursor
        )

        self.reset()
        self.clamp()
        self.raise_()
        self.show()

    def setSplit(self, split: "Split"):
        self._split = split

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        bg = self._helper.paletteColor("Window")
        p.fillRect(self.rect(), bg)

    def globalRect(self):
        qwin = self._helper.getQwin()
        mdi = self._helper.getMdi()
        if qwin and mdi:
            rect = self.geometry()
            return QRect(
                mdi.mapTo(qwin, QPoint(rect.x(), rect.y())),
                rect.size(),
            )
        return QRect()

    def orientation(self) -> Qt.Orientation:
        return self._orient

    def setOrientation(self, orient: Qt.Orientation, redraw: bool = True):
        if (
            orient in (Qt.Orientation.Horizontal, Qt.Orientation.Vertical)
            and orient != self._orient
        ):
            self._orient = orient
            self.setCursor(
                self._orient == Qt.Orientation.Vertical
                and Qt.CursorShape.SizeHorCursor
                or Qt.CursorShape.SizeVerCursor
            )
            if redraw:
                self.reset()
                self.clamp()
            return True

    def reset(self):
        x, y, w, h = self._split.getRect()
        if self._orient == Qt.Orientation.Vertical:
            self.setGeometry(
                x + int((w - SplitHandle.SIZE) / 2),
                y,
                SplitHandle.SIZE,
                h,
            )
        else:
            self.setGeometry(
                x,
                y + int((h - SplitHandle.SIZE) / 2),
                w,
                SplitHandle.SIZE,
            )

    def clamp(self):
        px, py, pw, ph = self._split.getRect()
        w = self.width()
        h = self.height()
        if self._orient == Qt.Orientation.Vertical:
            if pw < 100:
                self.reset()
                return
            if h != ph:
                self.resize(w, ph)
                h = ph
            x = max(px + 80, min(self.x(), px + pw - w - 80))
            y = max(py, min(self.y(), py + ph - h))
        else:
            if ph < 100:
                self.reset()
                return
            if w != pw:
                self.resize(pw, h)
                w = pw
            x = max(px, min(self.x(), px + pw - w))
            y = max(py + 80, min(self.y(), py + ph - h - 80))
        if x != self.x() or y != self.y():
            self.move(x, y)

    def event(self, event: QEvent):
        event_type = event.type()
        if event_type == QEvent.Type.ParentAboutToChange:
            pass
        elif event_type == QEvent.Type.ParentChange:
            pass
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._dragDelta = 0
            self._lastMousePos = toPoint(getEventGlobalPos(event))
            event.accept()

    def offset(self) -> int:
        x, y, *_ = self.geometry().getRect()
        return x if self._orient == Qt.Orientation.Vertical else y

    def moveTo(self, offset: int = 0):
        if self._orient == Qt.Orientation.Vertical:
            self.move(offset, self.y())
        else:
            self.move(self.x(), offset)

        self.clamp()
        first = self._split.first()
        second = self._split.second()

        if first:
            first.resize()
        if second:
            second.resize()

    def handleMove(self):
        if self._dragDelta == 0:
            return
        if self._orient == Qt.Orientation.Vertical:
            self.moveTo(self.x() + self._dragDelta)
        else:
            self.moveTo(self.y() + self._dragDelta)
        self._dragDelta = 0

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            if self._dragTimer is None:
                self._dragTimer = QTimer()
                self._dragTimer.timeout.connect(self.handleMove)
                self._dragTimer.start(10)

            pos = toPoint(getEventGlobalPos(event))
            if self._orient == Qt.Orientation.Vertical:
                self._dragDelta += pos.x() - self._lastMousePos.x()
            else:
                self._dragDelta += pos.y() - self._lastMousePos.y()
            self._lastMousePos = pos
            event.accept()

            mdi = self._helper.getMdi()
            if mdi:
                subwin = mdi.activeSubWindow()
                for c in subwin.findChildren(QWidget):
                    cls = c.metaObject().className()
                    if "KisFloatingMessage" in cls or "FloatingMessage" in cls:
                        c.setVisible(False)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragTimer:
                self._dragTimer.stop()
                self._dragTimer = None
            first = self._split.first()
            second = self._split.second()
            if first:
                first.resize()
            if second:
                second.resize()
            self._dragging = False
            event.accept()


class Split(QObject):
    STATE_SPLIT = 0
    STATE_COLLAPSED = 1

    resized = pyqtSignal()

    def __init__(
        self,
        parent: "Split | QWidget",
        controller: "SplitPane",
        toolbar: SplitToolbar | None = None,
        state: int | None = None,
        orient: Qt.Orientation = Qt.Orientation.Vertical,
        first: "Split | None" = None,
        second: "Split | None" = None,
    ):
        super().__init__(parent)

        self._controller = controller
        self._helper = controller.helper()
        self._state: int = Split.STATE_COLLAPSED if state is None else state
        self._rect: QRect = QRect()
        self._first: "Split | None" = first
        self._second: "Split | None" = second
        self._handle: "SplitHandle | None" = None
        self._toolbar: SplitToolbar | None = None
        self._attachResizeCallback: typing.Callable[..., Any] | None = None
        self._resizing: bool = False
        self._closing: bool = False
        self._forceResizing: bool = False
        self._lastHandleRect: QRect = QRect()

        mdi = self._helper.getMdi()
        assert mdi

        if self._state == Split.STATE_COLLAPSED:
            if isinstance(toolbar, SplitToolbar):
                self._toolbar = toolbar
                self._toolbar.setSplit(self)
                self._toolbar.setParent(mdi)
            else:
                self._toolbar = SplitToolbar(
                    parent=mdi,
                    split=self,
                    controller=self._controller,
                )

            self._toolbar.raise_()
            self._toolbar.show()
        else:
            self._handle = SplitHandle(
                self, helper=self._helper, orient=orient
            )
            assert self._first is not None
            assert self._second is not None
            self._first.setParent(self)
            self._second.setParent(self)

        self.attachEvents()
        self.destroyed.connect(self.clear)
        self._overlay = None

    def state(self) -> int:
        return self._state

    def showOverlay(self):
        if not self._overlay:
            qwin = self._helper.getQwin()
            rect = self.globalRect()
            if qwin:
                self._overlay = TabDragRect(qwin)
                self._overlay.show()
                self._overlay.setGeometry(rect)

    def hideOverlay(self):
        if self._overlay:
            self._overlay.deleteLater()
            self._overlay = None

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
                    self.resize()

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
                self.resize()
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
                self.resize(force=True)
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
        tabs = self._helper.isAlive(self.tabs(), SplitTabs)
        if tabs:
            return tabs.getWindow(index)

    def getTabView(self, index: int) -> View | None:
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

    def close(self):
        helper = self._helper
        if self._closing or not helper.isAlive(self, Split):
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
        if isinstance(parent, Split) and self._state == Split.STATE_COLLAPSED:
            first = parent._first
            second = parent._second
            assert first is not None
            assert second is not None
            if (
                first._state == Split.STATE_COLLAPSED
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
                    topSplit.resize(force=True)
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
                    topSplit.resize(force=True)
                parent.equalize()

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
            self._toolbar.tabs().purgeAllTabs()
            self._toolbar.deleteLater()
            self._toolbar = None
        if self._first:
            self._first.clear(True)
            self._first = None
        if self._second:
            self._second.clear(True)
            self._second = None
        if removeSelf and helper.isAlive(self, Split):
            # controller = self.controller()
            # helper = self._helper
            parent = self.parent()
            if parent and isinstance(parent, Split):
                if self == parent._first:
                    parent._first = None
                elif self == parent._second:
                    parent._second = None
            self.detachEvents()
            self.deleteLater()
            # XXX
            # central = helper.getCentral()
            # if central.findChild(Split) is None:
            #     controller.unsyncAllTabs()

    def isForceResizing(self):
        if self._forceResizing:
            return True
        top = self._helper.isAlive(self, Split)
        while top:
            top = self._helper.isAlive(top.parent(), Split)
            if top and top._forceResizing:
                return True
        return False

    def resize(self, force: bool = True):
        if self._resizing:
            return
        self._forceResizing = force
        self._resizing = True
        parent = self.parent()
        old_rect = self._rect
        if isinstance(parent, QWidget):
            # this is the origin rect x=0,y=0
            self._rect = parent.rect()
        elif isinstance(parent, Split):
            first = parent._first
            second = parent._second
            handle = parent._handle
            assert first is not None
            assert second is not None
            assert handle is not None
            px, py, pw, ph = parent.getRect()
            hx, hy, hw, hh = handle.geometry().getRect()
            if first == self:
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

        if self._state == Split.STATE_SPLIT:
            assert self._first is not None
            assert self._second is not None
            assert self._handle is not None
            handleRect = self._handle.globalRect()
            if (
                old_rect != self._rect
                or handleRect != self._lastHandleRect
                or self.isForceResizing()
            ):
                self._handle.clamp()
                self._lastHandleRect = handleRect
                self._first.resize()
                self._second.resize()
        elif self._state == Split.STATE_COLLAPSED and (
            old_rect != self._rect or self.isForceResizing()
        ):
            if self._toolbar is not None:
                self._toolbar.setFixedHeight(TAB_BAR_HEIGHT)
                self._toolbar.setGeometry(
                    self._rect.x(),
                    self._rect.y(),
                    self._rect.width(),
                    TAB_BAR_HEIGHT,
                )
                self.resizeSubWindow()
            self.resized.emit()
        self._forceResizing = False
        self._resizing = False

    def resizeSubWindow(self):
        if self._state != Split.STATE_COLLAPSED:
            return

        helper = self._helper
        win = helper.isAlive(self.getActiveTabWindow(), QMdiSubWindow)
        toolbar = helper.isAlive(self._toolbar, SplitToolbar)
        if win and toolbar:
            helper.disableToast()
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
            helper.enableToast()

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
                rect.setY(rect.y() + TAB_BAR_HEIGHT)
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
        dupe: bool = False,
    ):
        helper = self._helper
        tabs = tabSplit.tabs()

        if not tabs:
            return

        if tabIndex is None:
            tabIndex = tabSplit.currentIndex()

        uid = tabs.getUid(tabIndex)
        data = self._controller.getViewData(uid)

        if not data:
            return

        if dupe:
            self.controller().syncView(
                view=data.view, split=self, addView=True
            )
        else:
            kritaTab = self.controller().getIndexByView(data.view)
            if kritaTab != -1:
                self.controller().syncView(index=kritaTab, split=self)

        def cb():
            if helper.isAlive(tabSplit, Split):
                tabs = helper.isAlive(tabSplit.tabs(), SplitTabs)
                if (
                    not tabs or tabs.count() == 0
                ) and tabSplit.topSplit() != tabSplit:
                    tabSplit.close()

        QTimer.singleShot(10, cb)

    # TODO pass in new tab or view
    def makeSplit(
        self,
        orient: Qt.Orientation,
        dupe: bool = False,
        swap: bool = False,
        empty: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
    ):
        if self._state == Split.STATE_COLLAPSED:
            tabs = self.tabs()

            if not tabs:
                return

            isSelf = tabSplit == self
            toolbar = self._toolbar
            self._toolbar = None
            self._handle = SplitHandle(
                self, helper=self._helper, orient=orient
            )
            ret = (None, None)
            if swap:
                self._second = Split(
                    self, toolbar=toolbar, controller=self._controller
                )
                self._first = Split(self, controller=self._controller)
                ret = (self._first, self._second)
            else:
                self._first = Split(
                    self, toolbar=toolbar, controller=self._controller
                )
                self._second = Split(self, controller=self._controller)
                ret = (self._second, self._first)

            self._state = Split.STATE_SPLIT

            if not empty:
                # edge case tabSplit was passed in but it got split and now is first or second
                if isSelf:
                    tabSplit = self._second if swap else self._first
                elif tabSplit is None:
                    tabSplit = ret[1]

                if tabIndex is None:
                    tabIndex = tabSplit.currentIndex()

                ret[0].transferTab(
                    tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                )

            topSplit = self.topSplit()
            if topSplit:
                topSplit.resize(force=True)
            self._first.realignCanvas(nested=True)
            self._second.realignCanvas(nested=True)
            return ret

    def makeSplitBelow(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
    ):
        return self.makeSplit(
            Qt.Orientation.Horizontal,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
        )

    def makeSplitAbove(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
    ):
        return self.makeSplit(
            Qt.Orientation.Horizontal,
            swap=True,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
        )

    def makeSplitRight(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
    ):
        return self.makeSplit(
            Qt.Orientation.Vertical,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
        )

    def makeSplitLeft(
        self,
        dupe: bool = False,
        tabIndex: int | None = None,
        tabSplit: "Split | None" = None,
    ):
        return self.makeSplit(
            Qt.Orientation.Vertical,
            swap=True,
            dupe=dupe,
            tabIndex=tabIndex,
            tabSplit=tabSplit,
        )

    def makeSplitBetween(
        self,
        dupe: bool = False,
        tabSplit: "Split | None" = None,
        tabIndex: int | None = None,
    ):
        if self._state == Split.STATE_SPLIT:
            assert self._handle is not None
            assert self._first is not None
            assert self._second is not None

            second = self._second
            orient = self._handle.orientation()

            split = Split(self, controller=self._controller)
            toolbar = split._toolbar
            split._toolbar = None
            split._handle = SplitHandle(
                split, helper=self._helper, orient=orient
            )
            split._first = Split(
                split, toolbar=toolbar, controller=self._controller
            )
            split._second = second
            split._second.setParent(split)
            split._state = Split.STATE_SPLIT

            self._second = split

            if tabSplit is not None and tabIndex is not None:
                split._first.transferTab(
                    tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                )

            topSplit = self.topSplit()
            if topSplit:
                topSplit.resize(force=True)
            return split._first

    def makeSplitAtEdge(
        self,
        edge: Qt.AnchorPoint,
        dupe: bool = False,
        tabSplit: "Split | None" = None,
        tabIndex: int | None = None,
    ):
        topSplit = self.topSplit()
        if topSplit and topSplit.state() == Split.STATE_SPLIT:
            sizes = topSplit.saveSizes()

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

            if tabSplit is not None and tabIndex is not None:
                targetSplit.transferTab(
                    tabSplit=tabSplit, tabIndex=tabIndex, dupe=dupe
                )

            second.restoreSizes(sizes, orient=second.orientation())

    def resetLayout(self):
        tabs = self._helper.getTabBar()
        split = self.defaultSplit(False)
        if tabs and split:
            for i in range(tabs.count()):
                self._controller.syncView(index=i, split=split)
            topSplit = self.topSplit()
            if topSplit:
                topSplit.closeEmpties()

    def realignCanvas(
        self,
        index: int | None = None,
        view: View | None = None,
        nested: bool = False,
    ):
        if self._state == Split.STATE_COLLAPSED:
            helper = self._helper
            tabs = self.tabs()
            if not tabs:
                return

            def cb(_, data):
                app = helper.getApp()
                qwin = helper.getQwin()
                if app and qwin:
                    w, h = data.win.width(), data.win.height()
                    rawZoom = helper.getZoomLevel(True)
                    data.win.setFixedHeight(h + 1)
                    data.win.setFixedWidth(w + 1)
                    rawZoomX = helper.getZoomLevel(True)
                    fitToView = rawZoom != helper.getZoomLevel(True)
                    data.win.setFixedHeight(h)
                    data.win.setFixedWidth(w)

                    if not fitToView:
                        zoom = helper.getZoomLevel()
                        app.action("zoom_to_fit").trigger()
                        helper.setZoomLevel(zoom)

            tabs.exec(cb, index=index, view=view)
        elif self._state == Split.STATE_SPLIT and nested:
            if self._first:
                self._first.realignCanvas(nested=True)
            if self._second:
                self._second.realignCanvas(nested=True)

    def saveSizes(self) -> list[tuple["Split", int]]:
        if self._state == Split.STATE_SPLIT:
            assert self._first is not None
            assert self._second is not None
            assert self._handle is not None
            return (
                [(self._first, self._handle.offset())]
                + self._first.saveSizes()
                + self._second.saveSizes()
            )
        return []

    def restoreSizes(
        self,
        sizes: list[tuple["Split", int]],
        orient: Qt.Orientation | None = None,
    ):
        for sz in sizes:
            split, offset = sz
            parent = self._helper.isAlive(split.parent(), Split)
            if parent:
                handle = parent.handle()
                if handle:
                    if orient is None or orient == handle.orientation():
                        handle.moveTo(offset)

    def closeEmpties(self):
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


class SplitPane(Component):
    def __init__(self, window: Window):
        super().__init__(window)
        self._quit: bool = False
        self._syncing: bool = False
        self._viewData: dict[int, ViewData] = {}
        self._split: Split | None = None
        self._activeToolbar: SplitToolbar | None = None
        self._colors: SimpleNamespace | None = None
        self._optEnabled = getOpt("toggle", "split_panes")

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_next_tab",
            i18n("Goto next tab"),
            self.nextTab,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_prev_tab",
            i18n("Goto previous tab"),
            self.prevTab,
        )

        qapp = typing.cast(QApplication, QApplication.instance())
        qapp.aboutToQuit.connect(lambda: self.onQuit())

        self._poll = SimpleNamespace(short=QTimer(), long=QTimer())
        self._poll.short.timeout.connect(self.shortPoll)
        self._poll.long.timeout.connect(self.longPoll)

        self.attachStyles()

        OptionSignals.configSaved.connect(self.onConfigSave)

    def onQuit(self):
        self._quit = True

    def onConfigSave(self):
        isEnabled = getOpt("toggle", "split_panes")
        if isEnabled != self._optEnabled:
            self.toggleStyles()
            self.handleSplitter()
            self._optEnabled = isEnabled

    def shortPoll(self):
        if self._quit:
            return
        helper = self._helper
        doc = helper.getDoc()
        tabs = helper.getTabBar()
        if doc and tabs:
            self.updateDocumentTabs(doc)

    def longPoll(self):
        if self._quit:
            return
        helper = self._helper
        app = helper.getApp()
        tabs = helper.getTabBar()
        if app and tabs:
            for doc in app.documents():
                self.updateDocumentTabs(doc)

    def updateDocumentTabs(self, doc: Document):
        helper = self._helper
        tabs = helper.getTabBar()
        if not tabs:
            return

        data = helper.getDocData(doc)
        if not data:
            return
        currTabText = data.doc.get("tabText", None)
        view = data.views[0][0]
        index = self.getIndexByView(view)
        tabText = tabs.tabText(index)
        if len(tabText) > TAB_TEXT_MAX_LEN:
            tabText = f"…{tabText[-TAB_TEXT_MAX_LEN:]}"

        if currTabText != tabText:
            data.doc["tabText"] = tabText
            for v in data.views:
                view = v[0]
                index = self.getIndexByView(view)
                uid = self.getUid(index)
                if uid is not None:
                    viewData = self.getViewData(uid)
                    if viewData is not None:
                        toolbar = helper.isAlive(
                            viewData.toolbar, SplitToolbar
                        )
                        if toolbar:
                            toolbarTabs = toolbar.tabs()
                            splitTabIndex = toolbarTabs.getTabByView(view)
                            toolbarTabs.setTabText(splitTabIndex, tabText)

    def handleSplitter(self):
        helper = self._helper
        mdi = helper.getMdi()
        central = helper.getCentral()

        isEnabled = getOpt("toggle", "split_panes")

        if (
            not self.isHomeScreenShowing()
            and central
            and mdi
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
            and isEnabled
        ):
            if not self._split:
                self._viewData = {}

                self._split = Split(parent=central, controller=self)
                for i, _ in enumerate(mdi.subWindowList()):
                    self.syncView(index=i)

                self._poll.short.start(500)
                self._poll.long.start(5000)

        elif self._split:
            self._poll.short.stop()
            self._poll.long.stop()

            qwin = helper.getQwin()
            if qwin and mdi:
                updates = qwin.updatesEnabled()
                qwin.setUpdatesEnabled(False)
                viewMode = mdi.viewMode()

                for w in mdi.subWindowList():
                    w.showMaximized()
                    if viewMode == QMdiArea.ViewMode.SubWindowView:
                        w.showNormal()
                    w.setMinimumHeight(0)
                    w.setMaximumHeight(QWIDGETSIZE_MAX)
                    w.setMinimumWidth(0)
                    w.setMaximumWidth(QWIDGETSIZE_MAX)
                qwin.setUpdatesEnabled(updates)

                def cb():
                    mdi = helper.getMdi()
                    if mdi:
                        if mdi.viewMode() == QMdiArea.ViewMode.TabbedView:
                            s = mdi.size()
                            mdi.resize(s.width() + 1, s.height())
                            mdi.resize(s)
                        else:
                            mdi.tileSubWindows()

                QTimer.singleShot(0, cb)

            self._viewData = {}
            self._split.clear(True)
            self._split = None

    def colors(self):
        return self._colors

    def toggleStyles(self):
        if getOpt("toggle", "split_panes"):
            self.attachStyles()
        else:
            self.detachStyles()

    def detachStyles(self):
        app = typing.cast(QApplication, QApplication.instance())
        css = app.styleSheet()
        match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
        match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
        css = re.sub(
            rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
        )
        app.setStyleSheet(css)

    def attachStyles(self):
        if not getOpt("toggle", "split_panes"):
            return

        helper = self._helper
        useDarkIcons = helper.useDarkIcons()
        winColor = helper.paletteColor("Window")
        textColor = helper.paletteColor("Text")
        hlColor = helper.paletteColor("Highlight")
        closeIcon = (
            ":/dark_close-tab.svg" if useDarkIcons else ":/light_close-tab.svg"
        )

        colors = (
            SimpleNamespace(
                bar=winColor.darker(130).name(),
                tab=winColor.darker(120).name(),
                tabSeparator=winColor.darker(170).name(),
                tabSelected=winColor.lighter(120).name(),
                tabActive=hlColor.name(),
                tabText=textColor.name(),
                tabClose="lightcoral",
                menuSeparator=textColor.name(),
                splitHandle=winColor.name(),
            )
            if useDarkIcons
            else SimpleNamespace(
                bar=winColor.darker(150).name(),
                tab=winColor.darker(120).name(),
                tabSeparator=winColor.lighter(140).name(),
                tabSelected=winColor.lighter(130).name(),
                tabActive=hlColor.name(),
                tabText=textColor.name(),
                tabClose="darkred",
                menuSeparator=textColor.darker(150).name(),
                splitHandle=winColor.name(),
            )
        )

        style = f"""
                /* KRITA_UI_TWEAKS_STYLESHEET_BEGIN */
                QMainWindow::separator {{
                    background: transparent;
                }}
                QMdiArea[toasts="hidden"] KisFloatingMessage {{
                    opacity: 0;
                    min-width: 0;
                    max-width: 0;
                    min-height: 0;
                    max-height: 0;
                }}
                QMenu[class="splitPaneMenu"] {{
                    padding-top: 10px;
                    padding-bottom: 10px;
                }}
                QMenu[class="splitPaneMenu"]::separator {{
                    height: 1px;
                    margin: 10px 0;
                    background: {colors.menuSeparator};
                }}
                QMdiArea QTabBar, QMdiArea QTabBar::tab {{
                    min-height: 0;   
                    max-height: 0;
                }}
                SplitToolbar QPushButton[class="menuButton"] {{
                    background: {colors.bar};
                    border: none;
                    min-height: {TAB_BAR_HEIGHT}px;   
                    max-height: {TAB_BAR_HEIGHT}px;
                }}
                QMdiArea SplitTabs {{
                    qproperty-drawBase: 0;
                    background: {colors.bar};      
                    min-height: {TAB_BAR_HEIGHT}px;   
                    max-height: {TAB_BAR_HEIGHT}px;
                    border: 0;
                    margin: 0;
                    padding: 0;
                    padding-right: 50px;
                }}
                QMdiArea SplitTabs QToolButton {{
                    border: none;
                    background: {colors.bar};      
                }}
                QMdiArea SplitTabs::tab {{
                    min-width: 1px; 
                    max-width: 400px; 
                    height: 34px;     
                    min-height: {TAB_BAR_HEIGHT}px;   
                    max-height: {TAB_BAR_HEIGHT}px;
                    background: {colors.tab};
                    border-radius: 0;
                    border: 1px solid {colors.tab};
                    border-right: 1px solid {colors.tabSeparator};
                    padding: 0px 12px;
                }}
                QMdiArea SplitTabs::tab:last {{
                    border-right: 1px solid {colors.tabSeparator};
                }}
                QMdiArea SplitTabs::tab:selected {{
                    background: {colors.tabSelected}; 
                    border: 1px solid {colors.tabSelected};
                    border-right: 1px solid {colors.tabSelected};
                }}
                QMdiArea SplitTabs::close-button {{
                    image: url({closeIcon});
                    padding: 2px;
                    background: none;
                }}
                QMdiArea SplitTabs QAbstractButton[hover="true"] {{
                    background-color: {colors.tabClose};
                }}
                QMdiArea SplitTabs::close-button:pressed {{
                    background-color: red;
                }}
                QHeaderView::section {{
                    padding: 7px;
                }}
                QMdiArea SplitTabs::tear {{
                    width: 0px; 
                    border: none;
                }}
                QMdiArea SplitTabs[class="active"]::tab:selected {{
                    background: {colors.tabActive}; 
                    border: 1px solid {colors.tabActive};
                    border-right: 1px solid {colors.tabActive};
                }}
                /* KRITA_UI_TWEAKS_STYLESHEET_END */
            """

        self._colors = colors
        app = typing.cast(QApplication, QApplication.instance())

        css = app.styleSheet()

        match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
        match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
        css = re.sub(
            rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
        )
        app.setStyleSheet(css + style)

    def onWindowShown(self):
        super().onWindowShown()
        self.handleSplitter()

    def onViewModeChanged(self):
        super().onViewModeChanged()
        self.handleSplitter()

    def onHomeScreenToggled(self, visible: bool = False):
        super().onHomeScreenToggled(visible)
        self.handleSplitter()

    def onThemeChanged(self):
        if not self.topSplit():
            return

        self.attachStyles()

    def onViewChanged(self):
        if not self.topSplit():
            return
        super().onViewChanged()
        helper = self._helper
        mdi = helper.getMdi()
        if mdi:
            activeWin = mdi.activeSubWindow()
            winList = mdi.subWindowList()
            if activeWin and winList:
                activeIndex = winList.index(activeWin)
                self.syncView(index=activeIndex)

    def onSubWindowDestroyed(self, uid: int | None) -> None:
        helper = self._helper
        if isinstance(uid, int):
            data = self.popViewData(uid)
            if data:
                toolbar = helper.isAlive(data.toolbar, SplitToolbar)
                split = helper.isAlive(
                    toolbar.split() if toolbar else None, Split
                )
                if split:
                    tabs = helper.isAlive(split.tabs(), SplitTabs)
                    if tabs:
                        splitTabIndex = tabs.getTabByView(data.view)
                        if splitTabIndex != -1:
                            tabs.removeTab(splitTabIndex)

                def cb():
                    closeSplit = helper.isAlive(split, Split)
                    if closeSplit:
                        tabs = helper.isAlive(closeSplit.tabs(), SplitTabs)
                        if not tabs or tabs.count() == 0:
                            if closeSplit.topSplit() != closeSplit:
                                closeSplit.close()
                            self.setActiveToolbar()

                QTimer.singleShot(10, cb)

    def topSplit(self) -> "Split | None":
        central = self._helper.getCentral()
        if central:
            return central.findChild(Split)

    def defaultSplit(self, checkToolbar: bool = True) -> "Split | None":
        if checkToolbar:
            toolbar = self._helper.isAlive(self._activeToolbar, SplitToolbar)
            if toolbar:
                return toolbar.split()

        topSplit = self.topSplit()
        if topSplit:
            return topSplit.firstMostSplit()

    def nextTab(self):
        split = self.defaultSplit()
        if split:
            tabs = split.tabs()
            if tabs:
                tabs.nextTab()

    def prevTab(self):
        split = self.defaultSplit()
        if split:
            tabs = split.tabs()
            if tabs:
                tabs.prevTab()

    def setActiveToolbar(self, curr: SplitToolbar | None = None):
        top = self.topSplit()
        self._activeToolbar = self._helper.isAlive(
            self._activeToolbar, SplitToolbar
        )
        if not top or top.state() == Split.STATE_COLLAPSED:
            if self._activeToolbar:
                self._activeToolbar.tabs().setActiveHighlight(False)
            if top:
                self._activeToolbar = top.toolbar()
            else:
                self._activeToolbar = None
        elif curr:
            if self._activeToolbar and self._activeToolbar != curr:
                self._activeToolbar.tabs().setActiveHighlight(False)

            if top.state() == Split.STATE_SPLIT:
                self._activeToolbar = curr
                self._activeToolbar.tabs().setActiveHighlight(True)
            else:
                self._activeToolbar = None

    @contextmanager
    def _syncedCall(self):
        if self._syncing:
            yield False
            return

        helper = self._helper
        qwin = helper.getQwin()
        mdi = helper.getMdi()
        win = helper.getWin()

        if not (qwin and mdi and win):
            yield False
            return

        self._syncing = True
        updates = qwin.updatesEnabled()
        qwin.setUpdatesEnabled(False)
        helper.disableToast()
        try:
            yield True
        finally:
            helper.enableToast()
            qwin.setUpdatesEnabled(updates)
            self._syncing = False

    def syncView(
        self,
        index: int | None = None,
        split: "Split|None" = None,
        view: View | None = None,
        document: Document | None = None,
        addView: bool = False,
    ):

        if self._syncing or self._quit:
            return

        addTab = False
        with self._syncedCall() as sync:
            if not sync:
                return

            helper = self._helper
            tabs = helper.getTabBar()

            if not tabs:
                return

            mdi = helper.getMdi()
            qwin = helper.getQwin()
            win = helper.getWin()

            assert mdi is not None
            assert qwin is not None
            assert win is not None

            if addView:
                if not isinstance(document, Document):
                    if not isinstance(view, View):
                        return
                    document = view.document()
                view = win.addView(document)
                index = mdi.subWindowList().index(mdi.activeSubWindow())
                view = None

            if view is not None:
                index = self.getIndexByView(view)
                assert index != -1

            if index is None:
                return

            uid = self.getUid(index)

            if uid is not None:
                data = self.getViewData(uid)
                defaultSplit = self.defaultSplit()
                activeWin = mdi.subWindowList()[index]
                mdi.setActiveSubWindow(activeWin)
                activeView = helper.getView()

                if not activeView:
                    return

                helper.setViewData(activeView, "splitWindowUid", uid)

                if (
                    defaultSplit
                    and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
                ):

                    if data is None:
                        data = ViewData(
                            view=activeView,
                            win=activeWin,
                            toolbar=(
                                split.toolbar()
                                if split
                                else defaultSplit.toolbar()
                            ),
                            watcher=None,
                            watcherCallback=None,
                        )
                        data.watcherCallback = (
                            lambda _, uid=uid: self.onSubWindowDestroyed(uid)
                        )
                        data.watcher = SubWindowInterceptor(
                            data.watcherCallback
                        )
                        activeWin.installEventFilter(data.watcher)
                        addTab = True
                    else:
                        attachedSplit = helper.isAlive(
                            data.toolbar.split() if data.toolbar else None,
                            Split,
                        )
                        split = helper.isAlive(split, Split)
                        if attachedSplit and split and split != attachedSplit:
                            attachedTabs = attachedSplit.tabs()
                            if attachedTabs:
                                # FIXME refactor getTabByView
                                splitTabIndex = attachedTabs.getTabByView(
                                    data.view
                                )
                                if splitTabIndex != -1:
                                    attachedTabs.removeTab(splitTabIndex)
                            data.toolbar = split.toolbar()
                            addTab = True

                    toolbar = helper.isAlive(data.toolbar, SplitToolbar)
                    if toolbar:
                        toolbarSplit = helper.isAlive(toolbar.split(), Split)
                        toolbarTabs = toolbar.tabs()
                        splitTabIndex = -1
                        if addTab:
                            self.setViewData(uid, data)

                            tabText = tabs.tabText(index)
                            if len(tabText) > TAB_TEXT_MAX_LEN:
                                tabText = f"…{tabText[-TAB_TEXT_MAX_LEN:]}"

                            splitTabIndex = toolbarTabs.addTab(
                                tabs.tabIcon(index), tabText
                            )
                            if splitTabIndex != -1:
                                toolbarTabs.setUid(splitTabIndex, uid)
                                
                            QTimer.singleShot(
                                100,
                                lambda: toolbarSplit.realignCanvas(
                                    view=data.view
                                ),
                            )
                        else:
                            splitTabIndex = toolbarTabs.getTabByView(data.view)

                        if splitTabIndex != -1:
                            toolbarTabs.setCurrentIndex(splitTabIndex)

                        if toolbarSplit:
                            topSplit = toolbarSplit.topSplit()
                            if topSplit:
                                topSplit.resize(force=True)
                            data.win.raise_()
                            data.win.show()
                            ts = toolbar.split()
                            tp = ts.parent()
                            if isinstance(tp, Split):
                                self.setActiveToolbar(toolbar)
                            else:
                                self.setActiveToolbar(toolbar)

    def getUid(self, index: int | None) -> int | None:
        if index is not None:
            helper = self._helper
            mdi = helper.getMdi()
            if not mdi:
                return
            subwindows = mdi.subWindowList()
            if index >= 0 and index < len(subwindows):
                win = subwindows[index]
                uid = win.property("splitWindowUid")
                if not uid:
                    uid = helper.uid()
                    win.setProperty("splitWindowUid", uid)
                return uid

    def getViewData(self, uid: int | None) -> ViewData | None:
        if uid is not None:
            return self._viewData.get(uid, None)

    def setViewData(self, uid: int | None, data: Any) -> ViewData | None:
        if uid is not None:
            self._viewData[uid] = data

    def popViewData(self, uid: int | None) -> ViewData | None:
        if uid is not None:
            return self._viewData.pop(uid, None)

    def getIndexByView(self, view: View | None) -> int:
        mdi = self._helper.getMdi()
        if not mdi:
            return -1
        data = self._helper.getViewData(view)
        uid = data.get("splitWindowUid", None) if data else None
        if uid is not None:
            for i, w in enumerate(mdi.subWindowList()):
                if w.property("splitWindowUid") == uid:
                    return i
        return -1

    def getIndexByWindow(self, win: QMdiSubWindow | None) -> int:
        mdi = self._helper.getMdi()
        try:
            assert mdi is not None
            assert win is not None
            ret = mdi.subWindowList().index(win)
            return ret
        finally:
            return -1

    def getToolbarByView(self, view: View | None) -> SplitToolbar | None:
        if view is not None:
            data = self._helper.getViewData(view)
            uid = data.get("splitWindowUid", None) if data else None
            data = self.getViewData(uid)
            return (
                self._helper.isAlive(data.toolbar, SplitToolbar)
                if data
                else None
            )

    def getToolbarByWindow(
        self, win: QMdiSubWindow | None
    ) -> SplitToolbar | None:
        if win:
            uid = win.property("splitWindowUid")
            data = self.getViewData(uid)
            return (
                self._helper.isAlive(data.toolbar, SplitToolbar)
                if data
                else None
            )

    def getSplitByView(self, view: View | None) -> "Split | None":
        toolbar = self.getToolbarByView(view)
        if toolbar:
            return toolbar.split()

    def getSplitByWindow(self, win: QMdiSubWindow | None) -> "Split | None":
        toolbar = self.getToolbarByWindow(win)
        if toolbar:
            return toolbar.split()

