# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    toPoint,
    getEventGlobalPos,
    Qt,
    QWidget,
    QPoint,
    QTimer,
    QPaintEvent,
    QPainter,
    QColor,
    QRect,
    QEvent,
    QMouseEvent,
)


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .split import Split
    from ..helper import Helper
    from .split_pane import SplitPane
    
from ..options import (
    getOpt,
)

from .split_helpers import (
    QMDI_WIN_MIN_SIZE,
    SPLIT_MIN_SIZE,
)


class SplitHandle(QWidget):
    SIZE = getOpt("resize", "split_handle_size")

    def __init__(
        self,
        split: "Split",
        controller: "SplitPane",
        orient: Qt.Orientation | None = None,
        pos: int | None = None,
    ):
        super().__init__(controller._helper.getMdi())
        self.setObjectName("SplitHandle")
        self._controller: "SplitPane" = controller
        self._helper: "Helper" = controller._helper
        self._split: "Split" = split
        self._lastMousePos: QPoint = QPoint()
        self._dragging: bool = False
        self._dragDelta: int = 0
        self._lastDragDelta: int = 0
        self._dragTimer: QTimer | None = None
        self._ctrlDown: bool = False
        self._orient: Qt.Orientation = (
            orient
            if isinstance(orient, Qt.Orientation)
            else Qt.Orientation.Vertical
        )
        if self._orient == Qt.Orientation.Vertical:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.setProperty("orient", "vertical")
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
            self.setProperty("orient", "horizontal")
            
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True) 
        self.reset()
        if isinstance(pos, int):
            self.moveTo(pos)
        self.clamp()
        self.raise_()
        self.show()

    def setSplit(self, split: "Split"):
        self._split = split

    def split(self) -> "Split|None":
        from .split import Split

        return self._helper.isAlive(self._split, Split)

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
            refresh = orient != self._orient
            self._orient = orient
            if self._orient == Qt.Orientation.Vertical:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.setProperty("orient", "vertical")
            else:
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                self.setProperty("orient", "horizontal")
                
            if refresh:
                self._helper.refreshWidget(self)
                
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
            if pw < SPLIT_MIN_SIZE:
                self.reset()
                return
            if h != ph:
                self.resize(w, ph)
                h = ph
            x = max(
                px + QMDI_WIN_MIN_SIZE,
                min(self.x(), px + pw - w - QMDI_WIN_MIN_SIZE),
            )
            y = max(py, min(self.y(), py + ph - h))
        else:
            if ph < SPLIT_MIN_SIZE:
                self.reset()
                return
            if w != pw:
                self.resize(pw, h)
                w = pw
            x = max(px, min(self.x(), px + pw - w))
            y = max(
                py + QMDI_WIN_MIN_SIZE,
                min(self.y(), py + ph - h - QMDI_WIN_MIN_SIZE),
            )
        if x != self.x() or y != self.y():
            self.move(x, y)

    def event(self, event: QEvent):
        event_type = event.type()
        if event_type == QEvent.Type.ParentAboutToChange:
            pass
        elif event_type == QEvent.Type.ParentChange:
            pass
        return super().event(event)

    def _storeDragPos(self):
        topSplit = self._controller.topSplit()
        if topSplit:
            def cb(split: "Split"):
                view = split.getActiveTabView()
                win = split.getActiveTabWindow()
                if not (view and win):
                    return
                data = self._helper.getViewData(view)
                if data:
                    data["dragOrigin"] = self._helper.canvasPosition(
                        win=win, view=view
                    )
            topSplit.eachCollapsedSplit(cb)

    def _clearDragPos(self):
        topSplit = self._controller.topSplit()
        if topSplit:
            def cb(split: "Split"):
                view = split.getActiveTabView()
                win = split.getActiveTabWindow()
                if not (view and win):
                    return
                data = self._helper.getViewData(view)
                if data and "dragOrigin" in data:
                    del data["dragOrigin"]
            topSplit.eachCollapsedSplit(cb)

    def _checkCtrlModifier(self):
        ctrlDown = self._ctrlDown
        self._ctrlDown = self._controller.modifiers().ctrlDown

        if self._ctrlDown != ctrlDown:
            if self._ctrlDown:
                self._storeDragPos()
            else:
                self._clearDragPos()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._dragDelta = 0
            self._lastMousePos = toPoint(getEventGlobalPos(event))
            self._controller.setDragSplit(self._split)
            self._ctrlDown = self._controller.modifiers().ctrlDown
            self._storeDragPos()
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
            first.onResize()
        if second:
            second.onResize()

    def handleMove(self):
        self._checkCtrlModifier()
        if self._dragDelta == 0:
            return
        if self._orient == Qt.Orientation.Vertical:
            self.moveTo(self.x() + self._dragDelta)
        else:
            self.moveTo(self.y() + self._dragDelta)
        self._lastDragDelta = self._dragDelta
        self._dragDelta = 0

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self._checkCtrlModifier()
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

            self._helper.hideToast()

            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragTimer:
                self._dragTimer.stop()
                self._dragTimer = None

            self._lastDragDelta = 0
            first = self._split.first()
            second = self._split.second()
            if first:
                first.onResize()
            if second:
                second.onResize()

            self._controller.setDragSplit(None)
            self._clearDragPos()
            self._dragging = False
            event.accept()

