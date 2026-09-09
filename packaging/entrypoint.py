from astro_dwarf.qt_display import configure_qt_display

configure_qt_display()

from app import main


if __name__ == "__main__":
    raise SystemExit(main())
