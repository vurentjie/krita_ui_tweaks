# SPDX-License-Identifier: CC0-1.0

from krita import Krita, Extension, Window
from .pyqt import QObject
from .tools import Tools
from .split_pane import SplitPane
from .dockers import Dockers
from .component import Component, COMPONENT_GROUP
from .helper import Helper

from dataclasses import dataclass
from datetime import datetime


class Plugin(Extension):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._components: list[COMPONENT_GROUP | Helper] = []

    def setup(self):
        pass

    def validateComponents(self):
        for item in self._components[:]:
            if not (item and item["helper"] and item["helper"].getQwin()):
                self._components.remove(item)

    def createActions(self, window: Window | None):
        if not window:
            return

        qwin = window.qwindow()
        if not qwin:
            return

        self.validateComponents()
        qwin.destroyed.connect(self.validateComponents)

        # NOTE tools should be initialized before split pane
        group = {}
        group["createdTime"] = datetime.now()
        group["helper"]: Helper = Helper(
            qwin=window.qwindow(), pluginGroup=group
        )
        group["tools"]: Tools = Tools(
            window, pluginGroup=group, helper=group["helper"]
        )
        group["splitPane"]: SplitPane = SplitPane(
            window,
            pluginGroup=group,
            helper=group["helper"],
            pluginFactory = self,
            hasOtherWindows=len(self._components) > 0, # hack
        )
        group["dockers"]: Dockers = Dockers(
            window, pluginGroup=group, helper=group["helper"]
        )

        self._components.append(group)

        qwin = window.qwindow()
        qwin.setProperty("uiTweaks", group)

        # For debug in the scripter tool
        Krita.instance().uiTweaks = self._components
