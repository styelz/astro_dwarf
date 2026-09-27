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

    def test_display_jpeg_keeps_the_sky_dark(self) -> None:
        import cv2

        rng = np.random.default_rng(7)
        height, width = 360, 500
        field = rng.normal(18, 3.5, (height, width)).astype(np.float32)
        xs = rng.integers(6, width - 6, 70)
        ys = rng.integers(6, height - 6, 70)
        for x, y, bright in zip(xs, ys, rng.uniform(90, 240, len(xs))):
            field[y - 1 : y + 2, x - 1 : x + 2] = bright
        yy, xx = np.mgrid[0:height, 0:width]
        falloff = ((xx - width / 2) / (width / 2)) ** 2 + ((yy - height / 2) / (height / 2)) ** 2
        field *= np.clip(1.0 - 0.25 * falloff, 0.4, 1.0)
        field = np.clip(field, 0, 255).astype(np.uint8)
        overlap = 0.2
        pane_h, pane_w = 200, 280
        step_x = int(pane_w * (1.0 - overlap))
        step_y = int(pane_h * (1.0 - overlap))
        panes = []
        index = 1
        for row in (0, 1):
            for column in (0, 1):
                y0 = row * step_y
                x0 = column * step_x
                panes.append(StitchPane(index, row + 1, column + 1, field[y0 : y0 + pane_h, x0 : x0 + pane_w]))
                index += 1
        result = stitch_panes(panes, overlap=overlap)
        image = cv2.imdecode(np.frombuffer(result.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(image)
        self.assertLess(float(np.median(image)), 40.0)
        frame_h, frame_w = image.shape[:2]
        mid_y, mid_x = frame_h // 2, frame_w // 2
        seam = float(np.median(image[mid_y - 10 : mid_y + 10, mid_x - 10 : mid_x + 10]))
        corner = float(np.median(image[24:70, 24:70]))
        self.assertLess(abs(seam - corner), 18.0)

    def test_linear_stack_sky_stays_dark(self) -> None:
        import cv2

        rng = np.random.default_rng(5)
        height, width = 180, 240
        field = rng.normal(1000, 40, (height, width)).astype(np.float32)
        xs = rng.integers(8, width - 8, 20)
        ys = rng.integers(8, height - 8, 20)
        for x, y, bright in zip(xs, ys, rng.uniform(8000, 40000, len(xs))):
            field[y - 1 : y + 2, x - 1 : x + 2] = bright
        overlap = 0.35
        step = int(width * (1.0 - overlap))
        right = np.zeros_like(field)
        right[:, : width - step] = field[:, step:]
        right[:, width - step :] = field[:, :step]
        result = stitch_panes(
            [
                StitchPane(1, 1, 1, field),
                StitchPane(2, 1, 2, right),
            ],
            overlap=overlap,
        )
        image = cv2.imdecode(np.frombuffer(result.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(image)
        self.assertLess(float(np.median(image)), 45.0)


if __name__ == "__main__":
    unittest.main()
