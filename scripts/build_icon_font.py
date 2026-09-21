#!/usr/bin/env python3
"""Build the original HUD icon face at the MDL2 codepoints QML already uses.

Dev-only. Runtime does not import fontTools. Install fonttools, then:

    python scripts/build_icon_font.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "astro_dwarf" / "fonts" / "AstroDwarfIcons.ttf"
FAMILY = "Astro Dwarf Icons"
EM = 1000
ASC = 800
DESC = -200
ADV = 1000
CX = 500
CY = 400
STROKE = 150


def _require_fonttools():
    try:
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
    except ImportError as exc:
        raise SystemExit("fonttools is required to build the icon font: pip install fonttools") from exc
    return FontBuilder, TTGlyphPen


def _pen(TTGlyphPen):
    return TTGlyphPen(None)


def _close(pen):
    pen.closePath()


def _ring(pen, cx, cy, outer, inner, n=28):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((cx + outer * math.cos(a), cy + outer * math.sin(a)))
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    _close(pen)
    pts = []
    for i in range(n):
        a = -2 * math.pi * i / n
        pts.append((cx + inner * math.cos(a), cy + inner * math.sin(a)))
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    _close(pen)


def _poly(pen, pts):
    if len(pts) < 3:
        return
    pen.moveTo(pts[0])
    for p in pts[1:]:
        pen.lineTo(p)
    _close(pen)


def _rect(pen, x, y, w, h):
    _poly(pen, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)])


def _frame(pen, x, y, w, h, t):
    _rect(pen, x, y, w, t)
    _rect(pen, x, y + h - t, w, t)
    _rect(pen, x, y, t, h)
    _rect(pen, x + w - t, y, t, h)


def _segment(pen, x1, y1, x2, y2, w):
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length * w / 2, dx / length * w / 2
    _poly(
        pen,
        [
            (x1 + nx, y1 + ny),
            (x2 + nx, y2 + ny),
            (x2 - nx, y2 - ny),
            (x1 - nx, y1 - ny),
        ],
    )


def _cap(pen, x, y, w):
    r = w / 2
    _rect(pen, x - r, y - r, w, w)


def _polyline(pen, pts, w=STROKE):
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        _segment(pen, x1, y1, x2, y2, w)
        _cap(pen, x1, y1, w)
    if pts:
        _cap(pen, pts[-1][0], pts[-1][1], w)


def _disc(pen, cx, cy, r, n=24):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    _poly(pen, pts)


def notdef(pen):
    _frame(pen, 120, 80, 760, 760, 70)


def chevron_down(pen):
    _polyline(pen, [(220, 560), (500, 250), (780, 560)], STROKE)


def chevron_up(pen):
    _polyline(pen, [(220, 250), (500, 560), (780, 250)], STROKE)


def chevron_left(pen):
    _polyline(pen, [(640, 180), (320, 400), (640, 620)], STROKE)


def chevron_right(pen):
    _polyline(pen, [(360, 180), (680, 400), (360, 620)], STROKE)


def chevron_right_med(pen):
    _polyline(pen, [(400, 200), (680, 400), (400, 600)], 80)


def plus(pen):
    _rect(pen, 455, 180, STROKE, 440)
    _rect(pen, 280, 356, 440, STROKE)


def minus(pen):
    _rect(pen, 250, 356, 500, STROKE)


def close_x(pen):
    _polyline(pen, [(250, 180), (750, 620)], 80)
    _polyline(pen, [(750, 180), (250, 620)], 80)


def check(pen):
    _polyline(pen, [(220, 400), (410, 210), (790, 590)], 90)


def play(pen):
    _poly(pen, [(300, 160), (780, 400), (300, 640)])


def pause(pen):
    _rect(pen, 280, 170, 140, 460)
    _rect(pen, 580, 170, 140, 460)


def stop(pen):
    _rect(pen, 260, 180, 480, 440)


def copy(pen):
    _frame(pen, 320, 140, 460, 430, 70)
    _frame(pen, 190, 250, 460, 430, 70)


def trash(pen):
    _rect(pen, 250, 620, 500, 70)
    _rect(pen, 430, 700, 140, 70)
    _polyline(pen, [(300, 620), (340, 160), (660, 160), (700, 620)], 70)
    _rect(pen, 455, 230, 70, 300)


def edit(pen):
    _polyline(pen, [(230, 180), (620, 570)], 80)
    _poly(pen, [(620, 570), (790, 640), (720, 470)])
    _rect(pen, 200, 150, 180, 70)


def refresh(pen):
    _ring(pen, CX, CY, 250, 250 - 80, 32)
    _poly(pen, [(500, 650), (680, 650), (560, 780)])
    _poly(pen, [(500, 150), (320, 150), (440, 20)])


def settings(pen):
    _ring(pen, CX, CY, 160, 80, 20)
    for i in range(6):
        a = math.pi / 2 + i * math.pi / 3
        dx, dy = math.cos(a), math.sin(a)
        px, py = CX + 230 * dx, CY + 230 * dy
        _disc(pen, px, py, 55, 12)


def globe(pen):
    _ring(pen, CX, CY, 270, 190, 28)
    _rect(pen, CX - 40, CY - 250, 80, 500)
    _segment(pen, 250, CY, 750, CY, 70)


def pin(pen):
    _disc(pen, CX, 520, 150, 20)
    _disc(pen, CX, 520, 55, 16)
    _poly(pen, [(350, 430), (500, 140), (650, 430)])


def flag(pen):
    _rect(pen, 260, 140, 70, 560)
    _poly(pen, [(330, 680), (760, 560), (330, 430)])


def warn(pen):
    _poly(pen, [(500, 700), (180, 160), (820, 160)])
    _rect(pen, 455, 300, 90, 220)
    _rect(pen, 455, 200, 90, 70)


def bug(pen):
    _disc(pen, CX, 420, 170, 20)
    _rect(pen, 455, 560, 90, 140)
    _polyline(pen, [(330, 280), (220, 160)], 60)
    _polyline(pen, [(670, 280), (780, 160)], 60)
    _polyline(pen, [(300, 420), (180, 420)], 60)
    _polyline(pen, [(700, 420), (820, 420)], 60)


def devices(pen):
    _frame(pen, 160, 280, 520, 340, 70)
    _rect(pen, 300, 210, 240, 70)
    _frame(pen, 620, 140, 220, 360, 60)


def view_all(pen):
    gap = 70
    size = 190
    for col in range(2):
        for row in range(2):
            _rect(pen, 240 + col * (size + gap), 170 + row * (size + gap), size, size)


def folder(pen):
    _rect(pen, 180, 520, 260, 90)
    _frame(pen, 180, 180, 640, 430, 70)


def swap(pen):
    _polyline(pen, [(250, 520), (750, 520), (620, 640)], 80)
    _polyline(pen, [(750, 280), (250, 280), (380, 160)], 80)


def share(pen):
    _disc(pen, 280, 400, 70, 16)
    _disc(pen, 720, 620, 70, 16)
    _disc(pen, 720, 180, 70, 16)
    _polyline(pen, [(330, 430), (670, 590)], 60)
    _polyline(pen, [(330, 370), (670, 210)], 60)


def save(pen):
    _poly(pen, [(200, 160), (200, 660), (320, 780), (800, 780), (800, 160)])
    _rect(pen, 300, 500, 400, 200)
    _rect(pen, 360, 200, 280, 220)


def open_file(pen):
    _frame(pen, 200, 160, 500, 520, 70)
    _polyline(pen, [(520, 400), (800, 400), (800, 620)], 70)


def download(pen):
    _polyline(pen, [(500, 700), (500, 280)], 90)
    _polyline(pen, [(300, 460), (500, 250), (700, 460)], 90)
    _rect(pen, 220, 160, 560, 80)


def star(pen):
    pts = []
    for i in range(5):
        a = math.pi / 2 + i * 2 * math.pi / 5
        pts.append((CX + 260 * math.cos(a), CY + 260 * math.sin(a)))
        b = a + math.pi / 5
        pts.append((CX + 110 * math.cos(b), CY + 110 * math.sin(b)))
    _poly(pen, pts)


def eye(pen):
    _poly(pen, [(160, 400), (500, 640), (840, 400), (500, 160)])
    _disc(pen, CX, CY, 90, 16)


def eye_off(pen):
    eye(pen)
    _polyline(pen, [(220, 160), (780, 640)], 80)


def pipette(pen):
    _polyline(pen, [(280, 180), (620, 520)], 80)
    _poly(pen, [(620, 520), (790, 590), (720, 420)])
    _rect(pen, 230, 140, 120, 70)


def zoom_in(pen):
    _ring(pen, 430, 450, 210, 130, 24)
    _polyline(pen, [(580, 300), (780, 140)], 80)
    _rect(pen, 390, 410, 80, 80)
    _rect(pen, 390, 370, 80, 160)
    _rect(pen, 350, 410, 160, 80)


def zoom_out(pen):
    _ring(pen, 430, 450, 210, 130, 24)
    _polyline(pen, [(580, 300), (780, 140)], 80)
    _rect(pen, 350, 410, 160, 80)


def fit(pen):
    _frame(pen, 220, 180, 560, 440, 70)
    _polyline(pen, [(320, 520), (320, 600), (420, 600)], 70)
    _polyline(pen, [(680, 280), (680, 200), (580, 200)], 70)


def info(pen):
    _ring(pen, CX, CY, 280, 200, 28)
    _rect(pen, 455, 180, 90, 70)
    _rect(pen, 455, 280, 90, 260)


def target(pen):
    _ring(pen, CX, CY, 260, 190, 28)
    _ring(pen, CX, CY, 120, 50, 20)
    _rect(pen, CX - 35, 80, 70, 140)
    _rect(pen, CX - 35, 580, 70, 140)
    _rect(pen, 80, CY - 35, 140, 70)
    _rect(pen, 780, CY - 35, 140, 70)


def layers(pen):
    _poly(pen, [(500, 700), (200, 540), (500, 380), (800, 540)])
    _polyline(pen, [(220, 360), (500, 220), (780, 360)], 70)
    _polyline(pen, [(220, 250), (500, 110), (780, 250)], 70)


def pip(pen):
    _frame(pen, 160, 220, 520, 400, 70)
    _frame(pen, 470, 140, 340, 260, 70)


GLYPHS = {
    0xE1D2: target,
    0xE707: globe,
    0xE70D: chevron_down,
    0xE70E: chevron_up,
    0xE70F: edit,
    0xE710: plus,
    0xE711: close_x,
    0xE713: settings,
    0xE71A: pause,
    0xE71D: view_all,
    0xE71F: zoom_out,
    0xE72C: refresh,
    0xE734: flag,
    0xE73E: check,
    0xE74A: chevron_left,
    0xE74B: chevron_right,
    0xE74D: trash,
    0xE768: play,
    0xE769: stop,
    0xE76C: chevron_right_med,
    0xE774: globe,
    0xE7B3: eye_off,
    0xE7BA: warn,
    0xE7C4: pip,
    0xE7ED: eye,
    0xE838: star,
    0xE896: download,
    0xE8A3: zoom_in,
    0xE8A5: save,
    0xE8A7: open_file,
    0xE8AB: swap,
    0xE8B9: pin,
    0xE8C8: copy,
    0xE8CD: devices,
    0xE8EC: layers,
    0xE90F: bug,
    0xE962: info,
    0xE9A6: fit,
    0xEF3C: pipette,
}


def build(path: Path = OUT) -> Path:
    FontBuilder, TTGlyphPen = _require_fonttools()
    names = [".notdef", "space"]
    cmap = {0x20: "space"}
    for code in sorted(GLYPHS):
        name = f"uni{code:04X}"
        names.append(name)
        cmap[code] = name

    glyphs = {}
    pen = _pen(TTGlyphPen)
    notdef(pen)
    glyphs[".notdef"] = pen.glyph()
    glyphs["space"] = _pen(TTGlyphPen).glyph()
    for code, drawer in GLYPHS.items():
        pen = _pen(TTGlyphPen)
        drawer(pen)
        glyphs[f"uni{code:04X}"] = pen.glyph()

    metrics = {name: (ADV, 80) for name in names}
    metrics["space"] = (ADV, 0)

    fb = FontBuilder(EM, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASC, descent=DESC)
    fb.setupNameTable(
        {
            "familyName": FAMILY,
            "styleName": "Regular",
            "uniqueFontIdentifier": "astro-dwarf-icons-1.0",
            "fullName": FAMILY,
            "psName": "AstroDwarfIcons",
            "version": "Version 1.000",
            "description": "Original HUD geometry for Astro Dwarf chrome icons.",
        }
    )
    fb.setupOS2(
        sTypoAscender=ASC,
        sTypoDescender=DESC,
        usWinAscent=ASC,
        usWinDescent=-DESC,
        sxHeight=500,
        sCapHeight=700,
        fsType=0,
        fsSelection=0x40,
        usFirstCharIndex=0x20,
        usLastCharIndex=0xEF3C,
        # Bit 0 = Basic Latin, bit 57 = BMP private use (U+E000–F8FF).
        ulUnicodeRange1=0x00000001,
        ulUnicodeRange2=0x02000000,
        ulCodePageRange1=0x80000001,
    )
    fb.setupPost()
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(path)
    return path


def main() -> int:
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes), {len(GLYPHS)} icons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
