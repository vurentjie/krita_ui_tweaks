from ..pyqt import (
    toPoint,
    getEventPos,
    getEventGlobalPos,
    Qt,
    QColor,
    QGraphicsDropShadowEffect,
    QMainWindow,
    QMouseEvent,
    QObject,
    QPainter,
    QPaintEvent,
    QPainterPath,
    QPen,
    QPoint,
    QPushButton,
    QRect,
    QRectF,
    QTimer,
    QWidget,
)

from types import SimpleNamespace
from typing import Protocol, TYPE_CHECKING
import typing
import math

from ..colors import adjustColor
from ..options import getOpt
from ..i18n import i18n

from .split_helpers import (
    DRAG_VERTICAL_THRESHOLD,
    DRAG_ANGLE_THRESHOLD,
)
from .split_handle import SplitHandle

if TYPE_CHECKING:
    from ..helper import Helper
    from .split import Split
    from .split_pane import SplitPane
    from .split_tabs import SplitTabs
    from .split_toolbar import SplitToolbar


class SplitDrag(QObject):

    def __init__(self, parent: "SplitTabs"):
        from .split_tabs import SplitTabs

        assert isinstance(parent, SplitTabs) or isinstance(parent, QPushButton)
        super().__init__(parent)
        self._helper = parent._helper
        self._controller = parent._controller
        self._dragIndex: int = -1
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
        self._dropSplit: "Split" | None = None
        self._dropEdge: Qt.AnchorPoint | None = None

        self._leftDragStart: QPoint | None = None
        self._leftDragIndex: int = -1
        self._leftDragMode: (
            typing.Literal["detecting", "horizontal", "vertical"] | None
        ) = None
        self._allTabs = False

    def defaultDragIndex(self) -> int:
        if self._leftDragMode == "horizontal":
            return self._leftDragIndex
        return -1

    def reset(self):
        self._dragIndex = -1
        self._dropEdge = None
        self._dropAction = None
        self._dropSplit = None
        self._leftDragStart = None
        self._leftDragIndex = -1
        self._leftDragMode = None
        self._dragPos = None
        if self._dragTimer:
            self._dragTimer.stop()
            self._dragTimer = None
        self._allTabs = False
        self.hideDragPlaceHolder()
        self.hideDropPlaceHolder()

    def showDragPlaceHolder(self, pos: QPoint):
        parentWidget = self.parent()
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if self._dragPlaceHolder is None:
            colors = self._controller.adjustedColors()
            assert colors is not None
            bg = QColor(colors.dragTab)
            fg = QColor(colors.tabText)
            if self._allTabs:
                count = parentWidget.count()
                if count == 1:
                    text = f"{count} {i18n('Tab')}"
                elif count > 1:
                    text = f"{count} {i18n('Tabs')}"
                else:
                    text = i18n("All Tabs")
            else:
                text = parentWidget.tabText(self._dragIndex)

            tabFontBold = getOpt("tab_behaviour", "tab_font_bold")
            
            if getOpt("tab_behaviour", "tab_krita_style"):
                inset=True
                borderRadius=3
                palette = self._controller.adjustedColors()
                borderColor = adjustColor(QColor(palette.dropZone), lightness=0.7)
                borderColor.setAlpha(180)
            else:
                inset=False
                borderRadius=0
                borderColor=None
                
            self._dragPlaceHolder = SplitDragRect(
                parent=qwin,
                color=bg,
                text=text,
                textColor=fg,
                shadow=True,
                inset=inset,
                bold=tabFontBold,
                borderRadius=borderRadius,
                borderColor=borderColor,
            )

        self._dragPlaceHolder.show()
        self._dragPlaceHolder.raise_()
        if self._allTabs:
            parent = parentWidget.parent()
            if parent:
                self._dragPlaceHolder.setGeometry(pos.x(), pos.y(), 100, 100)
        else:
            self._dragPlaceHolder.setGeometry(
                pos.x(),
                pos.y(),
                parentWidget.tabRect(self._dragIndex).width(),
                parentWidget.height(),
            )

    def hideDragPlaceHolder(self):
        if self._dragPlaceHolder is not None:
            self._dragPlaceHolder.deleteLater()
            self._dragPlaceHolder = None

    def showDropPlaceHolder(self, rect: QRect):
        parentWidget = self.parent()
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if self._dropPlaceHolder is None:
            palette = self._controller.adjustedColors()
            assert palette is not None
            color = QColor(palette.dropZone)
            color.setAlpha(50)
            altColor = QColor(palette.dropZone).darker(150)
            altColor.setAlpha(100)
            self._dropPlaceHolder = SplitDragRect(
                qwin, color=color, altColor=altColor
            )

        self._dropPlaceHolder.show()
        self._dropPlaceHolder.setGeometry(rect)

    def hideDropPlaceHolder(self):
        if self._dropPlaceHolder is not None:
            self._dropPlaceHolder.deleteLater()
            self._dropPlaceHolder = None

    def handleDropZone(self):
        from .split import Split

        parentWidget = self.parent()
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        if (self._allTabs or self._dragIndex != -1) and isinstance(
            self._dragPos, QPoint
        ):
            globalPos = self._dragPos
            pos = qwin.mapFromGlobal(globalPos)
            self.showDragPlaceHolder(pos)

            currSplit = parentWidget.split()

            if not currSplit:
                return

            topSplit = helper.isAlive(currSplit.topSplit(), Split)
            if not topSplit:
                return

            targetSplit, el = topSplit.splitAt(pos)

            self._dropAction = None
            self._dropSplit = None
            self._dropEdge = None
            isOnlyTab = (
                parentWidget.count() == 1 if not self._allTabs else True
            )

            if targetSplit is None or (
                isOnlyTab and topSplit.state() == Split.STATE_COLLAPSED
            ):
                self.hideDropPlaceHolder()
            else:
                from .split import Split

                targetRect = targetSplit.globalRect(withToolBar=False)
                rx, ry, rw, rh = targetRect.getRect()

                isLocked = self._controller.isLocked()
                topRect = topSplit.globalRect(withToolBar=False)
                tx, ty, tw, th = topRect.getRect()

                x = pos.x()
                y = pos.y()
                edgeThreshold = 30

                if not isLocked:
                    if x > tx and x < tx + edgeThreshold and th != rh:
                        self._dropEdge = Qt.AnchorPoint.AnchorLeft
                        topRect.setWidth(edgeThreshold)
                    elif (
                        x > tx + tw - edgeThreshold
                        and x < tx + tw
                        and th != rh
                    ):
                        self._dropEdge = Qt.AnchorPoint.AnchorRight
                        topRect.setX(tx + tw - edgeThreshold)
                    elif y > ty and y < ty + edgeThreshold and tw != rw:
                        self._dropEdge = Qt.AnchorPoint.AnchorTop
                        topRect.setHeight(edgeThreshold)
                    elif (
                        y > ty + th - edgeThreshold
                        and y < ty + th
                        and tw != rw
                    ):
                        self._dropEdge = Qt.AnchorPoint.AnchorBottom
                        topRect.setY(ty + th - edgeThreshold)
                    else:
                        topRect = None

                    if topRect is not None:
                        if isinstance(el, SplitHandle):
                            self.hideDropPlaceholder()  # ty: ignore
                        else:
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
                    # Think must return here
                    targetSplit = (
                        first
                        if typing.cast(Split, first).state()
                        == Split.STATE_COLLAPSED
                        else second
                    )
                    # return

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

                targetSplit = typing.cast(Split, targetSplit)
                level = targetSplit.droppableLevel()

                from .split_toolbar import SplitToolbar

                hasToolbar = isinstance(el, SplitToolbar)

                if hasToolbar:
                    actions.transferTab = True
                    hasAction = True
                elif (
                    not isLocked
                    and level < 30
                    and not isinstance(el, SplitHandle)
                ):
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

                if isOnlyTab and not isLocked:
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
                                cx, cy, cw, ch = currRect.getRect()

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
                                        and ry == cy
                                    ):
                                        actions.makeSplitRight = False
                                    elif (
                                        orient == Qt.Orientation.Horizontal
                                        and rw == cw
                                        and rx == cx
                                    ):
                                        actions.makeSplitBelow = False

                if isLocked:
                    if actions.transferTab:
                        targetRect = targetSplit.globalRect()
                        self._dropAction = "transferTab"
                else:
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

    def mouseMove(self, event: QMouseEvent) -> bool:
        parentWidget = self.parent()
        isDragging = False

        if self._allTabs or self._dragIndex != -1:
            self._dragPos = toPoint(getEventGlobalPos(event))
            if self._dragTimer is None:
                self._dragTimer = QTimer()
                self._dragTimer.timeout.connect(self.handleDropZone)
                self._dragTimer.start(50)
            isDragging = True

        if self._leftDragStart is not None and self._leftDragMode is not None:
            currentPos = toPoint(getEventGlobalPos(event))
            dx = currentPos.x() - self._leftDragStart.x()
            dy = currentPos.y() - self._leftDragStart.y()
            distance = math.sqrt(dx * dx + dy * dy)

            if self._leftDragMode == "detecting":
                if distance >= getOpt("tab_behaviour", "tab_drag_deadzone"):
                    angle_rad = math.atan2(abs(dx), abs(dy))
                    angle_deg = math.degrees(angle_rad)

                    if angle_deg < DRAG_ANGLE_THRESHOLD:
                        self._leftDragMode = "vertical"
                        isDragging = True
                    else:
                        self._leftDragMode = "horizontal"
                        self._leftDragStart = None

            elif self._leftDragMode == "vertical":
                isDragging = True
                vertical_distance = abs(dy)
                if vertical_distance >= DRAG_VERTICAL_THRESHOLD and (
                    self._allTabs or self._dragIndex == -1
                ):
                    qwin = self._helper.getQwin()
                    if qwin:
                        self._controller.winClosed.connect(self.reset)
                        self._dragStart = self._leftDragStart
                        self._dragIndex = self._leftDragIndex
                        globalPos = currentPos
                        pos = qwin.mapFromGlobal(globalPos)
                        self.showDragPlaceHolder(pos)
                        parentWidget.setCursor(Qt.CursorShape.SizeAllCursor)
                        self._leftDragStart = None
                        self._leftDragIndex = -1
                        self._leftDragMode = None

        return isDragging

    def mousePress(self, event: QMouseEvent) -> bool:
        parentWidget = self.parent()
        qwin = self._helper.getQwin()
        if not qwin:
            return False

        btn = event.button()
        index = (
            -1
            if self._allTabs
            else parentWidget.tabAt(toPoint(getEventPos(event)))
        )
        self._dropEdge = None
        self._dropAction = None
        self._dropSplit = None
        self._allTabs = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if index >= 0 or self._allTabs:
            if btn == Qt.MouseButton.LeftButton:
                if getOpt("tab_behaviour", "tab_drag_left_btn"):
                    self._leftDragStart = toPoint(getEventGlobalPos(event))
                    self._leftDragIndex = index
                    self._leftDragMode = "detecting"
                else:
                    self._leftDragIndex = index
                    self._leftDragMode = "horizontal"
            elif btn == Qt.MouseButton.MiddleButton:
                self._controller.winClosed.connect(self.reset)
                if getOpt("tab_behaviour", "tab_drag_middle_btn"):
                    self._dragStart = getEventGlobalPos(event)
                    self._dragIndex = index
                    globalPos = toPoint(getEventGlobalPos(event))
                    pos = qwin.mapFromGlobal(globalPos)
                    self.showDragPlaceHolder(pos)
                    parentWidget.setCursor(Qt.CursorShape.SizeAllCursor)
                    return True
        return False

    def mouseRelease(self, event: QMouseEvent):
        from .split import Split

        parentWidget = self.parent()
        helper = self._helper
        dropSplit = helper.isAlive(self._dropSplit, Split)
        try:
            self._controller.winClosed.disconnect(self.reset)
        except:
            pass

        tabIndex = self._dragIndex if not self._allTabs else None
        if (
            (self._allTabs or self._dragIndex != -1)
            and self._dropAction
            and dropSplit
        ):
            if self._dropAction == "makeSplitAtEdge":
                assert self._dropEdge is not None
                dropSplit.makeSplitAtEdge(
                    tabIndex=tabIndex,
                    allTabs=self._allTabs,
                    tabSplit=parentWidget.split(),
                    edge=self._dropEdge,
                )
            else:
                cb = getattr(dropSplit, self._dropAction, None)
                if cb is not None:
                    cb(
                        tabIndex=tabIndex,
                        allTabs=self._allTabs,
                        tabSplit=parentWidget.split(),
                    )

        parentWidget.unsetCursor()
        self.reset()


