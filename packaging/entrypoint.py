from astro_dwarf.qt_display import configure_qt_display

configure_qt_display()

from astro_dwarf.splash import launch


if __name__ == "__main__":
    raise SystemExit(launch())
