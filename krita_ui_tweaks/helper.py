# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    pyqtBoundSignal,
    sip,
    QAbstractScrollArea,
    QApplication,
    QColor,
    QIcon,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
    QObject,
    QPalette,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QScrollBar,
    QStackedWidget,
    QTabBar,
    QTimer,
    QUuid,
    QWidget,
    QWidgetAction,
)

from krita import Krita, Window, Document, Canvas, View, Notifier

from dataclasses import dataclass
from itertools import count
from typing import Any, Type, TypeVar, TYPE_CHECKING
from types import SimpleNamespace

import typing
import math
import os
import time


if TYPE_CHECKING:
    from .component import Component
    from .tools import SCALING_MODE

T = TypeVar("T", bound=QObject)


@dataclass
class CanvasPosition:
    rect: QRect
    bbox: QRect
    viewport: QRect
    zoom: float
    minZoom: float | None = None
    maxZoom: float | None = None


@dataclass
class DocumentData:
    doc: dict[str, Any]
    views: list[tuple[View, dict[Any, Any]]]


COMPONENT_GROUP = dict[
    typing.Literal["tools", "splitPane", "dockers", "helper"], "Component|None"
]


class Helper:

    def __init__(
        self, qwin: QMainWindow, pluginGroup: COMPONENT_GROUP | None = None
    ):
        self._uid = count(1)
        self._componentGroup: COMPONENT_GROUP | None = pluginGroup
        self._qwin: QMainWindow = qwin
        self._docData: dict[QUuid, DocumentData] = {}
        self._cached: dict[str, Any] = {}
        self._isScrolling = False
        self._isZooming = False
        self._debounceTimer: QTimer = QTimer()
        self._debounceTimer.timeout.connect(self.runDebounceCallbacks)
        self._debounceCheckTime: float = time.monotonic()
        self._debounceCallbacks: dict[
            str, tuple[typing.Callable[..., Any], float, float]
        ] = {}
        typing.cast(pyqtBoundSignal, self.getNotifier().viewClosed).connect(
            lambda: QTimer.singleShot(10, self.refreshDocData)
        )

    def noop(self) -> None:
        pass

    def uid(self):
        return next(self._uid)

    def isAlive(self, obj: Any, cls: Type[T]) -> T | None:
        if isinstance(obj, cls) and not sip.isdeleted(typing.cast(Any, obj)):
            return obj
        return None

    def runDebounceCallbacks(self):
        now = time.monotonic()
        removeKeys = []
        for k in list(self._debounceCallbacks.keys()):
            v = self._debounceCallbacks.get(k, None)
            if v and now - v[1] >= v[2]:
                v[0]()
                removeKeys.append(k)

        for k in removeKeys:
            if k in self._debounceCallbacks:
                del self._debounceCallbacks[k]

        if not self._debounceCallbacks:
            self._debounceTimer.stop()

    def debounceCallback(
        self,
        key: str,
        cb: typing.Callable[..., Any],
        timeout_seconds: float = 2.0,
    ):
        if self._debounceTimer:
            exists = self._debounceCallbacks.get(key, None)
            now = exists[1] if exists else time.monotonic()
            self._debounceCallbacks[key] = (
                cb,
                now,
                timeout_seconds,
            )
            self.runDebounceCallbacks()
            if self._debounceCallbacks:
                self._debounceTimer.start(100)

    def useDarkIcons(self) -> bool:
        bg = self.paletteColor("Window")
        return bg.value() > 100

    def getApp(self) -> Krita:
        return Krita.instance()

    def getNotifier(self) -> Notifier:
        return self.getApp().notifier()

    def getAppDir(self):
        return self.getApp().getAppDataLocation()

    def getScriptDir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def getIconPath(self, name):
        return os.path.join(self.getScriptDir(), "icons", name)

    def getWin(self) -> Window | None:
        for w in self.getApp().windows():
            if w.qwindow() == self._qwin:
                return w

    def isActiveWin(self):
        win = self.getApp().activeWindow()
        return win and win.qwindow() == self._qwin

    def getDoc(self):
        view = self.getView()
        return self.isAlive(view.document(), Document) if view else None

    def docsByFile(self) -> dict[str, Document]:
        docs: dict[str, Document] = {}
        for d in self.getApp().documents():
            path = d.fileName()
            if path and os.path.exists(path):
                docs[path] = d
        return docs

    def viewsByFile(self) -> dict[str, list[View]]:
        views: dict[str, list[View]] = {}
        win = self.getWin()
        if win:
            for v in win.views():
                path = v.document().fileName()
                if path and os.path.exists(path):
                    if path not in views:
                        views[path] = []
                    views[path].append(v)
        return views

    def compareDoc(self, a: Document | None, b: Document | None) -> bool:
        if a and b:
            return a.rootNode().uniqueId() == b.rootNode().uniqueId()
        return False

    def getView(self):
        win = self.getWin()
        return self.isAlive(win.activeView(), View) if win else None

    def getDocData(
        self, obj: View | Document | None = None
    ) -> DocumentData | None:
        if isinstance(obj, View):
            obj = obj.document()
        if isinstance(obj, Document):
            uid = obj.rootNode().uniqueId()
            if uid not in self._docData:
                self._docData[uid] = DocumentData(doc={}, views=[])
            return self._docData.get(uid, None)

    def getViewData(self, view: View | None) -> dict[Any, Any] | None:
        if view:
            doc = view.document()
            if not doc:
                return
            uid = doc.rootNode().uniqueId()
            if uid not in self._docData:
                self._docData[uid] = DocumentData(doc={}, views=[])
            data = self._docData[uid]
            for v in data.views:
                if v[0] == view:
                    return v[1]
            v: tuple[View, dict[Any, Any]] = (view, {})
            data.views.append(v)
            return v[1]

    def setViewData(self, view: View, key: Any, val: Any) -> Any:
        data = self.getViewData(view)
        if data is not None:
            data[key] = val

    def refreshDocData(self):
        win = self.getWin()
        keep: dict[QUuid, DocumentData] = {}
        if win is not None:
            for view in win.views():
                doc = view.document()
                if doc:
                    uid = doc.rootNode().uniqueId()
                    if uid in self._docData:
                        curr = self._docData[uid]
                        if uid not in keep:
                            keep[uid] = DocumentData(doc=curr.doc, views=[])
                        for v in curr.views:
                            if v[0] == view:
                                keep[uid].views.append(v)
                                break
        self._docData = keep

    def getCanvas(self):
        view = self.getView()
        return view.canvas() if view else None

    def getQwin(self):
        win = self.getWin()
        return self.isAlive(win.qwindow(), QMainWindow) if win else None

    def getCentral(self):
        qwin = self.getQwin()
        return self.isAlive(qwin.centralWidget(), QWidget) if qwin else None

    def getMdi(self):
        cached = self.isAlive(self._cached.get("mdi", None), QMdiArea)
        if cached:
            return cached
        qwin = self.getQwin()
        self._cached["mdi"] = (
            self.isAlive(qwin.findChild(QMdiArea), QMdiArea) if qwin else None
        )
        return self._cached["mdi"]

    def getViewSubWindow(
        self, uid: int | None = None
    ) -> (QMdiSubWindow | None, View | None, dict[Any, Any] | None):
        subwin, view, data = None, None, None
        if isinstance(uid, int):
            win = self.getWin()
            mdi = self.getMdi()
            if mdi and win:

                subwin = next(
                    (
                        w
                        for w in mdi.subWindowList()
                        if w.property("uiTweaksId") == uid
                    ),
                    None,
                )

                for v in win.views():
                    d = self.getViewData(v)
                    if d and d.get("uiTweaksId") == uid:
                        view = v
                        data = d

        return (subwin, view, data)

    def getTabBar(self):
        cached = self.isAlive(self._cached.get("tabs", None), QTabBar)
        if cached:
            return cached
        central = self.getCentral()
        if central:
            for c in central.findChildren(QTabBar):
                obj = c.metaObject()
                if obj and obj.className() == "QTabBar":
                    self._cached["tabs"] = self.isAlive(c, QTabBar)
                    return self._cached["tabs"]

    def refreshWidget(
        self,
        widget: QWidget | None = None,
    ):
        if widget:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def paletteColor(self, key: str) -> QColor:
        role = getattr(QPalette.ColorRole, key, None)
        if role:
            return QApplication.palette().color(role)
        return QColor(0, 0, 0, 0)

    def settingColor(self, *args: str) -> QColor:
        try:
            app = self.getApp()
            if app:
                color = app.readSetting(*args)
                r, g, b = map(int, color.split(","))
                return QColor(r, g, b)
        except:
            return QColor(0, 0, 0, 0)

    def showToast(
        self, msg: str = "", icon: QIcon | None = None, ts: int = 2000
    ):
        view = self.getView()
        if view:
            if icon is None:
                icon = QIcon()
            view.showFloatingMessage(msg, icon, ts, 1)

    def hideToast(self):
        mdi = self.getMdi()
        if mdi:
            subwin = mdi.activeSubWindow()
            if subwin:
                for c in subwin.findChildren(QWidget):
                    if c.metaObject().className() == "KisFloatingMessage":
                        c.setVisible(False)

    def newAction(
        self,
        window: Window,
        name: str,
        description: str,
        callback: typing.Callable[..., Any],
        icon: QIcon | None = None,
        checkable: bool = False,
        menu: bool = False,
    ) -> QWidgetAction:
        if menu is True:
            action = window.createAction(name, description)
            _ = action.triggered.connect(callback)
        else:
            action = window.createAction(name, description, "")
            action.script = None  # pyright: ignore[reportAttributeAccessIssue]
            _ = action.triggered.connect(callback)
            action.setCheckable(checkable)

        if isinstance(icon, QIcon):
            action.setIcon(icon)
        else:
            path = os.path.join(os.path.dirname(__file__), name)
            if os.path.exists(path):
                icon = QIcon(path)
                action.setIcon(icon)
        return typing.cast(QWidgetAction, action)

    def isPrintSize(self, view: View) -> bool:
        # NOTE This is set in tools.py
        viewData = self.getViewData(view)
        return (
            viewData.get("printSize", False)
            if isinstance(viewData, dict)
            else False
        )

    def isScrolling(self) -> bool:
        return self._isScrolling

    def getScrollBars(
        self, win: QMdiSubWindow | None = None
    ) -> tuple[
        QScrollBar | None, QScrollBar | None, QAbstractScrollArea | None
    ]:
        bars = []
        if not win:
            mdi = self.getMdi()
            win = mdi.activeSubWindow() if mdi else None
        if win:
            scrollAreas = win.findChildren(QAbstractScrollArea)
            for sa in scrollAreas:
                if sa.objectName() == "" and isinstance(
                    sa, QAbstractScrollArea
                ):
                    hbar = sa.horizontalScrollBar()
                    vbar = sa.verticalScrollBar()
                    return (hbar, vbar, sa)
        return (None, None, None)

    def scrollOffset(
        self, win: QMdiSubWindow | None = None
    ) -> tuple[int | None, int | None]:
        if not win:
            mdi = self.getMdi()
            win = mdi.activeSubWindow() if mdi else None
        if win:
            scrollAreas = win.findChildren(QAbstractScrollArea)
            for sa in scrollAreas:
                if sa.objectName() == "" and type(sa) is QAbstractScrollArea:
                    hbar = sa.horizontalScrollBar()
                    vbar = sa.verticalScrollBar()
                    return (
                        hbar.value() if hbar else None,
                        vbar.value() if vbar else None,
                    )
        return (None, None)

    def scrollTo(
        self,
        win: QMdiSubWindow | None = None,
        x: int | None = None,
        y: int | None = None,
    ):
        if not win:
            mdi = self.getMdi()
            win = mdi.activeSubWindow() if mdi else None
        if win:
            self._isScrolling = True
            scrollAreas = win.findChildren(QAbstractScrollArea)
            for sa in scrollAreas:
                if sa.objectName() == "" and type(sa) is QAbstractScrollArea:
                    hbar = sa.horizontalScrollBar()
                    vbar = sa.verticalScrollBar()
                    if vbar and y is not None:
                        vbar.setValue(y)
                    if hbar and x is not None:
                        hbar.setValue(x)
            self._isScrolling = False

    def isZooming(self) -> bool:
        return self._isZooming

    def getZoomLevel(self, canvas: Canvas | None = None, raw: bool = False):
        app = self.getApp()
        qwin = self.getQwin()
        if not canvas:
            canvas = self.getCanvas()
            doc = self.getDoc()
        else:
            doc = canvas.view().document()

        if not (app and qwin and canvas and doc):
            return 1

        view = canvas.view()
        zoom = canvas.zoomLevel()
        res = 72
        dpi = doc.resolution()

        if self.isPrintSize(view):
            screen = qwin.screen()
            mm_per_inch = 25.4
            sw = screen.size().width()
            spw = screen.physicalSize().width()
            dpi = sw / spw * mm_per_inch
            val = math.ceil((zoom * res / dpi) * 1000) / 1000
            canvas.setZoomLevel(val)

        val = zoom * res / dpi

        if raw:
            return val

        # NOTE ceiling and truncating here
        # keeps the value aligned with what
        # Krita reports in the user interface
        return math.ceil(val * 1000) / 1000

    def setZoomLevel(
        self, canvas: Canvas | None = None, zoom: float | None = None
    ):
        if zoom is None:
            return
        if not canvas:
            canvas = self.getCanvas()
        if canvas:
            self._isZooming = True
            canvas.setZoomLevel(zoom)
            self._isZooming = False

    def canvasPosition(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        canvas: Canvas | None = None,
    ) -> CanvasPosition | None:
        if canvas:
            view = canvas.view()
        elif view:
            canvas = view.canvas()
        if not (view and canvas):
            return
        doc = view.document()
        imgRect = QRectF(0, 0, doc.width(), doc.height())
        flakeToCanvas = view.flakeToCanvasTransform()
        flakeToImg = view.flakeToImageTransform()
        imgToFlake = flakeToImg.inverted()[0]
        flakeRect = imgToFlake.mapRect(imgRect)
        bbox = flakeToCanvas.mapRect(flakeRect)
        flakeRect = flakeRect.toRect()
        scroll = self.scrollOffset(win)
        sx = scroll[0] if isinstance(scroll[0], int) else 0
        sy = scroll[1] if isinstance(scroll[1], int) else 0
        viewRect = win.contentsRect()
        viewRect.moveTo(0, 0)
        return CanvasPosition(
            # the unrotated image
            rect=QRect(
                -sx,
                -sy,
                flakeRect.width(),
                flakeRect.height(),
            ),
            # the bounding box of the rotated img
            bbox=bbox.toRect(),
            zoom=self.getZoomLevel(canvas, raw=True),
            viewport=viewRect,
        )

    def centerCanvas(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        canvas: Canvas | None = None,
        axis: typing.Literal["x", "y"] | None = None,
        centerY: int | None = None,
        centerX: int | None = None,
        intersected: bool = False,
    ):
        if not win:
            return

        if win:
            pos = self.canvasPosition(win=win, canvas=canvas, view=view)
            if pos:
                rect = pos.bbox
                splitRect = pos.viewport

                if intersected:
                    rect = splitRect.intersected(rect)

                rectCenter = rect.center()
                if centerY is None:
                    centerY = rectCenter.y()

                if centerX is None:
                    centerX = rectCenter.x()

                c = splitRect.center()
                c = QPoint(int(c.x()), int(c.y()))
                if axis == "x":
                    rect.moveCenter(QPoint(c.x(), int(centerY)))
                elif axis == "y":
                    rect.moveCenter(QPoint(int(centerX), c.y()))
                else:
                    rect.moveCenter(c)
                self.scrollTo(win=win, x=-int(rect.x()), y=-int(rect.y()))

    def zoomToFit(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        canvas: Canvas | None = None,
        zoomMax: float = math.inf,
        axis: typing.Literal["x", "y"] | None = None,
        keepScroll: bool = False,
        bbox: bool = True,
    ):
        if not win:
            return

        if canvas:
            view = canvas.view()
        elif view:
            canvas = view.canvas()

        pos = self.canvasPosition(win=win, view=view, canvas=canvas)

        if pos:
            x, y = self.scrollOffset(win)
            useRect = pos.bbox if bbox else pos.rect
            splitRect = pos.viewport
            _, _, cw, ch = useRect.getRect()
            _, _, vw, vh = splitRect.getRect()
            if vw == 0 or vh == 0:
                return
            sx = float(cw) / float(vw)
            sy = float(ch) / float(vh)
            if axis == "x":
                s = sx
            elif axis == "y":
                s = sy
            else:
                s = max(sx, sy)
            self.setZoomLevel(canvas, min(zoomMax, float(pos.zoom * (1 / s))))
            if keepScroll:
                if axis == "x":
                    self.scrollTo(win, None, y)
                elif axis == "y":
                    self.scrollTo(win, x, None)
                else:
                    self.scrollTo(win, x, y)
            else:
                if axis == "x":
                    self.centerCanvas(
                        win=win,
                        canvas=canvas,
                        view=view,
                        axis=axis,
                        centerY=splitRect.center().y(),
                    )
                elif axis == "y":
                    self.centerCanvas(
                        win=win,
                        canvas=canvas,
                        view=view,
                        axis=axis,
                        centerX=splitRect.center().x(),
                    )
                else:
                    self.centerCanvas(win=win, canvas=canvas, view=view)

    def zoomToFitWidth(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        canvas: Canvas | None = None,
    ):
        self.zoomToFit(win=win, view=view, canvas=canvas, axis="x")

    def zoomToFitHeight(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        canvas: Canvas | None = None,
    ):
        pos = self.canvasPosition(win=win, view=view)
        self.zoomToFit(win=win, view=view, canvas=canvas, axis="y")

    def scaleTo(
        self,
        win: QMdiSubWindow,
        view: View,
        oldPos: CanvasPosition,
        newPos: CanvasPosition,
        contain: bool = False,
        mode: "SCALING_MODE | None" = None,
        splitPane=None
    ):

        from .split_pane.split_helpers import log as dbgLog
        from .options import (
            getOpt,
        )
        def getPos(pos: CanvasPosition | None = None, win=win, view=view):
            if pos is None:
                pos = self.canvasPosition(win=win, view=view)
            assert pos is not None

            r = QRectF(pos.bbox)
            v = QRectF(pos.viewport)
            rc = r.center()
            vc = v.center()

            return SimpleNamespace(
                z=pos.zoom,
                r=r,
                v=v,
                rc=rc,
                vc=vc,
                vw=v.width(),
                vh=v.height(),
                cx=r.x(),
                cy=r.y(),
                cw=r.width(),
                ch=r.height(),
                ocw=pos.rect.width(),  # the real width not the bbox
                och=pos.rect.height(),  # the real height not the bbox
            )

        canvas = view.canvas()
        pos = getPos(oldPos)
        nw = newPos.viewport.width()
        nh = newPos.viewport.height()
        deltaX = nw - pos.vw
        deltaY = nh - pos.vh
        containDelta = 1.5

        if 0 in (pos.vw, pos.vh, nw, nh):
            return

        if deltaX != 0 and deltaY != 0:
            if nw <= nh:
                deltaY = 0
            else:
                deltaX = 0

        if getOpt("resize", "scaling_contained_only") and not pos.v.contains(
            pos.r
        ):
            return
            
        if getOpt("resize", "scaling_contained_partial") and not (
            pos.vw >= pos.cw and pos.vh >= pos.ch
        ):
            return

        if getOpt("resize", "scaling_contained_shorter") and not (
            pos.vw >= pos.cw or pos.vh >= pos.ch
        ):
            return

        if mode == "anchored":
            if deltaX != 0:
                scale = nw / pos.vw
                self.setZoomLevel(canvas, scale * pos.z)
                newPos = getPos()
                sy = pos.rc.y() - (newPos.ch * 0.5)
                sx = scale * pos.cx
                self.scrollTo(win, int(-sx), int(-sy))
                pass

            if deltaY != 0:
                scale = nh / pos.vh
                self.setZoomLevel(canvas, scale * pos.z)
                newPos = getPos()
                sx = pos.rc.x() - (newPos.cw * 0.5)
                sy = scale * pos.cy
                self.scrollTo(win, int(-sx), int(-sy))
                pass

        elif mode in ("contained", "expanded"):
            contain = mode == "contained"
            if deltaX < 0:
                containDelta = 1 / containDelta
                containWidth = pos.vw * containDelta
                intersect = pos.r.intersected(pos.v)
                iw = intersect.width()

                if containWidth > iw:
                    sw = iw / pos.vw
                    containWidth = iw * sw if sw > 0.5 else iw * (1 - sw)

                containHeight = pos.ch * (containWidth / pos.cw)

                if containHeight > pos.vh:
                    containWidth = pos.cw * (pos.vh / pos.ch)

                if nw <= containWidth:
                    containWidth = nw

                delta = abs(deltaX)
                deltaMax = abs(containWidth - pos.vw)
                scale = delta / deltaMax

                containZoom = pos.z * (containWidth / pos.cw)
                currZoom = pos.z + (scale * (containZoom - pos.z))
                self.setZoomLevel(canvas, currZoom)

                newPos = getPos()
                originCenter = pos.rc
                coversHeight = pos.cy <= 0 and pos.cy + pos.ch >= pos.vh
                containCenter = QPointF(
                    containWidth * 0.5,
                    pos.vc.y() if coversHeight else pos.rc.y(),
                )
                currCenter = originCenter + (
                    scale * (containCenter - originCenter)
                )

                sy = currCenter.y() - (newPos.ch * 0.5)
                sx = currCenter.x() - (newPos.cw * 0.5)
                self.scrollTo(win, int(-sx), int(-sy))

            if deltaX > 0:
                containWidth = pos.vw * containDelta

                if pos.cx + pos.cw > containWidth:
                    containWidth = (pos.cx + pos.cw) * containDelta

                if contain and containWidth < pos.cw:
                    containWidth = pos.cw

                containHeight = False
                if contain:
                    testHeight = pos.ch * (containWidth / pos.cw)
                    containHeight = testHeight > pos.vh
                    if containHeight:
                        containWidth = max(pos.cw, pos.vw * containDelta)

                delta = abs(deltaX)
                deltaMax = abs(containWidth - pos.vw)
                scale = delta / deltaMax

                if scale >= 1:
                    if containHeight or (contain and nh >= pos.vh):
                        self.zoomToFit(win=win, view=view)
                    else:
                        self.zoomToFitWidth(win=win, view=view)
                        if contain and getPos().nh >= pos.vh:
                            self.zoomToFit(win=win, view=view)
                            
                    self.centerCanvas(win=win, view=view)
                else:
                    containZoom = pos.z * (
                        (pos.vh / pos.ch)
                        if containHeight
                        else (containWidth / pos.cw)
                    )
                    currZoom = pos.z + (scale * (containZoom - pos.z))
                    self.setZoomLevel(canvas, currZoom)

                    newPos = getPos()
                    originCenter = pos.rc
                    containCenter = QPointF(containWidth * 0.5, pos.vc.y())
                    currCenter = originCenter + (
                        scale * (containCenter - originCenter)
                    )

                    sy = currCenter.y() - (newPos.ch * 0.5)
                    sx = currCenter.x() - (newPos.cw * 0.5)
                    self.scrollTo(win, int(-sx), int(-sy))

            if deltaY < 0:
                containDelta = 1 / containDelta
                containHeight = pos.vh * containDelta
                intersect = pos.r.intersected(pos.v)
                ih = intersect.height()

                if containHeight > ih:
                    sh = ih / pos.vh
                    containHeight = ih * sh if sh > 0.5 else ih * (1 - sh)

                containWidth = pos.cw * (containHeight / pos.ch)

                if containWidth > pos.vw:
                    containHeight = pos.ch * (pos.vw / pos.cw)

                if nh <= containHeight:
                    containHeight = nh

                delta = abs(deltaY)
                deltaMax = abs(containHeight - pos.vh)
                scale = delta / deltaMax

                containZoom = pos.z * (containHeight / pos.ch)
                currZoom = pos.z + (scale * (containZoom - pos.z))
                self.setZoomLevel(canvas, currZoom)

                newPos = getPos()
                originCenter = pos.rc
                coversWidth = pos.cx <= 0 and pos.cx + pos.cw >= pos.vw
                containCenter = QPointF(
                    pos.vc.x() if coversWidth else pos.rc.x(),
                    containHeight * 0.5,
                )
                currCenter = originCenter + (
                    scale * (containCenter - originCenter)
                )

                sx = currCenter.x() - (newPos.cw * 0.5)
                sy = currCenter.y() - (newPos.ch * 0.5)
                self.scrollTo(win, int(-sx), int(-sy))

            if deltaY > 0:
                containHeight = pos.vh * containDelta

                if pos.cy + pos.ch > containHeight:
                    containHeight = (pos.cy + pos.ch) * containDelta

                if contain and containHeight < pos.ch:
                    containHeight = pos.ch

                containWidth = False
                if contain:
                    testWidth = pos.cw * (containHeight / pos.ch)
                    containWidth = testWidth > pos.vw
                    if containWidth:
                        containHeight = max(pos.ch, pos.vh * containDelta)

                delta = abs(deltaY)
                deltaMax = abs(containHeight - pos.vh)
                scale = delta / deltaMax

                if scale >= 1:
                    if containWidth or (contain and nw >= pos.vw):
                        self.zoomToFit(win=win, view=view)
                    else:
                        self.zoomToFitHeight(win=win, view=view)
                        if contain and getPos().nw >= pos.vw:
                            self.zoomToFit(win=win, view=view)
                            
                    self.centerCanvas(win=win, view=view)
                else:
                    containZoom = pos.z * (
                        (pos.vw / pos.cw)
                        if containWidth
                        else (containHeight / pos.ch)
                    )
                    currZoom = pos.z + (scale * (containZoom - pos.z))
                    self.setZoomLevel(canvas, currZoom)

                    newPos = getPos()
                    originCenter = pos.rc
                    containCenter = QPointF(pos.vc.x(), containHeight * 0.5)
                    currCenter = originCenter + (
                        scale * (containCenter - originCenter)
                    )

                    sx = currCenter.x() - (newPos.cw * 0.5)
                    sy = currCenter.y() - (newPos.ch * 0.5)
                    self.scrollTo(win, int(-sx), int(-sy))

