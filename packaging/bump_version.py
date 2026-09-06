from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.strip().lstrip("v"))
    if not match:
        raise ValueError(f"Unsupported version: {value}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def format_version(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def read_file_version() -> str:
    return format_version(parse_version(VERSION_FILE.read_text(encoding="utf-8")))


def current_version() -> str:
    return read_file_version()


def bump_version(version: str, part: str) -> str:
    major, minor, patch = parse_version(version)
    if part == "major":
        return format_version((major + 1, 0, 0))
    if part == "minor":
        return format_version((major, minor + 1, 0))
    if part == "patch":
        return format_version((major, minor, patch + 1))
    raise ValueError(f"Unknown bump: {part}")


def write_version(version: str) -> None:
    parse_version(version)
    if read_file_version() != version:
        VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set or increment the Astro Dwarf version")
    parser.add_argument("--set", dest="set_version")
    parser.add_argument("--bump", choices=("major", "minor", "patch"))
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()
    if args.set_version:
        version = format_version(parse_version(args.set_version))
    elif args.bump:
        version = bump_version(current_version(), args.bump)
    else:
        version = current_version()
    if not args.print_only:
        write_version(version)
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
