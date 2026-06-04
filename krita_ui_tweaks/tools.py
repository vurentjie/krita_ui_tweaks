from .pyqt import (
    QtCore,
    QtGui,
    QtWidgets,
    QAction,
    QTimer,
    QEvent,
    QObject,
    QToolButton,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QApplication,
    QWidget,
    QMainWindow,
)

from krita import Window, Document, View
from dataclasses import dataclass, replace, fields
from contextlib import contextmanager
from typing import Any, TYPE_CHECKING
from datetime import datetime
from types import SimpleNamespace

import typing
import re
import json
import os
import time

from .options import getOpt
from .component import Component, COMPONENT_GROUP

from .helper import Helper
from .i18n import i18n

if TYPE_CHECKING:
    from .plugin import Plugin


class ToolManager(Component):

    def __init__(
        self,
        window: Window,
        plugin: "Plugin",
        pluginGroup: COMPONENT_GROUP | None = None,
        helper: Helper | None = None,
    ):
        super().__init__(window, pluginGroup=pluginGroup, helper=helper)

        self._activeTool = "KritaShape/KisToolBrush"
        self._syncingTool = False
        self._plugin = plugin
        self._toolActions: dict[str, SimpleNamespace | None] = {
            "InteractionTool": None,
            "KarbonCalligraphyTool": None,
            "KisAssistantTool": None,
            "KisToolCrop": None,
            "KisToolEncloseAndFill": None,
            "KisToolPath": None,
            "KisToolPencil": None,
            "KisToolPolygon": None,
            "KisToolPolyline": None,
            "KisToolSelectContiguous": None,
            "KisToolSelectElliptical": None,
            "KisToolSelectMagnetic": None,
            "KisToolSelectOutline": None,
            "KisToolSelectPath": None,
            "KisToolSelectPolygonal": None,
            "KisToolSelectRectangular": None,
            "KisToolSelectSimilar": None,
            "KisToolTransform": None,
            "KritaFill/KisToolFill": None,
            "KritaFill/KisToolGradient": None,
            "KritaSelected/KisToolColorSampler": None,
            "KritaShape/KisToolBrush": None,
            "KritaShape/KisToolDyna": None,
            "KritaShape/KisToolEllipse": None,
            "KritaShape/KisToolLazyBrush": None,
            "KritaShape/KisToolLine": None,
            "KritaShape/KisToolMeasure": None,
            "KritaShape/KisToolMultiBrush": None,
            "KritaShape/KisToolRectangle": None,
            "KritaShape/KisToolSmartPatch": None,
            "KritaTransform/KisToolMove": None,
            "PanTool": None,
            "PathTool": None,
            "SvgTextTool": None,
            "ToolReferenceImages": None,
            "ZoomTool": None,
        }

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        qwin = self._helper.getQwin()

        eventType = event.type()
        if (
            eventType == QEvent.Type.Show
            and isinstance(obj, QDialog)
            and obj.windowTitle() == i18n("Configure Toolbars")
        ):
            box = obj.findChild(QDialogButtonBox)
            if box:

                def cb(_, obj=obj):
                    QTimer.singleShot(200, self.onThemeChanged)

                for btn in box.buttons():
                    btn.clicked.connect(cb)
            return False

        if (
            eventType == QEvent.Type.ActivationChange
            and self._plugin._activeQwin != self._helper.getQwin()
        ):
            self._plugin._activeQwin = self._helper.getQwin()
            QTimer.singleShot(10, self.onViewChanged)

        return False

    def onViewChanged(self):
        tool = self.getActiveTool()
        action = (
            self._toolActions[tool].action
            if tool and tool in self._toolActions
            else None
        )
        if action:
            action.trigger()

    def onWindowInit(self):
        app = self._helper.getApp()
        win = self._helper.getWin()
        qwin = self._helper.getQwin()

        if app is None or qwin is None or win is None:
            return

        if not self._helper.isActiveWin():
            # cannot do app.action(name) without focus
            # and cannot force the focus at this point
            QTimer.singleShot(100, self.onWindowInit)
            return

        qapp = QApplication.instance()
        if qapp:
            qapp.installEventFilter(self)

        self.fixPrintSizeActions()
        win.activeViewChanged.connect(self.onViewChanged)

        for d in app.dockers():
            if d.objectName() == "ToolBox":
                for tb in d.findChildren(QToolButton):
                    tb.clicked.connect(
                        lambda _=None, action=tb.objectName(): self.onToolAction(
                            action
                        )
                    )
                break

        activeTool = self.getActiveTool()

        for name in self._toolActions.keys():
            action = app.action(name)
            if not action:
                continue

            self._toolActions[name] = SimpleNamespace(
                action=action,
                callback=lambda _=None, action=action: self.onToolAction(
                    action
                ),
            )

            action.triggered.connect(self._toolActions[name].callback)

            if name == activeTool:
                action.trigger()

    def onWindowDestroyed(self):
        app = self._helper.getApp()

        if app is None:
            return

        try:
            app.action("view_print_size").triggered.disconnect(
                self._updatePrintSize
            )
        except:
            pass

        for name in self._toolActions.keys():
            try:
                self._toolActions[name].action.triggered.disconnect(
                    self._toolActions[name].callback
                )
            except:
                pass

    def getActiveTool(self):
        if getOpt("toggle", "global_tool"):
            return self._plugin._globalTool

        if getOpt("toggle", "shared_tool"):
            return self._activeTool

    def setActiveTool(self, name):
        self._plugin._globalTool = name
        self._activeTool = name

    def onToolAction(self, action: QAction | str | None):
        qwin = self._helper.getQwin()
        if qwin is None:
            return

        if isinstance(action, str):
            actionData = self._toolActions.get(action, None)
            if actionData:
                action = actionData.action

        if not action or not qwin or self._syncingTool:
            return

        self._syncingTool = True

        name = action.objectName()
        msg = action.text()
        isTool = name in self._toolActions

        if isTool:
            activeTool = self.getActiveTool()
            self.setActiveTool(name)
            if activeTool != name:
                def restore(qwin=qwin):
                    for tb in qwin.findChildren(QToolButton):
                        ta = tb.defaultAction()
                        if ta:
                            objName = ta.objectName()
                            if objName in self._toolActions:
                                ta.setCheckable(True)
                                ta.setChecked(objName == self._activeTool)
                            
                self._helper.debounceCallback(
                    "toolbarButtons", restore, timeout_seconds=0.5
                )

        self._syncingTool = False

    def _updatePrintSize(self):
        qwin = self._helper.getQwin()
        if qwin is None:
            return

        app = self._helper.getApp()
        view = self._helper.getView()
        data = self._helper.getViewData(view)
        if isinstance(data, dict):
            action = app.action("view_print_size")
            data["printSize"] = action.isChecked() if action else False

    def fixPrintSizeActions(self):
        if self._helper.version() >= 5.3:
            return

        app = self._helper.getApp()
        win = self._helper.getWin()

        if not win:
            return

        def viewChanged():
            qwin = self._helper.getQwin()
            view = self._helper.getView()
            data = self._helper.getViewData(view)
            if not (isinstance(data, dict) and view and qwin):
                return

            if data.get("printSizeClick", False):
                action = app.action("view_print_size")
                savedState = data.get("printSize", False)
                if action and action.isChecked() != savedState:
                    action.trigger()
                return

            data["printSizeClick"] = True
            status = qwin.statusBar()
            if not status:
                return

            for widget in status.findChildren(QWidget):
                obj = widget.metaObject()
                name = obj.className() if obj else None
                if name and widget.isVisible() and name == "KoZoomWidget":
                    for btn in widget.findChildren(QToolButton):
                        tooltip = btn.toolTip()
                        if (
                            i18n("Pixel Size") in tooltip
                            or i18n("Print Size") in tooltip
                        ):
                            btn.clicked.connect(self._updatePrintSize)

        action = app.action("view_print_size")
        if action:
            action.triggered.connect(self._updatePrintSize)
            win.activeViewChanged.connect(viewChanged)
