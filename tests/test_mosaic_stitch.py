"""Host-side mosaic stitch: seed placement, star alignment, missing panes."""

from __future__ import annotations

import unittest

import numpy as np

from astro_dwarf.mosaic_stitch import StitchPane, overlap_warning, stitch_panes


def _field(width: int, height: int, rng: np.random.Generator) -> np.ndarray:
    image = np.zeros((height, width), dtype=np.float32)
    ys = rng.uniform(12, height - 12, 48)
    xs = rng.uniform(12, width - 12, 48)
    for x, y in zip(xs, ys):
        x0, x1 = int(x) - 2, int(x) + 3
        y0, y1 = int(y) - 2, int(y) + 3
        if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
            continue
        image[y0:y1, x0:x1] = 1.0
    return image


def _rotate(image: np.ndarray, degrees: float, shift: tuple[float, float]) -> np.ndarray:
    import cv2

    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    matrix[0, 2] += shift[0]
    matrix[1, 2] += shift[1]
    return cv2.warpAffine(image, matrix, (width, height), flags=cv2.INTER_LINEAR)


class MosaicStitchTests(unittest.TestCase):
    def test_recovers_shift_and_rotation(self) -> None:
        rng = np.random.default_rng(4)
        master = _field(220, 160, rng)
        overlap = 0.45
        step = int(round(220 * (1.0 - overlap)))
        left = master[:, :220]
        # Pane 2 sees the same sky the seed expects, plus a small pointing error.
        window = np.zeros_like(master)
        window[:, : 220 - step] = master[:, step:]
        window[:, 220 - step :] = master[:, :step]
        right = _rotate(window, 2.0, (5.0, -3.0))
        result = stitch_panes(
            [
                StitchPane(1, 1, 1, left, position_angle=0, fov_h=2.0, fov_v=1.2),
                StitchPane(2, 1, 2, right, position_angle=0, fov_h=2.0, fov_v=1.2),
            ],
            overlap=overlap,
        )
        self.assertIsNotNone(result.residual_px)
        self.assertLessEqual(result.residual_px, 0.5)
        self.assertEqual(result.unmatched, [])
        self.assertGreater(len(result.jpeg), 100)

    def test_starless_edge_keeps_seed(self) -> None:
        left = np.linspace(0.05, 0.2, 80, dtype=np.float32)[None, :].repeat(60, axis=0)
        right = np.linspace(0.2, 0.05, 80, dtype=np.float32)[None, :].repeat(60, axis=0)
        result = stitch_panes(
            [
                StitchPane(1, 1, 1, left),
                StitchPane(2, 1, 2, right),
            ],
            overlap=0.3,
        )
        self.assertEqual(result.unmatched, [(1, 2)])
        self.assertIsNone(result.residual_px)
        self.assertGreater(result.width, 80)

    def test_missing_pane_stitches_the_rest(self) -> None:
        rng = np.random.default_rng(9)
        image = _field(120, 90, rng)
        other = _field(120, 90, np.random.default_rng(3))
        result = stitch_panes(
            [
                StitchPane(1, 1, 1, image),
                StitchPane(2, 1, 2, image),
                StitchPane(4, 2, 2, other),
            ],
            overlap=0.4,
        )
        self.assertGreater(len(result.jpeg), 100)
        self.assertGreater(result.width, 120)
        self.assertGreater(result.height, 90)

    def test_low_overlap_warning(self) -> None:
        self.assertIn("15%", overlap_warning(0.1))
        self.assertEqual(overlap_warning(0.2), "")


if __name__ == "__main__":
    unittest.main()
