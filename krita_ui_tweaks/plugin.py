# SPDX-License-Identifier: CC0-1.0

from krita import Extension, Window
from .pyqt import QObject
from .tools import Tools
from .split_pane import SplitPane
from .dockers import Dockers
from .component import Component, COMPONENT_GROUP

from dataclasses import dataclass


class Plugin(Extension):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._components: list[COMPONENT_GROUP] = []

    def setup(self):
        pass

    def createActions(self, window: Window | None):
        if not window:
            return

        group = {}
        group["tools"] = Tools(window, pluginGroup=group)
        group["splitPane"] = SplitPane(window, pluginGroup=group)
        group["dockers"] = Dockers(window, pluginGroup=group)

        self._components.append(group)
