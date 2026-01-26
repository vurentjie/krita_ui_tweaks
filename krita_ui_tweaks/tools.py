# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    PYQT_SLOT,
    pyqtBoundSignal,
    QApplication,
    QIcon,
    QEvent,
    QDialog,
    QDialogButtonBox,
    QAction,
    QToolBar,
    QToolButton,
    QWidget,
    QMdiSubWindow,
    QMessageBox,
    QTimer,
    QRect,
)

from krita import Window, Krita
from .component import Component, COMPONENT_GROUP
from .options import showOptions, getOpt, signals as OptionSignals
from .i18n import i18n
from .helper import Helper, CanvasPosition

import time
import typing


FIT_ACTION = typing.Literal[
    "zoom_to_fit",
    "zoom_to_fit_height",
    "zoom_to_fit_width",
    "toggle_zoom_to_fit",
]

SCALING_ACTION = typing.Literal[
    "krita_ui_tweaks_scaling_mode_anchored",
    "krita_ui_tweaks_scaling_mode_contained",
    "krita_ui_tweaks_scaling_mode_expanded",
]

SCALING_MODE = typing.Literal[
    "anchored",
    "contained",
    "expanded",
]


class Tools(Component):
    def __init__(
        self,
        window: Window,
        pluginGroup: COMPONENT_GROUP | None = None,
        helper: Helper | None = None,
    ):
        super().__init__(window, pluginGroup=pluginGroup, helper=helper)

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks",
            i18n("Krita UI Tweaks"),
            self.showOptions,
            menu=True,
        )

        view = self._helper.getView()

        self._showToast = True
        self._defaultTool: str = "KritaShape/KisToolBrush"
        self._activeTool: str = self._defaultTool
        self._toolActions: dict[str, QAction | None] = {
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

        # NOTE ty will not typecheck if the actions are declared in the definition

        self._fitActions: dict[FIT_ACTION, QAction | None] = {}
        self._fitActions["zoom_to_fit"] = None
        self._fitActions["zoom_to_fit_height"] = None
        self._fitActions["zoom_to_fit_width"] = None
        self._fitActions["toggle_zoom_to_fit"] = None

        self._scalingActions: dict[SCALING_ACTION, QAction | None] = {}
        self._scalingActions["krita_ui_tweaks_scaling_mode_anchored"] = None
        self._scalingActions["krita_ui_tweaks_scaling_mode_contained"] = None
        self._scalingActions["krita_ui_tweaks_scaling_mode_expanded"] = None

        self._scalingToAction: dict[SCALING_MODE, SCALING_ACTION] = {}
        self._scalingToAction["anchored"] = (
            "krita_ui_tweaks_scaling_mode_anchored"
        )
        self._scalingToAction["contained"] = (
            "krita_ui_tweaks_scaling_mode_contained"
        )
        self._scalingToAction["expanded"] = (
            "krita_ui_tweaks_scaling_mode_expanded"
        )

        self._actionToScaling: dict[SCALING_ACTION, SCALING_MODE] = {}
        self._actionToScaling["krita_ui_tweaks_scaling_mode_anchored"] = (
            "anchored"
        )
        self._actionToScaling["krita_ui_tweaks_scaling_mode_contained"] = (
            "contained"
        )
        self._actionToScaling["krita_ui_tweaks_scaling_mode_expanded"] = (
            "expanded"
        )

        self._globalScalingMode: SCALING_ACTION | bool = (
            self._scalingToAction.get(
                getOpt("resize", "default_scaling_mode"), False
            )
        )

        val = "dark" if self._helper.useDarkIcons() else "light"
        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_scaling_mode_anchored",
            i18n("Scaling Mode Anchored"),
            self._helper.noop,
            checkable=True,
            icon=QIcon(
                self._helper.getIconPath(f"{val}_scaling-mode-anchored.png")
            ),
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_scaling_mode_contained",
            i18n("Scaling Mode Contained"),
            self._helper.noop,
            checkable=True,
            icon=QIcon(
                self._helper.getIconPath(f"{val}_scaling-mode-contained.png")
            ),
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_scaling_mode_expanded",
            i18n("Scaling Mode Expanded"),
            self._helper.noop,
            checkable=True,
            icon=QIcon(
                self._helper.getIconPath(f"{val}_scaling-mode-expanded.png")
            ),
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_center_canvas",
            i18n("Center Canvas"),
            self.centerCanvas,
            icon=QIcon(self._helper.getIconPath(f"{val}_center-canvas.png")),
        )

        OptionSignals.configSaved.connect(self.onConfigSave)

        app = QApplication.instance()
        app.installEventFilter(self)

    def showOptions(self):
        showOptions(self._componentGroup["splitPane"])

    def eventFilter(self, obj, event):
        # NOTE
        # not a big deal if this stops working
        # just every time toolbars are configured
        # highlights mysteriously vanish
        if isinstance(obj, QDialog):
            if event.type() == QEvent.Show:
                if obj.windowTitle() == Krita.krita_i18n("Configure Toolbars"):
                    box = obj.findChild(QDialogButtonBox)
                    if box:

                        def cb(_, obj=obj):
                            QTimer.singleShot(200, self.onThemeChanged)

                        for btn in box.buttons():
                            btn.clicked.connect(cb)
        return False

    def onConfigSave(self, context):
        qwin = self._helper.getQwin()
        if not qwin:
            return

        action = self._toolActions[self._activeTool]
        if not action:
            return
            
        if context.get("resize", "scaling_mode_per_view"):
            self.viewActions()

        name = action.objectName()
        if getOpt("toggle", "toolbar_icons"):
            for tb in qwin.findChildren(QToolButton):
                ta = tb.defaultAction()
                if ta and ta.objectName() in self._toolActions:
                    ta.setCheckable(True)
                    ta.setChecked(ta.objectName() == name)
        else:
            for tb in qwin.findChildren(QToolButton):
                ta = tb.defaultAction()
                if ta and ta.objectName() in self._toolActions:
                    ta.setChecked(False)
                    ta.setCheckable(False)

    def onThemeChanged(self):
        val = "dark" if self._helper.useDarkIcons() else "light"
        icons = {
            "krita_ui_tweaks_scaling_mode_anchored": f"{val}_scaling-mode-anchored.png",
            "krita_ui_tweaks_scaling_mode_contained": f"{val}_scaling-mode-contained.png",
            "krita_ui_tweaks_scaling_mode_expanded": f"{val}_scaling-mode-expanded.png",
            "krita_ui_tweaks_center_canvas": f"{val}_center-canvas.png",
        }
        app = self._helper.getApp()
        for name, path in icons.items():
            action = app.action(name)
            if action:
                icon = QIcon(self._helper.getIconPath(path))
                action.setIcon(icon)

        qwin = self._helper.getQwin()
        if qwin:
            for tb in qwin.findChildren(QToolButton):
                ta = tb.defaultAction()
                if ta and ta.isChecked():
                    ta.setChecked(False)
                    ta.setChecked(True)

    def onWindowShown(self):
        super().onWindowShown()
        app = self._helper.getApp()
        qwin = self._helper.getQwin()
        if not qwin:
            return

        splitPane = self._componentGroup["splitPane"]
        splitPane.winScrolled.connect(self.onSubWindowScrolled)
        splitPane.winResized.connect(self.onSubWindowResized)

        self.initPrintSizeActions()

        for name in self._toolActions.keys():
            action = app.action(name)
            self._toolActions[name] = action
            _ = action.triggered.connect(  # pyright: ignore[reportUnknownMemberType]
                typing.cast(
                    PYQT_SLOT,
                    lambda _, action=action: self.onToolAction(  # pyright: ignore[reportUnknownLambdaType]
                        action
                    ),
                )
            )

            if name == self._activeTool and getOpt("toggle", "shared_tool"):
                action.trigger()

    def onViewChanged(self):
        super().onViewChanged()

        helper = self._helper
        app = helper.getApp()
        qwin = helper.getQwin()
        view = helper.getView()
        data = helper.getViewData(view)

        if not (app and qwin and isinstance(data, dict)):
            return

        self.viewActions()

        action = None
        isSharedTool = getOpt("toggle", "shared_tool")

        if isSharedTool:
            action = self._toolActions[self._activeTool]
        else:
            name = data.get("viewTool", self._defaultTool)
            action = self._toolActions.get(name)

        if action:
            self._showToast = False
            action.trigger()
            self._showToast = True

    def onToolAction(self, action: QAction | None):
        if not action:
            return

        qwin = self._helper.getQwin()
        if not qwin:
            return

        name = action.objectName()
        msg = action.text()
        isTool = name in self._toolActions
        checkableIcons = getOpt("toggle", "toolbar_icons")

        splitPane = self._componentGroup.get("splitPane", None)
        if not splitPane or not splitPane.isSyncing():
            if self._showToast:
                self._helper.showToast(f"{msg}")
            if isTool:
                self._activeTool = name

        if isTool:
            view = self._helper.getView()
            data = self._helper.getViewData(view)
            if isinstance(data, dict):
                data["viewTool"] = name

            if checkableIcons:
                for tb in qwin.findChildren(QToolButton):
                    ta = tb.defaultAction()
                    if ta:
                        objName = ta.objectName()
                        if objName in self._toolActions:
                            ta.setCheckable(True)
                            ta.setChecked(objName == name)

    def initPrintSizeActions(self):
        app = self._helper.getApp()
        win = self._helper.getWin()

        if not win:
            return

        def updatePrintSize():
            view = self._helper.getView()
            data = self._helper.getViewData(view)
            if isinstance(data, dict):
                action = app.action("view_print_size")
                data["printSize"] = action.isChecked() if action else False

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
                            _ = btn.clicked.connect(  # pyright: ignore[reportUnknownMemberType]
                                updatePrintSize
                            )

        action = app.action("view_print_size")
        if action:
            _ = action.triggered.connect(  # pyright: ignore[reportUnknownMemberType]
                updatePrintSize
            )

            _ = typing.cast(  # pyright: ignore[reportUnknownMemberType,reportUnnecessaryCast]
                pyqtBoundSignal, win.activeViewChanged
            ).connect(
                viewChanged
            )

    def viewActions(self):
        helper = self._helper
        app = helper.getApp()
        qwin = helper.getQwin()
        view = helper.getView()
        mdi = helper.getMdi()
        win = mdi.activeSubWindow() if mdi else None
        data = helper.getViewData(view)

        if not (win and app and qwin and isinstance(data, dict)):
            return

        data["fitMode"] = data.get("fitMode", "zoom_to_fit")

        data["scalingMode"] = data.get(
            "scalingMode",
            self._scalingToAction.get(
                getOpt("resize", "default_scaling_mode"), False
            ),
        )

        for actions in (self._fitActions, self._scalingActions):
            dataKey = (
                "fitMode" if actions == self._fitActions else "scalingMode"
            )
            for name in actions.keys():
                a = app.action(name)
                actions[name] = a
                a.triggered.disconnect()
                a.setCheckable(True)
                if dataKey == "scalingMode":
                    val = (
                        data[dataKey]
                        if getOpt("resize", "scaling_mode_per_view")
                        else self._globalScalingMode
                    )
                    a.setChecked(name == val)
                else:
                    zoomToFit = data[dataKey] in (
                        "zoom_to_fit",
                        "toggle_zoom_to_fit",
                    )
                    testChecked = (
                        ("zoom_to_fit", "toggle_zoom_to_fit")
                        if zoomToFit
                        else [data[dataKey]]
                    )
                    a.setChecked(name in testChecked)
                a.triggered.connect(
                    lambda _, action=a: self.triggerViewAction(action)
                )

    def triggerViewAction(self, action):
        name = action.objectName()
        helper = self._helper
        view = helper.getView()
        mdi = helper.getMdi()
        win = mdi.activeSubWindow() if mdi else None
        data = helper.getViewData(view)
        splitPane = self._componentGroup["splitPane"]
        isScaling = name in self._scalingActions
        isFitting = name in self._fitActions
        dataKey = "fitMode" if isFitting else "scalingMode"
        actions = self._fitActions if isFitting else self._scalingActions

        if not (
            win and view and data and splitPane and isinstance(data, dict)
        ):
            return

        zoomToFit = name in ("zoom_to_fit", "toggle_zoom_to_fit")

        if not action.isChecked():
            if isFitting:
                if getOpt("resize", "restore_fit_mode"):
                    prevPos = data.get("toggleSavePosition", None)
                    if prevPos:
                        helper.setZoomLevel(
                            canvas=view.canvas(), zoom=prevPos.zoom
                        )
                        helper.scrollTo(
                            win=win,
                            x=-prevPos.bbox.x(),
                            y=-prevPos.bbox.y(),
                        )

                if zoomToFit:
                    self._fitActions["zoom_to_fit"].setChecked(False)
                    self._fitActions["toggle_zoom_to_fit"].setChecked(False)

            if isScaling:
                data[dataKey] = False
                self._globalScalingMode = None
            else:
                data[dataKey] = False
            if self._showToast:
                helper.showToast(f"{action.text()} {i18n('OFF')}")
            return

        if isScaling:
            self._globalScalingMode = name
            data[dataKey] = name
            for key in actions.keys():
                actions[key].setChecked(key in self._globalScalingMode)
            if self._showToast:
                helper.showToast(f"{action.text()} {i18n('ON')}")
        else:
            prevAction = data.get(dataKey, False)
            data[dataKey] = name

            testChecked = (
                ("zoom_to_fit", "toggle_zoom_to_fit") if zoomToFit else [name]
            )

            for key in actions.keys():
                actions[key].setChecked(key in testChecked)

            if self._showToast:
                helper.showToast(f"{action.text()} {i18n('ON')}")

            if not prevAction:
                data["toggleSavePosition"] = helper.canvasPosition(
                    win=win, view=view
                )

            if zoomToFit:
                helper.zoomToFit(win=win, view=view)
            elif name == "zoom_to_fit_width":
                helper.zoomToFitWidth(win=win, view=view)
            elif name == "zoom_to_fit_height":
                helper.zoomToFitHeight(win=win, view=view)

    def onSubWindowScrolled(self, uid: int):
        helper = self._helper
        splitPane = self._componentGroup["splitPane"]
        if helper.isScrolling() or helper.isZooming() or splitPane.isSyncing():
            return

        win, view, data = helper.getViewSubWindow(uid)
        if not (win and view and isinstance(data, dict)):
            return

        lastResize = getattr(splitPane, "_lastResize", None)
        if lastResize and time.monotonic() - lastResize > 0.5:
            if data:
                data["fitMode"] = False
                data["toggleSavePosition"] = None

                def cb(data=data, win=win, view=view):
                    data["prevResizePosition"] = helper.canvasPosition(
                        win=win, view=view
                    )

                wid = id(win)
                self._helper.debounceCallback(
                    f"updateResizePosition{wid}", cb, timeout_seconds=0.2
                )
                for key in self._fitActions.keys():
                    self._fitActions[key].setChecked(False)

    def onSubWindowResized(self, uid: int):
        helper = self._helper
        # TODO skip when moving splits around
        if helper.isScrolling() or helper.isZooming():
            return
        splitPane = self._componentGroup["splitPane"]
        splitPane._lastResize = time.monotonic()

        win, view, data = helper.getViewSubWindow(uid)
        if not (win and view and isinstance(data, dict)):
            return

        name = data.get("fitMode", "zoom_to_fit")
        prevPos = data.get("prevResizePosition", None)

        if name == "zoom_to_fit":
            helper.zoomToFit(win=win, view=view)
        elif name == "zoom_to_fit_width":
            helper.zoomToFitWidth(win=win, view=view)
        elif name == "zoom_to_fit_height":
            helper.zoomToFitHeight(win=win, view=view)
        else:
            if splitPane.resizingEnabled():
                name = (
                    data["scalingMode"]
                    if getOpt("resize", "scaling_mode_per_view")
                    else self._globalScalingMode
                )

                if name in (
                    "krita_ui_tweaks_scaling_mode_anchored",
                    "krita_ui_tweaks_scaling_mode_contained",
                    "krita_ui_tweaks_scaling_mode_expanded",
                ):
                    oldPos = data.get("dragOrigin", prevPos)
                    newPos = helper.canvasPosition(win=win, view=view)
                    helper.scaleTo(
                        win=win,
                        view=view,
                        oldPos=oldPos,
                        newPos=newPos,
                        mode=self._actionToScaling.get(name),
                        splitPane=splitPane,
                    )

        data["prevResizePosition"] = helper.canvasPosition(win=win, view=view)

    def centerCanvas(self):
        view = self._helper.getView()
        mdi = self._helper.getMdi()
        if not (view and mdi):
            return
        win = mdi.activeSubWindow()
        if not win:
            return
        data = self._helper.getViewData(view)
        if data and data.get("fitMode", False):
            return
        self._helper.centerCanvas(win=win, view=view)
