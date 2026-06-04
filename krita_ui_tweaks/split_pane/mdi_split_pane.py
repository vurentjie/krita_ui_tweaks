from ..pyqt import (
    Qt,
    QApplication,
    QObject,
    QPalette,
    QEvent,
    QMouseEvent,
    QResizeEvent,
    QRect,
    QWidget,
    QPoint,
    QUuid,
    QFrame,
    QMdiSubWindow,
    QVBoxLayout,
    QHBoxLayout,
    QTimer,
    QSizePolicy,
    QColor,
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


from .mdi_tab_bar import MdiTabBar
from .mdi_split_menu import MdiMenuButton

if TYPE_CHECKING:
    from .mdi_controller import MdiController
    from .mdi_split import MdiSplit


class MdiSplitPane(QWidget):

    def __init__(
        self,
        parent: QWidget,
        controller: "MdiController",
        id: QUuid | None = None,
    ):
        super().__init__(parent)

        self._controller = controller
        self._helper = controller._helper
        self._id = QUuid.createUuid() if id is None else id
        self._topBar: QWidget | None = None
        self._tabs: MdiTabBar | None = None
        self._menuBtn: MdiMenuButton | None = None
        self._viewFrame: QFrame | None = None
        self._guardClosingTab: bool = False
        self._subWindows: list[QMdiSubWindow] = []

        tabExpands = getOpt("tab_behaviour", "tab_expands")
        showMenuBtn = not getOpt("tab_behaviour", "tab_hide_menu_btn")

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self._viewFrame = QFrame(self)
        self._viewFrame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Plain)
        self._viewFrame.setLineWidth(1)
        self._viewFrame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._viewFrame.setAutoFillBackground(True)

        self._topBar = QWidget(self)
        self._topBar.setObjectName("MdiSplitTopBar")
        self._topBar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._topBar.setFixedHeight(getOpt("tab_behaviour", "tab_height") - 2)

        self._menuBtn = MdiMenuButton(self, controller=controller)
        self._menuBtn.setVisible(showMenuBtn)

        self._tabs = MdiTabBar(
            self, controller=self._controller, expanding=tabExpands
        )

        topBarLayout = QHBoxLayout(self._topBar)
        topBarLayout.setSpacing(0)
        topBarLayout.setContentsMargins(0, 0, 0, 0)
        topBarLayout.addWidget(self._tabs)
        topBarLayout.addWidget(self._menuBtn, 0, Qt.AlignmentFlag.AlignRight)
        topBarLayout.setStretch(0, 1)
        topBarLayout.setStretch(1, 0)

        layout.addWidget(self._topBar)
        layout.addWidget(self._viewFrame)

        self.setProperty("uid", self._id.toString())
        self.setAutoFillBackground(True)

        self._tabs.tabCloseRequested.connect(self.slotTabCloseRequested)
        self._tabs.tabMoved.connect(self.slotTabMoved)
        self._tabs.currentChanged.connect(self.slotCurrentTabChanged)

        QTimer.singleShot(0, self.slotConfigChanged)

        # TODO signals
        win = self._helper.getWin()
        mdi = self._helper.getMdi()
        notifier = self._helper.getNotifier()

        win.themeChanged.connect(self.slotConfigChanged)
        OptionSignals.configSaved.connect(self.slotConfigChanged)
        mdi.subWindowActivated.connect(self.slotSubWindowActivated)
        controller.activePaneChanged.connect(self.slotUpdateFrameBorder)

        self.updateFrameBorder()

    def id(self) -> QUuid:
        return self._id

    def parentSplit(self) -> "MdiSplit|None":
        from .mdi_split import MdiSplit

        return self._helper.isAlive(self.parent(), MdiSplit)

    def subWindows(self) -> list[QMdiSubWindow]:
        return self._subWindows

    def tabs(self) -> MdiTabBar | None:
        return self._helper.isAlive(self._tabs, MdiTabBar)

    def viewFrame(self) -> QFrame | None:
        return self._helper.isAlive(self._viewFrame, QFrame)

    def topBar(self) -> QWidget | None:
        return self._helper.isAlive(self._topBar, QWidget)

    def showMenu(
        self, tabIndex: int | None = None, tabPos: QPoint | None = None
    ):
        menuBtn = self._helper.isAlive(self._menuBtn, MdiMenuButton)
        if menuBtn is not None:
            menuBtn.showMenu(tabIndex, tabPos)

    def isActivePane(self) -> bool:
        return self._controller.activeSplitPane() == self

    def isEmpty(self) -> bool:
        return len(self._subWindows) == 0

    def addSubWindow(self, sw: QMdiSubWindow) -> int:
        sw = self._helper.isAlive(sw, QMdiSubWindow)
        if sw is None:
            return -1

        split = self.parentSplit()
        tabBar = self.tabs()

        if split is None or tabBar is None:
            return -1

        if sw in self._subWindows:
            return -1

        index = tabBar.addTab(sw.windowIcon(), self._controller.tabTitle(sw))

        self._subWindows.append(sw)
        self._syncSubWindows()
        sw.destroyed[QObject].connect(self.slotSubWindowDestroyed)

        self.updateFrameBorder()

        flags = sw.windowFlags()

        flags |= Qt.WindowType.FramelessWindowHint
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
        flags &= ~Qt.WindowType.WindowStaysOnBottomHint

        sw.setUpdatesEnabled(False)
        self.resizeSubWindow(sw, False)
        sw.setWindowFlags(flags)
        sw.showNormal()
        sw.setUpdatesEnabled(True)

        def cb():
            root = self._controller.rootSplit()
            if root is not None:
                root.refreshSplitSizes()

        QTimer.singleShot(0, cb)

        return index

    def _syncSubWindows(self):
        uid = self._id.toString()
        for idx, sw in enumerate(self._subWindows):
            sw = self._helper.isAlive(sw, QMdiSubWindow)
            if sw is not None:
                sw.setProperty("splitpane_uid", uid)
                sw.setProperty("splitpane_index", idx)

    def closeSubWindow(self, index: int) -> bool:
        sw = self.subWindowAt(index)
        if sw is not None:
            return sw.close()
        return False

    def closeAllSubWindows(self) -> bool:
        if self._controller.isLayoutLocked():
            return False

        allClosed = True
        closeWins = self._subWindows[:]

        for sw in closeWins:
            sw = self._helper.isAlive(sw, QMdiSubWindow)
            if sw is not None and not sw.close():
                allClosed = False

        return allClosed

    def resizeSubWindow(
        self, sw: QMdiSubWindow | None = None, refreshLayout: bool = True
    ):
        sw = self._helper.isAlive(sw, QMdiSubWindow)
        if sw is None:
            return

        mdi = self._helper.getMdi()
        bar = self.topBar()

        if bar is None or mdi is None:
            return

        r = self.rect()
        o = mdi.mapFromGlobal(self.mapToGlobal(r.topLeft()))

        typing.cast(QMdiSubWindow, sw).move(
            o.x() + 1, o.y() + bar.height() + 1
        )

        typing.cast(QMdiSubWindow, sw).setFixedSize(
            r.width() - 2,
            r.height() - bar.height() - 2,
        )

        if refreshLayout:
            rootSplit = self._controller.rootSplit()
            if rootSplit is not None:
                rootSplit.refreshLayout()

    def resizeCurrentSubWindow(self):
        self.resizeSubWindow(self.currentSubWindow())

    def currentIndex(self) -> int:
        tabBar = self.tabs()
        return tabBar.currentIndex() if tabBar is not None else -1

    def globalRect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    def globalFrameRect(self) -> QRect:
        viewFrame = self.viewFrame()
        return (
            QRect(viewFrame.mapToGlobal(QPoint(0, 0)), viewFrame.size())
            if viewFrame is not None
            else QRect()
        )

    def globalTopBarRect(self) -> QRect:
        bar = self.topBar()
        return (
            QRect(bar.mapToGlobal(QPoint(0, 0)), bar.size())
            if bar is not None
            else QRect()
        )

    # This does not check every possible scenario
    # It only checks one particular case to ignore during drag and drop
    def isAdjacentTo(
        self, pane: "MdiSplitPane|None" = None, edge: Qt.Edge | None = None
    ) -> bool:
        if pane is None or pane == self or edge is None:
            return False

        opposite = None
        match edge:
            case Qt.Edge.LeftEdge:
                opposite = Qt.Edge.RightEdge
            case Qt.Edge.RightEdge:
                opposite = Qt.Edge.LeftEdge
            case Qt.Edge.TopEdge:
                opposite = Qt.Edge.BottomEdge
            case Qt.Edge.BottomEdge:
                opposite = Qt.Edge.TopEdge

        return self._checkAdjacency(pane, edge) or pane._checkAdjacency(
            self, opposite
        )

    def _checkAdjacency(self, pane: "MdiSplitPane", edge: Qt.Edge) -> bool:
        parent = self.parentSplit()
        if parent is None:
            return False

        parentSplit = parent.parentSplit()
        if parentSplit is None:
            return False

        first = parentSplit.firstSplit()
        second = parentSplit.secondSplit()
        handle = parentSplit.handle()

        if first is None or second is None or handle is None:
            return False

        if handle.orientation() == Qt.Orientation.Vertical:
            return pane.height() == self.height() and (
                (pane == first.secondMostPane() and edge == Qt.Edge.LeftEdge)
                or (
                    pane == second.firstMostPane()
                    and edge == Qt.Edge.RightEdge
                )
            )

        return pane.width() == self.width() and (
            (pane == first.secondMostPane() and edge == Qt.Edge.TopEdge)
            or (pane == second.firstMostPane() and edge == Qt.Edge.BottomEdge)
        )

    def currentSubWindow(self) -> QMdiSubWindow | None:
        return self.subWindowAt(self.currentIndex())

    def subWindowAt(
        self, index: int, unsafe: bool = False
    ) -> QMdiSubWindow | None:
        if index >= 0 and index < len(self._subWindows):
            sw = self._subWindows[index]
            return sw if unsafe else self._helper.isAlive(sw, QMdiSubWindow)

    def viewAt(self, index: int, unsafe: bool = False) -> View | None:
        sw = self.subWindowAt(index, unsafe)
        return self._helper.getViewBySubWin(sw)

    def subWindowById(self, uid: int | None) -> QMdiSubWindow | None:
        if id is None:
            return
        for sw in self._subWindows:
            if sw.property("uiTweaksId") == uid:
                return sw

    def subWindowIndex(self, sw: QMdiSubWindow) -> int:
        return (
            self._subWindows.index(sw)
            if sw is not None and sw in self._subWindows
            else -1
        )

    def activateSubWindow(
        self, sw: QMdiSubWindow | None, setFocus: bool = False
    ):
        sw = self._helper.isAlive(sw, QMdiSubWindow)
        if sw is None:
            return

        index = self.subWindowIndex(sw)
        if index == -1:
            return

        sw.raise_()

        self._controller.setActiveSubWindow(sw)

        # Only set focus deliberately when clicking or cycling the tab
        # For other cases the user needs to tap once on the canvas first
        if setFocus:
            subWinWidget = sw.widget()
            if subWinWidget is not None:
                subWinWidget.setFocus(Qt.FocusReason.OtherFocusReason)

    def activateCurrentSubWindow(self, setFocus: bool = False):
        self.activateSubWindow(self.currentSubWindow(), setFocus)

    def cycleNextTab(self):
        self.cycleTab(1)

    def cyclePreviousTab(self):
        self.cycleTab(-1)

    def cycleTab(self, delta: int):
        size = len(self._subWindows)
        if size > 1:
            index = (self.currentIndex() + delta + size) % size
            if index > 0 and index < size:
                sw = self._subWindows[index]
                if sw is not None:
                    self.activateSubWindow(sw, True)

    def transferTab(self, tabIndex: int, targetPane: "MdiSplitPane") -> int:
        split = self.parentSplit()

        if split is None:
            return -1

        if tabIndex < 0 or tabIndex >= len(self._subWindows):
            return -1

        sw = self._helper.isAlive(self._subWindows[tabIndex], QMdiSubWindow)
        if sw is None:
            return -1

        self.removeTab(tabIndex)

        index = targetPane.addSubWindow(sw)

        if index != -1:
            # FIXME checks because of QTimer delay
            self._controller.setActiveSubWindow(sw)
            self._controller.setActiveSplitPane(targetPane)

            def cb(sw=sw):
                view = self._helper.getViewBySubWin(sw)
                if view is not None:
                    self._helper.centerCanvas(sw, view, epsilon=10)

            QTimer.singleShot(0, cb)

        return index

    def transferSubWindow(
        self, sw: QMdiSubWindow, targetPane: "MdiSplitPane"
    ) -> int:
        return self.transferTab(self.subWindowIndex(sw), targetPane)

    def duplicateTab(self, tabIndex: int) -> int:
        sw = self.subWindowAt(tabIndex)
        if sw is None:
            return -1

        win = self._helper.getWin()
        view = self._helper.getViewBySubWin(sw)

        if win is not None and view is not None:
            self._controller.openView(view.document(), self)

        return self.currentIndex()

    def closeTabsToRight(self, tabIndex: int):
        if tabIndex < 0:
            return

        removeWins = self._subWindows[tabIndex + 1 :]
        for sw in removeWins:
            sw.close()

    def closeTabsToLeft(self, tabIndex: int):
        if tabIndex <= 0 or tabIndex > len(self._subWindows):
            return

        removeWins = self._subWindows[:tabIndex]
        for sw in removeWins:
            sw.close()

    def closeOtherTabs(self, tabIndex: int):
        removeWins = self._subWindows[:]
        keep = self.subWindowAt(tabIndex)
        for sw in removeWins:
            if sw != keep:
                sw.close()

    # This does not destroy the subwindow
    # But if a subwindow is destroyed it will be called
    # Also if a subwindow is moved it will be called
    def removeTab(self, index: int):
        if not self._guardClosingTab:
            tabBar = self.tabs()

            if tabBar is None:
                return

            self._guardClosingTab = True
            sw = self.subWindowAt(index, True)

            if sw is not None:
                try:
                    sw.destroyed[QObject].disconnect(
                        self.slotSubWindowDestroyed
                    )
                except:
                    pass
                self._subWindows.pop(index)
                tabBar.removeTab(index)
                self._syncSubWindows()

            self._guardClosingTab = False

            split = self.parentSplit()
            if (
                split is not None
                and not self._controller.isLayoutLocked()
                and self.isEmpty()
            ):
                split.close()

    def event(self, event: QEvent) -> bool:
        result = super().event(event)

        if event.type() in (
            QEvent.Type.StyleChange,
            QEvent.Type.LayoutRequest,
        ):
            self.resizeCurrentSubWindow()

        return result

    def mousePressEvent(self, event: QMouseEvent):
        tabBar = self.tabs()

        if tabBar is None:
            return

        self._controller.setActiveSplitPane(self)

        if tabBar.count() == 0:
            self.updateFrameBorder(True)

        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.resizeCurrentSubWindow()

    def slotConfigChanged(self):
        tabExpands = getOpt("tab_behaviour", "tab_expands")
        showMenuBtn = not getOpt("tab_behaviour", "tab_hide_menu_btn")

        self.updateTopBar()

        tabBar = self.tabs()
        if tabBar is not None:
            tabBar.setExpanding(tabExpands)

        menuBtn = self._helper.isAlive(self._menuBtn, MdiMenuButton)
        if menuBtn is not None:
            menuBtn.setVisible(showMenuBtn)
            menuBtn.updateHeight()
            menuBtn.refreshIcon()

        self.updateFrameBorder()
        self.resizeCurrentSubWindow()

    def slotUpdateFrameBorder(self, force: bool = False):
        if force or self._controller.activeSplitPane() == self:
            self.updateFrameBorder()

    def updateTopBar(self):
        bar = self.topBar()

        if bar is None:
            return

        tabHeight = getOpt("tab_behaviour", "tab_height")
        pal = bar.palette()
        pal.setColor(
            QPalette.ColorRole.Window, self._helper.paletteColor("Window")
        )
        bar.setPalette(pal)
        bar.setAutoFillBackground(True)
        bar.setFixedHeight(tabHeight - 2)

    def updateFrameBorder(self, active: bool = False):
        viewFrame = self.viewFrame()
        if viewFrame is not None:
            pal = QApplication.palette()
            s = viewFrame.style()

            canvas = self._helper.settingColor("", "canvasBorderColor", "")
            hl = self._helper.paletteColor("Highlight")
            hlGreyScale = QColor.fromHsl(
                hl.hue(), 0, hl.lightness(), hl.alpha()
            )
            border = self._helper.paletteColor("Window").darker(130)
            useBorderColor = hl
            if not active:
                if border.lightness() < hlGreyScale.lightness():
                    useBorderColor = border
                else:
                    useBorderColor = hlGreyScale

            viewFrame.setStyleSheet(f"""
                QFrame {{
                  background: {canvas.name(QColor.NameFormat.HexArgb)};
                  border: 1px solid {useBorderColor.name(QColor.NameFormat.HexArgb)};
                }}
            """)

    def slotSubWindowActivated(self, sw: QMdiSubWindow | None = None):
        sw = self._helper.isAlive(sw, QMdiSubWindow)
        if sw is None:
            return

        tabBar = self.tabs()

        if tabBar is None:
            return

        index = self.subWindowIndex(sw)
        if index == -1:
            return

        tabBar.setCurrentIndex(index)
        self.resizeSubWindow(sw)
        self._controller.setActiveSplitPane(self)

    def slotSubWindowDestroyed(self, obj: QObject):

        for idx, sw in enumerate(self._subWindows):
            if not self._helper.isAlive(sw, QMdiSubWindow):
                self.removeTab(idx)
                split = self.parentSplit()
                if (
                    split is not None
                    and not self._controller.isLayoutLocked()
                    and self.isEmpty()
                ):
                    split.close()
                break

    def slotTabCloseRequested(self, index: int):
        if not self._guardClosingTab:
            self.closeSubWindow(index)

    def slotTabMoved(self, fromPos: int, toPos: int):
        tabBar = self.tabs()

        if (
            tabBar is not None
            and fromPos != toPos
            and fromPos >= 0
            and fromPos < len(self._subWindows)
            and toPos >= 0
            and toPos < len(self._subWindows)
        ):
            self._subWindows.insert(toPos, self._subWindows.pop(fromPos))
            self._syncSubWindows()

    def slotCurrentTabChanged(self, index: int):
        sw = self.subWindowAt(index)
        if sw is not None:
            self.activateSubWindow(sw)

    def saveState(self) -> dict[Any, Any]:
        mdi = self._helper.getMdi()
        if mdi is None:
            return {}

        subWins = self.subWindows()
        tabBar = self.tabs()

        if subWins is None or tabBar is None:
            return {}

        uid = self._id.toString()

        state = {}
        state["state"] = "c"
        state["uid"] = uid
        state["active"] = tabBar.currentIndex()
        state["isActiveSplit"] = self._controller.activeSplitPane() == self
        state["files"] = []

        for idx, sw in enumerate(subWins):
            view = self._helper.getViewBySubWin(sw)
            if view:
                doc = view.document()
                path = doc.fileName()
                if os.path.exists(path):
                    state["files"].append(path)

        return state

    def restoreState(
        self, state: dict[Any, Any], context: dict[Any, Any]
    ) -> bool:
        if not state:
            return False

        if state.get("state", None) != "c":
            return False

        if not isinstance(context, dict):
            context = {}

        app = self._helper.getApp()
        mdi = self._helper.getMdi()
        tabBar = self.tabs()
        win = self._helper.getWin()

        if mdi is None or tabBar is None or win is None:
            return False

        uid = state.get("uid", None)
        self._id = QUuid(uid)
        self.setProperty("uid", self._id.toString())

        def addViews(context=context, state=state):
            app = self._helper.getApp()
            mdi = self._helper.getMdi()
            tabBar = self.tabs()
            win = self._helper.getWin()

            if mdi is None or tabBar is None or win is None:
                return False

            files = state.get("files", [])
            active = state.get("active", tabBar.currentIndex())
            openDocs = self._helper.getDocsByFile()

            for path in files:
                if path in openDocs:
                    self._controller.openView(openDocs[path].doc, self)
                else:
                    doc = app.openDocument(path)
                    if not doc:
                        continue
                    openDocs[path] = SimpleNamespace(doc=doc)
                    self._controller.openView(doc, self)

            if self._helper.isAlive(tabBar, QWidget) and active != -1:
                tabBar.setCurrentIndex(active)

        context["callbacks"].views.append(addViews)

        if state.get("isActiveSplit", False):

            def setActive():
                self._controller.setActiveSplitPane(self)

            context["callbacks"].activate.append(setActive)

        return True

    def cycleNextTab(self):
        self.cycleTab(1)

    def cyclePreviousTab(self):
        self.cycleTab(-1)

    def cycleTab(self, delta: int):
        size = len(self._subWindows)
        if size > 1:
            index = (self.currentIndex() + delta + size) % size
            sw = self.subWindowAt(index)
            if sw:
                self.activateSubWindow(sw, True)

