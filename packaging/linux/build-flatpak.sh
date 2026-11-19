#!/bin/bash
# Runs inside the Ubuntu 24.04 container started by the release workflow.
# VERSION and PKG_ARCH come from that job. dist/AstroDwarf is the binary
# already built on the host, so an x64 build keeps the host's older glibc.
set -euo pipefail

: "${VERSION:?VERSION is required}"
: "${PKG_ARCH:?PKG_ARCH is required}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y flatpak flatpak-builder ca-certificates dbus

flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y --noninteractive flathub \
  org.freedesktop.Platform//26.08 \
  org.freedesktop.Sdk//26.08

stage=packaging/linux/flatpak-stage
rm -rf "$stage"
mkdir -p "$stage/payload" "$stage/icons"
cp -a dist/AstroDwarf/. "$stage/payload/"
cp -a packaging/icons/hicolor/. "$stage/icons/"
cp packaging/linux/flatpak-run.sh "$stage/flatpak-run.sh"
cp packaging/linux/astro-dwarf.flatpak.desktop "$stage/astro-dwarf.flatpak.desktop"
chmod +x "$stage/flatpak-run.sh" "$stage/payload/AstroDwarf" "$stage/payload/AstroDwarfWorker"

rm -rf flatpak-build flatpak-repo
flatpak-builder --disable-rofiles-fuse --force-clean --repo=flatpak-repo \
  --install --install-deps-from=flathub \
  flatpak-build packaging/linux/com.astrodwarf.app.yml

mkdir -p release
flatpak build-bundle \
  --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
  flatpak-repo \
  "release/AstroDwarf-${VERSION}-linux-${PKG_ARCH}.flatpak" \
  com.astrodwarf.app

mkdir -p /run/dbus
if [ ! -S /run/dbus/system_bus_socket ]; then
  dbus-daemon --system --fork
fi
dbus-run-session -- timeout 90s flatpak run \
  --env=QT_QPA_PLATFORM=offscreen \
  --env=QT_DEBUG_PLUGINS=1 \
  --env=ASTRO_DWARF_TEST_EXIT_MS=3000 \
  com.astrodwarf.app
