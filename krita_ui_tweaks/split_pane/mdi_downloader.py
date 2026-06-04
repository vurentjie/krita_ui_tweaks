from ..pyqt import (
    Qt,
    toPoint,
    getEventGlobalPos,
    QApplication,
    QRect,
    QPoint,
    QObject,
    QEvent,
    QMdiSubWindow,
    QTimer,
    QMessageBox,
    QProgressDialog,
    QNetworkAccessManager,
    QNetworkRequest,
    QNetworkReply,
    QMenu,
    QUrl,
)

from typing import Any, TypedDict, TYPE_CHECKING

import typing
import os
import tempfile

from ..i18n import i18n

NUMBER = int | float

DownloadCallback = typing.Callable[[bool, str | None, QUrl, str | None], None]


class MdiDownloader:

    def __init__(self, callback: DownloadCallback):
        self._callback: DownloadCallback = callback
        self._net: QNetworkAccessManager = QNetworkAccessManager()
        self._queue: list[QUrl] = []
        self._currReply: QNetworkReply | None = None
        self._dialog: QProgressDialog | None = None

    def download(self, urls: QUrl | str | list[QUrl | str]):
        if not isinstance(urls, (list, tuple)):
            urls = [urls]

        for u in urls:
            if isinstance(u, str):
                u = QUrl(u)
            self._queue.append(u)

        if not self._currReply:
            self._startNext()

    def abort(self):
        self._queue.clear()

        if self._currReply:
            self._currReply.abort()

    def _startNext(self):
        if not self._queue:
            return

        url = self._queue.pop(0)
        request = QNetworkRequest(url)
        reply = self._net.get(request)

        self._currReply = reply

        if not self._dialog:
            self._dialog = QProgressDialog(
                i18n("Downloading"), i18n("Cancel"), 0, 100
            )
            self._dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._dialog.canceled.connect(self.abort)

        self._dialog.setLabelText(i18n("Downloading") + f" {url.fileName()}")
        self._dialog.setValue(0)
        self._dialog.setMaximum(100)
        self._dialog.show()

        reply.downloadProgress.connect(self._onProgress)
        reply.finished.connect(lambda r=reply, u=url: self._onFinished(r, u))

    def _onProgress(self, received, total):
        if total > 0 and self._dialog:
            self._dialog.setMaximum(total)
            self._dialog.setValue(received)

    def _onFinished(self, reply, url):
        if self._dialog:
            self._dialog.close()
            self._dialog = None

        err = reply.error()
        if err == QNetworkReply.NetworkError.NoError:
            data = reply.readAll()
            suffix = os.path.splitext(url.fileName())[1]
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

            with open(tmp.name, "wb") as f:
                f.write(bytes(data))

            self._callback(True, tmp.name, url, None)
        else:
            self._callback(False, None, url, reply.errorString())

        reply.deleteLater()
        self._currReply = None
        self._startNext()

