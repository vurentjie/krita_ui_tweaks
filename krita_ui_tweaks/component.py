# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    QApplication,
    pyqtSignal,
    pyqtBoundSignal,
    QMdiArea,
    QEvent,
    QObject,
    QMainWindow,
    QTimer,
    QDynamicPropertyChangeEvent,
)

from krita import Krita, Window
from dataclasses import dataclass
from .helper import Helper
import typing
from typing import Any

i18n = Krita.krita_i18n


class WindowShown(QObject):
    def __init__(
        self, parent: QMainWindow, callback: typing.Callable[..., None]
    ):
        super().__init__(parent)
        self._callback: typing.Callable[..., None] = callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.parent() and event.type() == QEvent.Type.Show:
            self._callback()
        return False


@dataclass
class ComponentFilters:
    windowShow: WindowShown | None


@dataclass
class ComponentFlags:
    viewMode: QMdiArea.ViewMode | None
    windowInit: bool


class ComponentTimers(QObject):
    shortPoll = pyqtSignal()
    longPoll = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._shortPoll = QTimer()
        self._longPoll = QTimer()
        self._shortPoll.timeout.connect(self._onShortPoll)
        self._longPoll.timeout.connect(self._onLongPoll)
        self._shortPoll.start(100)
        self._longPoll.start(5000)

    def _onShortPoll(self):
        self.shortPoll.emit()

    def _onLongPoll(self):
        self.longPoll.emit()


componentTimers = ComponentTimers()

COMPONENT_GROUP = dict[
    typing.Literal["tools", "controller", "dockers", "helper", "bugfix"],
    "Component|None",
]


class Component(QObject):
    def __init__(
        self,
        window: Window,
        pluginGroup: COMPONENT_GROUP | None = None,
        helper: Helper | None = None,
    ):
        super().__init__()
        self._qwin: QMainWindow | None = window.qwindow()
        self._componentGroup = pluginGroup

        if not self._qwin:
            return

        self._helper: Helper = helper

        self._componentFlags = ComponentFlags(viewMode=None, windowInit=False)
        self._componentFilters = ComponentFilters(
            windowShow=None,
        )
        self._componentTimers = componentTimers

        self._qwin.destroyed.connect(self.onWindowDestroyed)
        
        if self._qwin.isVisible():
            QTimer.singleShot(0, self.onWindowInit)
        else:
            self._componentFilters.windowShow = WindowShown(
                self._qwin, self.onWindowInit
            )
            self._qwin.installEventFilter(self._componentFilters.windowShow)

    def helper(self):
        return self._helper
        
    def onWindowInit(self):
        if self._componentFlags.windowInit:
            return

        self._componentFlags.windowInit = True 

        filters = self._componentFilters
        if self._qwin and filters.windowShow:
            self._qwin.removeEventFilter(filters.windowShow)
            filters.windowShow = None

        win = self._helper.getWin()
        timers = self._componentTimers

        if win:

            notifier = self._helper.getNotifier()

            typing.cast(
                pyqtBoundSignal, notifier.configurationChanged
            ).connect(self.onKritaConfigChanged)

            mdi = self._helper.getMdi()
            if mdi:
                self._componentTimers.shortPoll.connect(self._checkViewMode)

            typing.cast(pyqtBoundSignal, win.activeViewChanged).connect(
                self.onViewChanged
            )

            typing.cast(pyqtBoundSignal, win.themeChanged).connect(
                self.onThemeChanged
            )

    def onWindowDestroyed(self):
        pass

    def onKritaConfigChanged(self):
        pass

    def onThemeChanged(self):
        pass

    def onViewChanged(self):
        pass

    def onViewModeChanged(self):
        pass

    def _checkViewMode(self):
        mdi = self._helper.getMdi()
        if mdi:
            flags = self._componentFlags
            viewMode = mdi.viewMode()
            if viewMode != flags.viewMode:
                flags.viewMode = viewMode
                self.onViewModeChanged()


