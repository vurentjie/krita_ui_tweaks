from ..pyqt import (
    Qt,
    QWidget,
    QResizeEvent,
    QPoint,
    QRect,
    QSize,
    QMdiSubWindow,
    QTimer,
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

from .mdi_split_pane import MdiSplitPane
from .mdi_split_handle import MdiSplitHandle

if TYPE_CHECKING:
    from .mdi_controller import MdiController


class MdiSplit(QWidget):
    MIN_SIZE = 80

    STATE_SPLIT = 0
    STATE_TABBED = 1

    HIT_NONE = 0
    HIT_HANDLE = 1
    HIT_FRAME = 2
    HIT_TOPBAR = 3

    def __init__(
        self,
        parent: QWidget,
        controller: "MdiController",
        orient: Qt.Orientation | None = None,
        firstSplit: "MdiSplit|None" = None,
        secondSplit: "MdiSplit|None" = None,
        pane: MdiSplitPane | None = None,
    ):
        super().__init__(parent)

        self._controller = controller
        self._helper = controller._helper
        self._pane: MdiSplitPane | None = None
        self._handle: MdiSplitHandle | None = None
        self._firstSplit: MdiSplit | None = None
        self._secondSplit: MdiSplit | None = None

        if firstSplit is not None or secondSplit is not None:
            self._handle = MdiSplitHandle(
                self, controller=controller, orient=orient
            )
            self._handle.show()
            self._handle.raise_()

            firstSplit = self._helper.isAlive(firstSplit, MdiSplit)
            secondSplit = self._helper.isAlive(secondSplit, MdiSplit)

            if firstSplit is None:
                self._firstSplit = MdiSplit(self, controller=controller)
            else:
                self._firstSplit = typing.cast(MdiSplit, firstSplit)
                self._firstSplit.setParent(self)

            if secondSplit is None:
                self._secondSplit = MdiSplit(self, controller=controller)
            else:
                self._secondSplit = typing.cast(MdiSplit, secondSplit)
                self._secondSplit.setParent(self)

            self._handle.handleMoved.connect(self.slotHandleMoved)
        else:
            pane = self._helper.isAlive(pane, MdiSplitPane)
            if pane is None:
                self._pane = MdiSplitPane(self, controller=controller)
            else:
                self._pane = typing.cast(MdiSplitPane, pane)
                self._pane.setParent(self)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.slotHandleMoved()

    def slotHandleMoved(self):
        self.refreshSplitSizes()

    def refreshSplitSizes(self, refreshLayout: bool = True):
        if refreshLayout:
            root = self.rootSplit()
            if root is None:
                return
            root.refreshLayout()

        splitHandle = self.handle()
        if splitHandle is not None:
            first = self.firstSplit()
            second = self.secondSplit()

            if first is None or second is None:
                return

            first.setGeometry(splitHandle.firstRect())
            first.refreshSplitSizes(False)

            second.setGeometry(splitHandle.secondRect())
            second.refreshSplitSizes(False)
            return

        splitPane = self.pane()
        if splitPane is not None:
            splitPane.setGeometry(self.rect())
            sw = splitPane.currentSubWindow()
            if sw is not None:
                splitPane.resizeSubWindow(sw)
                sw.raise_()

    # With the splitters the mdi area consists of 3 layers
    # - At the top the current subwindows for each split
    # - Then the split pane ui covers all the other windows
    # - At the bottom and hidden are the other subwindows (ignored until they become current)
    def refreshLayout(self, dbg=False):
        self.raise_()

        if self.isSplitState():
            first = self.firstSplit()
            second = self.secondSplit()

            if first is not None and second is not None:
                first.refreshLayout()
                second.refreshLayout()
        else:
            splitPane = self.pane()
            if splitPane is not None:
                sw = splitPane.currentSubWindow()
                if sw is not None:
                    sw.raise_()

    # Mutating the split layout inside the callback will have undefined behaviour
    def eachPane(self, callback: typing.Callable[["MdiSplitPane"], Any]):
        splitPane = self.pane()
        if splitPane is not None:
            callback(splitPane)
            return

        first = self.firstSplit()
        if first is not None:
            first.eachPane(callback)

        second = self.secondSplit()
        if second is not None:
            second.eachPane(callback)

    # Mutating the split layout inside the callback will have undefined behaviour
    def eachSplit(self, callback: typing.Callable[["MdiSplit"], Any]):
        if self.isSplitState():
            callback(self)

            first = self.firstSplit()
            if first is not None:
                first.eachSplit(callback)

            second = self.secondSplit()
            if second is not None:
                second.eachSplit(callback)

    def rootSplit(self) -> "MdiSplit|None":
        return self._controller.rootSplit()

    def firstSplit(self) -> "MdiSplit|None":
        return self._helper.isAlive(self._firstSplit, MdiSplit)

    def secondSplit(self) -> "MdiSplit|None":
        return self._helper.isAlive(self._secondSplit, MdiSplit)

    def parentSplit(self) -> "MdiSplit|None":
        return self._helper.isAlive(self.parent(), MdiSplit)

    def pane(self) -> MdiSplitPane | None:
        return self._helper.isAlive(self._pane, MdiSplitPane)

    def isSplitState(self) -> bool:
        return not self.isTabbedState()

    def isTabbedState(self) -> bool:
        return self.pane() is not None

    def handle(self) -> MdiSplitHandle | None:
        return self._helper.isAlive(self._handle, MdiSplitHandle)

    def resetHandle(self):
        h = self.handle()
        if h is not None:
            h.reset()
            h.clamp()

    def firstMostPane(self) -> MdiSplitPane | None:
        firstMost = self
        while firstMost.firstSplit() is not None:
            firstMost = typing.cast(MdiSplit, firstMost.firstSplit())
        return firstMost.pane()

    def secondMostPane(self) -> MdiSplitPane | None:
        secondMost = self
        while secondMost.secondSplit() is not None:
            secondMost = typing.cast(MdiSplit, secondMost.secondSplit())
        return secondMost.pane()

    def collapseLayout(self):
        # This can be called when the layout is locked from the menu entry
        # So remember the state and restore it at the end
        locked = self._controller.isLayoutLocked()

        # Lock the layout to avoid side effects
        # of panes being removed while transferring
        self._controller.setLayoutLocked(True)

        firstPane = self.firstMostPane()

        def doTransfer(p: MdiSplitPane):
            nonlocal firstPane
            if firstPane == p:
                return

            subWins = p.subWindows()
            copyWins = subWins[:]
            for sw in copyWins:
                p.transferSubWindow(sw, typing.cast(MdiSplitPane, firstPane))

        self.eachPane(doTransfer)

        self._controller.setLayoutLocked(False)

        emptyPanes = []
        hasNonEmpty = False

        def collectEmpties(p: MdiSplitPane, emptyPanes=emptyPanes):
            nonlocal hasNonEmpty
            subWins = p.subWindows()
            if len(subWins) == 0:
                emptyPanes.append(p)
            else:
                hasNonEmpty = True

        self.eachPane(collectEmpties)

        for p in emptyPanes:
            if hasNonEmpty or p != firstPane:
                p.parentSplit().close()

        self._controller.setLayoutLocked(locked)

    def closeEmpties(self):
        if self._controller.isLayoutLocked():
            return

        emptyPanes = []

        def collectEmpties(p: MdiSplitPane):
            nonlocal emptyPanes
            subWins = p.subWindows()
            if len(subWins) == 0:
                emptyPanes.append(p)

        self.eachPane(collectEmpties)

        for p in emptyPanes:
            p.parentSplit().close()

    def splitAt(self, globalPos: QPoint) -> tuple["MdiSplit|None", int | None]:
        hit = [None, MdiSplit.HIT_NONE]

        if self.globalRect().contains(globalPos):
            if self.isSplitState():
                splitHandle = self.handle()
                first = self.firstSplit()
                second = self.secondSplit()
                if (
                    splitHandle is not None
                    and first is not None
                    and second is not None
                ):
                    if splitHandle.globalRect().contains(globalPos):
                        hit[0] = self
                        hit[1] = MdiSplit.HIT_HANDLE
                    else:
                        hit = first.splitAt(globalPos)
                        if hit[1] == MdiSplit.HIT_NONE:
                            hit = second.splitAt(globalPos)
            else:
                splitPane = self.pane()
                if splitPane is not None:
                    if splitPane.globalTopBarRect().contains(globalPos):
                        hit[0] = self
                        hit[1] = MdiSplit.HIT_TOPBAR
                    elif splitPane.globalFrameRect().contains(globalPos):
                        hit[0] = self
                        hit[1] = MdiSplit.HIT_FRAME

        return tuple(hit)  # ty: ignore

    def close(self) -> bool:
        splitPane = self.pane()

        if splitPane is None:
            return False

        split = self.parentSplit()
        locked = self._controller.isLayoutLocked()
        self._controller.setLayoutLocked(False)
        result = (
            self._collapseSplit()
            if split is not None
            else splitPane.closeAllSubWindows()
        )
        self._controller.setLayoutLocked(locked)

        return result

    def clear(self):
        self._reassignPane()

    def globalRect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    #  Returns the maximum adjacent splits along width or height.
    #
    #  Example:
    #  Max along width is A + B + C + D = 4
    #  Max along height is X + Y + Z = 3
    #  ! do not contribute
    #  ┌───┬─┬─┬─────────┐   ┌───┬─┬─┬─────────┐
    #  │ A │B│C│    D    │   │ ! │!│X│    !    │
    #  │   ├─┴─┤         │   │   ├─┴─┤         │
    #  │   │ ! │         │   │   │ Y │         │
    #  ├───┼───┤         │   ├───┼───┤         │
    #  │ ! │ ! │         │   │ ! │ Z │         │
    #  └───┴───┴─────────┘   └───┴───┴─────────┘

    def maxAdjacentSplits(self) -> QSize:
        if self.isTabbedState():
            return QSize(1, 1)

        splitHandle = self.handle()
        first = self.firstSplit()
        second = self.secondSplit()

        if splitHandle is None or first is None or second is None:
            return QSize(1, 1)

        orient: Qt.Orientation = splitHandle.orientation()
        firstMin: QSize = first.maxAdjacentSplits()
        secondMin: QSize = second.maxAdjacentSplits()

        if orient == Qt.Orientation.Vertical:
            return QSize(
                firstMin.width() + secondMin.width(),
                max(firstMin.height(), secondMin.height()),
            )

        return QSize(
            max(firstMin.width(), secondMin.width()),
            firstMin.height() + secondMin.height(),
        )

    def minDragSizeHint(self) -> QSize:
        sz: QSize = self.maxAdjacentSplits()
        return QSize(
            (sz.width() * MdiSplit.MIN_SIZE)
            + ((sz.width() - 1) * MdiSplitHandle.HANDLE_SIZE),
            (sz.height() * MdiSplit.MIN_SIZE)
            + ((sz.height() - 1) * MdiSplitHandle.HANDLE_SIZE),
        )

    def equalizeLayout(self, orient: Qt.Orientation | None = None):
        if self.isTabbedState():
            splitPane = self.pane()
            if splitPane is None:
                return
            sw = splitPane.currentSubWindow()
            view = self._helper.getViewBySubWin(sw)
            if view is not None:
                self._helper.centerCanvas(sw, view, epsilon=10)
            return

        splitHandle = self.handle()
        first = self.firstSplit()
        second = self.secondSplit()

        if splitHandle is None or first is None or second is None:
            return

        if not orient or orient == splitHandle.orientation():
            firstCounts = first.maxAdjacentSplits()
            secondCounts = second.maxAdjacentSplits()

            proportion = 0.5

            if splitHandle.orientation() == Qt.Orientation.Vertical:
                totalWidthUnits = firstCounts.width() + secondCounts.width()
                proportion = float(firstCounts.width()) / totalWidthUnits
            else:
                totalHeightUnits = firstCounts.height() + secondCounts.height()
                proportion = float(firstCounts.height()) / totalHeightUnits

            splitHandle.setProportion(proportion)

        first.equalizeLayout(orient)
        second.equalizeLayout(orient)

    def _makeSplit(
        self,
        edge: Qt.Edge | None,
        tabSplit: "MdiSplit|None",
        tabIndex: int,
        duplicate: bool,
    ) -> "MdiSplit|None":
        tabSplitParent: MdiSplit | None = None
        tabPane: MdiSplitPane | None = None
        sw: QMdiSubWindow | None = None
        isFirstSplit: bool = False
        tabSplitOrient: Qt.Orientation | None = None

        if tabSplit is not None:
            tabSplitParent = tabSplit.parentSplit()
            tabPane = tabSplit.pane()
            sw = tabPane.subWindowAt(tabIndex) if tabPane is not None else None
            isFirstSplit = (
                True
                if (
                    tabSplitParent is not None
                    and tabSplit == tabSplitParent.firstSplit()
                )
                else False
            )
            parentHandle = (
                tabSplitParent.handle() if tabSplitParent is not None else None
            )
            if parentHandle is not None:
                tabSplitOrient = parentHandle.orientation()

        if self._controller.isLayoutLocked():
            return None

        restoreHandleOffsets: list[tuple[MdiSplitHandle, int]] = []

        parent: MdiSplit | None = self.parentSplit()
        parentHandle = parent.handle() if parent is not None else None
        parentOrient = (
            parentHandle.orientation()
            if parentHandle is not None
            else Qt.Orientation.Vertical
        )

        # The new split
        createdSplit: MdiSplit | None = None

        # All the children of the current split are moved to createdSplit's counterpart
        movedSplit: MdiSplit | None = None

        if self.isSplitState():
            splitHandle = self.handle()

            if splitHandle is None:
                return

            handleOffset: int = splitHandle.offset()
            orient = splitHandle.orientation()

            firstSplit = self.firstSplit()
            secondSplit = self.secondSplit()

            if edge in (Qt.Edge.RightEdge, Qt.Edge.BottomEdge):
                self._firstSplit = MdiSplit(
                    self,
                    controller=self._controller,
                    orient=orient,
                    firstSplit=firstSplit,
                    secondSplit=secondSplit,
                )
                self._secondSplit = MdiSplit(
                    self,
                    controller=self._controller,
                )
                movedSplit = self._firstSplit
                createdSplit = self._secondSplit
            else:
                self._secondSplit = MdiSplit(
                    self,
                    controller=self._controller,
                    orient=orient,
                    firstSplit=firstSplit,
                    secondSplit=secondSplit,
                )
                self._firstSplit = MdiSplit(
                    self,
                    controller=self._controller,
                )
                movedSplit = self._secondSplit
                createdSplit = self._firstSplit

            newSplitHeight = self.height() * 0.33
            newSplitWidth = self.width() * 0.33

            def collectHandleOffsets(s: MdiSplit):
                nonlocal handleOffset
                nonlocal restoreHandleOffsets
                nonlocal movedSplit

                h = s.handle()
                if h is not None:
                    if s == movedSplit:
                        if (
                            edge == Qt.Edge.TopEdge
                            and h.orientation() == Qt.Orientation.Horizontal
                        ):
                            handleOffset -= (
                                newSplitHeight + MdiSplitHandle.HANDLE_SIZE
                            )
                        elif (
                            edge == Qt.Edge.LeftEdge
                            and h.orientation() == Qt.Orientation.Vertical
                        ):
                            handleOffset -= (
                                newSplitWidth + MdiSplitHandle.HANDLE_SIZE
                            )
                        restoreHandleOffsets.append((h, handleOffset))
                    else:
                        restoreHandleOffsets.append((h, h.offset()))

            movedSplit.eachSplit(collectHandleOffsets)

            splitHandle.setOrientation(
                Qt.Orientation.Vertical
                if edge in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge)
                else Qt.Orientation.Horizontal
            )

            match edge:
                case Qt.Edge.LeftEdge:
                    splitHandle.moveTo(newSplitWidth)
                case Qt.Edge.TopEdge:
                    splitHandle.moveTo(newSplitHeight)
                case Qt.Edge.RightEdge:
                    splitHandle.moveTo(self.width() - newSplitWidth)
                case Qt.Edge.BottomEdge:
                    splitHandle.moveTo(self.height() - newSplitHeight)
                case _:
                    pass

        else:
            keepPane = self.pane()

            if keepPane is None:
                return None

            self._pane = None

            self._handle = MdiSplitHandle(
                self,
                controller=self._controller,
                orient=(
                    Qt.Orientation.Vertical
                    if edge in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge)
                    else Qt.Orientation.Horizontal
                ),
            )
            self._handle.show()
            self._handle.raise_()
            self._handle.handleMoved.connect(self.slotHandleMoved)

            if edge in (Qt.Edge.RightEdge, Qt.Edge.BottomEdge):
                self._firstSplit = MdiSplit(
                    self, controller=self._controller, pane=keepPane
                )
                self._secondSplit = MdiSplit(self, controller=self._controller)
                movedSplit = self._firstSplit
                createdSplit = self._secondSplit
            else:
                self._secondSplit = MdiSplit(
                    self, controller=self._controller, pane=keepPane
                )
                self._firstSplit = MdiSplit(self, controller=self._controller)
                movedSplit = self._secondSplit
                createdSplit = self._firstSplit

        self._firstSplit.show()
        self._secondSplit.show()

        activePane = createdSplit.pane()

        if duplicate:
            win = self._helper.getWin()
            view = self._helper.getViewBySubWin(sw)
            if win is not None and view is not None:
                self._controller.openView(view.document(), activePane)

        elif activePane and tabPane:

            tabPane.transferTab(tabIndex, activePane)

            if tabPane.isEmpty():

                if (
                    tabSplit is not None
                    and not self._controller.isLayoutLocked()
                ):
                    tabSplit.close()

                if (
                    tabSplitParent is not None
                    and tabSplit is not None
                    and parent is not None
                    and parentHandle is not None
                    and tabSplitParent == parent
                    and parentHandle.orientation() == parentOrient
                ):
                    newHandlePos = 0
                    # First and second exchange positions
                    # They should keep their original sizes
                    if parentOrient == Qt.Orientation.Vertical:
                        newHandlePos = (
                            parent.width() - tabSplit.width()
                            if isFirstSplit
                            else tabSplit.width()
                        )
                    else:
                        newHandlePos = (
                            parent.height() - tabSplit.height()
                            if isFirstSplit
                            else tabSplit.height()
                        )

                    if newHandlePos > 0:
                        restoreHandleOffsets.append(
                            (parentHandle, newHandlePos)
                        )

                elif (
                    tabSplitParent is not None
                    and parent is not None
                    and tabSplitOrient == parentOrient
                ):

                    # Handle a few cases where the removed pane
                    # leaves extra width/height that needs to be reallocated
                    # It is not perfect but better than not having it
                    topSplit = parent.parentSplit()
                    if topSplit is not None:
                        topSplit.equalizeLayout(parentOrient)

            self._controller.setActiveSplitPane(activePane)

        rootSplit = self.rootSplit()

        if self == rootSplit:
            rootOrient = (
                Qt.Orientation.Vertical
                if edge in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge)
                else Qt.Orientation.Horizontal
            )
            self.equalizeLayout(rootOrient)

            def cb(
                restoreHandleOffsets=restoreHandleOffsets,
                rootOrient=rootOrient,
            ):
                for off in restoreHandleOffsets:
                    if off[0].orientation() != rootOrient:
                        off[0].moveTo(off[1])

            QTimer.singleShot(0, cb)
        else:
            def cb(restoreHandleOffsets=restoreHandleOffsets):
                for off in restoreHandleOffsets:
                    off[0].moveTo(off[1])

            QTimer.singleShot(0, cb)

        if rootSplit is not None:
            rootSplit.refreshSplitSizes()

        if movedSplit:

            # FIXME checks because of QTimer delay
            # FIXME the pane from where the tab came from
            # plus its sibling split if resized
            # plus the new split
            # plus the new splits sibling !!
            def recenterCanvases(p: MdiSplitPane):
                sw = p.currentSubWindow()
                view = self._helper.getViewBySubWin(sw)
                if view is not None:
                    self._helper.centerCanvas(sw, view, epsilon=10)
                pass

            QTimer.singleShot(
                0,
                lambda movedSplit=movedSplit, recenterCanvases=recenterCanvases: movedSplit.eachPane(
                    recenterCanvases
                ),
            )

        def updateTabBars(p: MdiSplitPane):
            tabs = p.tabs()
            if tabs is not None:
                tabs.slotConfigChanged()

        rootSplit.eachPane(updateTabBars)

        return createdSplit

    # Can be called when all subwindows for a split close
    # Meaning it may be called when the app quits
    def _collapseSplit(self) -> bool:
        split = self.parentSplit()
        if split is None:
            return False

        first = split.firstSplit()
        second = split.secondSplit()

        removeSplit = None
        keepSplit = None

        if first == self:
            removeSplit = first
            keepSplit = second
        elif second == self:
            removeSplit = second
            keepSplit = first

        if removeSplit is None and keepSplit is None:
            return False

        # Only called on tabbed splits, this keeps it simple
        removePane = typing.cast(MdiSplit, removeSplit).pane()
        if removePane is None:
            return False

        # User canceled closing a window
        if not removePane.closeAllSubWindows():
            return False

        keepPane = typing.cast(MdiSplit, keepSplit).pane()

        if keepPane is not None:
            split._reassignPane(keepPane)
        else:
            split._reassignSplits(keepSplit)

        return True

    # Reassigns a child pane or just add a new empty pane to an ancestor split (which has existing splits)
    def _reassignPane(self, newPane: MdiSplitPane | None = None):
        first = self.firstSplit()
        second = self.secondSplit()

        splitHandle = self.handle()
        if splitHandle is not None:
            splitHandle.deleteLater()
            self._handle = None

        splitPane = self.pane()
        if splitPane is not None and splitPane != newPane:
            splitPane.deleteLater()
            self._pane = None

        transferPane = self._helper.isAlive(newPane, MdiSplitPane)
        self._pane = (
            MdiSplitPane(self, controller=self._controller)
            if transferPane is None
            else transferPane
        )
        self._pane.setParent(self)
        self._pane.show()

        if first is not None:
            first.deleteLater()

        if second is not None:
            second.deleteLater()

        self._firstSplit = None
        self._secondSplit = None

        rootSplit = self.rootSplit()
        if rootSplit is not None:
            rootSplit.refreshSplitSizes()

    # Reassigns child splits to an ancestor split (which has existing splits)
    def _reassignSplits(self, parent: "MdiSplit|None" = None):
        if parent is None:
            return

        first = self.firstSplit()
        second = self.secondSplit()

        if first is None or second is None:
            return

        parentHandle = parent.handle()

        self._firstSplit = parent.firstSplit()
        self._secondSplit = parent.secondSplit()

        if (
            self._firstSplit is None
            or self._secondSplit is None
            or parentHandle is None
        ):
            return

        offset = parentHandle.offset()

        self._firstSplit.setParent(self)
        self._secondSplit.setParent(self)

        if first is not None:
            first.deleteLater()

        if second is not None:
            second.deleteLater()

        self._firstSplit.show()
        self._secondSplit.show()

        splitHandle = self.handle()
        if splitHandle is not None and parentHandle is not None:
            splitHandle.setOrientation(parentHandle.orientation())
            splitHandle.moveTo(offset)

        rootSplit = self.rootSplit()
        if rootSplit is None:
            return

        rootSplit.refreshSplitSizes()

    def makeSplitLeft(
        self,
        tabSplit: "MdiSplit|None" = None,
        tabIndex: int = -1,
        duplicate: bool = False,
    ) -> "MdiSplit|None":
        return self._makeSplit(Qt.Edge.LeftEdge, tabSplit, tabIndex, duplicate)

    def makeSplitRight(
        self,
        tabSplit: "MdiSplit|None" = None,
        tabIndex: int = -1,
        duplicate: bool = False,
    ) -> "MdiSplit|None":
        return self._makeSplit(
            Qt.Edge.RightEdge, tabSplit, tabIndex, duplicate
        )

    def makeSplitAbove(
        self,
        tabSplit: "MdiSplit|None" = None,
        tabIndex: int = -1,
        duplicate: bool = False,
    ) -> "MdiSplit|None":
        return self._makeSplit(Qt.Edge.TopEdge, tabSplit, tabIndex, duplicate)

    def makeSplitBelow(
        self,
        tabSplit: "MdiSplit|None" = None,
        tabIndex: int = -1,
        duplicate: bool = False,
    ) -> "MdiSplit|None":
        return self._makeSplit(
            Qt.Edge.BottomEdge, tabSplit, tabIndex, duplicate
        )

    def makeSplitAtEdge(
        self,
        edge: Qt.Edge | None = None,
        tabSplit: "MdiSplit|None" = None,
        tabIndex: int = -1,
        duplicate: bool = False,
    ) -> "MdiSplit|None":
        root = self.rootSplit()
        return (
            root._makeSplit(edge, tabSplit, tabIndex, duplicate)
            if root is not None
            else None
        )

    def saveState(self) -> dict[Any, Any]:
        if self.isSplitState():
            mdi = self._helper.getMdi()
            splitHandle = self.handle()
            first = self.firstSplit()
            second = self.secondSplit()

            if (
                mdi is None
                or splitHandle is None
                or first is None
                or second is None
            ):
                return {}

            state = {}
            state["state"] = (
                "v"
                if splitHandle.orientation() == Qt.Orientation.Vertical
                else "h"
            )
            state["offset"] = splitHandle.offset()
            state["first"] = first.saveState()
            state["second"] = second.saveState()
            return state

        else:
            pane = self.pane()
            if pane is None:
                return {}
            return pane.saveState()

    def restoreState(
        self, state: dict[Any, Any], context: dict[Any, Any]
    ) -> bool:
        if not state:
            return False

        if not isinstance(context, dict):
            context = {}

        self.collapseLayout()

        if state.get("state", None) == "c":
            splitPane = self.pane()
            if not splitPane:
                return False
            return splitPane.restoreState(state, context)

        splitType = state.get("state", None)

        if splitType not in ("v", "h"):
            return False

        handleOrient = (
            Qt.Orientation.Vertical
            if splitType == "v"
            else Qt.Orientation.Horizontal
        )

        handleOffset = state.get("offset", -1)
        firstState = state.get("first", None)
        secondState = state.get("second", None)
        mdiWidth = context.get("winWidth", 0)
        mdiHeight = context.get("winHeight", 0)

        mdi = self._helper.getMdi()
        if mdi is None:
            return False

        if handleOrient == Qt.Orientation.Vertical:
            self.makeSplitRight()
            if (
                handleOffset > 0
                and mdiWidth
                and mdiWidth > 0
                and mdi.width() > 0
            ):
                handleOffset = int(
                    float(handleOffset) / mdiWidth * mdi.width()
                )
            else:
                handleOffset = int(mdi.width() * 0.5)
        else:
            self.makeSplitBelow()
            if (
                handleOffset > 0
                and mdiHeight
                and mdiHeight > 0
                and mdi.height() > 0
            ):
                handleOffset = int(
                    float(handleOffset) / mdiHeight * mdi.height()
                )
            else:
                handleOffset = int(mdi.height() * 0.5)

        first = self.firstSplit()
        second = self.secondSplit()
        splitHandle = self.handle()

        if first is None or second is None or splitHandle is None:
            return False

        def cb(splitHandle=splitHandle, handleOffset=handleOffset):
            if self._helper.isAlive(splitHandle, MdiSplitHandle):
                splitHandle.moveTo(handleOffset)

        context["callbacks"].resize.append(cb)

        if not first.restoreState(firstState, context):
            return False

        if not second.restoreState(secondState, context):
            return False

        return True
