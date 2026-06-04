# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    pyqtBoundSignal,
    sip,
    Qt,
    QScrollBar,
    QAbstractScrollArea,
    QApplication,
    QColor,
    QIcon,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QObject,
    QPalette,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QLineF,
    QTabBar,
    QTimer,
    QUuid,
    QWidget,
    QWidgetAction,
    QModelIndex,
    QItemSelectionModel,
    QTreeView,
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
import re

from .i18n import i18n

if TYPE_CHECKING:
    from .plugin import Plugin
    from .component import Component

T = TypeVar("T", bound=QObject)

COMPONENT_GROUP = dict[
    typing.Literal["tools", "splitPane", "dockers", "helper"], "Component|None"
]


@dataclass
class CanvasPosition:
    rect: QRect
    bbox: QRect
    viewport: QRect


@dataclass
class DocumentData:
    doc: dict[str, Any]
    views: list[tuple[View, dict[Any, Any]]]


class Helper:

    def __init__(
        self,
        window,
        plugin: "Plugin",
        pluginGroup: COMPONENT_GROUP | None = None,
    ):
        qwin = window.qwindow()

        self._plugin = plugin
        self._version = None
        self._componentGroup: COMPONENT_GROUP | None = pluginGroup
        self._qwin: QMainWindow = qwin
        self._cached: dict[str, Any] = {}
        self._docData: dict[QUuid, DocumentData] = {}

        self._debounceTimer: QTimer = QTimer()
        self._debounceTimer.timeout.connect(self.runDebounceCallbacks)
        self._debounceCheckTime: float = time.monotonic()
        self._debounceCallbacks: dict[
            str, tuple[typing.Callable[..., Any], float, float]
        ] = {}

        def cb():
            self.debounceCallback(
                "refreshDocData", self.refreshDocData, timeout_seconds=2
            )

        typing.cast(pyqtBoundSignal, self.getNotifier().viewClosed).connect(cb)

    def version(self) -> float:
        if self._version is not None:
            return self._version

        version = self.getApp().version()
        num = re.search(r"^(\d+)\.(\d+)", version)

        if num:
            major = int(num.group(1))
            minor = int(num.group(2))
            self._version = float(f"{major}.{minor}")
        else:
            self._version = 0

        return self._version

    def getScriptDir(self):
        return os.path.dirname(os.path.abspath(__file__))

    def getIconPath(self, name):
        return os.path.join(self.getScriptDir(), "icons", name)

    def uid(self):
        return self._plugin.uid()

    def isAlive(self, obj: Any, cls: Type[T]) -> T | None:
        if isinstance(obj, cls) and not sip.isdeleted(typing.cast(Any, obj)):
            return obj
        return None

    def runDebounceCallbacks(self):
        now = time.monotonic()
        removeKeys = []
        runCallbacks = []
        for k in list(self._debounceCallbacks.keys()):
            v = self._debounceCallbacks.get(k, None)
            if v and now - v[1] >= v[2]:
                runCallbacks.append(v[0])
                removeKeys.append(k)

        for k in removeKeys:
            if k in self._debounceCallbacks:
                del self._debounceCallbacks[k]

        for cb in runCallbacks:
            cb()

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

    def getApp(self) -> Krita:
        return Krita.instance()

    def getNotifier(self) -> Notifier:
        return self.getApp().notifier()

    def getWin(self) -> Window | None:
        for w in self.getApp().windows():
            if w.qwindow() == self._qwin:
                return w

    def isActiveWin(self):
        win = self.getApp().activeWindow()
        return win and win.qwindow() == self._qwin

    def getQwin(self):
        win = self.getWin()
        return self.isAlive(win.qwindow(), QMainWindow) if win else None

    def focusQwin(self, qwin: QMainWindow | None = None):
        if qwin is None:
            qwin = self.getQwin()
        if qwin is None:
            return
        if qwin.isMinimized():
            qwin.showNormal()
        qwin.show()
        qwin.raise_()
        qwin.activateWindow()

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

    def getDefaultTabBar(self):
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

    def getSubWinById(self, uid: int | None) -> QMdiSubWindow | None:
        if uid is None:
            return
        mdi = self.getMdi()
        if mdi:
            for sw in mdi.subWindowList():
                if sw.property("uiTweaksId") == uid:
                    return sw

    def getSubWinByView(self, view: View | None) -> QMdiSubWindow | None:
        if view is None:
            return
        return self.getSubWinById(self.getViewId(view))

    def getDoc(self):
        view = self.getView()
        return self.isAlive(view.document(), Document) if view else None

    def getDocData(self, doc: Document | None) -> DocumentData | None:
        if isinstance(doc, Document):
            uid = doc.rootNode().uniqueId()
            if uid not in self._docData:
                self._docData[uid] = DocumentData(doc={}, views=[])
            return self._docData.get(uid, None)

    def compareDoc(self, a: Document | None, b: Document | None) -> bool:
        if a and b:
            return a.rootNode().uniqueId() == b.rootNode().uniqueId()
        return False

    def getDocViews(
        self, win: Window | None = None
    ) -> dict[str, SimpleNamespace]:
        docs: dict[str, SimpleNamespace] = {}
        obj = self.getApp() if win is None else win
        for view in obj.views():
            doc = view.document()
            uid = doc.rootNode().uniqueId().toString()
            if uid in docs:
                docs[uid].views.append(view)
            else:
                docs[uid] = SimpleNamespace(doc=doc, views=[view])
        return docs

    def getDocsByFile(
        self, win: Window | None = None
    ) -> dict[str, SimpleNamespace]:
        obj = self.getApp() if win is None else win
        viewCounts = self.getDocViews(obj)

        docs: dict[str, SimpleNamespace] = {}
        for i, (k, v) in enumerate(viewCounts.items()):
            path = v.doc.fileName()
            if path and os.path.exists(path):
                if path in docs:
                    if len(docs[path].views) < len(v.views):
                        docs[path] = v
                else:
                    docs[path] = v

        return docs

    def getView(self) -> View | None:
        win = self.getWin()
        return self.isAlive(win.activeView(), View) if win else None

    def getViewId(self, view) -> View | None:
        data = self.getViewData(view)
        if data:
            return data.get("uiTweaksId")

    def getViewById(self, uid: int | None) -> View | None:
        if uid is None:
            return
        win = self.getWin()
        if win:
            for v in win.views():
                if self.getViewId(v) == uid:
                    return v

    def getViewBySubWin(self, sw) -> View | None:
        if isinstance(sw, QMdiSubWindow):
            return self.getViewById(sw.property("uiTweaksId"))

    def getViewData(self, view: View | None) -> dict[Any, Any] | None:
        if not view:
            return

        data = self.getDocData(view.document())

        if data is None:
            return

        for v in data.views:
            if v[0] == view:
                return v[1]

        v: tuple[View, dict[Any, Any]] = (view, {})
        data.views.append(v)
        return v[1]

    def setViewData(self, view: View | None, key: Any, val: Any):
        data = self.getViewData(view)
        if data is not None:
            data[key] = val

    def refreshDocData(self):
        # TODO test this
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

    def getWidgetByClass(self, parent, kind, cls):
        if self.isAlive(parent, QWidget):
            children = parent.findChildren(kind)
            for c in children:
                if (
                    self.isAlive(c, QWidget)
                    and c.metaObject().className() == cls
                ):
                    return c

    def getWidgetsByClass(self, parent, kind, cls):
        widgets = []
        if self.isAlive(parent, QWidget):
            children = parent.findChildren(kind)
            for c in children:
                if (
                    self.isAlive(c, QWidget)
                    and c.metaObject().className() == cls
                ):
                    widgets.append(c)
        return widgets

    def getDockerByName(self, name):
        if not self.isAlive(self._cached.get(name, None), QWidget):
            app = self.getApp()
            self._cached[name] = next(
                (d for d in app.dockers() if d.objectName() == name), None
            )
        return self.isAlive(self._cached.get(name, None), QWidget)

    def paletteColor(self, key: str, widget: QWidget | None = None) -> QColor:
        role = getattr(QPalette.ColorRole, key, None)
        if role:
            if widget:
                return widget.palette().color(role)
            else:
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

    def useDarkIcons(self) -> bool:
        bg = self.paletteColor("Window")
        return bg.value() > 100

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
            action.script = None
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

    def canvasScrollArea(
        self, win: QMdiSubWindow | None = None
    ) -> QAbstractScrollArea | None:
        if not win:
            mdi = self.getMdi()
            win = mdi.activeSubWindow() if mdi else None
        return self.getWidgetByClass(
            win, QAbstractScrollArea, "KisCanvasController"
        )

    def canvasScrollBars(
        self, win: QMdiSubWindow | None = None
    ) -> tuple[QScrollBar | None, QScrollBar | None]:
        sa = self.canvasScrollArea(win)
        return (
            (sa.horizontalScrollBar(), sa.verticalScrollBar())
            if sa is not None
            else (None, None)
        )

    def canvasScrollOffset(
        self, win: QMdiSubWindow | None = None
    ) -> tuple[int | None, int | None]:
        sa = self.canvasScrollArea(win)
        if sa is not None:
            hbar = sa.horizontalScrollBar()
            vbar = sa.verticalScrollBar()
            return (
                hbar.value() if hbar else None,
                vbar.value() if vbar else None,
            )
        return (None, None)

    def canvasScrollTo(
        self,
        win: QMdiSubWindow | None = None,
        x: int | None = None,
        y: int | None = None,
    ):
        sa = self.canvasScrollArea(win)
        if sa is not None:
            hbar = sa.horizontalScrollBar()
            vbar = sa.verticalScrollBar()
            if vbar and y is not None:
                vbar.setValue(y)
            if hbar and x is not None:
                hbar.setValue(x)

    def canvasPosition(
        self, win: QMdiSubWindow | None = None, view: View | None = None
    ) -> CanvasPosition | None:
        if win is None:
            mdi = self.getMdi()
            win = mdi.activeSubWindow() if mdi else None

        if view is None:
            view = self.getViewBySubWin(win)

        if view is None or win is None:
            return

        canvas = view.canvas()
        doc = view.document()
        imgRect = QRectF(0, 0, doc.width(), doc.height())
        flakeToCanvas = view.flakeToCanvasTransform()
        flakeToImg = view.flakeToImageTransform()
        imgToFlake = flakeToImg.inverted()[0]
        flakeRect = imgToFlake.mapRect(imgRect)
        bbox = flakeToCanvas.mapRect(flakeRect)
        flakeRect = flakeRect.toRect()
        scroll = self.canvasScrollOffset(win)
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
            viewport=viewRect,
        )

    def centerCanvas(
        self,
        win: QMdiSubWindow,
        view: View | None = None,
        epsilon: int | None = None,
    ):
        if win:
            pos = self.canvasPosition(win=win, view=view)
            if pos:
                rect = pos.bbox
                c = QPointF(pos.viewport.center())

                # consider it already centered
                rc = QPointF(rect.center())
                if epsilon and QLineF(rc, c).length() < epsilon:
                    return

                c = QPoint(int(c.x()), int(c.y()))
                rect.moveCenter(c)
                self.canvasScrollTo(
                    win=win, x=-int(rect.x()), y=-int(rect.y())
                )
