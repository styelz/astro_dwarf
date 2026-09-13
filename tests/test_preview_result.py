import unittest

from astro_dwarf.qt_backend import stacking_preview_result_copy


class StackingPreviewResultCopyTests(unittest.TestCase):
    def test_completed_session_is_not_live_video(self) -> None:
        title, detail = stacking_preview_result_copy(True, False, "M31", False)
        self.assertEqual(title, "SESSION COMPLETE")
        self.assertIn("M31", detail)
        self.assertIn("not live video", detail)
        self.assertIn("Dismiss", detail)

    def test_stopped_session_uses_warning_title(self) -> None:
        title, detail = stacking_preview_result_copy(False, True, "M42", True)
        self.assertEqual(title, "SESSION STOPPED")
        self.assertIn("next capture", detail)

    def test_failed_session_keeps_the_still(self) -> None:
        title, detail = stacking_preview_result_copy(False, False, "   ", False)
        self.assertEqual(title, "SESSION FAILED")
        self.assertIn("this target", detail)


if __name__ == "__main__":
    unittest.main()
