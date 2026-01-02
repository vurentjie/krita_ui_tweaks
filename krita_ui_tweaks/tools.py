# SPDX-License-Identifier: CC0-1.0

from .pyqt import (
    PYQT_SLOT,
    pyqtBoundSignal,
    QAction,
    QToolButton,
    QWidget,
)

from .component import Component, Window
from .options import showOptions, getOpt, signals as OptionSignals
from .i18n import i18n

import typing


class Tools(Component):
    def __init__(self, window: Window):
        super().__init__(window)

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks",
            i18n("Krita UI Tweaks"),
            showOptions,
            menu=True,
        )

        self._activeTool: str = "KritaShape/KisToolBrush"
        self._toolActions: dict[str, QAction | None] = {
            "view_toggle_reference_images": None,
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

        OptionSignals.configSaved.connect(self.onConfigSave)

    def onConfigSave(self):
        qwin = self._helper.getQwin()
        if not qwin:
            return
        action = self._toolActions[self._activeTool]
        if not action:
            return
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

    def onWindowShown(self):
        super().onWindowShown()
        app = self._helper.getApp()

        self.fixPrintSizeBug()

        for action in app.actions():
            name = action.objectName()
            if name in self._toolActions:
                self._toolActions[name] = action
                _ = action.triggered.connect(  # pyright: ignore[reportUnknownMemberType]
                    typing.cast(
                        PYQT_SLOT,
                        lambda _, action=action: self.onToolAction(  # pyright: ignore[reportUnknownLambdaType]
                            action
                        ),
                    )
                )
                if name == self._activeTool and getOpt(
                    "toggle", "shared_tool"
                ):
                    action.trigger()

    def onViewChanged(self):
        super().onViewChanged()
        if getOpt("toggle", "shared_tool"):
            action = self._toolActions[self._activeTool]
            if action:
                self._helper.disableToast()
                action.trigger()
                self._helper.enableToast()

    def onToolAction(self, action: QAction | None):
        if not action:
            return
        qwin = self._helper.getQwin()
        if not qwin:
            return
        name = action.objectName()
        msg = action.text()
        checkableIcons = getOpt("toggle", "toolbar_icons")

        if checkableIcons and name == "view_toggle_reference_images":
            for tb in qwin.findChildren(QToolButton):
                ta = tb.defaultAction()
                if ta and ta.objectName() == name:
                    ta.setCheckable(True)
                    ta.setChecked(ta.isChecked())
            return

        self._helper.showToast(f"{msg}")
        self._activeTool = name

        if checkableIcons:
            for tb in qwin.findChildren(QToolButton):
                ta = tb.defaultAction()
                if ta and ta.objectName() in self._toolActions:
                    ta.setCheckable(True)
                    ta.setChecked(ta.objectName() == name)

    def fixPrintSizeBug(self):
        app = self._helper.getApp()
        win = self._helper.getWin()

        if not win:
            return

        def updatePrintSize():
            view = self._helper.getView()
            data = self._helper.getViewData(view)
            if data:
                action = app.action("view_print_size")
                data["printSize"] = action.isChecked() if action else False

        def viewChanged():
            qwin = self._helper.getQwin()
            view = self._helper.getView()
            data = self._helper.getViewData(view)
            if not (data and view and qwin):
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