class SplitDragRect(QWidget):
    def __init__(
        self,
        parent: QWidget | QMainWindow,
        color: QColor | None = None,
        altColor: QColor | None = None,
        text: str | None = None,
        textColor: QColor | None = None,
        bold: bool = False,
        shadow: bool = False,
        inset: bool = False,
        borderRadius: int = 0,
        borderColor: QColor | None = None,
    ):
        super().__init__(parent)

        self._color = QColor(10, 10, 100, 100) if color is None else color
        self._altColor = altColor
        self._text = text
        self._textColor = textColor if textColor else Qt.GlobalColor.white
        self._textAlign = Qt.AlignmentFlag.AlignCenter
        self._borderRadius = borderRadius
        self._borderColor = borderColor
        self._inset = inset
        self._bold = bold
        if shadow:
            self._shadow = QGraphicsDropShadowEffect()
            self._shadow.setBlurRadius(16)
            self._shadow.setOffset(2, 2)
            self._shadow.setColor(QColor(0, 0, 0, 80))
            self.setGraphicsEffect(self._shadow)

    def setText(self, text: str | None):
        self._text = text
        self.update()

    def setTextAlign(self, align: Qt.AlignmentFlag):
        self._textAlign = align
        self.update()

    def setColor(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        if self._borderRadius == 0:
            p.fillRect(rect, self._color)
        else:
            p.setBrush(self._color)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, self._borderRadius, self._borderRadius)

            if self._inset:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 50), 1))
                p.drawRoundedRect(
                    rect.adjusted(1, 1, -1, -1),
                    self._borderRadius,
                    self._borderRadius,
                )

            if self._borderColor:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(self._borderColor, 2))
                p.drawRoundedRect(
                    rect, self._borderRadius + 1, self._borderRadius + 1
                )

        if self._altColor:
            stripe_width = 5
            pen = QPen(self._altColor, stripe_width * 2)
            p.setPen(pen)

            w, h = rect.width(), rect.height()
            for x in range(-h, w, stripe_width * 2):
                p.drawLine(x, 0, x + h, h)

        if self._text:
            p.setPen(self._textColor)
            if self._bold:
                font = p.font()
                font.setBold(True)
                p.setFont(font)
            p.drawText(
                self.rect(),
                self._textAlign
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                self._text,
            )
