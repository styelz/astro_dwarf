"""Release filenames for the installers added beside the existing set."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW = (ROOT / ".github" / "workflows" / "release-installers.yml").read_text(
    encoding="utf-8"
)
FLATPAK_SCRIPT = (ROOT / "packaging" / "linux" / "build-flatpak.sh").read_text(
    encoding="utf-8"
)
MANIFEST = (ROOT / "packaging" / "linux" / "com.astrodwarf.app.yml").read_text(
    encoding="utf-8"
)
WRAPPER = (ROOT / "packaging" / "linux" / "flatpak-run.sh").read_text(encoding="utf-8")
NFPM = (ROOT / "packaging" / "linux" / "nfpm.yaml").read_text(encoding="utf-8")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def render(
    template: str,
    source: str = WORKFLOW,
    version: str = "1.2.105",
    **values: str,
) -> str:
    _assert(template in source, template)
    text = template.replace("${VERSION}", version)
    for key, value in values.items():
        text = text.replace("${" + key + "}", value)
    return text


def test_existing_x64_and_apple_silicon_names_stay() -> None:
    names = {
        render("AstroDwarf-${VERSION}-${APP_ARCH}.AppImage", APP_ARCH="x86_64"),
        render("AstroDwarf-${VERSION}-linux-${DEB_ARCH}.deb", DEB_ARCH="amd64"),
        render("AstroDwarf-${VERSION}-linux-${PKG_ARCH}.rpm", PKG_ARCH="x86_64"),
        render(
            "AstroDwarf-${VERSION}-linux-${PKG_ARCH}.pkg.tar.zst",
            PKG_ARCH="x86_64",
        ),
        render("AstroDwarf-${VERSION}-macos-${MAC_ARCH}.dmg", MAC_ARCH="arm64"),
        render("AstroDwarf-${VERSION}-macos-${MAC_ARCH}.pkg", MAC_ARCH="arm64"),
    }
    _assert(
        names
        == {
            "AstroDwarf-1.2.105-x86_64.AppImage",
            "AstroDwarf-1.2.105-linux-amd64.deb",
            "AstroDwarf-1.2.105-linux-x86_64.rpm",
            "AstroDwarf-1.2.105-linux-x86_64.pkg.tar.zst",
            "AstroDwarf-1.2.105-macos-arm64.dmg",
            "AstroDwarf-1.2.105-macos-arm64.pkg",
        },
        str(names),
    )


def test_intel_mac_arm_linux_and_flatpak_names() -> None:
    mac = render("AstroDwarf-${VERSION}-macos-${MAC_ARCH}.dmg", MAC_ARCH="x86_64")
    deb = render("AstroDwarf-${VERSION}-linux-${DEB_ARCH}.deb", DEB_ARCH="arm64")
    rpm = render("AstroDwarf-${VERSION}-linux-${PKG_ARCH}.rpm", PKG_ARCH="aarch64")
    appimage = render("AstroDwarf-${VERSION}-${APP_ARCH}.AppImage", APP_ARCH="aarch64")
    flatpak = render(
        "AstroDwarf-${VERSION}-linux-${PKG_ARCH}.flatpak",
        FLATPAK_SCRIPT,
        PKG_ARCH="aarch64",
    )
    flatpak_x64 = render(
        "AstroDwarf-${VERSION}-linux-${PKG_ARCH}.flatpak",
        FLATPAK_SCRIPT,
        PKG_ARCH="x86_64",
    )
    _assert(mac == "AstroDwarf-1.2.105-macos-x86_64.dmg", mac)
    _assert(deb == "AstroDwarf-1.2.105-linux-arm64.deb", deb)
    _assert(rpm == "AstroDwarf-1.2.105-linux-aarch64.rpm", rpm)
    _assert(appimage == "AstroDwarf-1.2.105-aarch64.AppImage", appimage)
    _assert(flatpak == "AstroDwarf-1.2.105-linux-aarch64.flatpak", flatpak)
    _assert(flatpak_x64 == "AstroDwarf-1.2.105-linux-x86_64.flatpak", flatpak_x64)
    for needle in (
        "macos-15-intel",
        "ubuntu-22.04",
        "ubuntu-24.04-arm",
        "python_arch: x64",
        "nfpm_arch: amd64",
        "nfpm_arch: arm64",
    ):
        _assert(needle in WORKFLOW, needle)
    _assert("release/*.flatpak" in WORKFLOW, "flatpak upload")
    _assert("packaging/linux/build-flatpak.sh" in WORKFLOW, "flatpak script")
    _assert("Candidate:" in WORKFLOW, "installable package check")
    _assert('apt-cache show "$pkg"' not in WORKFLOW, "virtual package was treated as installable")


def test_flatpak_bundle_uses_the_frozen_tree() -> None:
    _assert("app-id: com.astrodwarf.app" in MANIFEST, MANIFEST)
    _assert('runtime-version: "26.08"' in MANIFEST, MANIFEST)
    _assert("--share=network" in MANIFEST, MANIFEST)
    _assert("--filesystem=home" in MANIFEST, MANIFEST)
    _assert('exec "$ROOT/AstroDwarf"' in WRAPPER, WRAPPER)
    _assert("ROOT=/app/lib/astro-dwarf" in WRAPPER, WRAPPER)
    _assert('arch: "${NFPM_ARCH}"' in NFPM, NFPM)


if __name__ == "__main__":
    test_existing_x64_and_apple_silicon_names_stay()
    test_intel_mac_arm_linux_and_flatpak_names()
    test_flatpak_bundle_uses_the_frozen_tree()
    print("ok")
