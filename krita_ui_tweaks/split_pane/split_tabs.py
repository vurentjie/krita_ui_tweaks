# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    toPoint,
    getEventGlobalPos,
    getEventPos,
    pyqtSignal,
    Qt,
    QColor,
    QEvent,
    QFont,
    QFontMetrics,
    QMdiSubWindow,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPoint,
    QProxyStyle,
    QRect,
    QStyle,
    QStyleOption,
    QStyleOptionTab,
    QStyleOptionTabBarBase,
    QStylePainter,
    QTabBar,
    QTimer,
    QWheelEvent,
    QWidget,
)

from krita import View, Document
from typing import Any, TYPE_CHECKING

import typing

from ..options import getOpt

from .split_helpers import SplitData
from .split import Split
from .split_drag import SplitDrag

if TYPE_CHECKING:
    from .split_toolbar import SplitToolbar
    from .split_pane import SplitPane


class RemoveBottomBorder(QProxyStyle):
    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        if element == QStyle.PrimitiveElement.PE_FrameTabBarBase:
            return
        super().drawPrimitive(element, option, painter, widget)


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
        self._redrawDelay = False

        self.setExpanding(False)
        self.setMouseTracking(True)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.tabCloseRequested.connect(self.purgeTab)
        self.setMinimumHeight(0)
        self.setMinimumWidth(0)
        self.attachStyle()
        self._helper.refreshWidget(self)

        self._customStyle = RemoveBottomBorder(self.style())
        self._customStyle.setParent(self)
        self.setStyle(self._customStyle)

        self.currentChanged.connect(self.onCurrentChange)

    def attachStyle(self):
        helper = self._helper
        useDarkIcons = helper.useDarkIcons()
        winColor = helper.paletteColor("Window")
        textColor = helper.paletteColor("Text")
        hlColor = helper.paletteColor("Highlight")
        closeIcon = (
            ":/dark_close-tab.svg" if useDarkIcons else ":/light_close-tab.svg"
        )

        colors = self._controller.adjustedColors()

        tabBarHeight = getOpt("tab_behaviour", "tab_height")
        tabFontSize = getOpt("tab_behaviour", "tab_font_size")
        tabFontBold = (
            "bold" if getOpt("tab_behaviour", "tab_font_bold") else "normal"
        )
        useKritaStyle = getOpt("tab_behaviour", "tab_krita_style")

        if useKritaStyle:
            self.setStyleSheet(
                f"""
                QMdiArea SplitTabs {{
                    background: {winColor.name()};
                    min-height: {tabBarHeight + 2}px;   
                    max-height: {tabBarHeight + 2}px;
                    padding-right: 50px;
                    border: 0;
                }} 
                QMdiArea SplitTabs::tab {{
                    min-width: 1px; 
                    max-width: 400px; 
                    font-size: {tabFontSize}px;
                    font-weight: {tabFontBold};
                    height: {tabBarHeight + 2}px;     
                    min-height: {tabBarHeight + 2}px;   
                    max-height: {tabBarHeight + 2}px;
                }}
                QMdiArea SplitTabs::close-button {{
                    image: url({closeIcon});
                    padding: 2px;
                    background: none;
                    margin: 0;
                }}
                QMdiArea SplitTabs QAbstractButton[hover="true"] {{
                    background-color: {colors.tabClose};
                }}
                QMdiArea SplitTabs::close-button:pressed {{
                    background-color: red;
                }}
                QMdiArea SplitTabs::tear {{
                    width: 0px; 
                    border: none;
                }}
            """
            )

        else:
            self.setStyleSheet(
                f"""
                QMdiArea SplitTabs {{
                    qproperty-drawBase: 0;
                    background: {colors.bar};      
                    min-height: {tabBarHeight}px;   
                    max-height: {tabBarHeight}px;
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
                    font-size: {tabFontSize}px;
                    font-weight: {tabFontBold};
                    height: {tabBarHeight}px;     
                    min-height: {tabBarHeight}px;   
                    max-height: {tabBarHeight}px;
                    background: {colors.tab};
                    border-radius: 0;
                    border: 0;
                    border-right: 1px solid {colors.tabSeparator};
                    padding: 0px 12px;
                }}
                QMdiArea SplitTabs::tab:last {{
                    border-right: 1px solid {colors.tabSeparator};
                }}
                QMdiArea SplitTabs::tab:selected {{
                    background: {colors.tabSelected}; 
                    border-right: 1px solid {colors.tabSeparator};
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
                QMdiArea SplitTabs::tear {{
                    width: 0px; 
                    border: none;
                }}
                QMdiArea SplitTabs[class="active"]::tab:selected {{
                    background: {colors.tabActive}; 
                    border-right: 1px solid {colors.tabActive};
                }}
            """
            )

    def tabSizeHint(self, index: int):
        size = super().tabSizeHint(index)
        tabBarHeight = getOpt("tab_behaviour", "tab_height")
        tabFontSize = getOpt("tab_behaviour", "tab_font_size")
        tabFontBold = getOpt("tab_behaviour", "tab_font_bold")
        font = QFont(self.font())
        font.setBold(tabFontBold)
        font.setPixelSize(tabFontSize)
        metrics = QFontMetrics(font)
        text = self.tabText(index)
        size.setWidth(
            size.width()
            + metrics.horizontalAdvance(text)
            - metrics.horizontalAdvance(text)
            + 6
        )
        return size

    def paintEvent(self, event: QPaintEvent):

        if not getOpt("tab_behaviour", "tab_krita_style"):
            super().paintEvent(event)
            return

        painter = QStylePainter(self)
        colors = self._controller.adjustedColors()
        tabFontSize = getOpt("tab_behaviour", "tab_font_size")
        tabFontBold = getOpt("tab_behaviour", "tab_font_bold")
        active = self.property("class") == "active"

        dragIndex = self._draggable.defaultDragIndex()
        
            
        if not self._redrawDelay:
            for i in range(self.count()):
                if i == dragIndex or (
                    dragIndex != -1 and i == self.currentIndex()
                ):
                    continue
                opt = QStyleOptionTab()
                self.initStyleOption(opt, i)

                font = painter.font()
                font.setBold(tabFontBold)
                font.setPixelSize(tabFontSize)
                painter.setFont(font)
                opt.fontMetrics = QFontMetrics(font)

                if (
                    active
                    and (opt.state & QStyle.StateFlag.State_Selected)
                    and dragIndex == -1
                    and not self._redrawDelay
                ):
                    pal = QPalette(opt.palette)
                    pal.setColor(
                        QPalette.ColorRole.Window, QColor(colors.tabActive)
                    )
                    opt.palette = pal

                painter.drawControl(QStyle.ControlElement.CE_TabBarTab, opt)

        if dragIndex != -1 or self._redrawDelay:
            self._redrawDelay = True
            
            super().paintEvent(event)

            def cb():
                self._redrawDelay = False
                self.update()

            self._helper.debounceCallback(
                f"repaintSplitTab{id(self)}", cb, timeout_seconds=0.4
            )

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

    def getTabByDocument(self, doc: Document) -> int:
        if self._helper.isAlive(doc, Document):
            for i in range(self.count()):
                uid = self.getUid(i)
                data = self._controller.getSplitData(uid)
                if data and data.view and data.view.document() == doc:
                    return i

            fname = doc.fileName()
            for i in range(self.count()):
                uid = self.getUid(i)
                data = self._controller.getSplitData(uid)
                if data and data.view:
                    f = data.view.document().fileName()
                    if f and f == fname:
                        return i
        return -1

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

