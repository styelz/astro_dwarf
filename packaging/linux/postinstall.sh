#!/bin/sh
# Refresh desktop and icon caches after install or removal. Missing helpers
# are normal on some spins; the files are still in the standard locations.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d /usr/share/icons/hicolor ]; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true
fi
if command -v xdg-icon-resource >/dev/null 2>&1; then
    xdg-icon-resource forceupdate 2>/dev/null || true
fi
