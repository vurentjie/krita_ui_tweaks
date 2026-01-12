# SPDX-License-Identifier: CC0-1.0

from krita import Krita, Extension, Window
from .pyqt import QObject
from .tools import Tools
from .split_pane import SplitPane
from .dockers import Dockers
from .component import Component, COMPONENT_GROUP
from .helper import Helper

from dataclasses import dataclass


class Plugin(Extension):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._components: list[COMPONENT_GROUP|Helper] = []

    def setup(self):
        pass

    def createActions(self, window: Window | None):
        if not window:
            return

        group = {}
        group["helper"] = Helper(qwin=window.qwindow())
        group["tools"] = Tools(window, pluginGroup=group, helper=group["helper"])
        group["splitPane"] = SplitPane(window, pluginGroup=group, helper=group["helper"])
        group["dockers"] = Dockers(window, pluginGroup=group, helper=group["helper"])

        self._components.append(group)
        
        # For debug in the scripter tool
        Krita.instance().uiTweaks = self._components
