import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtTest import QSignalSpy, QTest

from astro_dwarf.screen_color import ScreenColorPicker, grab_color_at


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


class ScreenColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()

    def test_grab_color_at_returns_qcolor(self):
        color = grab_color_at(QPoint(0, 0))
        self.assertIsInstance(color, QColor)

    def test_start_and_cancel_toggles_picking(self):
        picker = ScreenColorPicker()
        cancelled = QSignalSpy(picker.cancelled)
        self.assertFalse(picker.picking)
        picker.start()
        self.assertTrue(picker.picking)
        picker.cancel()
        self.assertFalse(picker.picking)
        self.assertGreaterEqual(cancelled.count(), 1)
        QTest.qWait(20)

    def test_cancel_when_idle_is_noop(self):
        picker = ScreenColorPicker()
        picker.cancel()
        self.assertFalse(picker.picking)


if __name__ == "__main__":
    unittest.main()
