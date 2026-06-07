# SPDX-License-Identifier: CC0-1.0

from krita import Krita, Extension, Window
from .pyqt import QObject, QMessageBox, QDockWidget
from .helper import Helper
from .split_pane import MdiController
from .tools import ToolManager
from .dockers import Dockers
from .component import Component, COMPONENT_GROUP

from datetime import datetime
from itertools import count


class Plugin(Extension):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._uid = count(1)
        self._components: list[COMPONENT_GROUP | Helper] = []
        self._globalTool: str = "KritaShape/KisToolBrush"
        self._sessionRestore = False
        self._sessionWasRestored = False
        self._activeQwin = None

        Krita.instance().uiTweaks = self

    def setup(self):
        pass

    def uid(self):
        return next(self._uid)

    def getValidatedComponents(self):
        for item in self._components[:]:
            if not (item and item["helper"] and item["helper"].getQwin()):
                self._components.remove(item)
        return self._components

    def createActions(self, window: Window | None):
        if not window:
            return

        if len(window.views()) > 0:
            return

        qwin = window.qwindow()

        if not qwin:
            return

        for item in self._components:
            if item and item["helper"] and item["helper"].getQwin() == qwin:
                return

        group = {}

        group["created"] = datetime.now()

        group["helper"]: Helper = Helper(
            window=window, plugin=self, pluginGroup=group
        )

        # if group["helper"].version() < 5.3:
        group["tools"]: ToolManager = ToolManager(
            window=window,
            plugin=self,
            pluginGroup=group,
            helper=group["helper"],
        )

        group["controller"]: MdiController = MdiController(
            window=window,
            plugin=self,
            pluginGroup=group,
            helper=group["helper"],
        )

        group["dockers"]: Dockers = Dockers(
            window,
            plugin=self,
            pluginGroup=group,
            helper=group["helper"],
        )

        self._components.append(group)
