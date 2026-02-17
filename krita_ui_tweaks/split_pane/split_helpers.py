# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    Qt,
    toPoint,
    getEventGlobalPos,
    QApplication,
    QRect,
    QPoint,
    QObject,
    QEvent,
    QMdiSubWindow,
    QTimer,
    QMessageBox,
    QProgressDialog,
    QNetworkAccessManager,
    QNetworkRequest,
    QNetworkReply,
    QMenu,
    QUrl,
)

from krita import Krita, View
from dataclasses import dataclass
from typing import Any, TypedDict, TYPE_CHECKING

import typing
import os
import tempfile

from ..helper import CanvasPosition, Helper
from ..i18n import i18n

if TYPE_CHECKING:
    from .split import Split
    from .split_handle import SplitHandle
    from .split_pane import SplitPane
    from .split_tabs import SplitTabs
    from .split_toolbar import SplitToolbar

NUMBER = int | float


class CollapsedLayout(TypedDict):
    state: typing.Literal["c"]
    files: list[str]
    active: str | None
    splitSize: int


class SplitLayout(TypedDict):
    state: typing.Literal["v", "h"]
    first: "SplitLayout | CollapsedLayout | None"
    second: "SplitLayout | CollapsedLayout | None"
    splitSize: int


class SavedLayout(TypedDict):
    state: typing.Literal["s"]
    winWidth: int
    winHeight: int
    layout: "SplitLayout | CollapsedLayout | None"
    path: str | None
    locked: bool


DRAG_VERTICAL_THRESHOLD = 40
DRAG_ANGLE_THRESHOLD = 45

QMDI_WIN_MIN_SIZE = 80
SPLIT_MIN_SIZE = QMDI_WIN_MIN_SIZE + 20


@dataclass
class FitViewState:
    fitToView: bool
    fitToHeight: bool
    fitToWidth: bool
    outOfView: bool


@dataclass
class MenuAction:
    text: str | None = None
    callback: typing.Callable[..., Any] | None = None
    separator: bool = False
    enabled: bool = True
    visible: bool = True
    menu: QMenu | None = None


@dataclass
class SplitData:
    view: View
    win: QMdiSubWindow
    toolbar: "SplitToolbar | None"
    custom: dict[Any, Any]


def almostEqual(a: NUMBER, b: NUMBER, eps: NUMBER = 1) -> bool:
    return abs(a - b) <= eps


def almostEqualPos(a: QPoint, b: QPoint, eps: NUMBER = 1) -> bool:
    return almostEqual(a.x(), b.x()) and almostEqual(a.y(), b.y())


def dbg(split: "Split", msg: Any, clear: bool = False):
    if split == split._controller.defaultSplit():
        split._controller.debugMsg(msg, clear)


def log(msg):
    ki = Krita.instance()
    ki._log = getattr(ki, "_log", [])
    ki._log.append(msg)
    ki._printlog = lambda log=ki._log: list(map(print, log))


class EventInterceptor(QObject):
    def __init__(
        self,
        callbacks: dict[str, typing.Callable[..., Any]],
    ):
        super().__init__()
        self._callbacks = callbacks

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        t = event.type()
        if t == QEvent.Type.Close:
            cb = self._callbacks.get("destroyed", None)
            if cb:
                obj.destroyed.connect(cb)
        elif t == QEvent.Type.Resize:
            cb = self._callbacks.get("resized", None)
            if cb:
                cb()

        return False


# Some hacks from 5.3+ beta
# Detecting canvas scroll has become much harder
class ScrollInterceptor(QObject):
    def __init__(
        self,
        helper: "Helper",
    ):
        super().__init__()
        self._helper = helper
        self._btns = {
            Qt.MouseButton.MiddleButton: False,
            Qt.MouseButton.RightButton: False,
        }
        self._uidBtn = {}
        self._keys = {}

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # TODO can write this better, but for now just need to get it working again

        t = event.type()

        if t not in (
            QEvent.Type.Wheel,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.TabletMove,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
        ):
            return False

        helper = self._helper
        if not helper.isActiveWin():
            return False

        mdi = helper.getMdi()
        sw = mdi.activeSubWindow() if mdi else None

        if not sw:
            return False

        qwin = helper.getQwin()
        splitPane = self._helper._componentGroup["splitPane"]
        cls = obj.metaObject().className()
        uid = sw.property("uiTweaksId")

        if t == QEvent.Type.KeyPress:
            self._keys[event.key()] = f"{self._helper.scrollOffset(sw)}"
            return False

        if t == QEvent.Type.KeyRelease:
            k = event.key()
            s = self._keys.get(k)
            uid = sw.property("uiTweaksId")
            if s:
                del self._keys[k]
                if s != f"{self._helper.scrollOffset(sw)}":
                    splitPane.onSubWindowScrolled(uid)
            return False

        if cls == "QWidgetWindow":
            if t == QEvent.Type.TabletMove:
                buttons = event.buttons()
                middleWasDown = self._btns[Qt.MouseButton.MiddleButton]
                rightWasDown = self._btns[Qt.MouseButton.RightButton]
                middle = buttons & Qt.MouseButton.MiddleButton
                right = buttons & Qt.MouseButton.RightButton
                self._btns[Qt.MouseButton.MiddleButton] = middle
                self._btns[Qt.MouseButton.RightButton] = right
                s = f"{self._helper.scrollOffset(sw)}"

                if middle and not middleWasDown:
                    sw.setProperty("scrollInterceptorMiddle", s)
                elif right and not rightWasDown:
                    sw.setProperty("scrollInterceptorRight", s)
                elif not middle and middleWasDown:
                    m = sw.property("scrollInterceptorMiddle")
                    sw.setProperty("scrollInterceptorMiddle", None)
                    if m and m != s:
                        splitPane.onSubWindowScrolled(uid)
                elif not right and rightWasDown:
                    r = sw.property("scrollInterceptorRight")
                    sw.setProperty("scrollInterceptorRight", None)
                    if r and r != s:
                        splitPane.onSubWindowScrolled(uid)

        elif cls == "KisOpenGLCanvas2":
            if t == QEvent.Type.Wheel:
                def cb(uid=uid, obj=obj, sw=sw):
                    if helper.isChildOfSubWindow(obj, sw):
                        splitPane.onSubWindowScrolled(uid)
                self._helper.debounceCallback(
                    f"canvasWheel{uid}", cb, timeout_seconds=0.5
                )
                    
            elif t == QEvent.Type.MouseButtonPress:
                self._uidBtn = { uid: f"{self._helper.scrollOffset(sw)}" }

            elif t == QEvent.Type.MouseButtonRelease:
                s = self._uidBtn.get(uid) 
                if s:
                    self._uidBtn = {}
                    if s != f"{self._helper.scrollOffset(sw)}":
                        splitPane.onSubWindowScrolled(uid)

        return False


