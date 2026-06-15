# SPDX-License-Identifier: CC0-1.0

from ..pyqt import (
    QWIDGETSIZE_MAX,
    pyqtSignal,
    qChecksum,
    toPoint,
    getEventPos,
    getEventGlobalPos,
    Qt,
    QPoint,
    QApplication,
    QEvent,
    QMdiArea,
    QObject,
    QWidget,
    QMdiSubWindow,
    QMessageBox,
    QColor,
    QTimer,
    QScrollBar,
    QFileDialog,
    QByteArray,
    QDataStream,
    QIODevice,
    QPixmap,
    QImage,
    QMenu,
    QMainWindow,
    QUrl,
    QDir,
    QDialog,
    QRect,
    QPaintEvent,
    QPainter,
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
import sys

from ..options import (
    getOpt,
    setOpt,
    showOptions,
    signals as OptionSignals,
    VERSION,
)

from ..component import Component, COMPONENT_GROUP

from ..helper import Helper
from ..i18n import i18n
from ..colors import ColorScheme, adjustColor

from .mdi_downloader import MdiDownloader
from .mdi_split import MdiSplit
from .mdi_split_pane import MdiSplitPane

if TYPE_CHECKING:
    from ..plugin import Plugin


class MdiMessageBox(QWidget):

    def __init__(
        self,
        parent: QWidget | QMainWindow,
        color: QColor | None = None,
        altColor: QColor | None = None,
        text: str | None = None,
        textColor: QColor | None = None,
        bold: bool = False,
        shadow: bool = False,
        inset: bool = False,
        borderRadius: int = 0,
        borderColor: QColor | None = None,
    ):
        super().__init__(parent)

        self._color = QColor(10, 10, 100, 100) if color is None else color
        self._altColor = altColor
        self._text = text
        self._textColor = textColor if textColor else Qt.GlobalColor.white
        self._textAlign = Qt.AlignmentFlag.AlignCenter
        self._borderRadius = borderRadius
        self._borderColor = borderColor
        self._inset = inset
        self._bold = bold
        if shadow:
            self._shadow = QGraphicsDropShadowEffect()
            self._shadow.setBlurRadius(16)
            self._shadow.setOffset(2, 2)
            self._shadow.setColor(QColor(0, 0, 0, 80))
            self.setGraphicsEffect(self._shadow)

    def setText(self, text: str | None):
        self._text = text
        self.update()

    def setTextAlign(self, align: Qt.AlignmentFlag):
        self._textAlign = align
        self.update()

    def setColor(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if self._borderRadius == 0:
            p.fillRect(rect, self._color)
        else:
            p.setBrush(self._color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, self._borderRadius, self._borderRadius)

            if self._inset:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, 50), 1))
                p.drawRoundedRect(
                    rect.adjusted(1, 1, -1, -1),
                    self._borderRadius,
                    self._borderRadius,
                )

            if self._borderColor:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(self._borderColor, 2))
                p.drawRoundedRect(
                    rect, self._borderRadius + 1, self._borderRadius + 1
                )

        if self._altColor:
            stripe_width = 5
            pen = QPen(self._altColor, stripe_width * 2)
            p.setPen(pen)

            w, h = rect.width(), rect.height()
            for x in range(-h, w, stripe_width * 2):
                p.drawLine(x, 0, x + h, h)

        if self._text:
            p.setPen(self._textColor)
            font = p.font()

            if self._bold:
                font.setBold(True)

            font.setPixelSize(16)
            p.setFont(font)
            p.drawText(
                self.rect(),
                self._textAlign
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                self._text,
            )


