# SPDX-License-Identifier: CC0-1.0

try:
    from PyQt6 import QtCore, QtGui, QtWidgets, sip as QtSip

    QAction = QtGui.QAction

    def getEventPos(  # pyright: ignore[reportRedeclaration]
        event: QtGui.QMouseEvent,
    ) -> QtCore.QPointF:
        return event.position()

    def getEventGlobalPos(  # pyright: ignore[reportRedeclaration]
        event: QtGui.QMouseEvent,
    ) -> QtCore.QPointF:
        return event.globalPosition()

    def toPoint(  # pyright: ignore[reportRedeclaration]
        pos: QtCore.QPointF,
    ) -> QtCore.QPoint:
        return pos.toPoint()

except:
    from PyQt5 import QtCore, QtGui, QtWidgets, sip as QtSip

    QAction = QtWidgets.QAction

    def getEventPos(event: QtGui.QMouseEvent) -> QtCore.QPoint:
        return event.pos()

    def getEventGlobalPos(event: QtGui.QMouseEvent) -> QtCore.QPoint:
        return event.globalPos()

    def toPoint(pos: QtCore.QPoint):
        return pos


import typing

sip = QtSip

QWIDGETSIZE_MAX = getattr(QtCore, "QWIDGETSIZE_MAX", 16777215)

pyqtBoundSignal = QtCore.pyqtBoundSignal
pyqtSignal = QtCore.pyqtSignal
pyqtSlot = typing.cast(
    typing.Callable[..., None] | QtCore.pyqtBoundSignal,
    QtCore.pyqtSlot,  # pyright: ignore [reportUnknownMemberType]
)
QAbstractItemModel = QtCore.QAbstractItemModel
QByteArray = QtCore.QByteArray
QCoreApplication = QtCore.QCoreApplication
QDir = QtCore.QDir
QEvent = QtCore.QEvent
QDynamicPropertyChangeEvent = QtCore.QDynamicPropertyChangeEvent
QObject = QtCore.QObject
QPoint = QtCore.QPoint
QPointF = QtCore.QPointF
QRect = QtCore.QRect
QRectF = QtCore.QRectF
QSettings = QtCore.QSettings
QSize = QtCore.QSize
QStandardPaths = QtCore.QStandardPaths
Qt = QtCore.Qt
QTimer = QtCore.QTimer
QUuid = QtCore.QUuid

QBrush = QtGui.QBrush
QColor = QtGui.QColor
QCursor = QtGui.QCursor
QFont = QtGui.QFont
QIcon = QtGui.QIcon
QImage = QtGui.QImage
QImageReader = QtGui.QImageReader
QMouseEvent = QtGui.QMouseEvent
QMoveEvent = QtGui.QMoveEvent
QResizeEvent = QtGui.QResizeEvent
QPaintEvent = QtGui.QPaintEvent
QPainter = QtGui.QPainter
QPalette = QtGui.QPalette
QPen = QtGui.QPen
QPixmap = QtGui.QPixmap
QStandardItem = QtGui.QStandardItem
QStandardItemModel = QtGui.QStandardItemModel
QTransform = QtGui.QTransform
QWheelEvent = QtGui.QWheelEvent
QWindow = QtGui.QWindow

QAbstractScrollArea = QtWidgets.QAbstractScrollArea
QApplication = QtWidgets.QApplication
QCheckBox = QtWidgets.QCheckBox
QColorDialog = QtWidgets.QColorDialog
QComboBox = QtWidgets.QComboBox
QDialogButtonBox = QtWidgets.QDialogButtonBox
QDialog = QtWidgets.QDialog
QDialog = QtWidgets.QDialog
QDockWidget = QtWidgets.QDockWidget
QFileDialog = QtWidgets.QFileDialog
QFormLayout = QtWidgets.QFormLayout
QFrame = QtWidgets.QFrame
QGraphicsDropShadowEffect = QtWidgets.QGraphicsDropShadowEffect
QHBoxLayout = QtWidgets.QHBoxLayout
QHeaderView = QtWidgets.QHeaderView
QLabel = QtWidgets.QLabel
QLineEdit = QtWidgets.QLineEdit
QListView = QtWidgets.QListView
QListWidgetItem = QtWidgets.QListWidgetItem
QListWidget = QtWidgets.QListWidget
QMainWindow = QtWidgets.QMainWindow
QMdiArea = QtWidgets.QMdiArea
QMdiSubWindow = QtWidgets.QMdiSubWindow
QMenu = QtWidgets.QMenu
QMessageBox = QtWidgets.QMessageBox
QProxyStyle = QtWidgets.QProxyStyle
QPushButton = QtWidgets.QPushButton
QScrollArea = QtWidgets.QScrollArea
QScrollBar = QtWidgets.QScrollBar
QSizePolicy = QtWidgets.QSizePolicy
QSpinBox = QtWidgets.QSpinBox
QStackedWidget = QtWidgets.QStackedWidget
QStyledItemDelegate = QtWidgets.QStyledItemDelegate
QStyleOptionViewItem = QtWidgets.QStyleOptionViewItem
QStyle = QtWidgets.QStyle
QTabBar = QtWidgets.QTabBar
QTabWidget = QtWidgets.QTabWidget
QToolBar = QtWidgets.QToolBar
QToolButton = QtWidgets.QToolButton
QTreeView = QtWidgets.QTreeView
QVBoxLayout = QtWidgets.QVBoxLayout
QWidgetAction = QtWidgets.QWidgetAction
QWidget = QtWidgets.QWidget

PYQT_SIGNAL = QtCore.pyqtSignal | QtCore.pyqtBoundSignal
PYQT_SLOT = typing.Callable[..., None] | QtCore.pyqtBoundSignal
