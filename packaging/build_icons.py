from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
ICON_DIR = ROOT / "icons"
HICOLOR_SIZES = (32, 48, 64, 128, 256, 512)


def build_icon(size: int = 1024) -> Image.Image:
    image = Image.new("RGBA", (size, size), "#05080f")
    draw = ImageDraw.Draw(image)
    scale = size / 1024

    def box(values: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(round(value * scale) for value in values)

    draw.ellipse(box((108, 108, 916, 916)), fill="#0b1520", outline="#4de8ff", width=round(36 * scale))
    draw.ellipse(box((254, 254, 770, 770)), fill="#122033", outline="#1e4a63", width=round(24 * scale))
    draw.ellipse(box((416, 416, 608, 608)), fill="#4de8ff")
    draw.ellipse(box((472, 472, 552, 552)), fill="#e8f7ff")
    draw.arc(box((164, 354, 860, 670)), 188, 352, fill="#3dffb0", width=round(38 * scale))
    return image


def _resample() -> int:
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def write_hicolor_pngs(icon: Image.Image) -> None:
    resample = _resample()
    for size in HICOLOR_SIZES:
        dest = ICON_DIR / "hicolor" / f"{size}x{size}" / "apps"
        dest.mkdir(parents=True, exist_ok=True)
        icon.resize((size, size), resample).save(dest / "astro-dwarf.png", optimize=True)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    icon = build_icon()
    icon.save(ICON_DIR / "astro-dwarf.png", optimize=True)
    icon.save(
        ICON_DIR / "astro-dwarf.ico",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    write_hicolor_pngs(icon)
    assets = ROOT.parent / "astro_dwarf" / "qml" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    icon.resize((256, 256), _resample()).save(assets / "astro-dwarf.png", optimize=True)
    try:
        icon.save(ICON_DIR / "astro-dwarf.icns")
    except Exception:
        pass


if __name__ == "__main__":
    main()