class MdiController(Component):
    activePaneChanged = pyqtSignal()

    def __init__(
        self,
        window: Window,
        plugin: "Plugin",
        pluginGroup: COMPONENT_GROUP | None = None,
        helper: Helper | None = None,
    ):
        super().__init__(window, pluginGroup=pluginGroup, helper=helper)

        self.setObjectName("MdiController")
        app = self._helper.getApp()

        self._plugin = plugin
        self._quit = False

        self._pauseEventFilter = False
        self._rootSplit: MdiSplit | None = None
        self._activeSplitPane: MdiSplitPane | None = None
        self._dirtyPanes: list[MdiSplitPane] = []

        self._layoutLocked = False
        self._currentLayoutFile = ""

        self._restoreSubWin: QMdiSubWindow | None = None
        self._handledPrefDialog = False

        self._sessionLayout = app.readSetting(
            "krita_ui_tweaks", "restoreLayout", ""
        )

        self._sessionPath = app.readSetting(
            "krita_ui_tweaks", "restoreLayoutPath", ""
        )

        # Track recent files because adding a view from pykrita does not add it to recent files
        self._recentFiles = {}

        self._colors = None
        self._adjustedColors = None

        self._optEnabled = getOpt("toggle", "split_panes")

        self._showRulers = app.readSetting("", "showrulers", "") == "true"

        self._showScrollbars = (
            app.readSetting("", "hideScrollbars", "") != "true"
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks",
            i18n("Krita UI Tweaks"),
            self.showOptions,
            menu=True,
        )

        qapp = typing.cast(QApplication, QApplication.instance())
        qapp.aboutToQuit.connect(lambda: self.onQuit())

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_next_tab",
            i18n("Goto next tab"),
            self.slotNextTab,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_prev_tab",
            i18n("Goto previous tab"),
            self.slotPreviousTab,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_save_layout_as",
            i18n("Save Layout As…"),
            self.saveLayoutFile,
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
            self.openLayoutFile,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_toggle_layout_lock",
            i18n("Toggle Layout Locked"),
            self.toggleLayoutLocked,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_equalize_layout",
            i18n("Equalize Layout"),
            self.slotEqualizeLayout,
        )

        _ = self._helper.newAction(
            window,
            "krita_ui_tweaks_reset_layout",
            i18n("Reset Layout"),
            self.slotResetLayout,
        )

    def rootSplit(self) -> MdiSplit:
        return self._helper.isAlive(self._rootSplit, MdiSplit)

    def showOptions(self):
        showOptions(self)

    def onQuit(self):
        self._quit = True

    def onWindowInit(self):
        super().onWindowInit()

        qapp = QApplication.instance()
        qapp.installEventFilter(self)

        mdi = self._helper.getMdi()
        mdi.subWindowActivated.connect(self.onSubWindowActivated)

        self.updateColors()
        self.toggleStyleSheet()

        OptionSignals.configSaved.connect(self.onConfigSave)

        QTimer.singleShot(100, self.restoreSessionLayout)
        
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        
        if sys.platform != 'darwin' and self._pauseEventFilter:
            return False
            
        mdi = self._helper.getMdi()
        qwin = self._helper.getQwin()
        split = self.rootSplit()
        eventType = event.type()
        
        if (
            not self._handledPrefDialog
            and split
            and eventType == QEvent.Type.Show
            and isinstance(obj, QDialog)
            and obj.metaObject().className() == "KisDlgPreferences"
        ):
            self._handledPrefDialog = True
            self._restoreSubWin = mdi.activeSubWindow()
            return False

        if (
            eventType == QEvent.Type.Close
            and isinstance(obj, QMainWindow)
            and obj == qwin
        ):
            self.saveSessionLayout()
            self.saveRecentFiles()
            return False

        if split is None or mdi is None:
            return False

        if (
            eventType == QEvent.Type.Show
            and isinstance(obj, QMenu)
            and obj.objectName() == "drop_popup"
        ):
            qwin = self._helper.getQwin()
            if qwin is not None:
                menuPos = obj.pos()
                eventPane = self.paneAtGlobalPos(menuPos)
                if eventPane is not None:
                    self.setActiveSplitPane(eventPane)
            return False

        if eventType in (
            QEvent.Type.DragEnter,
            QEvent.Type.DragMove,
            QEvent.Type.Drop,
        ):
            qwin = self._helper.getQwin()
            globalPos = obj.mapToGlobal(toPoint(getEventPos(event)))
            pos = qwin.mapFromGlobal(globalPos)
            accepts = False
            data = event.mimeData()

            targetSplit = None
            eventPane = self.paneAtGlobalPos(globalPos)

            if eventPane is not None and eventPane.isEmpty():
                if eventType == QEvent.Type.Drop:
                    self.setActiveSplitPane(eventPane)

                if data.hasImage() or data.hasUrls():
                    accepts = True

            if accepts:
                event.acceptProposedAction()
                if eventType == QEvent.Type.Drop:
                    try:
                        files = []
                        urls = []
                        if data.hasUrls():
                            for url in data.urls():
                                if url.isLocalFile():
                                    files.append(url.toLocalFile())
                                else:
                                    urls.append(url.toString())

                        app = self._helper.getApp()
                        docs = self._helper.getDocsByFile()

                        def processFile(
                            filePath,
                            modify=False,
                            docs=docs,
                            eventPane=eventPane,
                        ):
                            helper = self._helper
                            handled = False
                            win = self._helper.getWin()

                            if filePath in docs:
                                doc = docs[filePath].doc
                                if helper.isAlive(doc, Document):
                                    handled = True
                                    self.openView(doc, eventPane)

                            if not handled:
                                if os.path.exists(typing.cast(str, filePath)):
                                    doc = app.openDocument(filePath)
                                    if doc:
                                        if modify:
                                            doc.setModified(True)
                                        docs[filePath] = SimpleNamespace(
                                            doc=doc
                                        )
                                        self.openView(doc, eventPane)

                        def processDownload(
                            success, tmpFile, url, errorString
                        ):
                            if success:
                                processFile(tmpFile, True)
                                try:
                                    os.remove(tmpFile)
                                except:
                                    pass
                            else:
                                QMessageBox.warning(
                                    None, i18n("Download Failed"), errorString
                                )
                            pass

                        for f in files:
                            processFile(f)

                        if urls:
                            choice = QMessageBox.question(
                                None,
                                "Krita",
                                i18n("Download the following urls?")
                                + "\n\n"
                                + "\n".join(urls),
                                QMessageBox.StandardButton.No
                                | QMessageBox.StandardButton.Yes,
                                QMessageBox.StandardButton.No,
                            )

                            if choice == QMessageBox.StandardButton.Yes:
                                dl = MdiDownloader(callback=processDownload)
                                dl.download(urls)
                    finally:
                        return True
            else:
                event.ignore()

            return False

        if (
            eventType == QEvent.Type.Resize
            and split is not None
            and obj == mdi.viewport()
        ):
            split.setGeometry(mdi.viewport().rect())
            return False

        if (
            split is not None
            and mdi is not None
            and eventType
            in (
                QEvent.Type.MouseButtonPress,
                QEvent.Type.TabletPress,
                QEvent.Type.TouchBegin,
            )
            and isinstance(obj, QWidget)
            and mdi.isAncestorOf(obj)
        ):
            globalPos = toPoint(getEventGlobalPos(event))
            if globalPos:
                sw = mdi.activeSubWindow()
                subWinPane = self.paneBySubWindow(sw)
                eventPane = self.paneAtGlobalPos(globalPos)
                # Workaround to set the active pane for when the sub-window is already active (subWindowActivated does not fire)
                # The active pane can also be an empty pane, it is not strictly tied to the active sub-window
                if eventPane is not None and eventPane == subWinPane:
                    self.setActiveSplitPane(eventPane)
            return False

        return False

    def onViewModeChanged(self):
        super().onViewModeChanged()
        self.toggleSplitter()

    def onViewChanged(self):
        paused = self._pauseEventFilter
        self._pauseEventFilter = True
        super().onViewChanged()
        helper = self._helper
        mdi = helper.getMdi()
        view = helper.getView()
        win = helper.getWin()
        if mdi is not None and view is not None and win is not None:
            activeSubWin = mdi.activeSubWindow()
            subWinList = mdi.subWindowList()
            if activeSubWin is not None and subWinList:
                uid = activeSubWin.property("uiTweaksId")

                # only handle windows not yet added
                if not uid:
                    uid = helper.uid()
                    activeSubWin.setProperty("uiTweaksId", uid)
                    helper.setViewData(view, "uiTweaksId", uid)

                    if self.rootSplit() is not None:
                        self.syncSubWindow(activeSubWin, True)

                isEnabled = (
                    getOpt("toggle", "split_panes")
                    and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
                )

                if isEnabled:
                    self.toggleSplitter()
                    
        self._pauseEventFilter = paused

    def onSubWindowActivated(self, sw):
        paused = self._pauseEventFilter
        self._pauseEventFilter = True
        mdi = self._helper.getMdi()
        rootSplit = self.rootSplit()
        subWins = mdi.subWindowList() if mdi is not None else None

        if (
            self._helper.isAlive(self._restoreSubWin, QMdiSubWindow)
            and rootSplit
            and sw != self._restoreSubWin
            and mdi is not None
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
        ):

            # XXX hack

            def restore(reset=True):
                mdi = self._helper.getMdi()
                if mdi is not None:
                    sw = self._restoreSubWin
                    alive = self._helper.isAlive(sw, QMdiSubWindow)
                    if reset or not alive:
                        self._restoreSubWin = None
                    if alive:
                        mdi.setActiveSubWindow(sw)
                        pane = self.activeSplitPane()
                        if pane is not None:
                            pane.activateCurrentSubWindow(True)

            QTimer.singleShot(0, lambda cb=restore: cb(False))

            self._helper.debounceCallback(
                "resetWin", restore, timeout_seconds=0.5
            )

        elif sw is not None:
            activePane = self.activeSplitPane()
            if activePane:
                activePane.resizeSubWindow(sw, forceResize = True)

            if rootSplit is not None:
                rootSplit.refreshLayout()
        else:
            self.toggleSplitter()

        self._pauseEventFilter = paused
        
    def toggleSplitter(self):

        helper = self._helper
        mdi = helper.getMdi()
        app = helper.getApp()

        isEnabled = getOpt("toggle", "split_panes")
        subWins = mdi.subWindowList() if mdi is not None else None
        restoreLayout = None

        if (
            mdi is not None
            and mdi.viewMode() == QMdiArea.ViewMode.TabbedView
            and isEnabled
            and subWins
        ):
            rootSplit = self.rootSplit()
            if rootSplit is None:
                self._rootSplit = MdiSplit(mdi.viewport(), controller=self)
                self.setActiveSplitPane(self._rootSplit.firstMostPane())
                mdi.viewport().installEventFilter(self)

                if subWins:
                    for sw in subWins:
                        sw.showNormal()
                        activePane = self.activeSplitPane()
                        if activePane is not None:
                            self.syncSubWindow(sw, True)

                mdi.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )

                mdi.setVerticalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                )

                self._rootSplit.show()
                self._rootSplit.setGeometry(mdi.viewport().rect())

                self._rootSplit.resetHandle()
                self._rootSplit.refreshSplitSizes()

                self._componentTimers.shortPoll.connect(self.shortPoll)
                self._componentTimers.longPoll.connect(self.longPoll)

            if self._plugin._sessionRestore:
                try:
                    layout = self._plugin._sessionRestore
                    self._plugin._sessionRestore = None
                    self.restoreSplitState(layout)
                except:
                    self._plugin._sessionRestore = None
                    pass

        elif self.rootSplit() is not None:
            try:
                self._componentTimers.shortPoll.disconnect(self.shortPoll)
                self._componentTimers.longPoll.disconnect(self.longPoll)
            except:
                pass

            self._layoutLocked = False
            self._currentLayoutFile = ""
            self._rootSplit.hide()
            self._rootSplit.deleteLater()
            self._rootSplit = None
            self.setActiveSplitPane(None)

            if subWins:
                for sw in subWins:
                    sw.showMaximized()
                    if mdi.viewMode() == QMdiArea.ViewMode.SubWindowView:
                        flags = sw.windowFlags()
                        flags &= ~Qt.WindowType.FramelessWindowHint
                        sw.setWindowFlags(flags)
                        sw.showNormal()
                    sw.setMinimumHeight(0)
                    sw.setMaximumHeight(QWIDGETSIZE_MAX)
                    sw.setMinimumWidth(0)
                    sw.setMaximumWidth(QWIDGETSIZE_MAX)

                QTimer.singleShot(0, lambda mdi=mdi: mdi.tileSubWindows())

            if mdi is not None:
                mdi.setHorizontalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAsNeeded
                )
                mdi.setVerticalScrollBarPolicy(
                    Qt.ScrollBarPolicy.ScrollBarAsNeeded
                )

    def setActiveSubWindow(self, sw: QMdiSubWindow):
        mdi = self._helper.getMdi()
        if mdi is not None:
            mdi.setActiveSubWindow(sw)

    def redrawDirtyPanes(self):
        for p in self._dirtyPanes:
            pane = self._helper.isAlive(p, MdiSplitPane)
            if pane:
                tabs = pane.tabs()
                if tabs is not None:
                    tabs.attachStyleSheet()
                pane.updateFrameBorder()
        self._dirtyPanes = []

    def setActiveSplitPane(
        self,
        pane: MdiSplitPane | None,
        focusSubWindow: bool = False,
        redraw: bool = True,
    ):
        oldPane = self._helper.isAlive(self._activeSplitPane, MdiSplitPane)
        newPane = self._helper.isAlive(pane, MdiSplitPane)

        if oldPane == newPane:
            return

        if oldPane is not None:
            oldPane.setProperty("active", None)
            if redraw and oldPane not in self._dirtyPanes:
                self._dirtyPanes.append(oldPane)

        if newPane is not None:
            root = self.rootSplit()
            if root is not None and root.isSplitState():
                newPane.setProperty("active", True)
            newPane.activateCurrentSubWindow(focusSubWindow)
            if redraw and newPane not in self._dirtyPanes:
                self._dirtyPanes.append(newPane)

        self._helper.debounceCallback(
            "setActiveSplitPane", self.redrawDirtyPanes, timeout_seconds=0.5
        )

        self._activeSplitPane = newPane
        self.activePaneChanged.emit()

    def activeSplitPane(self):
        split = self.rootSplit()

        if split is not None:
            activePane = self._helper.isAlive(
                self._activeSplitPane, MdiSplitPane
            )
            if activePane is not None:
                tabBar = activePane.tabs()
                if tabBar is not None:
                    return activePane

            pane = split.firstMostPane()
            if pane is not None:
                self.setActiveSplitPane(pane)

        else:
            self._activeSplitPane = None

        return self._activeSplitPane

    def openView(
        self, doc: Document, pane: MdiSplitPane | None = None
    ) -> View | None:
        win = self._helper.getWin()
        if win is not None and isinstance(doc, Document):
            if pane is not None:
                self.setActiveSplitPane(pane, False, False)

            paused = self._pauseEventFilter
            self._pauseEventFilter = True
            view = win.addView(doc)
            self._pauseEventFilter = paused
            path = doc.fileName()
            if path and os.path.exists(path):
                self._recentFiles[path] = datetime.now()

            return view

    # From python plugin Krita only updates the recent files on restart
    # So this is only called when Krita exits
    def saveRecentFiles(self):
        if not self._recentFiles:
            return

        try:
            recents = sorted(
                self._recentFiles, key=self._recentFiles.get, reverse=True
            )

            app = self._helper.getApp()
            maxEntries = int(
                app.readSetting("RecentFiles", "maxRecentFileItems", "0")
            )

            for i in range(0, maxEntries):
                if len(recents) >= maxEntries:
                    break
                f = app.readSetting("RecentFiles", f"File{i+1}", "")
                if not f or not os.path.exists(f):
                    continue
                recents.append(f)

            recents = recents[:maxEntries]
            idx = 1

            for f in recents:
                if f and os.path.exists(f):
                    n = os.path.basename(f)
                    home = QDir.homePath()
                    if f.startswith(home):
                        f = f.replace(home, "$HOME", 1)
                    app.writeSetting("RecentFiles", f"File{idx}", f)
                    app.writeSetting("RecentFiles", f"Name{idx}", n)
                    idx += 1
        except:
            pass

    def syncSubWindow(
        self, sw: QMdiSubWindow | None = None, add: bool = False
    ):
        if add:
            pane = self.activeSplitPane()
            if pane is not None:
                pane.addSubWindow(sw)

    def saveSessionLayout(self):
        try:
            if self._quit:
                return

            qwin = self._helper.getQwin()
            app = self._helper.getApp()
            if app is None or qwin is None:
                return

            if not self.rootSplit() or not getOpt("toggle", "restore_layout"):
                app.writeSetting("krita_ui_tweaks", "restoreLayout", "")
                return

            if self._plugin:
                components = self._plugin.getValidatedComponents()

                sortedComponents = sorted(
                    components, key=lambda obj: obj["created"]
                )

                if len(sortedComponents) == 0:
                    return

                if sortedComponents[0]["controller"] != self:
                    return

            app = self._helper.getApp()
            layout = self.saveSplitState()
            files, _ = self.getLayoutFiles(layout, True)

            app.writeSetting(
                "krita_ui_tweaks",
                "restoreLayout",
                json.dumps(layout) if (layout and files) else "",
            )

            app.writeSetting(
                "krita_ui_tweaks",
                "restoreLayoutPath",
                (
                    self._currentLayoutFile
                    if (self._currentLayoutFile and layout and files)
                    else ""
                ),
            )

        except Exception as e:
            pass

    def restoreSessionLayout(self, force=False):
        try:
            if self._plugin._sessionWasRestored:
                return

            self._plugin._sessionWasRestored = True

            app = self._helper.getApp()
            mdi = self._helper.getMdi()
            win = self._helper.getWin()
            central = self._helper.getCentral()

            if app.readSetting("", "sessionOnStartup", "") == "0" and getOpt(
                "toggle", "restore_layout"
            ):
                if (
                    app is None
                    or mdi is None
                    or central is None
                    or win is None
                ):
                    return

                if mdi.viewMode() != QMdiArea.ViewMode.TabbedView:
                    return

                try:
                    layout = json.loads(self._sessionLayout)
                except:
                    layout = None

                if not layout:
                    return

                layoutPath = self._sessionPath
                files, _ = self.getLayoutFiles(layout)

                if not files:
                    return

                docs = self._helper.getDocsByFile()
                self._plugin._sessionRestore = layout

                if files[0] in docs:
                    self.openView(docs[files[0]].doc)
                else:
                    doc = app.openDocument(files[0])
                    if doc:
                        self.openView(doc)

        except Exception as e:
            self._plugin._sessionRestore = False
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n(
                    f"An unexpected error occurred trying to load previous session.\n\n{e}"
                ),
            )

    def getLayoutFiles(
        self, layout: dict[Any, Any] | None, dbg=False
    ) -> tuple[list[str], list[str]]:
        exists = []
        missing = []

        if not layout:
            return exists, missing

        try:
            state = layout.get("state", None)
            if state == "s":
                exists, missing = self.getLayoutFiles(layout["layout"])
            elif state == "c":
                for f in layout["files"]:
                    if os.path.exists(f):
                        exists.append(f)
                    else:
                        missing.append(f)
            elif state in ("v", "h"):
                exists_first, missing_first = self.getLayoutFiles(
                    layout["first"]
                )
                exists_second, missing_second = self.getLayoutFiles(
                    layout["second"]
                )
                exists = list(set(exists_first + exists_second))
                missing = list(set(missing_first + missing_second))
        except:
            exists = []
            missing = []

        return exists, missing

    def _refreshRulers(self):
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            app = self._helper.getApp()
            mdi = self._helper.getMdi()
            rulers = self._showRulers
            self._showRulers = app.readSetting("", "showrulers", "") == "true"
            if mdi and rulers != self._showRulers:
                for w in mdi.subWindowList():
                    for r in w.findChildren(QWidget):
                        if r.metaObject().className() == "KoRuler":
                            r.setVisible(self._showRulers)

    def _refreshScrollbars(self):
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            app = self._helper.getApp()
            mdi = self._helper.getMdi()
            show = self._showScrollbars
            self._showScrollbars = (
                app.readSetting("", "hideScrollbars", "") != "true"
            )
            if mdi and show != self._showScrollbars:
                for w in mdi.subWindowList():
                    for bar in self._helper.canvasScrollBars(w):
                        if isinstance(bar, QScrollBar):
                            bar.setVisible(self._showScrollbars)
            rootSplit.refreshSplitSizes()

    def paneBySubWindow(self, sw: QMdiSubWindow) -> "MdiSplitPane|None":
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            splitPane = None

            def cb(p: "MdiSplitPane"):
                nonlocal splitPane
                if p.subWindowIndex(sw) != -1:
                    splitPane = p

            rootSplit.eachPane(cb)
            return splitPane

    def paneByView(self, view: View) -> "MdiSplitPane|None":
        sw = self._helper.getSubWinByView(view)
        return self.paneBySubWindow(sw) if sw is not None else None

    def paneAtGlobalPos(self, globalPos: QPoint) -> "MdiSplitPane|None":
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            splitPane = None

            def cb(p: "MdiSplitPane"):
                nonlocal splitPane

                frame = typing.cast(QWidget, p.viewFrame())
                if frame is not None:
                    localPos = frame.mapFromGlobal(globalPos)
                    if frame.rect().contains(localPos):
                        splitPane = p

            rootSplit.eachPane(cb)
            return splitPane

    def slotResetLayout(self):
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            rootSplit.collapseLayout()
            self._layoutLocked = False

    def slotEqualizeLayout(self):
        rootSplit = self.rootSplit()
        if rootSplit is not None:
            rootSplit.equalizeLayout()

    def colors(self, refresh=False):
        if self._colors is None or refresh:
            helper = self._helper
            useDarkIcons = helper.useDarkIcons()
            winColor = helper.paletteColor("Window")
            textColor = helper.paletteColor("Text")
            hlColor = helper.paletteColor("Highlight")
            hlGreyScale = QColor.fromHsl(
                hlColor.hue(), 0, hlColor.lightness(), hlColor.alpha()
            )

            border = (
                winColor.darker(130) if useDarkIcons else winColor.lighter(120)
            )
            tabSeparator = (
                border
                if border.lightness() < hlGreyScale.lightness()
                else hlGreyScale
            )

            self._colors = (
                ColorScheme(
                    tab=adjustColor(winColor, lightness=0.8).name(),
                    tabSeparator=tabSeparator.name(),
                    tabSelected=adjustColor(winColor, lightness=1.2).name(),
                    tabActive=hlColor.name(),
                    tabText=textColor.name(),
                    tabClose=QColor("lightcoral").name(),
                    menuSeparator=textColor.name(),
                    dropZone=hlColor.name(),
                    dragTab=hlColor.name(),
                )
                if useDarkIcons
                else ColorScheme(
                    tab=adjustColor(winColor, lightness=0.85).name(),
                    tabSeparator=tabSeparator.name(),
                    tabSelected=adjustColor(winColor, lightness=1.3).name(),
                    tabActive=hlColor.name(),
                    tabText=textColor.name(),
                    tabClose=QColor("darkred").name(),
                    menuSeparator=adjustColor(textColor, lightness=0.5).name(),
                    dropZone=hlColor.name(),
                    dragTab=hlColor.name(),
                )
            )

        return self._colors

    def adjustedColors(self):
        return self._adjustedColors

    def updateColors(self):
        helper = self._helper
        useDarkIcons = helper.useDarkIcons()
        winColor = helper.paletteColor("Window")
        textColor = helper.paletteColor("Text")
        hlColor = helper.paletteColor("Highlight")

        self._colors = self.colors(True)

        colors = replace(self._colors)

        for f in fields(colors):
            override = getOpt("colors", f.name)
            if override:
                setattr(colors, f.name, override)

        self._adjustedColors = colors

    def onKritaConfigChanged(self):
        self._refreshScrollbars()

    def onConfigSave(self, context: dict[str, dict[str, bool]]):
        self.updateColors()

        isEnabled = getOpt("toggle", "split_panes")
        if isEnabled != self._optEnabled:
            self._optEnabled = isEnabled
            self.toggleStyleSheet()
            self.toggleSplitter()

        def updated(section, key, context=context):
            return context.get(section, {}).get(key, False)

        if any(
            updated("tab_behaviour", k)
            for k in (
                "tab_max_chars",
                "tab_hide_filesize",
                "tab_expands",
                "tab_krita_style",
            )
        ):
            app = self._helper.getApp()
            if app:
                for doc in app.documents():
                    _, f = self.updateDocumentTabs(doc)

    def shortPoll(self):
        if self._quit:
            return

        self._refreshRulers()

        doc = self._helper.getDoc()
        rootSplit = self.rootSplit()
        if doc is not None and rootSplit is not None:
            self.updateDocumentTabs(doc)

    def longPoll(self):
        if self._quit:
            return

        app = self._helper.getApp()
        rootSplit = self.rootSplit()
        if app is not None and rootSplit is not None:
            updated = False
            for doc in app.documents():
                self.updateDocumentTabs(doc, True)

    def toggleStyleSheet(self):
        if getOpt("toggle", "split_panes"):
            self._attachStyleSheet()
        else:
            self._detachStyleSheet()
        self._updateMdiLayout()

    def _detachStyleSheet(self):
        mdi = self._helper.getMdi()
        if mdi is None:
            return
        css = mdi.styleSheet()
        match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
        match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
        css = re.sub(
            rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
        )
        mdi.setStyleSheet(css)

    def _attachStyleSheet(self):
        mdi = self._helper.getMdi()
        if mdi is None:
            return

        style = f"""
            QMdiArea QTabBar, QMdiArea QTabBar::tab {{
                min-height: 0;
                max-height: 0;
            }}
        """

        css = mdi.styleSheet()
        match_first = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_BEGIN\s*\*/"
        match_last = r"/\*\s*KRITA_UI_TWEAKS_STYLESHEET_END\s*\*/"
        css = re.sub(
            rf"{match_first}.*?{match_last}", "", css, flags=re.DOTALL
        )
        mdi.setStyleSheet(
            css
            + "/* KRITA_UI_TWEAKS_STYLESHEET_BEGIN */"
            + style
            + "/* KRITA_UI_TWEAKS_STYLESHEET_END */"
        )

    def _updateMdiLayout(self):
        # hack when toggling the builtin tab bar
        central = self._helper.getCentral()
        if central is not None:
            w = central.width()
            h = central.height()
            central.resize(w - 1, h)
            central.resize(w + 1, h)
            central.resize(w, h)

    def onThemeChanged(self):
        self.updateColors()
        self.toggleStyleSheet()

    def tabTitle(self, sw) -> str:
        mdi = self._helper.getMdi()
        if mdi is None:
            return ""

        index = mdi.subWindowList().index(sw)
        if index == -1:
            return ""

        view = self._helper.getViewBySubWin(sw)
        return self.formatTabText(index, view.document()) if view else ""

    def formatTabText(self, index: int, doc: Document) -> str:
        rootSplit = self.rootSplit()
        if rootSplit is None:
            return ""

        tabs = self._helper.getDefaultTabBar()
        mdi = self._helper.getMdi()

        if tabs is None or mdi is None:
            return ""

        subWins = mdi.subWindowList()
        if index < 0 or index >= len(subWins):
            return ""

        maxChars = getOpt("tab_behaviour", "tab_max_chars")
        tabExpands = getOpt("tab_behaviour", "tab_expands")

        ellipsis = "…"
        mod = " *" if doc.modified() else ""
        name = os.path.basename(doc.fileName())
        size = ""

        if not name.strip():
            name = i18n("[Not saved]")

        if not getOpt("tab_behaviour", "tab_hide_filesize"):
            winTitle = subWins[index].windowTitle()
            fileInfo, _, _ = winTitle.rpartition("[")
            _, _, size = fileInfo.rpartition("(")
            size = f" ({size}".rstrip()

        if not tabExpands and len(name) > maxChars:
            name = f"{name[:maxChars]}{ellipsis}"

        return f"{name}{size}{mod}"

    def updateDocumentTabs(
        self, doc: Document, dbg=False
    ) -> tuple[bool, bool]:
        helper = self._helper
        tabs = helper.getDefaultTabBar()
        data = helper.getDocData(doc)
        mdi = helper.getMdi()
        rootSplit = self.rootSplit()

        if mdi is None or tabs is None or data is None or rootSplit is None:
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
        sw = helper.getSubWinByView(view)

        if sw is None:
            return (False, False)

        index = mdi.subWindowList().index(sw)

        if index == -1:
            return (False, False)

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

            def cb(pane: "MdiSplitPane"):
                nonlocal doc
                nonlocal helper

                tabs = pane.tabs()
                subWins = pane.subWindows()

                # FIXME check this condition should it be OR
                if tabs is None and subWins is None:
                    return

                for idx, sw in enumerate(subWins):
                    view = helper.getViewBySubWin(sw)
                    if view and self._helper.compareDoc(view.document(), doc):
                        tabs.setTabText(idx, tabText)

            rootSplit.eachPane(cb)

        return updatedTab, updatedFileName

    def currentLayoutName(self):
        if self._currentLayoutFile:
            return os.path.basename(self._currentLayoutFile)

        return ""

    def isLayoutLocked(self):
        return self._layoutLocked

    def setLayoutLocked(self, lock: bool):
        self._layoutLocked = lock

    def toggleLayoutLocked(self):
        self._layoutLocked = not self._layoutLocked

    def saveCurrentLayout(self):
        self.saveLayoutFile(self._currentLayoutFile)

    def saveSplitState(self) -> dict[Any, Any] | None:
        try:
            finalState = {}
            rootSplit = self.rootSplit()
            mdi = self._helper.getMdi()
            if rootSplit is not None and mdi is not None:
                finalState["state"] = "s"
                finalState["version"] = VERSION
                finalState["locked"] = self.isLayoutLocked()
                finalState["layout"] = rootSplit.saveState()
                finalState["winWidth"] = mdi.width()
                finalState["winHeight"] = mdi.height()

            return finalState
        except Exception as e:
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n(f"An unexpected error occurred.\n\n{e}"),
            )

    def restoreSplitState(self, state: dict[Any, Any]) -> bool:
        rootSplit = self.rootSplit()

        if rootSplit is None:
            return False

        if not state:
            return False

        app = self._helper.getApp()
        qwin = self._helper.getQwin()
        mdi = self._helper.getMdi()
        central = self._helper.getCentral()

        if qwin is None or mdi is None or central is None:
            return False

        if mdi.viewMode() != QMdiArea.ViewMode.TabbedView:
            return False

        for i in range(0, central.count()):
            if central.widget(i) == mdi:
                central.setCurrentIndex(i)
                break

        try:
            context = {}
            layout = state.get("layout", {})
            locked = state.get("locked", False)
            version = state.get("version", None)
            context["version"] = version
            context["winWidth"] = state.get("winWidth", None)
            context["winHeight"] = state.get("winHeight", None)
            context["callbacks"] = SimpleNamespace(
                resize=[], views=[], activate=[]
            )

            msg = MdiMessageBox(
                central,
                text=i18n("Loading…"),
                color=QColor(0, 0, 0),
                borderRadius=5,
            )
            msg.show()

            rect = QRect(0, 0, 120, 40)
            rect.moveCenter(central.rect().center())
            rect.moveBottom(central.rect().bottom() - 20)
            msg.setGeometry(rect)
            msg.raise_()

            qwin.setUpdatesEnabled(False)
            oldSubWins = mdi.subWindowList()

            if not rootSplit.restoreState(layout, context):
                msg.deleteLater()
                return False

            firstMostPane = rootSplit.firstMostPane()
            tabs = firstMostPane.tabs()
            if tabs is None:
                msg.deleteLater()
                return False

            tabs.setVisible(False)
            callbacks = context.get("callbacks", None)

            def runCallbacks(
                needsUpdate=False,
                locked=locked,
                oldSubWins=oldSubWins,
                version=version,
                callbacks=callbacks,
                qwin=qwin,
                mdi=mdi,
                rootSplit=rootSplit,
                msg=msg,
            ):
                if not self._helper.isAlive(qwin, QMainWindow):
                    return

                if not self._helper.isAlive(rootSplit, MdiSplit):
                    qwin.setUpdatesEnabled(True)
                    return

                if needsUpdate:
                    qwin.setUpdatesEnabled(True)
                    QTimer.singleShot(0, runCallbacks)
                elif callbacks.resize:
                    for cb in callbacks.resize:
                        cb()
                    callbacks.resize = None
                    qwin.setUpdatesEnabled(True)
                    QTimer.singleShot(0, runCallbacks)
                elif callbacks.views:
                    qwin.setUpdatesEnabled(False)
                    cb = callbacks.views.pop()
                    if cb:
                        cb()
                    QTimer.singleShot(0, lambda: runCallbacks(True))
                else:
                    self.setLayoutLocked(locked)

                    qwin.setUpdatesEnabled(False)
                    for sw in oldSubWins:
                        sw.close()

                    if not version:
                        self.slotEqualizeLayout()

                    def updateTabBars(p: MdiSplitPane):
                        tabs = p.tabs()
                        if tabs is not None:
                            tabs.setVisible(True)
                            tabs.slotConfigChanged()

                    rootSplit.eachPane(updateTabBars)

                    for cb in callbacks.activate:
                        cb()

                    qwin.setUpdatesEnabled(True)
                    msg.deleteLater()

            QTimer.singleShot(0, runCallbacks)

            return True

        except Exception as e:
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n(f"An unexpected error occurred.\n\n{e}"),
            )
            return False

    def saveLayoutFile(self, filename: str = ""):
        mdi = self._helper.getMdi()
        if mdi is None:
            return False

        rootSplit = self.rootSplit()
        if rootSplit is None:
            return

        splitState = self.saveSplitState()

        if not splitState:
            # TODO test
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n("An unexpected error occurred."),
            )
            return

        hasPath = filename and isinstance(filename, str)
        if not hasPath:
            filename, _ = QFileDialog.getSaveFileName(
                None, "Save JSON", "", "Layout files (*.json);;All files (*)"
            )

        if not filename:
            return

        if not filename.lower().endswith(".json"):
            filename += ".json"

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(splitState, f, ensure_ascii=False, indent=2)
                self._currentLayoutFile = filename
        except Exception as e:
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n(f"An unexpected error occurred.\n\n{e}\n\n{splitState}"),
            )

    def openLayoutFile(self):
        filename, _ = QFileDialog.getOpenFileName(
            None, "Open JSON", "", "Layout files (*.json);;All files (*)"
        )

        if not filename or not filename.endswith(".json"):
            return

        self._currentLayoutFile = ""

        try:
            with open(filename, "r", encoding="utf-8") as f:
                splitState = json.load(f)
                if self.restoreSplitState(splitState):
                    self._currentLayoutFile = filename
        except Exception as e:
            QMessageBox.warning(
                None,
                i18n("Krita"),
                i18n(f"An unexpected error occurred.\n\n{e}"),
            )

    def slotNextTab(self):
        self.cycleTab(1)

    def slotPreviousTab(self):
        self.cycleTab(-1)

    def cycleTab(self, delta: int):
        pane = self.activeSplitPane()
        if pane is not None:
            pane.cycleTab(delta)
            return

        mdi = self._helper.getMdi()
        if mdi is None:
            return

        subWins = mdi.subWindowList()
        size = len(subWins)

        if size > 1:
            index = (
                subWins.index(mdi.activeSubWindow()) + delta + size
            ) % size
            mdi.setActiveSubWindow(subWins[index])

    def openExternalView(self, view: View | None = None):
        view = self._helper.isAlive(view, View)
        if view is None:
            return
        self.openView(view.document())
        self._helper.focusQwin()

    def profile(self, msg="Profile", start=None):
        import time

        if not hasattr(self, "_profile_time"):
            self._profile_time = time.perf_counter()
            self._profiled = []

        elapsed_time = time.perf_counter() - (start if start is not None else self._profile_time)
        self._profiled.append(f"[{elapsed_time:.4f}s] {msg}")

