# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    pyqtBoundSignal,
    sip,
    QWidgetAction,
    QColor,
    QIcon,
    QMainWindow,
    QApplication,
    QMdiArea,
    QMessageBox,
    QAbstractScrollArea,
    QTabBar,
    QWidget,
    QUuid,
    QPalette,
    QObject,
    QTimer,
    QStackedWidget,
    QLineEdit,
)

from krita import Krita, Window, Document, View, Notifier

from dataclasses import dataclass
from itertools import count
from typing import Any, Type, TypeVar

import typing
import math
import os

T = TypeVar("T", bound=QObject)


@dataclass
class DocumentData:
    doc: dict[str, Any]
    views: list[tuple[View, dict[Any, Any]]]


class Helper:

    def __init__(self, qwin: QMainWindow):
        self._uid = count(1)
        self._qwin: QMainWindow = qwin
        self._toastEnableTimer: QTimer | None = None
        self._docData: dict[QUuid, DocumentData] = {}
        self._cached: dict[str, Any] = {}
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
        cached = self.isAlive(self._cached.get('mdi', None), QMdiArea)
        if cached:
            return cached
        qwin = self.getQwin()
        self._cached['mdi'] = self.isAlive(qwin.findChild(QMdiArea), QMdiArea) if qwin else None
        return self._cached['mdi']

    def getTabBar(self):
        cached = self.isAlive(self._cached.get('tabs', None), QTabBar)
        if cached:
            return cached
        central = self.getCentral()
        if central:
            for c in central.findChildren(QTabBar):
                obj = c.metaObject()
                if obj and obj.className() == "QTabBar":
                    self._cached['tabs'] = self.isAlive(c, QTabBar)
                    return self._cached['tabs']

    def refreshWidget(self, widget: QWidget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def paletteColor(self, key: str) -> QColor:
        role = getattr(QPalette.ColorRole, key, None)
        if role:
            return QApplication.palette().color(role)
        return QColor(0, 0, 0, 0)

    def showToast(
        self, msg: str = "", icon: QIcon | None = None, ts: int = 2000
    ):
        view = self.getView()
        if view:
            if icon is None:
                icon = QIcon()
            view.showFloatingMessage(msg, icon, ts, 1)

    def disableToast(self):
        mdi = self.getMdi()
        if self._toastEnableTimer:
            self._toastEnableTimer.stop()
            self._toastEnableTimer = None
        if mdi:
            mdi.setProperty("toasts", "hidden")

    def enableToast(self):
        if not self._toastEnableTimer:

            def cb():
                mdi = self.getMdi()
                if mdi:
                    mdi.setProperty("toasts", "visible")
                self._toastEnableTimer = None

            t = QTimer()
            t.setSingleShot(True)
            t.timeout.connect(cb)
            t.start(50)
            self._toastEnableTimer = t

    def showMsg(self, title: str = "", msg: str = ""):
        if len(msg) == 0:
            _ = QMessageBox.information(None, "", title)
        else:
            _ = QMessageBox.information(None, title, msg)

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

    def scrollOffset(self) -> tuple[int | None, int | None]:
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

    def scrollTo(self, x: int | None = None, y: int | None = None):
        mdi = self.getMdi()
        win = mdi.activeSubWindow() if mdi else None
        if win:
            scrollAreas = win.findChildren(QAbstractScrollArea)
            for sa in scrollAreas:
                if sa.objectName() == "" and type(sa) is QAbstractScrollArea:
                    hbar = sa.horizontalScrollBar()
                    vbar = sa.verticalScrollBar()
                    if vbar and y is not None:
                        vbar.setValue(y)
                    if hbar and x is not None:
                        hbar.setValue(x)

    def getZoomLevel(self, raw: bool = False):
        app = self.getApp()
        qwin = self.getQwin()
        canvas = self.getCanvas()
        doc = self.getDoc()

        if not (app and qwin and canvas and doc):
            return 1

        action = app.action("view_print_size")
        isPrintSize = action.isChecked() if action else False
        zoom = canvas.zoomLevel()
        res = 72
        dpi = doc.resolution()

        if isPrintSize:
            screen = qwin.screen()
            mm_per_inch = 25.4
            sw = screen.size().width()
            spw = screen.physicalSize().width()
            dpi = sw / spw * mm_per_inch

        val = zoom * res / dpi

        if raw:
            return val

        # NOTE ceiling and truncating here
        # keeps the value aligned with what
        # Krita reports in the user interface
        # and is the value to use when doing
        # setZoomLevel(getZoomLevel())
        return math.ceil(val * 1000) / 1000

    def setZoomLevel(self, z: float):
        canvas = self.getCanvas()
        if canvas:
            canvas.setZoomLevel(z)

