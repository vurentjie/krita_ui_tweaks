# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    PYQT_SLOT,
    pyqtBoundSignal,
    Qt,
    QAction,
    QToolButton,
    QWidget,
    QDockWidget,
    QObject,
    QEvent,
    QApplication,
)


from krita import Window
from .options import showOptions, getOpt, signals as OptionSignals
from .component import Component, COMPONENT_GROUP
from .i18n import i18n


class Dockers(Component):
    def __init__(
        self, window: Window, pluginGroup: COMPONENT_GROUP | None = None
    ):
        super().__init__(window, pluginGroup=pluginGroup)

        app = self._helper.getApp()
        assert app is not None

        self._dockingEnabled = (
            app.readSetting("krita_ui_tweaks", "dockingEnabled", "true")
            == "true"
        )
        self._optEnabled = getOpt("toggle", "toggle_docking")

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_toggle_dockers",
            i18n("Toggle docking"),
            self.toggleDocking,
        )

        OptionSignals.configSaved.connect(self.onConfigSave)

        for dock in window.dockers():
            dock.setProperty(
                "onDockMoved", lambda _, d=dock: self.onDockMoved(d)
            )
            dock.topLevelChanged.connect(dock.property("onDockMoved"))
            if not self._dockingEnabled and dock.isFloating():
                dock.setAllowedAreas(Qt.NoDockWidgetArea)

    def onConfigSave(self):
        isEnabled = getOpt("toggle", "toggle_docking")
        if isEnabled != self._optEnabled:
            if isEnabled:
                self.updateDockers(enable=self._dockingEnabled, quiet=True)
            else:
                app = self._helper.getApp()
                if app:
                    app.writeSetting(
                        "krita_ui_tweaks", "dockingEnabled", "true"
                    )
                self.updateDockers(enable=True, quiet=True)

        self._optEnabled = isEnabled

    def onDockMoved(self, dock):
        if not getOpt("toggle", "toggle_docking"):
            return
        if dock.isFloating():
            dock.setAllowedAreas(
                Qt.AllDockWidgetAreas
                if self._dockingEnabled
                else Qt.NoDockWidgetArea
            )

    def toggleDocking(self):
        if not getOpt("toggle", "toggle_docking"):
            return
        window = self._helper.getWin()
        app = self._helper.getApp()
        if not (window and app):
            return
        self._dockingEnabled = not self._dockingEnabled
        app.writeSetting(
            "krita_ui_tweaks",
            "dockingEnabled",
            "true" if self._dockingEnabled else "false",
        )
        self.updateDockers(self._dockingEnabled)

    def updateDockers(self, enable: bool = True, quiet: bool = False):
        window = self._helper.getWin()
        if not window:
            return
        if enable:
            self._helper.showToast(i18n("Docking enabled"))
            for dock in window.dockers():
                if dock.isFloating():
                    dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        else:
            self._helper.showToast(i18n("Docking disabled"))
            for dock in window.dockers():
                if dock.isFloating():
                    dock.setAllowedAreas(Qt.NoDockWidgetArea)

