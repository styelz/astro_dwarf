#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -t 1 ]; then
    C_RESET='\033[0m'
    C_MAGENTA='\033[35m'
    C_CYAN='\033[36m'
    C_DARKCYAN='\033[36m'
    C_YELLOW='\033[33m'
    C_GREEN='\033[32m'
    C_GRAY='\033[90m'
    C_RED='\033[31m'
    C_WHITE='\033[37m'
else
    C_RESET=''
    C_MAGENTA=''
    C_CYAN=''
    C_DARKCYAN=''
    C_YELLOW=''
    C_GREEN=''
    C_GRAY=''
    C_RED=''
    C_WHITE=''
fi

banner() {
    printf '\n'
    printf '%b  ========================================%b\n' "$C_MAGENTA" "$C_RESET"
    printf '%b           Astro Dwarf%b\n' "$C_CYAN" "$C_RESET"
    printf '%b    Telescope control and scheduling%b\n' "$C_DARKCYAN" "$C_RESET"
    printf '%b  ========================================%b\n' "$C_MAGENTA" "$C_RESET"
    printf '\n'
}

step() {
    printf '%b  > %s%b\n' "$C_YELLOW" "$1" "$C_RESET"
}

ok() {
    printf '%b    %s%b\n' "$C_GREEN" "$1" "$C_RESET"
}

info() {
    printf '%b    %s%b\n' "$C_GRAY" "$1" "$C_RESET"
}

fail() {
    printf '\n%b  ! %s%b\n\n' "$C_RED" "$1" "$C_RESET"
}

banner
printf '%b  This script prepares a private Python setup,%b\n' "$C_WHITE" "$C_RESET"
printf '%b  then opens the Astro Dwarf desktop app.%b\n\n' "$C_WHITE" "$C_RESET"

step "Looking for Python 3.11 or newer..."
PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
        PYTHON=$candidate
        break
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.11 or newer was not found. Install Python, then run this script again."
    exit 1
fi

ok "Found Python ($PYTHON)."

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
step "Checking the app's private Python folder..."
if [ ! -x "$VENV_PYTHON" ]; then
    info "Creating it now. This only happens the first time."
    "$PYTHON" -m venv "$SCRIPT_DIR/.venv"
    ok "Private Python folder is ready."
else
    ok "Already set up. Skipping this step."
fi

step "Checking the packages Astro Dwarf needs..."
if ! "$VENV_PYTHON" -c 'import sys, PySide6, numpy, cv2; from dwarf_python_api.lib.dwarf_utils import perform_read_camera_params_http_v3, perform_enter_astro_mode; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
    if ! command -v git >/dev/null 2>&1; then
        fail "Git is needed for the first install. Install Git, then run this script again."
        exit 1
    fi

    info "Installing packages. The first run can take a minute."
    "$VENV_PYTHON" -m pip install -e ".[device]"
    ok "Packages are installed."
else
    ok "Packages are already installed. Skipping this step."
fi

printf '\n'
step "Starting Astro Dwarf..."
info "The app window should open in a moment."
printf '\n'
if [ -r /proc/sys/kernel/osrelease ] && grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease; then
    [ -n "$QT_QPA_PLATFORM" ] || export QT_QPA_PLATFORM=xcb
    [ -n "$QT_XCB_GL_INTEGRATION" ] || export QT_XCB_GL_INTEGRATION=none
    [ -n "$QT_QUICK_BACKEND" ] || export QT_QUICK_BACKEND=software
fi
exec "$VENV_PYTHON" app.py