class KeyModiferInterceptor(QObject):
    def __init__(self):
        super().__init__()
        self.ctrlDown: bool = False

    def eventFilter(self, obj: QObject, event: QEvent):
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Control
        ):
            self.ctrlDown = True

        elif (
            event.type() == QEvent.Type.KeyRelease
            and event.key() == Qt.Key.Key_Control
        ):
            self.ctrlDown = False

        return False


def getLayoutFiles(
    layout: "SavedLayout | CollapsedLayout | SplitLayout | None",
) -> tuple[list[str], list[str]]:
    exists = []
    missing = []

    if not layout:
        return exists, missing

    try:
        state = layout.get("state", None)
        if state == "s":
            layout = typing.cast(SavedLayout, layout)
            exists, missing = getLayoutFiles(layout["layout"])
        elif state == "c":
            layout = typing.cast(CollapsedLayout, layout)
            for f in layout["files"]:
                if os.path.exists(f):
                    exists.append(f)
                else:
                    missing.append(f)
        elif state in ("v", "h"):
            layout = typing.cast(SplitLayout, layout)
            exists_first, missing_first = getLayoutFiles(layout["first"])
            exists_second, missing_second = getLayoutFiles(layout["second"])
            exists = list(set(exists_first + exists_second))
            missing = list(set(missing_first + missing_second))
    except:
        exists = []
        missing = []

    return exists, missing


DownloadCallback = typing.Callable[[bool, str | None, QUrl, str | None], None]


class Downloader:

    def __init__(self, callback: DownloadCallback):
        self._callback: DownloadCallback = callback
        self._net: QNetworkAccessManager = QNetworkAccessManager()
        self._queue: list[QUrl] = []
        self._currReply: QNetworkReply | None = None
        self._dialog: QProgressDialog | None = None

    def download(self, urls: QUrl | str | list[QUrl | str]):
        if not isinstance(urls, (list, tuple)):
            urls = [urls]

        for u in urls:
            if isinstance(u, str):
                u = QUrl(u)
            self._queue.append(u)

        if not self._currReply:
            self._startNext()

    def abort(self):
        self._queue.clear()

        if self._currReply:
            self._currReply.abort()

    def _startNext(self):
        if not self._queue:
            return

        url = self._queue.pop(0)
        request = QNetworkRequest(url)
        reply = self._net.get(request)

        self._currReply = reply

        if not self._dialog:
            self._dialog = QProgressDialog(
                i18n("Downloading"), i18n("Cancel"), 0, 100
            )
            self._dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._dialog.canceled.connect(self.abort)

        self._dialog.setLabelText(i18n("Downloading") + f" {url.fileName()}")
        self._dialog.setValue(0)
        self._dialog.setMaximum(100)
        self._dialog.show()

        reply.downloadProgress.connect(self._onProgress)
        reply.finished.connect(lambda r=reply, u=url: self._onFinished(r, u))

    def _onProgress(self, received, total):
        if total > 0 and self._dialog:
            self._dialog.setMaximum(total)
            self._dialog.setValue(received)

    def _onFinished(self, reply, url):
        if self._dialog:
            self._dialog.close()
            self._dialog = None

        err = reply.error()
        if err == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            suffix = os.path.splitext(url.fileName())[1]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            with open(tmp.name, "wb") as f:
                f.write(bytes(data))

            self._callback(True, tmp.name, url, None)
        else:
            self._callback(False, None, url, reply.errorString())

        reply.deleteLater()
        self._currReply = None
        self._startNext()

