#!/bin/sh
# Launch the bundled PyInstaller tree. /app is read-only; settings go to the
# per-app data directory Flatpak gives Qt.
ROOT=/app/lib/astro-dwarf
GTK_MODULES=
GTK3_MODULES=
export GTK_MODULES GTK3_MODULES
[ -n "$QTWEBENGINE_DISABLE_SANDBOX" ] || export QTWEBENGINE_DISABLE_SANDBOX=1
[ -n "$NO_AT_BRIDGE" ] || export NO_AT_BRIDGE=1

case "${LANG:-}" in
    ""|C|POSIX) export LANG=C.UTF-8 ;;
esac
case "${LC_ALL:-}" in
    C|POSIX) export LC_ALL=C.UTF-8 ;;
esac
if [ -z "${FONTCONFIG_FILE:-}" ] && [ -f "$ROOT/_internal/fonts/fonts.conf" ]; then
    export FONTCONFIG_FILE="$ROOT/_internal/fonts/fonts.conf"
    export FONTCONFIG_PATH="$ROOT/_internal/fonts"
fi
[ -n "$QT_LOGGING_RULES" ] || export QT_LOGGING_RULES="js.warning=false;js.critical=false"

if [ "${ASTRO_DWARF_QT_SOFTWARE:-}" = "1" ]; then
    [ -n "$QT_QPA_PLATFORM" ] || export QT_QPA_PLATFORM=xcb
    [ -n "$QT_XCB_GL_INTEGRATION" ] || export QT_XCB_GL_INTEGRATION=none
    [ -n "$QT_QUICK_BACKEND" ] || export QT_QUICK_BACKEND=software
    [ -n "$QTWEBENGINE_CHROMIUM_FLAGS" ] || export QTWEBENGINE_CHROMIUM_FLAGS="--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox --disable-features=Vulkan --enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader"
fi
exec "$ROOT/AstroDwarf" "$@"
