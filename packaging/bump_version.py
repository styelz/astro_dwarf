from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "astro_dwarf" / "version.py"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value.strip().lstrip("v"))
    if not match:
        raise ValueError(f"Unsupported version: {value}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def format_version(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def read_file_version() -> str:
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def git_tag_versions() -> list[tuple[int, int, int]]:
    try:
        output = subprocess.check_output(
            ["git", "tag", "--list", "v*"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    versions = []
    for line in output.splitlines():
        try:
            versions.append(parse_version(line))
        except ValueError:
            continue
    return versions


def current_version() -> str:
    versions = [parse_version(read_file_version()), *git_tag_versions()]
    return format_version(max(versions))


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
        pyproject = PYPROJECT.read_text(encoding="utf-8")
        updated = re.sub(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{version}"', pyproject, count=1)
        if updated == pyproject:
            raise ValueError("Could not update pyproject.toml version")
        PYPROJECT.write_text(updated, encoding="utf-8")
    INIT.write_text(
        '"""Astro Dwarf native multi-telescope controller."""\n\n'
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )


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
