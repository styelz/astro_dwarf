"""Launch Astro Dwarf from the repository root."""

from astro_dwarf.splash import launch


def main() -> int | None:
    return launch(__file__)


if __name__ == "__main__":
    raise SystemExit(main())
