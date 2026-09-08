from __future__ import annotations

import socket
import sys
from typing import Optional

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from .runtime import ffmpeg_mjpeg_command, ffmpeg_path

CREATE_NO_WINDOW = 0x08000000


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

    def frame_size(self) -> tuple[int, int]:
        """Native (width, height) of the latest decoded frame; (0, 0) when empty."""
        image = self._image
        if image.isNull():
            return (0, 0)
        return (image.width(), image.height())


class StreamPlayer(QObject):
    """Live preview via ffmpeg CLI so RTSP matches VLC and stays off Qt Multimedia."""

    frameReady = Signal(object)
    failed = Signal(str)
    statusChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._process: QProcess | None = None
        self._url = ""
        self._transports: list[str | None] = [None]
        self._transport_index = 0
        self._cancelled = False
        self._got_frame = False
        self._buffer = b""
        self._stderr = ""
        self._watchdog = QTimer(self)
        self._watchdog.setSingleShot(True)
        self._watchdog.timeout.connect(self._on_watchdog)

    @Slot(str)
    def openStream(self, url: str) -> None:
        self._cancelled = False
        self._url = url
        if url.startswith("rtsp://"):
            # VLC typically uses TCP; UDP often never errors, it just stays blank.
            self._transports = ["tcp", "udp"]
        else:
            self._transports = [None]
        self._transport_index = 0
        self.statusChanged.emit("Opening camera stream…")
        self._start_process()

    @Slot()
    def closeStream(self) -> None:
        self._cancelled = True
        self._url = ""
        self._watchdog.stop()
        self._teardown()

    def _start_process(self) -> None:
        self._teardown()
        if self._cancelled or not self._url:
            return
        transport = self._transports[self._transport_index]
        if transport == "tcp":
            self.statusChanged.emit("Opening camera stream over TCP…")
        elif transport == "udp":
            self.statusChanged.emit("TCP stream failed, retrying over UDP…")
        command = ffmpeg_mjpeg_command(self._url, transport)
        program, arguments = command[0], command[1:]
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        if sys.platform == "win32" and hasattr(
            process, "setCreateProcessArgumentsModifier"
        ):
            process.setCreateProcessArgumentsModifier(
                lambda args: args.setCreateFlags(int(args.createFlags()) | CREATE_NO_WINDOW)
            )
        process.readyReadStandardOutput.connect(self._on_stdout)
        process.readyReadStandardError.connect(self._on_stderr)
        process.errorOccurred.connect(self._on_process_error)
        process.finished.connect(self._on_finished)
        self._process = process
        self._got_frame = False
        self._buffer = b""
        self._stderr = ""
        process.start(program, arguments)
        if not process.waitForStarted(4000):
            if not self._cancelled:
                self._retry_or_fail(f"Could not start ffmpeg ({ffmpeg_path()})")
            return
        self._watchdog.start(8000)

    def _teardown(self) -> None:
        self._watchdog.stop()
        process = self._process
        self._process = None
        self._buffer = b""
        if process is None:
            return
        for signal_name in ("readyReadStandardOutput", "readyReadStandardError", "errorOccurred", "finished"):
            try:
                getattr(process, signal_name).disconnect()
            except (RuntimeError, TypeError):
                pass
        if process.state() != QProcess.ProcessState.NotRunning:
            process.kill()
            process.waitForFinished(1500)
        process.deleteLater()

    def _on_stdout(self) -> None:
        if self._process is None:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        while True:
            start = self._buffer.find(b"\xff\xd8")
            end = self._buffer.find(b"\xff\xd9", start + 2) if start >= 0 else -1
            if start < 0 or end < 0:
                if len(self._buffer) > 5_000_000:
                    self._buffer = self._buffer[-64_000:]
                return
            jpeg = self._buffer[start : end + 2]
            self._buffer = self._buffer[end + 2 :]
            image = QImage.fromData(jpeg, "JPG")
            if image.isNull():
                continue
            self._got_frame = True
            self._watchdog.stop()
            self.frameReady.emit(image)

    def _on_stderr(self) -> None:
        if self._process is None:
            return
        text = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
        self._stderr = (self._stderr + text)[-4000:]

    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if self._cancelled or self._process is None:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._retry_or_fail(f"Could not start ffmpeg ({ffmpeg_path()})")

    def _on_finished(self) -> None:
        if self._cancelled or self._process is None:
            return
        detail = self._stderr.strip().splitlines()[-1] if self._stderr.strip() else "ffmpeg exited"
        self._retry_or_fail(detail)

    def _on_watchdog(self) -> None:
        if self._cancelled or self._got_frame:
            return
        self._retry_or_fail("No frames received from the camera stream")

    def _retry_or_fail(self, message: str) -> None:
        if self._cancelled:
            return
        if self._got_frame:
            return
        if self._transport_index + 1 < len(self._transports):
            self._transport_index += 1
            self._start_process()
            return
        text = message or "Stream failed"
        self.failed.emit(text)
