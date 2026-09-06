from __future__ import annotations

import os
import socket
from typing import Optional

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtQuick import QQuickImageProvider


def port_is_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def stream_port(url: str) -> int:
    if url.startswith("http://"):
        return 8092
    return 554


class LiveImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.Image)
        self._image = QImage()

    def requestImage(self, _id, _size, requested_size):
        image = self._image
        if image.isNull():
            return QImage()
        if requested_size.isValid():
            return image.scaled(requested_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return image

    def update(self, image: QImage) -> None:
        self._image = image

    def clear(self) -> None:
        self._image = QImage()


class StreamPlayer(QObject):
    """QMediaPlayer that must live on a worker thread so RTSP open cannot freeze the UI."""

    frameReady = Signal(object)
    failed = Signal(str)
    statusChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._player: QMediaPlayer | None = None
        self._sink: QVideoSink | None = None
        self._audio: QAudioOutput | None = None
        self._url = ""
        self._tried_tcp = False
        self._cancelled = False

    @Slot(str)
    def openStream(self, url: str) -> None:
        self._cancelled = False
        self._url = url
        self._tried_tcp = not url.startswith("rtsp://")
        self._apply_transport(udp=url.startswith("rtsp://"))
        self.statusChanged.emit("Opening camera stream…")
        self._start_player(url)

    @Slot()
    def closeStream(self) -> None:
        self._cancelled = True
        self._url = ""
        self._teardown()

    def _apply_transport(self, udp: bool) -> None:
        os.environ["QT_FFMPEG_RTSP_TRANSPORT"] = "udp" if udp else "tcp"

    def _start_player(self, url: str) -> None:
        self._teardown()
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)
        self._player = QMediaPlayer(self)
        self._player.setVideoSink(self._sink)
        self._player.setAudioOutput(self._audio)
        self._player.errorOccurred.connect(self._on_error)
        self._player.setSource(QUrl(url))
        self._player.play()

    def _teardown(self) -> None:
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
            self._player.deleteLater()
            self._player = None
        if self._sink is not None:
            self._sink.deleteLater()
            self._sink = None
        if self._audio is not None:
            self._audio.deleteLater()
            self._audio = None

    def _on_frame(self, frame) -> None:
        if frame.isValid():
            self.frameReady.emit(frame.toImage())

    def _on_error(self, _error, message: str) -> None:
        if self._cancelled:
            return
        text = message or "Stream failed"
        if self._url.startswith("rtsp://") and not self._tried_tcp:
            self._tried_tcp = True
            self._apply_transport(udp=False)
            self.statusChanged.emit("UDP stream failed, retrying over TCP…")
            self._start_player(self._url)
            return
        self.failed.emit(text)
