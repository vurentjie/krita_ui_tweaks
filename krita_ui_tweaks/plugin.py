# SPDX-License-Identifier: CC0-1.0

from krita import Extension, Window
from .pyqt import QObject
from .tools import Tools
from .split_pane import SplitPane
from .dockers import Dockers
from .component import Component

class Plugin(Extension):
    def __init__(self, parent: QObject):
        super().__init__(parent)
        self._components: list[Component] = []

    def setup(self):
        pass

    def createActions(self, window: Window | None):
        if not window:
            return

        self._components.append(Tools(window))
        self._components.append(SplitPane(window))
        self._components.append(Dockers(window))
