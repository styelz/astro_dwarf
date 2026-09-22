#!/bin/bash
export DISPLAY=:0.0
export XAUTHORITY=/home/pbp/.Xauthority
export QTWEBENGINE_CHROMIUM_FLAGS='--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox --disable-features=Vulkan --use-gl=angle --use-angle=gl'

# Close the previous probe if it is still ours.
if pid=$(pgrep -n -f '/tmp/extract15/squashfs-root/usr/bin/AstroDwarf'); then
  kill "$pid" 2>/dev/null || true
  sleep 1
fi

cd /tmp/extract15/squashfs-root
nohup ./AppRun > /tmp/astro-gl.log 2>&1 &
sleep 8
WID=$(xdotool search --onlyvisible --name ASTRO | tail -1)
echo "WID=$WID"
xdotool getwindowgeometry --shell "$WID"
xdotool windowactivate --sync "$WID"
eval "$(xdotool getwindowgeometry --shell "$WID")"
SX=$((WIDTH * 11 / 14))
xdotool mousemove --window "$WID" "$SX" 78 click 1
sleep 14
import -window "$WID" /tmp/astro-gl-sky.png
echo "=== LOG ==="
cat /tmp/astro-gl.log
ls -l /tmp/astro-gl-sky.png
