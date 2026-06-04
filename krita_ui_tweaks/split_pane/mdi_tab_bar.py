from ..pyqt import (
    toPoint,
    getEventGlobalPos,
    QApplication,
    Qt,
    QIcon,
    QTabBar,
    QWidget,
    QColor,
    QTimer,
    QPoint,
    QEvent,
    QResizeEvent,
    QPaintEvent,
    QMouseEvent,
    QPalette,
    QStylePainter,
    QStyleOption,
    QStyleOptionTab,
    QRect,
    QPen,
    QFontMetrics,
    QGraphicsDropShadowEffect,
    QPainter,
    QStyle,
    QSize,
    QToolButton,
    QMessageBox,
)

from ..options import showOptions, getOpt, signals as OptionSignals

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

if TYPE_CHECKING:
    from .mdi_split import MdiSplit
    from .mdi_split_pane import MdiSplitPane
    from .mdi_controller import MdiController


class MdiTabDragPlaceholder(QWidget):

    def __init__(
        self, parent: QWidget, controller: "MdiController", text: str = ""
    ):
        super().__init__(parent)
        colors = controller.adjustedColors()
        self._controller = controller
        self._text = text
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(colors.dragTab))
        self.setPalette(pal)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(2, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def paintEvent(self, event: QPaintEvent):
        painter = QStylePainter(self)
        rect = event.rect()
        pal = self.palette()
        textColor = pal.color(QPalette.ColorRole.Text)

        opt = QStyleOption()
        opt.initFrom(self)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt)
        painter.setPen(textColor)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._text)


class MdiTabDropPlaceholder(QWidget):

    def __init__(self, parent: QWidget, controller: "MdiController"):
        super().__init__(parent)
        self._controller = controller

    def paintEvent(self, event: QPaintEvent):
        colors = self._controller.adjustedColors()
        painter = QStylePainter(self)
        opt = QStyleOption()
        opt.initFrom(self)

        painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt)

        rect = event.rect()
        stripeWidth = 6
        w = rect.width()
        h = rect.height()
        pal = self.palette()
        bg = QColor(colors.dropZone)
        altBg = QColor(colors.dropZone).darker(150)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bg.setAlpha(60)
        altBg.setAlpha(110)
        painter.fillRect(rect, bg)

        pen = QPen(altBg, stripeWidth * 2)
        painter.setPen(pen)

        for x in range(-h, w, stripeWidth * 2):
            painter.drawLine(x, 0, x + h, h)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(bg, 1))
        painter.drawRect(rect.adjusted(1, 1, -1, -1))


