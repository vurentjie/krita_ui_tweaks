# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    pyqtSignal,
    Qt,
    QTimer,
    QApplication,
    pyqtBoundSignal,
    QMdiArea,
    QWIDGETSIZE_MAX,
    QColor,
    QMdiSubWindow,
    QAbstractScrollArea,
    QScrollBar,
    QTabBar,
    QMessageBox,
)

from krita import Window, Document, View
from dataclasses import dataclass, replace, fields
from contextlib import contextmanager
from typing import Any

import typing
import re
import json
import os
import time

from ..component import Component, COMPONENT_GROUP
from ..options import (
    getOpt,
    setOpt,
    signals as OptionSignals,
)

from ..helper import Helper
from ..i18n import i18n
from ..colors import ColorScheme

from .split_drag import SplitDragRect
from .split_tabs import SplitTabs
from .split_toolbar import SplitToolbar
from .split import Split

from .split_helpers import (
    SavedLayout,
    SplitData,
    EventInterceptor,
    KeyModiferInterceptor,
    getLayoutFiles,
)


class SplitPane(Component):
    winClosed = pyqtSignal(int)
    winScrolled = pyqtSignal(int)
    winResized = pyqtSignal(int)

    def __init__(
        self,
        window: Window,
        pluginGroup: COMPONENT_GROUP | None = None,
        helper: Helper | None = None,
    ):
        super().__init__(window, pluginGroup=pluginGroup, helper=helper)
        self.setObjectName("SplitPane")
        self._quit: bool = False
        self._syncing: bool = False
        self._splitData: dict[int, SplitData] = {}
        self._split: Split | None = None
        self._activeToolbar: SplitToolbar | None = None
        self._colors: ColorScheme | None = None
        self._adjustedColors: ColorScheme | None = None
        self._optEnabled = getOpt("toggle", "split_panes")
        self._layoutRestored = False
        self._layoutLoaded = False
        self._loadLayout: "SavedLayout | None" = None
        self._activeLayoutPath: str | None = None
        self._canvasColor: str | None = None
        self._currTheme: str | None = None
        self._layoutLocked: bool = False
        self._dragSplit: "Split|None" = None
        self._modifiers: KeyModiferInterceptor | None = None
        self._resizingEnabled = True
        self._debugMsg = None
        self._debugId = 0

        app = self._helper.getApp()
        if app:
            self._currTheme = app.readSetting("theme", "Theme", "")
            self._canvasColor = app.readSetting("", "canvasBorderColor", "")
            if app.readSetting("", "sessionOnStartup", "") != "0":
                setOpt("toggle", "restore_layout", False)
                app.writeSetting("krita_ui_tweaks", "restoreLayout", "")
                app.writeSetting("krita_ui_tweaks", "restoreLayoutPath", "")

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_next_tab",
            i18n("Goto next tab"),
            self.nextTab,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_prev_tab",
            i18n("Goto previous tab"),
            self.prevTab,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_save_layout_as",
            i18n("Save Layout As…"),
            self.saveLayout,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_save_layout",
            i18n("Save Current Layout"),
            self.saveCurrentLayout,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_load_layout",
            i18n("Open Layout"),
            self.loadLayout,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_toggle_layout_lock",
            i18n("Toggle Layout Locked"),
            self.toggleLock,
        )

        qapp = typing.cast(QApplication, QApplication.instance())
        qapp.aboutToQuit.connect(lambda: self.onQuit())

        self.attachStyles()

        OptionSignals.configSaved.connect(self.onConfigSave)

        notifier = self._helper.getNotifier()
        if notifier:
            typing.cast(pyqtBoundSignal, notifier.imageSaved).connect(
                self._doSaveLayout
            )

    def resizingEnabled(self):
        return self._resizingEnabled

    def setResizingEnabled(self, enabled: bool):
        self._resizingEnabled = enabled

    def modifiers(self):
        return self._modifiers

    def helper(self):
        return self._helper

    def onQuit(self):
        self._quit = True

    def isLocked(self):
        mdi = self._helper.getMdi()
        if not mdi:
            return False
        return (
            self._layoutLocked
            and getOpt("toggle", "split_panes")
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
        )

    def lock(self, silent: bool = False):
        self._layoutLocked = True
        if not silent:
            self._helper.showToast(i18n("Layout locked"))
            self._doSaveLayout()

    def unlock(self, silent: bool = False):
        self._layoutLocked = False
        if not silent:
            self._helper.showToast(i18n("Layout unlocked"))
            self._doSaveLayout()

    def toggleLock(self, silent: bool = False):
        self._layoutLocked = not self._layoutLocked
        if not silent:
            self._helper.showToast(
                i18n("Layout locked")
                if self._layoutLocked
                else i18n("Layout unlocked")
            )

    def setLayoutPath(self, path: str | None):
        self._activeLayoutPath = path

    def getLayoutPath(self):
        return self._activeLayoutPath

    def saveLayout(self):
        topSplit = self.topSplit()
        if topSplit:
            topSplit.saveLayout()

    def saveCurrentLayout(self):
        topSplit = self.topSplit()
        if topSplit:
            topSplit.saveLayout(self._activeLayoutPath)

    def loadLayout(self):
        topSplit = self.topSplit()
        if topSplit:
            topSplit.loadLayout()

    def onConfigSave(self, context: dict[str, dict[str, bool]]):
        isEnabled = getOpt("toggle", "split_panes")
        if isEnabled != self._optEnabled:
            self.toggleStyles()
            self.handleSplitter()
            self._optEnabled = isEnabled

        if getOpt("toggle", "restore_layout"):
            self._doSaveLayout()

        def updated(section, key, context=context):
            return context.get(section, {}).get(key, False)

        if any(
            updated("tab_behaviour", k)
            for k in (
                "tab_font_size",
                "tab_font_bold",
                "tab_height",
            )
        ) or context.get("colors", None):
            self.attachStyles()
            topSplit = self.topSplit()
            if topSplit:
                topSplit.onResize(force=True)

        if any(
            updated("tab_behaviour", k)
            for k in ("tab_max_chars", "tab_ellipsis")
        ):
            app = self._helper.getApp()
            if app:
                for doc in app.documents():
                    _, f = self.updateDocumentTabs(doc)

    def savePreviousLayout(self):
        self._helper.debounceCallback(
            "saveLayout", self._doSaveLayout, timeout_seconds=2
        )

    def _doSaveLayout(self):
        if not self._layoutRestored:
            return
        app = self._helper.getApp()
        if not app:
            return

        isEnabled = getOpt("toggle", "restore_layout")
        if isEnabled:
            topSplit = self.topSplit()
            if topSplit:
                layout = topSplit.getLayout(verify=False)
                try:
                    files, _ = getLayoutFiles(layout)
                    app.writeSetting(
                        "krita_ui_tweaks",
                        "restoreLayout",
                        json.dumps(layout) if len(files) > 0 else "",
                    )
                    app.writeSetting(
                        "krita_ui_tweaks",
                        "restoreLayoutPath",
                        (
                            self._activeLayoutPath
                            if self._activeLayoutPath
                            else ""
                        ),
                    )
                except:
                    pass
        else:
            app.writeSetting("krita_ui_tweaks", "restoreLayout", "false")

    def shortPoll(self):
        if self._quit:
            return
        helper = self._helper
        doc = helper.getDoc()
        tabs = helper.getTabBar()
        if doc and tabs:
            _, f = self.updateDocumentTabs(doc)
            if f:
                self.savePreviousLayout()

    def longPoll(self):
        if self._quit:
            return
        helper = self._helper
        app = helper.getApp()
        tabs = helper.getTabBar()
        if app and tabs:
            canvasColor = app.readSetting("", "canvasBorderColor", "")
            if canvasColor != self._canvasColor:
                self._canvasColor = canvasColor
                topSplit = self.topSplit()
                if topSplit:
                    topSplit.updateCanvasBacking()

            updated = False
            for doc in app.documents():
                _, f = self.updateDocumentTabs(doc)
                if f:
                    updated = True
            if updated:
                self.savePreviousLayout()

    def updateDocumentTabs(self, doc: Document) -> tuple[bool, bool]:
        helper = self._helper
        tabs = helper.getTabBar()
        data = helper.getDocData(doc)

        if not (tabs and data):
            return (False, False)

        updatedTab, updatedFileName = False, False

        savedTabText = data.doc.get("tabText", None)
        savedFileName = data.doc.get("fileName", None)
        savedTabModified = data.doc.get("tabModified", None)
        
        if len(data.views) == 0:
            return (False, False)

        if len(data.views[0]) == 0:
            return (False, False)

        view = data.views[0][0]
        index = self.getIndexByView(view)

        fileName = doc.fileName()
        tabModified = doc.modified()

        tabText = self.formatTabText(index, doc)

        if len(tabText) == 0:
            return (False, False)

        if fileName and not os.path.exists(fileName):
            doc.setModified(True)

        if savedFileName != fileName:
            data.doc["fileName"] = fileName
            updatedFileName = True

        if savedTabText != tabText or savedTabModified != tabModified:
            updatedTab = True
            data.doc["tabText"] = tabText
            data.doc["tabModified"] = tabModified
            for v in data.views:
                view = v[0]
                index = self.getIndexByView(view)
                uid = self.getUid(index)
                if uid is not None:
                    splitData = self.getSplitData(uid)
                    if splitData is not None:
                        toolbar = helper.isAlive(
                            splitData.toolbar, SplitToolbar
                        )
                        if toolbar:
                            toolbarTabs = toolbar.tabs()
                            splitTabIndex = toolbarTabs.getTabByView(view)
                            toolbarTabs.setTabText(splitTabIndex, tabText)

        return updatedTab, updatedFileName

    def loadDefaultLayout(self):
        if self._layoutLoaded:
            return

        self._layoutLoaded = True

        helper = self._helper
        app = helper.getApp()
        win = helper.getWin()
        mdi = helper.getMdi()
        central = helper.getCentral()
        isEnabled = getOpt("toggle", "split_panes")
        loadLayout: "SavedLayout | None" = None

        if (
            app
            and win
            and central
            and mdi
            and isEnabled
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
            and app.readSetting("", "sessionOnStartup", "") == "0"
        ):
            if getOpt("toggle", "restore_layout"):
                try:
                    layout = json.loads(
                        app.readSetting("krita_ui_tweaks", "restoreLayout", "")
                    )
                    if isinstance(layout, dict):
                        loadLayout = typing.cast(SavedLayout, layout)
                        layoutPath = app.readSetting(
                            "krita_ui_tweaks", "restoreLayoutPath", ""
                        )
                        if os.path.exists(layoutPath):
                            loadLayout["path"] = layoutPath

                    files, missing = getLayoutFiles(loadLayout)
                    if len(files) == 0:
                        _ = QMessageBox.warning(
                            None,
                            "Krita",
                            i18n(
                                "Unable to restore session.\nThese files are missing:"
                            )
                            + "\n"
                            + "\n".join(missing),
                        )
                        return

                    # NOTE
                    # Open the first file in the layout.
                    # After the split instance is created
                    # the layout will be restored properly.
                    # Doing it this way at startup
                    # fixes weird issues with the floating
                    # messages Krita displays.

                    def cb():
                        doc = app.openDocument(files[0])
                        if doc:
                            self._loadLayout = loadLayout
                            win.addView(doc)

                    QTimer.singleShot(100, cb)

                except:
                    pass

    def handleSplitter(self):
        helper = self._helper
        app = helper.getApp()
        if not app:
            return

        mdi = helper.getMdi()
        central = helper.getCentral()
        isEnabled = getOpt("toggle", "split_panes")

        self.loadDefaultLayout()

        if (
            not self.isHomeScreenShowing()
            and central
            and mdi
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
            and isEnabled
        ):
            if not self._split:
                if self._loadLayout:
                    layout = self._loadLayout
                    self._loadLayout = None

                    def cb(layout=layout):
                        try:
                            assert self._split is not None
                            topSplit = self._split.topSplit()
                            if topSplit:
                                topSplit.restoreLayout(layout)
                        finally:
                            self._layoutRestored = True

                    QTimer.singleShot(100, cb)
                else:
                    self._layoutRestored = True

                self._layoutLocked = False
                self._splitData = {}
                self._activeLayoutPath = None
                self._split = Split(parent=central, controller=self)

                for i, _ in enumerate(mdi.subWindowList()):
                    self.syncView(index=i)

                self._componentTimers.shortPoll.connect(self.shortPoll)
                self._componentTimers.longPoll.connect(self.longPoll)

        elif self._split:
            try:
                self._componentTimers.shortPoll.disconnect(self.shortPoll)
                self._componentTimers.longPoll.disconnect(self.longPoll)
            except:
                pass

            self._layoutLocked = False
            self._splitData = {}
            self._split.clear(True)
            self._split = None

            qwin = helper.getQwin()
            if qwin and mdi:
                updates = qwin.updatesEnabled()
                qwin.setUpdatesEnabled(False)
                viewMode = mdi.viewMode()

                for w in mdi.subWindowList():
                    w.showMaximized()
                    if viewMode == QMdiArea.ViewMode.SubWindowView:
                        w.showNormal()
                    w.setMinimumHeight(0)
                    w.setMaximumHeight(QWIDGETSIZE_MAX)
                    w.setMinimumWidth(0)
                    w.setMaximumWidth(QWIDGETSIZE_MAX)
                qwin.setUpdatesEnabled(updates)

                def cb():
                    mdi = helper.getMdi()
                    if mdi:
                        if mdi.viewMode() == QMdiArea.ViewMode.TabbedView:
                            s = mdi.size()
                            mdi.resize(s.width() + 1, s.height())
                            mdi.resize(s)
                        else:
                            mdi.tileSubWindows()

                QTimer.singleShot(0, cb)

    def initSubWindow(self, win: QMdiSubWindow):
        helper = self._helper
        uid = win.property("uiTweaksId")

        _, view, data = helper.getViewSubWindow(uid)

        if not (view and data):
            return

        interceptor = data.get("viewInterceptor", None)
        callbacks = data.get("viewInterceptorCallbacks", None)

        if not (interceptor and callbacks):

            def destroy(_=None, uid=uid):
                if self._split:
                    self.onSubWindowDestroyed(uid)

            def resize(_=None, uid=uid):
                self.onSubWindowResized(uid)

            def scroll(_=None, uid=uid):
                self.onSubWindowScrolled(uid)

            callbacks = {
                "resized": resize,
                "scrolled": scroll,
                "destroyed": destroy,
            }

            interceptor = EventInterceptor(
                callbacks={
                    "destroyed": callbacks.get("destroyed"),
                    "resized": callbacks.get("resized"),
                }
            )

            helper.setViewData(view, "viewInterceptor", interceptor)
            helper.setViewData(view, "viewInterceptorCallbacks", callbacks)

        win.installEventFilter(interceptor)

        for bar in self._helper.getScrollBars(win):
            if isinstance(bar, QScrollBar):
                bar.valueChanged.connect(callbacks["scrolled"])

    def colors(self):
        return self._colors

    def adjustedColors(self):
        return self._adjustedColors

    def toggleStyles(self):
        if getOpt("toggle", "split_panes"):
            self.attachStyles()
        else:
            self.detachStyles()

    def detachStyles(self):
        app = typing.cast(QApplication, QApplication.instance())
        css = app.styleSheet()
        match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
        match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
        css = re.sub(
            rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
        )
        app.setStyleSheet(css)

    def attachStyles(self):
        if not getOpt("toggle", "split_panes"):
            return

        helper = self._helper
        useDarkIcons = helper.useDarkIcons()
        winColor = helper.paletteColor("Window")
        textColor = helper.paletteColor("Text")
        hlColor = helper.paletteColor("Highlight")
        closeIcon = (
            ":/dark_close-tab.svg" if useDarkIcons else ":/light_close-tab.svg"
        )

        self._colors = (
            ColorScheme(
                bar=winColor.darker(130).name(),
                tab=winColor.darker(120).name(),
                tabSeparator=winColor.darker(170).name(),
                tabSelected=winColor.lighter(120).name(),
                tabActive=hlColor.name(),
                tabText=textColor.name(),
                tabClose=QColor("lightcoral").name(),
                menuSeparator=textColor.name(),
                splitHandle=winColor.name(),
                dropZone=hlColor.name(),
                dragTab=hlColor.name(),
            )
            if useDarkIcons
            else ColorScheme(
                bar=winColor.darker(150).name(),
                tab=winColor.darker(120).name(),
                tabSeparator=winColor.lighter(140).name(),
                tabSelected=winColor.lighter(130).name(),
                tabActive=hlColor.name(),
                tabText=textColor.name(),
                tabClose=QColor("darkred").name(),
                menuSeparator=textColor.darker(150).name(),
                splitHandle=winColor.name(),
                dropZone=hlColor.name(),
                dragTab=hlColor.name(),
            )
        )

        colors = replace(self._colors)
        for f in fields(colors):
            override = getOpt("colors", f.name)
            if override:
                setattr(colors, f.name, override)
        self._adjustedColors = colors

        hideFloatingMessage = ""
        if getOpt("toggle", "hide_floating_message"):
            hideFloatingMessage = """
                QMdiArea KisFloatingMessage {
                    opacity: 0;
                    min-width: 0;
                    max-width: 0;
                    min-height: 0;
                    max-height: 0;
                }
            """

        tabBarHeight = getOpt("tab_behaviour", "tab_height")
        tabFontSize = getOpt("tab_behaviour", "tab_font_size")
        tabFontBold = (
            "bold" if getOpt("tab_behaviour", "tab_font_bold") else "normal"
        )
        style = f"""
                /* KRITA_UI_TWEAKS_STYLESHEET_BEGIN */
                QMainWindow::separator:vertical {{
                    background: transparent;
                }}
                {hideFloatingMessage}
                QMenu[class="splitPaneMenu"] {{
                    padding-top: 10px;
                    padding-bottom: 10px;
                }}
                QMenu[class="splitPaneMenu"]::separator {{
                    height: 1px;
                    margin: 10px 0;
                    background: {colors.menuSeparator};
                }}
                QMdiArea QTabBar, QMdiArea QTabBar::tab {{
                    min-height: 0;   
                    max-height: 0;
                }}
                SplitToolbar QPushButton[class="menuButton"] {{
                    background: {colors.bar};
                    border: none;
                    min-height: {tabBarHeight}px;   
                    max-height: {tabBarHeight}px;
                }}
                QMdiArea SplitTabs {{
                    qproperty-drawBase: 0;
                    background: {colors.bar};      
                    min-height: {tabBarHeight}px;   
                    max-height: {tabBarHeight}px;
                    border: 0;
                    margin: 0;
                    padding: 0;
                    padding-right: 50px;
                }}
                QMdiArea SplitTabs QToolButton {{
                    border: none;
                    background: {colors.bar};      
                }}
                QMdiArea SplitTabs::tab {{
                    min-width: 1px; 
                    max-width: 400px; 
                    font-size: {tabFontSize}px;
                    font-weight: {tabFontBold};
                    height: {tabBarHeight}px;     
                    min-height: {tabBarHeight}px;   
                    max-height: {tabBarHeight}px;
                    background: {colors.tab};
                    border-radius: 0;
                    border: 1px solid {colors.tab};
                    border-right: 1px solid {colors.tabSeparator};
                    padding: 0px 12px;
                }}
                QMdiArea SplitTabs::tab:last {{
                    border-right: 1px solid {colors.tabSeparator};
                }}
                QMdiArea SplitTabs::tab:selected {{
                    background: {colors.tabSelected}; 
                    border: 1px solid {colors.tabSelected};
                    border-right: 1px solid {colors.tabSelected};
                }}
                QMdiArea SplitTabs::close-button {{
                    image: url({closeIcon});
                    padding: 2px;
                    background: none;
                }}
                QMdiArea SplitTabs QAbstractButton[hover="true"] {{
                    background-color: {colors.tabClose};
                }}
                QMdiArea SplitTabs::close-button:pressed {{
                    background-color: red;
                }}
                QMdiArea SplitTabs::tear {{
                    width: 0px; 
                    border: none;
                }}
                QMdiArea SplitTabs[class="active"]::tab:selected {{
                    background: {colors.tabActive}; 
                    border: 1px solid {colors.tabActive};
                    border-right: 1px solid {colors.tabActive};
                }}
                /* KRITA_UI_TWEAKS_STYLESHEET_END */
            """

        # NOTE
        # needs to be attached on app at startup,
        # for config changes it should attach to mdi (faster and more stable)

        app = typing.cast(QApplication, QApplication.instance())
        mdi = self._helper.getMdi()
        widget = mdi if mdi else app

        if widget:
            css = widget.styleSheet()
            match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
            match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
            css = re.sub(
                rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
            )
            widget.setStyleSheet(css + style)

    def onWindowShown(self):
        super().onWindowShown()

        app = QApplication.instance()
        self._modifiers = KeyModiferInterceptor()
        app.installEventFilter(self._modifiers)

        self.handleSplitter()

    def onViewModeChanged(self):
        super().onViewModeChanged()
        self.handleSplitter()

    def onHomeScreenToggled(self, visible: bool = False):
        super().onHomeScreenToggled(visible)
        self.handleSplitter()

    def onThemeChanged(self):
        topSplit = self.topSplit()
        if not topSplit:
            return

        self.attachStyles()
        # just use resize to refresh the icons to avoid a second iteration
        topSplit.onResize(force=True, refreshIcons=True)

    def onViewChanged(self):
        super().onViewChanged()
        helper = self._helper
        mdi = helper.getMdi()
        view = helper.getView()
        if mdi and view:
            activeWin = mdi.activeSubWindow()
            winList = mdi.subWindowList()
            if activeWin and winList:

                # NOTE
                # initializing this here now,
                # so it also works in subwindow mode
                # since toolbar actions need the id
                uid = activeWin.property("uiTweaksId")
                if not uid:
                    uid = helper.uid()
                    activeWin.setProperty("uiTweaksId", uid)
                helper.setViewData(view, "uiTweaksId", uid)

                self.initSubWindow(activeWin)

                activeIndex = winList.index(activeWin)
                if self.topSplit():
                    self.syncView(index=activeIndex)

    def onSubWindowDestroyed(self, uid: int | None) -> None:
        self.winClosed.emit(uid)
        split = self.getSplitByUid(uid)
        data = self.popSplitData(uid)
        if split and data:
            tabs = self._helper.isAlive(split.tabs(), SplitTabs)
            if tabs:
                splitTabIndex = tabs.getTabByView(data.view)
                if splitTabIndex != -1:
                    tabs.removeTab(splitTabIndex)
            split.checkShouldClose()

    def onSubWindowResized(self, uid: int | None) -> None:
        self.winResized.emit(uid)

    def onSubWindowScrolled(self, uid: int | None) -> None:
        self.winScrolled.emit(uid)

    def setDragSplit(self, split: "Split|None"):
        self._dragSplit = split

    def dragSplit(self):
        return self._dragSplit

    def topSplit(self) -> "Split | None":
        central = self._helper.getCentral()
        if central:
            return central.findChild(Split)

    def defaultSplit(self, checkToolbar: bool = True) -> "Split | None":
        if checkToolbar:
            toolbar = self._helper.isAlive(self._activeToolbar, SplitToolbar)
            if toolbar:
                return toolbar.split()

        topSplit = self.topSplit()
        if topSplit:
            return topSplit.firstMostSplit()

    def nextTab(self):
        split = self.defaultSplit()
        if split:
            tabs = split.tabs()
            if tabs:
                tabs.nextTab()

    def prevTab(self):
        split = self.defaultSplit()
        if split:
            tabs = split.tabs()
            if tabs:
                tabs.prevTab()

    def formatTabText(self, index: int, doc: Document) -> str:
        tabs = self._helper.getTabBar()
        if not tabs:
            return ""

        tabText = tabs.tabText(index)
        if getOpt("tab_behaviour", "tab_hide_filesize"):
            name = os.path.basename(doc.fileName())
            if not name.strip():
                name = i18n("[Not saved]")
            mod = " *" if doc.modified() else ""
            tabText = f"{name}{mod}"

        maxChars = getOpt("tab_behaviour", "tab_max_chars")
        if len(tabText) > maxChars:
            ellipsis = "…" if getOpt("tab_behaviour", "tab_ellipsis") else ""
            tabText = f"{ellipsis}{tabText[-maxChars:]}"
        return tabText

    def setActiveToolbar(self, curr: SplitToolbar | None = None):
        top = self.topSplit()
        self._activeToolbar = self._helper.isAlive(
            self._activeToolbar, SplitToolbar
        )
        if not top or top.state() == Split.STATE_COLLAPSED:
            if self._activeToolbar:
                self._activeToolbar.tabs().setActiveHighlight(False)
            if top:
                self._activeToolbar = top.toolbar()
            else:
                self._activeToolbar = None
        elif curr:
            if self._activeToolbar and self._activeToolbar != curr:
                self._activeToolbar.tabs().setActiveHighlight(False)

            if top.state() == Split.STATE_SPLIT:
                self._activeToolbar = curr
                self._activeToolbar.tabs().setActiveHighlight(True)
            else:
                self._activeToolbar = None

    def isSyncing(self):
        return self._syncing

    @contextmanager
    def syncedCall(self, force: bool = False):
        if self._syncing and not force:
            yield False
            return

        helper = self._helper
        qwin = helper.getQwin()
        mdi = helper.getMdi()
        win = helper.getWin()

        if not (qwin and mdi and win):
            yield False
            return

        syncing = self._syncing
        self._syncing = True
        updates = qwin.updatesEnabled()
        qwin.setUpdatesEnabled(False)
        try:
            yield True
        finally:
            qwin.setUpdatesEnabled(updates)
            self._syncing = syncing

    def isSyncing(self):
        return self._syncing

    def syncView(
        self,
        index: int | None = None,
        split: "Split|None" = None,
        view: View | None = None,
        document: Document | None = None,
        addView: bool = False,
        makeCurrent: bool = True,
    ):
        if self._syncing or self._quit:
            return

        with self.syncedCall() as sync:
            if not sync:
                return

            helper = self._helper

            mdi = helper.getMdi()
            qwin = helper.getQwin()
            win = helper.getWin()

            assert mdi is not None
            assert qwin is not None
            assert win is not None

            if addView:
                if not isinstance(document, Document):
                    if not isinstance(view, View):
                        return
                    document = view.document()
                view = win.addView(document)
                index = mdi.subWindowList().index(mdi.activeSubWindow())
                view = None

            tabs = helper.getTabBar()
            if not tabs:
                return

            if view is not None:
                index = self.getIndexByView(view)
                if index == -1:
                    return

            if index is None:
                return

            uid = self.getUid(index)

            if uid is not None:
                data = self.getSplitData(uid)
                defaultSplit = self.defaultSplit()
                activeWin = mdi.subWindowList()[index]

                if makeCurrent or data is None:
                    makeCurrent = True
                    mdi.setActiveSubWindow(activeWin)
                    activeView = helper.getView()
                else:
                    activeView = data.view

                if not activeView:
                    return

                helper.setViewData(activeView, "uiTweaksId", uid)

                if (
                    defaultSplit
                    and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
                ):

                    addTab = False
                    if data is None:
                        data = SplitData(
                            view=activeView,
                            win=activeWin,
                            toolbar=(
                                split.toolbar()
                                if split
                                else defaultSplit.toolbar()
                            ),
                            custom={},
                        )

                        addTab = True
                    else:
                        attachedSplit = helper.isAlive(
                            data.toolbar.split() if data.toolbar else None,
                            Split,
                        )
                        split = helper.isAlive(split, Split)
                        if attachedSplit and split and split != attachedSplit:
                            attachedTabs = attachedSplit.tabs()
                            if attachedTabs:
                                splitTabIndex = attachedTabs.getTabByView(
                                    data.view
                                )
                                if splitTabIndex != -1:
                                    attachedTabs.removeTab(splitTabIndex)
                            data.toolbar = split.toolbar()
                            addTab = True

                    toolbar = helper.isAlive(data.toolbar, SplitToolbar)
                    if toolbar:
                        toolbarSplit = helper.isAlive(toolbar.split(), Split)
                        assert toolbarSplit is not None
                        toolbarTabs = toolbar.tabs()
                        splitTabIndex = -1
                        if addTab:
                            self.setSplitData(uid, data)

                            tabText = self.formatTabText(
                                index, data.view.document()
                            )

                            splitTabIndex = toolbarTabs.addTab(
                                tabs.tabIcon(index), tabText
                            )
                            if splitTabIndex != -1:
                                toolbarTabs.setUid(splitTabIndex, uid)

                            self.savePreviousLayout()
                        else:
                            splitTabIndex = toolbarTabs.getTabByView(data.view)

                        if splitTabIndex != -1 and makeCurrent:
                            toolbarTabs.setCurrentIndex(splitTabIndex)

                        if toolbarSplit:
                            topSplit = toolbarSplit.topSplit()
                            if topSplit:
                                topSplit.onResize(force=True)

                            if makeCurrent:
                                data.win.raise_()
                                data.win.show()
                                ts = toolbar.split()
                                tp = ts.parent()
                                if isinstance(tp, Split):
                                    self.setActiveToolbar(toolbar)
                                else:
                                    self.setActiveToolbar(toolbar)

    def getUid(self, index: int | None) -> int | None:
        if index is not None:
            helper = self._helper
            mdi = helper.getMdi()
            if not mdi:
                return
            subwindows = mdi.subWindowList()
            if index >= 0 and index < len(subwindows):
                win = subwindows[index]
                uid = win.property("uiTweaksId")
                if not uid:
                    uid = helper.uid()
                    win.setProperty("uiTweaksId", uid)
                return uid

    def getSplitData(self, uid: int | None) -> SplitData | None:
        if uid is not None:
            return self._splitData.get(uid, None)

    def setSplitData(self, uid: int | None, data: Any) -> SplitData | None:
        if uid is not None:
            self._splitData[uid] = data

    def getSplitDataByIndex(self, index: int) -> SplitData | None:
        uid = self.getUid(index)
        return self.getSplitData(uid)

    def getSplitDataByWindow(
        self, win: QMdiSubWindow | None
    ) -> SplitData | None:
        index = self.getIndexByWindow(win)
        return self.getSplitDataByIndex(index)

    def getSplitDataByView(self, view: View | None) -> SplitData | None:
        index = self.getIndexByView(view)
        return self.getSplitDataByIndex(index)

    def popSplitData(self, uid: int | None) -> SplitData | None:
        if uid is not None:
            return self._splitData.pop(uid, None)

    def getIndexByView(self, view: View | None) -> int:
        mdi = self._helper.getMdi()
        if not mdi:
            return -1
        data = self._helper.getViewData(view)
        uid = data.get("uiTweaksId", None) if data else None
        if uid is not None:
            for i, w in enumerate(mdi.subWindowList()):
                if w.property("uiTweaksId") == uid:
                    return i
        return -1

    def getIndexByWindow(self, win: QMdiSubWindow | None) -> int:
        mdi = self._helper.getMdi()
        try:
            assert mdi is not None
            assert win is not None
            ret = mdi.subWindowList().index(win)
            return ret
        finally:
            return -1

    def getToolbarByView(self, view: View | None) -> SplitToolbar | None:
        if view is not None:
            data = self._helper.getViewData(view)
            uid = data.get("uiTweaksId", None) if data else None
            data = self.getSplitData(uid)
            return (
                self._helper.isAlive(data.toolbar, SplitToolbar)
                if data
                else None
            )

    def getToolbarByWindow(
        self, win: QMdiSubWindow | None
    ) -> SplitToolbar | None:
        win = self._helper.isAlive(win, QMdiSubWindow)
        if win:
            uid = win.property("uiTweaksId")
            data = self.getSplitData(uid)
            return (
                self._helper.isAlive(data.toolbar, SplitToolbar)
                if data
                else None
            )

    def getSplitByView(self, view: View | None) -> "Split | None":
        toolbar = self.getToolbarByView(view)
        if toolbar:
            return self._helper.isAlive(toolbar.split(), Split)

    def getSplitByWindow(self, win: QMdiSubWindow | None) -> "Split | None":
        toolbar = self.getToolbarByWindow(win)
        if toolbar:
            return self._helper.isAlive(toolbar.split(), Split)

    def getSplitByUid(self, uid: int | None = None) -> "Split | None":
        helper = self._helper
        # Note that this route deliberately
        # skips going through view or window
        # for cases where those have been destroyed
        if isinstance(uid, int):
            data = self._splitData.get(uid, None)
            if data:
                toolbar = helper.isAlive(data.toolbar, SplitToolbar)
                return helper.isAlive(
                    toolbar.split() if toolbar else None, Split
                )

    def debugMsg(self, msg: Any, clear: bool = False):
        helper = self._helper
        qwin = helper.getQwin()

        if not qwin:
            return

        self._debugId += 1
        if msg:
            msg = f"{self._debugId}: {msg}"
        else:
            msg = ""

        self._all = getattr(self, "_all", "")
        if clear:
            self._all = ""
        self._all = f"{msg} ____ {self._all}"[:500]

        if getattr(self, "_msg", None) is None:
            self._debugMsg = SplitDragRect(
                parent=qwin, text=msg, color=helper.paletteColor("Window")
            )
            self._debugMsg.setTextAlign(Qt.AlignmentFlag.AlignLeft)

        self._debugMsg.setText(self._all)
        self._debugMsg.show()
        self._debugMsg.raise_()
        self._debugMsg.setGeometry(700, 0, qwin.width() - 700, 23)

