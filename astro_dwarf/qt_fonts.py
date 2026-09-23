"""Pick HUD typefaces that are actually installed.

Theme.qml requests Segoe UI / Cascadia Mono / an icon face. Windows may have
Segoe MDL2 Assets, but QFontDatabase.families() often omits symbol fonts, and
Linux usually has none of them. The package ships Astro Dwarf Icons (original
geometry at the MDL2 codepoints QML already uses) plus Liberation Sans/Mono.

Never substitute a missing icon family onto the UI sans — that blanks every
Private Use glyph. Keep the candidate order in sync with Theme.qml.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

UI_FONT_CANDIDATES = (
    "Segoe UI",
    "Inter",
    "Noto Sans",
    "Ubuntu",
    "Liberation Sans",
    "DejaVu Sans",
    "Cantarell",
    "Source Sans 3",
    "Source Sans Pro",
    "Adwaita Sans",
    "FreeSans",
    "Nimbus Sans",
    "Helvetica Neue",
    "Helvetica",
    "Sans Serif",
)

MONO_FONT_CANDIDATES = (
    "Cascadia Mono",
    "Cascadia Code",
    "Consolas",
    "JetBrains Mono",
    "Ubuntu Mono",
    "Liberation Mono",
    "DejaVu Sans Mono",
    "Noto Sans Mono",
    "Source Code Pro",
    "Adwaita Mono",
    "FreeMono",
    "Menlo",
    "Monaco",
    "monospace",
)

BUNDLED_ICON_FAMILY = "Astro Dwarf Icons"
ICON_FONT_CANDIDATES = (
    BUNDLED_ICON_FAMILY,
    "Segoe MDL2 Assets",
    "Segoe Fluent Icons",
)


@dataclass(frozen=True)
class HudFonts:
    ui: str
    mono: str
    icon: str
    has_icon_font: bool


def bundled_font_dir() -> Path | None:
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "fonts")
    candidates.append(Path(__file__).resolve().parent / "fonts")
    for folder in candidates:
        if folder.is_dir():
            return folder
    return None


def load_bundled_fonts() -> list[str]:
    """Register shipped TTF/OTF faces with Qt. Safe to call more than once."""
    from PySide6.QtGui import QFontDatabase

    folder = bundled_font_dir()
    if folder is None:
        return []
    families: list[str] = []
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() not in {".ttf", ".otf"}:
            continue
        # On Windows, registering this face next to Segoe MDL2 makes Qt Quick
        # merge PUA glyphs onto the bundled font and the HUD icons go blank.
        if sys.platform == "win32" and path.stem.lower() == "astrodwarficons":
            continue
        handle = QFontDatabase.addApplicationFont(str(path))
        if handle < 0:
            continue
        families.extend(QFontDatabase.applicationFontFamilies(handle))
    return families


def installed_font_map(families: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in families:
        key = str(name).casefold()
        mapping.setdefault(key, name)
    return mapping


def pick_family(candidates: tuple[str, ...], available: dict[str, str], fallback: str) -> str:
    for name in candidates:
        found = available.get(name.casefold())
        if found:
            return found
    return fallback


def _icon_candidate_names() -> set[str]:
    return {name.casefold() for name in ICON_FONT_CANDIDATES}


def supplement_icon_families(available: dict[str, str]) -> dict[str, str]:
    """Symbol faces can exist without appearing in QFontDatabase.families()."""
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:
        return available
    has_family = getattr(QFontDatabase, "hasFamily", None)
    if not callable(has_family):
        return available
    filled = dict(available)
    for name in ICON_FONT_CANDIDATES:
        key = name.casefold()
        if key in filled:
            continue
        try:
            if QFontDatabase.hasFamily(name):
                filled[key] = name
        except Exception:
            continue
    return filled


def resolve_hud_fonts(families: list[str] | None = None, *, probe_system: bool | None = None) -> HudFonts:
    if families is None:
        from PySide6.QtGui import QFontDatabase

        families = list(QFontDatabase.families())
        probe = True if probe_system is None else probe_system
    else:
        probe = False if probe_system is None else probe_system
    available = installed_font_map(families)
    if probe:
        available = supplement_icon_families(available)
    ui = pick_family(UI_FONT_CANDIDATES, available, "Sans Serif")
    mono = pick_family(MONO_FONT_CANDIDATES, available, "monospace")
    icon = pick_family(ICON_FONT_CANDIDATES, available, ui)
    has_icon = icon.casefold() in _icon_candidate_names()
    return HudFonts(ui=ui, mono=mono, icon=icon, has_icon_font=has_icon)


def apply_hud_fonts(application, fonts: HudFonts | None = None) -> HudFonts:
    """Set the application default and substitutions before QML loads."""
    from PySide6.QtGui import QFont

    load_bundled_fonts()
    fonts = fonts or resolve_hud_fonts()
    ui_font = QFont(fonts.ui)
    ui_font.setStyleHint(QFont.StyleHint.SansSerif)
    ui_font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    strategy = QFont.StyleStrategy.PreferAntialias
    no_shape = getattr(QFont.StyleStrategy, "PreferNoShaping", None)
    if no_shape is not None and sys.platform.startswith("linux"):
        # letterSpacing + HarfBuzz repeats the last cluster on some Linux fonts.
        # The same flag makes macOS Core Text drop typed characters.
        strategy = strategy | no_shape
    ui_font.setStyleStrategy(strategy)
    application.setFont(ui_font)
    QFont.insertSubstitutions("Segoe UI", [fonts.ui])
    QFont.insertSubstitutions("Cascadia Mono", [fonts.mono])
    return fonts