class MdiTabBar(QTabBar):

    DND_INACTIVE = 0
    DND_ACTIVE = 1
    DND_DETECTING = 2
    DND_BUILTIN = 3

    DROP_NONE = 0
    DROP_SPLITBETWEEN = 1
    DROP_SPLITLEFT = 2
    DROP_SPLITRIGHT = 3
    DROP_SPLITABOVE = 4
    DROP_SPLITBELOW = 5
    DROP_TRANSFERTAB = 6

    ICON_CLOSE_DARK = QIcon(":/dark_close-tab.svg")
    ICON_CLOSE_LIGHT = QIcon(":/light_close-tab.svg")

    def __init__(
        self,
        parent: QWidget,
        controller: "MdiController",
        expanding: bool = False,
    ):
        super().__init__(parent)

        self._controller = controller
        self._helper = controller._helper
        self._repaintTimer: QTimer | None = None
        self._dragTimer: QTimer = QTimer(self)
        self._dragRect: MdiTabDragPlaceholder | None = None
        self._dropRect: MdiTabDropPlaceholder | None = None
        self._dropSplit: MdiSplit | None = None
        self._dragDropState = MdiTabBar.DND_INACTIVE
        self._dropAction = MdiTabBar.DROP_NONE
        self._dragStartPos = QPoint()
        self._dragCurrPos = QPoint()
        self._dragIndex = -1
        self._repaintScheduled = False

        colors = self._controller.adjustedColors()
        self._tabActiveColor = QColor(colors.tabActive)
        self._tabSelectedColor = QColor(colors.tabSelected)
        self._tabHeight = getOpt("tab_behaviour", "tab_height")

        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.setDocumentMode(True)
        self.setMovable(True)
        self.setExpanding(expanding)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setAcceptDrops(True)
        self.setChangeCurrentOnDrag(True)
        self.setDrawBase(False)
        self.setFixedHeight(self._tabHeight)

        self.attachStyleSheet()

        win = self._helper.getWin()
        mdi = self._helper.getMdi()
        notifier = self._helper.getNotifier()

        win.themeChanged.connect(self.slotThemeChanged)
        OptionSignals.configSaved.connect(self.slotConfigChanged)
        self._dragTimer.timeout.connect(self.onDragMove)

    def pane(self) -> "MdiSplitPane|None":
        from .mdi_split_pane import MdiSplitPane

        w = self.parentWidget()
        while w is not None:
            pane = self._helper.isAlive(w, MdiSplitPane)
            if pane:
                return pane
            w = w.parentWidget()

    def tabInserted(self, index: int):
        super().tabInserted(index)
        self._setTabCloseButton(index)

    def tabSizeHint(self, index: int) -> QSize:
        size = super().tabSizeHint(index)
        currFont = self.font()
        metrics = QFontMetrics(currFont)
        text = self.tabText(index)

        extraWidth = 16
        textWidthAdjustment = (
            metrics.horizontalAdvance(text)
            - metrics.horizontalAdvance(text)
            + extraWidth
        )
        size.setWidth(size.width() + textWidthAdjustment)
        size.setHeight(self._tabHeight)
        return size

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.setUsesScrollButtons(self.width() > 80)

    def paintEvent(self, event: QPaintEvent):
        if not getOpt("tab_behaviour", "tab_krita_style"):
            super().paintEvent(event)
            return

        # Let Qt do all the rendering during dragging
        # Once dragging stops the active highlight gets reapplied
        isBuiltinTabDrag = (
            self._dragDropState == MdiTabBar.DND_BUILTIN
            and self._dragIndex != -1
        )
        if isBuiltinTabDrag or self._repaintScheduled:
            self._debounceScheduleRepaint()
            super().paintEvent(event)
            return

        super().paintEvent(event)

        currIndex = self.currentIndex()

        if currIndex != -1:
            splitPane = self.pane()
            activeHighlight = (
                splitPane is not None
                and splitPane.isActivePane()
                and self._controller.rootSplit().firstSplit()
            )

            painter = QStylePainter(self)
            opt = QStyleOptionTab()
            self.initStyleOption(opt, currIndex)

            if opt.state & QStyle.StateFlag.State_Selected:
                pal = opt.palette
                pal.setColor(
                    QPalette.ColorRole.Window,
                    (
                        self._tabActiveColor
                        if activeHighlight
                        else self._tabSelectedColor
                    ),
                )
                opt.palette = pal

            painter.drawControl(QStyle.ControlElement.CE_TabBarTab, opt)

    def mousePressEvent(self, event: QMouseEvent):
        btn = event.button()

        self._dragIndex = self.tabAt(event.pos())

        splitPane = self.pane()
        if splitPane is not None:
            globalPos = toPoint(getEventGlobalPos(event))

            self._controller.setActiveSplitPane(splitPane, True)
            if self.count() == 0:
                splitPane.updateFrameBorder(True)

            showMenuBtn = not getOpt("tab_behaviour", "tab_hide_menu_btn")

            match btn:
                case Qt.MouseButton.LeftButton:
                    if (
                        self._dragIndex >= 0
                        and self._dragDropState == MdiTabBar.DND_INACTIVE
                    ):
                        self._dragStartPos = globalPos
                        self._dragDropState = MdiTabBar.DND_DETECTING

                case Qt.MouseButton.MiddleButton:
                    if (
                        self._dragIndex >= 0
                        and self._dragDropState == MdiTabBar.DND_INACTIVE
                    ):
                        self._dragStartPos = globalPos
                        self._dragDropState = MdiTabBar.DND_ACTIVE

                case Qt.MouseButton.RightButton:
                    if not showMenuBtn or self._dragIndex >= 0:
                        splitPane.showMenu(self._dragIndex, globalPos)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragIndex != -1:
            globalPos = toPoint(getEventGlobalPos(event))

            if self._dragDropState == MdiTabBar.DND_DETECTING:
                dx = globalPos.x() - self._dragStartPos.x()
                dy = globalPos.y() - self._dragStartPos.y()
                squaredDist = dx * dx + dy * dy

                if squaredDist > 25:
                    self._dragDropState = (
                        MdiTabBar.DND_ACTIVE
                        if (abs(dy) > abs(dx) * 0.9)
                        else MdiTabBar.DND_BUILTIN
                    )

            if self._dragDropState == MdiTabBar.DND_ACTIVE:
                self._dragCurrPos = globalPos

                if not self._dragTimer.isActive():
                    self._dragTimer.start(50)

        if self._dragDropState in (
            MdiTabBar.DND_INACTIVE,
            MdiTabBar.DND_BUILTIN,
        ):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragTimer.isActive():
            self._dragTimer.stop()

        if self._dragDropState == MdiTabBar.DND_ACTIVE:
            self.onDragDrop()

        self._dragIndex = -1
        self._dragDropState = MdiTabBar.DND_INACTIVE

        if self._helper.isAlive(self._dragRect, QWidget):
            self._dragRect.hide()
            self._dragRect.deleteLater()
            self._dragRect = None

        if self._helper.isAlive(self._dropRect, QWidget):
            self._dropRect.hide()
            self._dropRect.deleteLater()
            self._dropRect = None

        super().mouseReleaseEvent(event)

    def onDragMove(self):
        self._showDropPlaceholder()
        self._showDragPlaceholder()

    def onDragDrop(self):
        self._performDragDrop()

    def slotThemeChanged(self):
        self._refreshAllTabCloseButtons()
        self._refreshStyle()
        self.attachStyleSheet()

    def slotConfigChanged(self):
        self._tabHeight = getOpt("tab_behaviour", "tab_height")
        self.setFixedHeight(self._tabHeight)
        self._refreshAllTabCloseButtons()
        self._refreshStyle()
        self.attachStyleSheet()

    def slotTabCloseButtonClick(self):
        btn = self.sender()

        if not isinstance(btn, QToolButton):
            return

        for i in range(0, self.count()):
            if self.tabButton(i, QTabBar.ButtonPosition.RightSide) == btn:
                self.tabCloseRequested.emit(i)
                break

    def _refreshStyle(self):
        s = self.style()
        pal = QApplication.palette()
        colors = self._controller.adjustedColors()

        self._tabActiveColor = QColor(colors.tabActive)
        self._tabSelectedColor = QColor(colors.tabSelected)

        self.setPalette(pal)
        s.unpolish(self)
        s.polish(self)
        self.update()

    def _setTabCloseButton(self, index: int):
        btn = QToolButton(self)
        btn.setObjectName("MdiTabCloseButton")
        btn.setAutoFillBackground(True)
        btn.setAutoRaise(True)
        btn.clicked.connect(self.slotTabCloseButtonClick)
        self.setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)
        self._refreshTabCloseButtonStyle(index)
        self._refreshStyle()

    def _refreshTabCloseButtonStyle(self, index: int):
        colors = self._controller.adjustedColors()
        btn = self._helper.isAlive(
            self.tabButton(index, QTabBar.ButtonPosition.RightSide),
            QToolButton,
        )

        # if the button was removed or replaced
        if btn is None or btn.objectName() != "MdiTabCloseButton":
            return

        maxSize = min(24, int(self._tabHeight * 0.67))
        if maxSize % 2:
            maxSize -= 1

        btn.setFixedSize(maxSize, maxSize)

        if self._helper.useDarkIcons():
            btn.setIcon(MdiTabBar.ICON_CLOSE_DARK)
        else:
            btn.setIcon(MdiTabBar.ICON_CLOSE_LIGHT)

        btn.setStyleSheet(f"""
            QToolButton {{ background: transparent; border: none; border-radius: 3px; }}
            QToolButton:hover {{ background-color: {colors.tabClose}; }}
        """)

    def _refreshAllTabCloseButtons(self):
        for i in range(0, self.count()):
            self._refreshTabCloseButtonStyle(i)

    def _debounceScheduleRepaint(self):
        if self._repaintTimer is None:
            self._repaintTimer = QTimer(self)
            self._repaintTimer.setSingleShot(True)

            def cb():
                self._repaintScheduled = False
                self.update()

            self._repaintTimer.timeout.connect(cb)

        self._repaintScheduled = True
        self._repaintTimer.start(200)

    def _showDragPlaceholder(self):
        if self._dragDropState == MdiTabBar.DND_ACTIVE:
            win = self.window()
            if win is None:
                return

            if not self._helper.isAlive(self._dragRect, QWidget):
                self._dragRect = MdiTabDragPlaceholder(
                    win,
                    controller=self._controller,
                    text=self.tabText(self._dragIndex),
                )

            winPos = win.mapFromGlobal(self._dragCurrPos)
            size = self.tabSizeHint(self._dragIndex)
            self._dragRect.show()
            self._dragRect.raise_()
            self._dragRect.setGeometry(
                winPos.x(), winPos.y(), size.width(), size.height()
            )

    def _showDropPlaceholder(self):
        from .mdi_split import MdiSplit

        self._dropAction = MdiTabBar.DROP_NONE
        self._dropSplit = None

        win = self.window()
        rootSplit = self._controller.rootSplit()
        activePane = self._controller.activeSplitPane()

        if rootSplit is None or activePane is None:
            return

        if self._dragDropState == MdiTabBar.DND_ACTIVE:
            edge = activePane.topBar().height()

            hit = rootSplit.splitAt(self._dragCurrPos)
            split = hit[0]

            if split is not None:
                pane = split.pane()
                viewportPos = rootSplit.mapFromGlobal(self._dragCurrPos)

                sw = split.width()
                sh = split.height()

                vx = viewportPos.x()
                vy = viewportPos.y()
                vw = rootSplit.width()
                vh = rootSplit.height()

                hitHandle = hit[1] == MdiSplit.HIT_HANDLE
                hitTopBar = hit[1] == MdiSplit.HIT_TOPBAR

                dropRectGeometry = QRect()

                if not hitTopBar and not self._controller.isLayoutLocked():
                    if (vx > 0) and (vx < edge) and (sh != vh or hitHandle):
                        dropRectGeometry = rootSplit.globalRect()
                        dropRectGeometry.setWidth(edge)
                        self._dropAction = MdiTabBar.DROP_SPLITLEFT
                        self._dropSplit = rootSplit
                    elif (
                        (vx > vw - edge)
                        and (vx < vw)
                        and (sh != vh or hitHandle)
                    ):
                        dropRectGeometry = rootSplit.globalRect()
                        dropRectGeometry.setX(dropRectGeometry.x() + vw - edge)
                        self._dropAction = MdiTabBar.DROP_SPLITRIGHT
                        self._dropSplit = rootSplit
                    elif (
                        (vy > self.height())
                        and (vy < self.height() + edge)
                        and (sw != vw or hitHandle)
                    ):
                        dropRectGeometry = rootSplit.globalRect()
                        dropRectGeometry.translate(0, self.height() - 1)
                        dropRectGeometry.setHeight(edge)
                        self._dropAction = MdiTabBar.DROP_SPLITABOVE
                        self._dropSplit = rootSplit
                    elif (
                        (vy > vh - edge)
                        and (vy < vh)
                        and (sw != vw or hitHandle)
                    ):
                        dropRectGeometry = rootSplit.globalRect()
                        dropRectGeometry.setY(dropRectGeometry.y() + vh - edge)
                        self._dropAction = MdiTabBar.DROP_SPLITBELOW
                        self._dropSplit = rootSplit

                if self._dropAction == MdiTabBar.DROP_NONE:
                    tabs = pane.tabs() if pane is not None else None
                    isOnlyTab = self.count() == 1

                    match hit[1]:
                        case MdiSplit.HIT_HANDLE:
                            if not self._controller.isLayoutLocked():
                                h = split.handle()
                                f = split.firstSplit()
                                s = split.secondSplit()

                                if (
                                    f is not None
                                    and s is not None
                                    and h is not None
                                ):
                                    secondMost = (
                                        f.secondMostPane().globalRect()
                                    )
                                    firstMost = s.firstMostPane().globalRect()

                                    if (
                                        h.orientation()
                                        == Qt.Orientation.Vertical
                                        and secondMost.y() != firstMost.y()
                                        and firstMost.height()
                                        != split.height()
                                        and secondMost.height()
                                        != split.height()
                                    ):
                                        dropRectGeometry = h.globalRect()
                                        dropRectGeometry.translate(-30, 0)
                                        dropRectGeometry.setWidth(
                                            h.width() + 60
                                        )
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITBETWEEN
                                        )
                                        self._dropSplit = split
                                    elif (
                                        h.orientation()
                                        == Qt.Orientation.Horizontal
                                        and secondMost.x() != firstMost.x()
                                        and firstMost.width() != split.width()
                                        and secondMost.width() != split.width()
                                    ):
                                        dropRectGeometry = h.globalRect()
                                        dropRectGeometry.translate(0, -10)
                                        dropRectGeometry.setHeight(
                                            h.height() + 20
                                        )
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITBETWEEN
                                        )
                                        self._dropSplit = split

                        case MdiSplit.HIT_TOPBAR:
                            if tabs != self:
                                dropRectGeometry = split.globalRect()
                                self._dropAction = MdiTabBar.DROP_TRANSFERTAB
                                self._dropSplit = split

                        case MdiSplit.HIT_FRAME:
                            if (
                                pane is not None
                                and not self._controller.isLayoutLocked()
                                and not (isOnlyTab and tabs == self)
                            ):
                                frame = pane.viewFrame()
                                framePos = frame.mapFromGlobal(
                                    self._dragCurrPos
                                )

                                fx = framePos.x()
                                fy = framePos.y()
                                fw = frame.width()
                                fh = frame.height()

                                dropWidth = int(fw * 0.4)
                                dropHeight = int(fh * 0.4)

                                leftAdj = isOnlyTab and pane.isAdjacentTo(
                                    self.pane(), Qt.Edge.LeftEdge
                                )
                                rightAdj = isOnlyTab and pane.isAdjacentTo(
                                    self.pane(), Qt.Edge.RightEdge
                                )
                                topAdj = isOnlyTab and pane.isAdjacentTo(
                                    self.pane(), Qt.Edge.TopEdge
                                )
                                botAdj = isOnlyTab and pane.isAdjacentTo(
                                    self.pane(), Qt.Edge.BottomEdge
                                )

                                topDist = (
                                    math.inf if topAdj else float(fy) / fh
                                )
                                botDist = (
                                    math.inf if botAdj else float(fh - fy) / fh
                                )
                                leftDist = (
                                    math.inf if leftAdj else float(fx) / fw
                                )
                                rightDist = (
                                    math.inf
                                    if rightAdj
                                    else float(fw - fx) / fw
                                )

                                minDist = min(
                                    topDist, botDist, leftDist, rightDist
                                )

                                if (
                                    self._dropAction == MdiTabBar.DROP_NONE
                                    and minDist == leftDist
                                    and not leftAdj
                                ):
                                    dropRectGeometry = pane.globalFrameRect()
                                    dropRectGeometry.setWidth(dropWidth)
                                    if dropRectGeometry.contains(
                                        self._dragCurrPos
                                    ):
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITLEFT
                                        )
                                        self._dropSplit = split

                                if (
                                    self._dropAction == MdiTabBar.DROP_NONE
                                    and minDist == rightDist
                                    and not rightAdj
                                ):
                                    dropRectGeometry = pane.globalFrameRect()
                                    dropRectGeometry.setX(
                                        dropRectGeometry.x()
                                        + dropRectGeometry.width()
                                        - dropWidth
                                    )
                                    if dropRectGeometry.contains(
                                        self._dragCurrPos
                                    ):
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITRIGHT
                                        )
                                        self._dropSplit = split

                                if (
                                    self._dropAction == MdiTabBar.DROP_NONE
                                    and minDist == topDist
                                    and not topAdj
                                ):
                                    dropRectGeometry = pane.globalFrameRect()
                                    dropRectGeometry.setHeight(dropHeight)
                                    if dropRectGeometry.contains(
                                        self._dragCurrPos
                                    ):
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITABOVE
                                        )
                                        self._dropSplit = split

                                if (
                                    self._dropAction == MdiTabBar.DROP_NONE
                                    and minDist == botDist
                                    and not botAdj
                                ):
                                    dropRectGeometry = pane.globalFrameRect()
                                    dropRectGeometry.setY(
                                        dropRectGeometry.y()
                                        + dropRectGeometry.height()
                                        - dropHeight
                                    )
                                    if dropRectGeometry.contains(
                                        self._dragCurrPos
                                    ):
                                        self._dropAction = (
                                            MdiTabBar.DROP_SPLITBELOW
                                        )
                                        self._dropSplit = split

                rootSplit.refreshLayout()

                if self._dropAction != MdiTabBar.DROP_NONE:
                    if not self._helper.isAlive(
                        self._dropRect, MdiTabDropPlaceholder
                    ):
                        self._dropRect = MdiTabDropPlaceholder(
                            win, self._controller
                        )

                    self._dropRect.show()
                    self._dropRect.raise_()
                    self._dropRect.setGeometry(
                        dropRectGeometry.translated(-win.geometry().topLeft())
                    )
                    return

        if self._helper.isAlive(self._dropRect, QWidget):
            rootSplit.refreshLayout()
            self._dropRect.deleteLater()
            self._dropRect = None

    def _performDragDrop(self):
        from .mdi_split import MdiSplit

        pane = self.pane()
        split = pane.parentSplit() if pane is not None else None
        ensureDropSplit = self._helper.isAlive(self._dropSplit, MdiSplit)

        if split is None or not ensureDropSplit or self._dragIndex == -1:
            self._dropAction = MdiTabBar.DROP_NONE
            return

        handle = self._dropSplit.handle()
        firstSplit = self._dropSplit.firstSplit()
        dropPane = self._dropSplit.pane()

        match self._dropAction:
            case MdiTabBar.DROP_SPLITLEFT:
                self._dropSplit.makeSplitLeft(split, self._dragIndex)

            case MdiTabBar.DROP_SPLITRIGHT:
                self._dropSplit.makeSplitRight(split, self._dragIndex)

            case MdiTabBar.DROP_SPLITABOVE:
                self._dropSplit.makeSplitAbove(split, self._dragIndex)

            case MdiTabBar.DROP_SPLITBELOW:
                self._dropSplit.makeSplitBelow(split, self._dragIndex)

            case MdiTabBar.DROP_SPLITBETWEEN:
                if handle is not None and firstSplit is not None:
                    if handle.orientation() == Qt.Orientation.Vertical:
                        firstSplit.makeSplitRight(split, self._dragIndex)
                    else:
                        firstSplit.makeSplitBelow(split, self._dragIndex)

            case MdiTabBar.DROP_TRANSFERTAB:
                if pane is not None:
                    pane.transferTab(self._dragIndex, dropPane)

        rootSplit = self._dropSplit.rootSplit()

        if rootSplit is not None and self._dropAction != MdiTabBar.DROP_NONE:

            def cb():
                nonlocal rootSplit
                if self._helper.isAlive(rootSplit, MdiSplit):

                    def updateTabBars(pane):
                        tabs = pane.tabs()
                        if tabs is not None:
                            tabs.slotConfigChanged()

                    rootSplit.eachPane(updateTabBars)

            QTimer.singleShot(0, cb)

        self._dropAction = MdiTabBar.DROP_NONE

    def attachStyleSheet(self):
        # TODO add back custom colors and flat tabs
        flatTheme = not getOpt("tab_behaviour", "tab_krita_style")
        colors = self._controller.adjustedColors()

        # QMdiArea MdiTabBar QToolButton {{
        #     border: none;
        #     background: {colors.bar};
        # }}
        if flatTheme:
            closeIcon = (
                ":/dark_close-tab.svg"
                if self._helper.useDarkIcons()
                else ":/light_close-tab.svg"
            )
            self.setStyleSheet(f"""
                QMdiArea MdiTabBar {{
                    qproperty-drawBase: 0;
                    min-height: {self._tabHeight}px;
                    max-height: {self._tabHeight}px;
                    border: 0;
                    margin: 0;
                    padding: 0;
                }}
                QMdiArea MdiTabBar::tab {{
                    min-width: 1px;
                    max-width: 400px;
                    height: {self._tabHeight}px;
                    min-height: {self._tabHeight}px;
                    max-height: {self._tabHeight}px;
                    background: {colors.tab};
                    border-radius: 0;
                    border: 0;
                    border-right: 1px solid {colors.tabSeparator};
                    padding: 0px 12px;
                }}
                QMdiArea MdiTabBar::tab:selected {{
                    background: {colors.tabSelected};
                    border-right: 1px solid {colors.tabSeparator};
                }}
                QMdiArea MdiTabBar::tab:first, QMdiArea MdiTabBar::tab:selected:first {{
                    border-left: 1px solid {colors.tabSeparator};
                }}
                QMdiArea MdiTabBar::close-button {{
                    image: url({closeIcon});
                    width: 24px;
                    height: 24px;
                    border-radius: 3px;
                }}
                QMdiArea MdiTabBar::close-button:hover {{
                    background-color: {colors.tabClose};
                }}
                QMdiArea MdiTabBar::close-button:pressed {{
                    background-color: red;
                }}
                QMdiArea MdiTabBar::tear {{
                    width: 0px;
                    border: none;
                }}
                QMdiArea MdiSplitPane[active="true"] MdiTabBar::tab:selected {{
                    background: {colors.tabActive};
                    border-right: 1px solid {colors.tabActive};
                }}
            """)

        else:
            self.setStyleSheet(f"""
                QMdiArea MdiTabBar {{
                    min-height: {self._tabHeight}px;
                    max-height: {self._tabHeight}px;
                }}
                QMdiArea MdiTabBar::tab {{
                    height: {self._tabHeight}px;
                    min-height: {self._tabHeight}px;
                    max-height: {self._tabHeight}px;
                }}
                QMdiArea MdiTabBar::tear {{
                    width: 0px;
                    border: none;
                }}
            """)

