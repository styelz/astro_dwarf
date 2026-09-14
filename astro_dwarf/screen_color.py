from __future__ import annotations

from PySide6.QtCore import Property, QEvent, QObject, QPoint, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeyEvent, QRasterWindow


def grab_color_at(pos: QPoint | None = None) -> QColor:
    """Return the screen pixel under `pos`, or under the cursor."""
    point = QCursor.pos() if pos is None else QPoint(pos)
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    if screen is None:
        return QColor()
    geo = screen.geometry()
    pixmap = screen.grabWindow(0, point.x() - geo.x(), point.y() - geo.y(), 1, 1)
    image = pixmap.toImage()
    if image.isNull() or image.width() < 1 or image.height() < 1:
        return QColor()
    return image.pixelColor(0, 0)


class ScreenColorPicker(QObject):
    """Eyedropper: follow the cursor, click to sample, Escape to cancel.

    A 1×1 always-on-top window tracks the cursor so the click stays in-process
    on Windows, where mouse grabs do not work across other applications.
    """

    pickingChanged = Signal()
    sampleChanged = Signal()
    cursorChanged = Signal()
    picked = Signal(QColor)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._picking = False
        self._sample = QColor()
        self._cursor = QPoint(0, 0)
        self._dummy: QRasterWindow | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._poll)

    @Property(bool, notify=pickingChanged)
    def picking(self) -> bool:
        return self._picking

    @Property(QColor, notify=sampleChanged)
    def sample(self) -> QColor:
        return QColor(self._sample)

    @Property(int, notify=cursorChanged)
    def cursorX(self) -> int:
        return int(self._cursor.x())

    @Property(int, notify=cursorChanged)
    def cursorY(self) -> int:
        return int(self._cursor.y())

    @Slot()
    def start(self) -> None:
        if self._picking:
            return
        app = QGuiApplication.instance()
        if app is None:
            return
        self._picking = True
        self.pickingChanged.emit()
        app.installEventFilter(self)
        QGuiApplication.setOverrideCursor(Qt.CursorShape.CrossCursor)
        self._ensure_dummy()
        self._poll()
        self._timer.start()

    @Slot()
    def cancel(self) -> None:
        if not self._picking:
            return
        self._stop(emit_cancelled=True)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if not self._picking:
            return False
        etype = event.type()
        if etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            return True
        if etype == QEvent.Type.MouseButtonRelease:
            self._commit()
            return True
        if etype == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self._stop(emit_cancelled=True)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._commit()
                return True
        return False

    def _ensure_dummy(self) -> None:
        if self._dummy is not None:
            return
        dummy = QRasterWindow()
        dummy.setFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        dummy.resize(1, 1)
        dummy.setOpacity(0.01)
        self._dummy = dummy

    def _poll(self) -> None:
        if not self._picking:
            return
        pos = QCursor.pos()
        dummy = self._dummy
        if dummy is not None and dummy.isVisible():
            dummy.hide()
        color = grab_color_at(pos)
        if dummy is not None:
            dummy.setPosition(pos)
            try:
                dummy.show()
            except RuntimeError:
                pass
        moved = pos != self._cursor
        self._cursor = pos
        if moved:
            self.cursorChanged.emit()
        if color.isValid() and color != self._sample:
            self._sample = color
            self.sampleChanged.emit()

    def _commit(self) -> None:
        color = QColor(self._sample)
        if not color.isValid():
            color = grab_color_at()
        self._stop(emit_cancelled=False)
        if color.isValid():
            self._sample = color
            self.sampleChanged.emit()
            self.picked.emit(color)

    def _stop(self, *, emit_cancelled: bool) -> None:
        if not self._picking:
            return
        self._timer.stop()
        app = QGuiApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        QGuiApplication.restoreOverrideCursor()
        if self._dummy is not None:
            self._dummy.hide()
        self._picking = False
        self.pickingChanged.emit()
        if emit_cancelled:
            self.cancelled.emit()
