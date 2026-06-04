from ..pyqt import (
    pyqtSignal,
    toPoint,
    getEventGlobalPos,
    Qt,
    QObject,
    QEvent,
    QWidget,
    QPoint,
    QTimer,
    QStyle,
    QPaintEvent,
    QMouseEvent,
    QResizeEvent,
    QStylePainter,
    QStyleOption,
    QRect,
    QSize,
)

from ..options import (
    getOpt,
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

if TYPE_CHECKING:
    from .mdi_split import MdiSplit
    from .mdi_split_pane import MdiSplitPane
    from .mdi_controller import MdiController


class MdiSplitHandle(QWidget):
    handleMoved = pyqtSignal()

    HANDLE_SIZE = 8

    DRAG_NONE = 0
    DRAG_START = 1
    DRAG_MOVE = 2
    DRAG_END = 3

    def __init__(
        self,
        parent: QWidget,
        controller: "MdiController",
        orient: Qt.Orientation,
    ):
        super().__init__(parent)

        self._controller = controller
        self._helper = controller._helper
        self._dragTimer = QTimer(self)
        self._dragState: int = MdiSplitHandle.DRAG_NONE
        self._orient: Qt.Orientation = (
            Qt.Orientation.Vertical if not orient else orient
        )
        self._dragEdge: Qt.Edge | None = None
        self._startPos = -1
        self._startSize = -1
        self._prevPos = -1
        self._startMousePos = -1
        self._currMousePos = -1
        self._proportion = 0.5

        self._dragTimer.timeout.connect(self.slotHandleMove)

        self.setCursor(
            Qt.CursorShape.SizeHorCursor
            if orient == Qt.Orientation.Vertical
            else Qt.CursorShape.SizeVerCursor
        )
        self.setAutoFillBackground(True)

        if parent is not None:
            parent.installEventFilter(self)

        self.reset()

    def orientation(self) -> Qt.Orientation:
        return self._orient

    def setOrientation(self, orient: Qt.Orientation, offset: int = -1):
        if self._orient == orient:
            return
        self._orient = orient
        self.setCursor(
            Qt.CursorShape.SizeHorCursor
            if orient == Qt.Orientation.Vertical
            else Qt.CursorShape.SizeVerCursor
        )
        self.reset()

        if offset != -1:
            self.moveTo(offset)

    def dragState(self) -> int:
        return self._dragState

    def parentSplit(self) -> "MdiSplit|None":
        from .mdi_split import MdiSplit

        return self._helper.isAlive(self.parentWidget(), MdiSplit)

    def dragParent(self) -> "MdiSplitHandle|None":
        if self._dragState != MdiSplitHandle.DRAG_NONE:
            return self

        split = self.parentSplit()
        if split is not None:
            split = split.parentSplit()
            handle = split.handle() if split is not None else None
            if handle:
                return handle.dragParent()

        return None

    def offset(self) -> int:
        return (
            self.x() if self._orient == Qt.Orientation.Vertical else self.y()
        )

    def moveTo(self, offset: int):
        split = self.parentSplit()
        if split is None:
            return

        match self._orient:
            case Qt.Orientation.Vertical:
                if offset != self.x():
                    self.move(int(offset), self.y())
                    self._proportion = float(self.x()) / float(split.width())
                    self.clamp()
                    self.handleMoved.emit()

            case Qt.Orientation.Horizontal:
                if offset != self.y():
                    self.move(self.x(), int(offset))
                    self._proportion = float(self.y()) / float(split.height())
                    self.clamp()
                    self.handleMoved.emit()

    def proportion(self) -> float:
        return self._proportion

    def setProportion(self, proportion: float):
        split = self.parentSplit()
        if split is None:
            return

        size = (
            split.width()
            if self._orient == Qt.Orientation.Vertical
            else split.height()
        )
        clampVal = max(0.0, min(proportion, 1.0))
        self.moveTo(round(clampVal * size))

    def reset(self):
        split = self.parentSplit()
        if split is None:
            return

        r = split.rect()
        self._proportion = 0.5
        hsz = MdiSplitHandle.HANDLE_SIZE

        if self._orient == Qt.Orientation.Vertical:
            self.setGeometry((r.width() - hsz), 0, hsz, r.height())
        else:
            self.setGeometry(0, (r.height() - hsz), r.width(), hsz)

    def clamp(self, proportionalHint: bool = False):
        from .mdi_split import MdiSplit

        split = self.parentSplit()
        if split is None:
            return

        sw = split.width()
        sh = split.height()
        hw = self.width()
        hh = self.height()

        dragHandle = self.dragParent()
        inSecondRect = self._dragEdge in (
            Qt.Edge.RightEdge,
            Qt.Edge.BottomEdge,
        )

        if self._orient == Qt.Orientation.Vertical:
            if sw < MdiSplit.MIN_SIZE:
                self.reset()
                return

            if hh != sh:
                self.resize(hw, sh)
                hh = sh

            # When the viewport is resized use the cached proportions
            hx = (
                self.x()
                if (dragHandle is not None or not proportionalHint)
                else round(self._proportion * sw)
            )
            hy = max(0, min(self.y(), sh - hh))

            # Keep split handles anchored when on either side of the one being dragged
            if dragHandle is not None and dragHandle != self:
                if inSecondRect:
                    hx = self._startPos - (self._startSize - sw)
                elif self._startSize >= sw:
                    hx = min(
                        self._startPos, self._startPos + (self._startSize - sw)
                    )

            # See MdiSplit maxAdjacentSplits() and minDragSizeHint()
            # Which is what these offsets are
            hx = max(self.minOffset(), min(hx, self.maxOffset()))

            if hx != self.x() or hy != self.y():
                self.move(int(hx), int(hy))

            if dragHandle is not None:
                self._proportion = float(self.x()) / float(split.width())

        else:
            if sh < MdiSplit.MIN_SIZE:
                self.reset()
                return

            if hw != sw:
                self.resize(sw, hh)
                hw = sw

            # When the viewport is resized use the cached proportions
            hy = (
                self.y()
                if (dragHandle is not None or not proportionalHint)
                else round(self._proportion * sh)
            )
            hx = max(0, min(self.x(), sw - hw))

            # Keep split handles anchored when on either side of the one being dragged
            if dragHandle is not None and dragHandle != self:
                if inSecondRect:
                    hy = self._startPos - (self._startSize - sh)
                elif self._startSize >= sh:
                    hy = min(
                        self._startPos, self._startPos + (self._startSize - sh)
                    )

            # See MdiSplit maxAdjacentSplits() and minDragSizeHint()
            # Which is what these offsets are

            hy = max(self.minOffset(), min(hy, self.maxOffset()))

            if hx != self.x() or hy != self.y():
                self.move(int(hx), int(hy))

            if dragHandle is not None:
                self._proportion = float(self.y()) / float(split.height())

    def paintEvent(self, event: QPaintEvent):
        painter = QStylePainter(self)
        rect = event.rect()

        opt = QStyleOption()
        opt.initFrom(self)

        painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt)

        # QSplitter does this, but the dots are always slightly off-center on vertical handles:
        # opt.state = d->m_orient == Qt.Orientation.Vertical ? QStyle::State_Horizontal : QStyle::State_None

        # Do the rotation here to keep it centered
        if self._orient == Qt.Orientation.Vertical:
            painter.translate(self.width() / 2.0, self.height() / 2.0)
            painter.rotate(90)
            painter.translate(-self.height() / 2.0, -self.width() / 2.0)
            rotatedRect = QRect(0, 0, self.height(), self.width())
            opt.rect = rotatedRect
        else:
            opt.rect = rect

        painter.drawControl(QStyle.ControlElement.CE_Splitter, opt)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            eventPos = toPoint(getEventGlobalPos(event))

            if self._orient == Qt.Orientation.Vertical:
                self._startPos = self.pos().x()
                self._startMousePos = eventPos.x()
                self._currMousePos = self._startMousePos
            else:
                self._startPos = self.pos().y()
                self._startMousePos = eventPos.y()
                self._currMousePos = self._startMousePos

            self._dragState = MdiSplitHandle.DRAG_START
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragState == MdiSplitHandle.DRAG_NONE:
            return

        if not self._dragTimer.isActive():
            self._dragTimer.start(100)

        eventPos = toPoint(getEventGlobalPos(event))

        self._currMousePos = (
            eventPos.x()
            if self._orient == Qt.Orientation.Vertical
            else eventPos.y()
        )
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragTimer.isActive():
                self._dragTimer.stop()

            if self._dragState == MdiSplitHandle.DRAG_MOVE:
                self._dragState = MdiSplitHandle.DRAG_END
                self.handleMoved.emit()

            self._dragState = MdiSplitHandle.DRAG_NONE
            event.accept()

    def eventFilter(self, parent: QObject, event: QEvent) -> bool:
        eventType = event.type()

        if parent == self.parentWidget() and eventType in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self.clamp(True)

        return super().eventFilter(parent, event)

    def slotHandleMove(self):
        if self._dragState == MdiSplitHandle.DRAG_START:
            split = self.parentSplit()
            if split is None:
                return

            first = split.firstSplit()
            second = split.secondSplit()
            if first is None or second is None:
                return

            def storeFirst(s: "MdiSplit"):
                self._storeChildOffsets(s, True)

            def storeSecond(s: "MdiSplit"):
                self._storeChildOffsets(s, False)

            first.eachSplit(storeFirst)
            second.eachSplit(storeSecond)

            self.handleMoved.emit()
            self._dragState = MdiSplitHandle.DRAG_MOVE

        if self._dragState != MdiSplitHandle.DRAG_MOVE:
            return

        self.moveTo(self._startPos + self._currMousePos - self._startMousePos)

    def _storeChildOffsets(self, s: "MdiSplit", inFirstSplit: bool):
        splitHandle = s.handle()
        if splitHandle is not None:
            vert = splitHandle._orient == Qt.Orientation.Vertical

            if vert:
                splitHandle._dragEdge = (
                    Qt.Edge.LeftEdge if inFirstSplit else Qt.Edge.RightEdge
                )
                splitHandle._startSize = s.width()
            else:
                splitHandle._dragEdge = (
                    Qt.Edge.TopEdge if inFirstSplit else Qt.Edge.BottomEdge
                )
                splitHandle._startSize = s.height()

            splitHandle._startPos = splitHandle.offset()
            splitHandle._prevPos = splitHandle._startPos

    def firstRect(self) -> QRect:
        split = self.parentSplit()
        if split is None:
            return QRect()

        self.clamp()
        geom = self.geometry()

        if self._orient == Qt.Orientation.Vertical:
            return QRect(0, 0, max(0, geom.x()), geom.height())
        else:
            return QRect(0, 0, geom.width(), max(0, geom.y()))

    def secondRect(self) -> QRect:
        split = self.parentSplit()
        if split is None:
            return QRect()

        self.clamp()
        geom = self.geometry()

        if self._orient == Qt.Orientation.Vertical:
            return QRect(
                max(0, geom.x() + geom.width()),
                0,
                max(0, split.width() - geom.x() - geom.width()),
                geom.height(),
            )
        else:
            return QRect(
                0,
                max(0, geom.y() + geom.height()),
                geom.width(),
                max(0, split.height() - geom.y() - geom.height()),
            )

    def minOffset(self) -> int:
        from .mdi_split import MdiSplit

        split = self.parentSplit()
        first = split.firstSplit() if split is not None else None

        if first is None:
            return MdiSplit.MIN_SIZE

        sz = first.minDragSizeHint()
        return (
            sz.width()
            if self._orient == Qt.Orientation.Vertical
            else sz.height()
        )

    def maxOffset(self) -> int:
        from .mdi_split import MdiSplit

        split = self.parentSplit()
        second = split.secondSplit() if split is not None else None

        if second is None:
            return MdiSplit.MIN_SIZE

        sz = second.minDragSizeHint()
        if self._orient == Qt.Orientation.Vertical:
            return split.width() - sz.width()  # ty: ignore

        return split.height() - sz.height()  # ty: ignore

    def globalRect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
