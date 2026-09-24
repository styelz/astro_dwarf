from __future__ import annotations

import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .location import has_site_coordinates
from .runtime import package_root

ALADIN_LITE_HOME = "https://aladin.cds.unistra.fr/AladinLite/"
ATLAS_PAGE_NAME = "index.html"

_atlas_server: ThreadingHTTPServer | None = None
_atlas_server_lock = threading.Lock()


def atlas_page_path() -> Path:
    return package_root() / "qml" / "sky_atlas" / ATLAS_PAGE_NAME


def atlas_root() -> Path:
    return atlas_page_path().parent


def _start_atlas_server() -> str:
    global _atlas_server
    root = atlas_root()
    if not (root / ATLAS_PAGE_NAME).is_file():
        return ALADIN_LITE_HOME

    class _Handler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    handler = partial(_Handler, directory=str(root.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="sky-atlas-http", daemon=True)
    thread.start()
    _atlas_server = server
    port = int(server.server_address[1])
    return f"http://127.0.0.1:{port}/{ATLAS_PAGE_NAME}"


def atlas_page_url() -> str:
    global _atlas_server
    with _atlas_server_lock:
        if _atlas_server is not None:
            port = int(_atlas_server.server_address[1])
            return f"http://127.0.0.1:{port}/{ATLAS_PAGE_NAME}"
        return _start_atlas_server()


def stop_atlas_server() -> None:
    global _atlas_server
    with _atlas_server_lock:
        server = _atlas_server
        _atlas_server = None
    if server is None:
        return
    server.shutdown()
    server.server_close()


_SKY_NAME_UI_TEXT = re.compile(r"simbad pointer|want to know|use the simbad", re.IGNORECASE)


def clean_sky_target_name(raw: Any, fallback: str = "") -> str:
    """Return a single-line object name, dropping map UI/tooltip text."""
    text = str(raw or "").strip()
    line = next((part.strip() for part in text.splitlines() if part.strip()), "")
    line = re.sub(r"<[^>]*>", " ", line)
    line = re.sub(r"\s+", " ", line).strip()
    if not line or len(line) > 60 or _SKY_NAME_UI_TEXT.search(line):
        return fallback
    return line


def parse_atlas_harvest(raw: Any) -> dict[str, Any] | None:
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text or text in {"undefined", "null"}:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    try:
        ra = float(data.get("ra_hours"))
        dec = float(data.get("dec_degrees"))
    except (TypeError, ValueError):
        return None
    if ra != ra or dec != dec:
        return None
    name = clean_sky_target_name(data.get("name"))
    out: dict[str, Any] = {
        "name": name,
        "ra_hours": round(((ra % 24.0) + 24.0) % 24.0, 6),
        "dec_degrees": round(max(-90.0, min(90.0, dec)), 6),
    }
    obj_type = str(data.get("type") or "").strip()
    if obj_type:
        out["type"] = obj_type
    try:
        mag = float(data.get("magnitude"))
    except (TypeError, ValueError):
        mag = float("nan")
    if mag == mag:
        out["magnitude"] = mag
    return out


# Vertical field shared with Stellarium Web. On a landscape map this is
# Aladin's inscribed axis (``setFov``) and Stellarium's ``core.fov``.
SKY_MAP_FOV_DEG = 70.0


def atlas_set_fov_from_view(fov_x: Any, fov_y: Any = None) -> float | None:
    """Aladin ``setFov`` argument from ``getFov()`` ``[x, y]`` degrees.

    ``setFov`` is the inscribed (smaller) axis, so restoring ``getFov()[0]``
    zooms the map. Persist ``min(x, y)`` so a restore is a no-op. That degree
    value is the zoom Stellarium applies too.
    """
    try:
        x = float(fov_x)
    except (TypeError, ValueError):
        x = float("nan")
    try:
        y = float(fov_y) if fov_y is not None else float("nan")
    except (TypeError, ValueError):
        y = float("nan")
    if x == x and x > 0 and y == y and y > 0:
        return float(min(x, y))
    if x == x and x > 0:
        return float(x)
    if y == y and y > 0:
        return float(y)
    return None


def atlas_view_payload(ra_deg: float, dec_deg: float, fov: float | None = None) -> dict[str, Any]:
    view = {
        "ra_hours": ((float(ra_deg) / 15.0) % 24.0 + 24.0) % 24.0,
        "dec_degrees": max(-90.0, min(90.0, float(dec_deg))),
    }
    if fov is not None and fov == fov and fov > 0:
        view["fov"] = float(fov)
    return view


def sky_atlas_ready_script() -> str:
    return ATLAS_READY_JS


def sky_atlas_boot_script() -> str:
    return ATLAS_BOOT_JS


def sky_atlas_harvest_script() -> str:
    return ATLAS_HARVEST_JS


def sky_atlas_view_poll_script() -> str:
    return ATLAS_VIEW_POLL_JS


def sky_atlas_view_script(payload: dict[str, Any]) -> str:
    return f"{ATLAS_VIEW_APPLY_JS}({json.dumps(payload)})"


def sky_atlas_view_pos_script(ra_hours: float, dec_degrees: float) -> str:
    return (
        f"{ATLAS_VIEW_POS_JS}({float(ra_hours)}, {float(dec_degrees)})"
    )


def sky_atlas_pin_target_script(payload: dict[str, Any] | None = None) -> str:
    data = payload if isinstance(payload, dict) else {}
    name = str(data.get("name") or "").strip() or "FOV centre"
    body: dict[str, Any] = {"name": name}
    try:
        ra = float(data.get("ra_hours"))
        dec = float(data.get("dec_degrees"))
    except (TypeError, ValueError):
        ra = dec = float("nan")
    if ra == ra and dec == dec:
        body["ra_hours"] = ra
        body["dec_degrees"] = dec
    return f"{ATLAS_PIN_TARGET_JS}({json.dumps(body)})"


def sky_atlas_lock_target_script(payload: dict[str, Any]) -> str:
    return f"{ATLAS_LOCK_JS}({json.dumps(payload)})"


def sky_atlas_fov_script(payload: dict[str, Any]) -> str:
    return f"{ATLAS_FOV_JS}({json.dumps(payload)})"


def sky_atlas_live_script(data_url: str, enabled: bool, opacity: float, live_pane: int) -> str:
    return (
        f"{ATLAS_LIVE_JS}({json.dumps(str(data_url or ''))}, {json.dumps(bool(enabled))}, "
        f"{float(opacity)}, {int(live_pane)})"
    )


def sky_atlas_pane_script(pane_urls: dict[str, Any]) -> str:
    return f"{ATLAS_PANE_JS}({json.dumps(pane_urls)})"


def sky_atlas_open_menu_script(x: float = 0.0, y: float = 0.0) -> str:
    return f"{ATLAS_OPEN_MENU_JS}({float(x or 0.0)}, {float(y or 0.0)})"


def sky_atlas_site_script(latitude: Any, longitude: Any) -> str:
    try:
        lat = float(latitude or 0)
        lon = float(longitude or 0)
    except (TypeError, ValueError):
        lat = 0.0
        lon = 0.0
    payload = {
        "lat": lat,
        "lon": lon,
        "has_site": has_site_coordinates(lat, lon),
    }
    return f"{ATLAS_SITE_JS}({json.dumps(payload)})"


def sky_atlas_home_script() -> str:
    return ATLAS_HOME_JS


ATLAS_ASTRO_JS = r"""
(function(){
  var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
  if (box.astro && typeof box.astro.labelOnFov === "function" && typeof box.astro.drawScreenMosaic === "function"
      && typeof box.astro.drawPaneMedia === "function" && typeof box.astro.bindLiveOpacityWheel === "function"
      && typeof box.astro.paneCenterXY === "function" && typeof box.astro.overlayPixRoll === "function"
      && typeof box.astro.paintIndex === "function"
      && typeof box.astro.strokeTargetQuad === "function"
      && typeof box.astro.applyFov === "function" && typeof box.astro.markMoved === "function")
    return box.astro;
  box.lookBound = false;
  box.objectsBound = false;
  function deg(value) {
    return ((Number(value) % 360) + 360) % 360;
  }
  function clamp(value, lo, hi) {
    return Math.max(lo, Math.min(hi, value));
  }
  function gmstDeg(date) {
    var jd = date.getTime() / 86400000 + 2440587.5;
    var t = (jd - 2451545.0) / 36525.0;
    var gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
      + 0.000387933 * t * t - t * t * t / 38710000.0;
    return deg(gmst);
  }
  function lstDeg(lon, date) {
    return deg(gmstDeg(date) + Number(lon || 0));
  }
  function radecToAltaz(raDeg, decDeg, lat, lon, date) {
    var ha = (lstDeg(lon, date) - Number(raDeg)) * Math.PI / 180;
    var dec = Number(decDeg) * Math.PI / 180;
    var phi = Number(lat) * Math.PI / 180;
    var sinAlt = Math.sin(dec) * Math.sin(phi) + Math.cos(dec) * Math.cos(phi) * Math.cos(ha);
    var alt = Math.asin(clamp(sinAlt, -1, 1));
    var az = Math.atan2(
      -Math.cos(dec) * Math.sin(ha),
      Math.sin(dec) * Math.cos(phi) - Math.cos(dec) * Math.sin(phi) * Math.cos(ha)
    );
    return {az: deg(az * 180 / Math.PI), alt: alt * 180 / Math.PI};
  }
  function altazToRadec(azDeg, altDeg, lat, lon, date) {
    var az = Number(azDeg) * Math.PI / 180;
    var alt = Number(altDeg) * Math.PI / 180;
    var phi = Number(lat) * Math.PI / 180;
    var sinDec = Math.sin(alt) * Math.sin(phi) + Math.cos(alt) * Math.cos(phi) * Math.cos(az);
    var dec = Math.asin(clamp(sinDec, -1, 1));
    var cosDec = Math.cos(dec);
    var ha = 0;
    if (Math.abs(cosDec) > 1e-10 && Math.abs(Math.cos(phi)) > 1e-10) {
      ha = Math.atan2(
        -Math.sin(az) * Math.cos(alt) / cosDec,
        (Math.sin(alt) - Math.sin(dec) * Math.sin(phi)) / (cosDec * Math.cos(phi))
      );
    }
    return [deg(lstDeg(lon, date) - ha * 180 / Math.PI), dec * 180 / Math.PI];
  }
  function parallacticDeg(raDeg, decDeg, lat, lon, date) {
    var ha = (lstDeg(lon, date) - Number(raDeg)) * Math.PI / 180;
    var dec = Number(decDeg) * Math.PI / 180;
    var phi = Number(lat) * Math.PI / 180;
    return Math.atan2(
      Math.sin(ha),
      Math.tan(phi) * Math.cos(dec) - Math.sin(dec) * Math.cos(ha)
    ) * 180 / Math.PI;
  }
  function zenithRotation(raDeg, decDeg, lat, lon, date) {
    return -parallacticDeg(raDeg, decDeg, lat, lon, date);
  }
  function offsetRaDec(raHours, decDeg, eastDeg, northDeg) {
    var ra = ((Number(raHours) % 24) + 24) % 24 * Math.PI / 12;
    var dec = Number(decDeg) * Math.PI / 180;
    var eastT = Math.tan(eastDeg * Math.PI / 180);
    var northT = Math.tan(northDeg * Math.PI / 180);
    var cosDec = Math.cos(dec), sinDec = Math.sin(dec);
    var cosRa = Math.cos(ra), sinRa = Math.sin(ra);
    var x = cosDec * cosRa - eastT * sinRa - northT * sinDec * cosRa;
    var y = cosDec * sinRa + eastT * cosRa - northT * sinDec * sinRa;
    var z = sinDec + northT * cosDec;
    var n = Math.hypot(x, y, z) || 1;
    return {
      ra_hours: ((Math.atan2(y / n, x / n) * 12 / Math.PI) % 24 + 24) % 24,
      dec_degrees: Math.asin(Math.max(-1, Math.min(1, z / n))) * 180 / Math.PI
    };
  }
  function offsetCamera(raHours, decDeg, rightDeg, upDeg, paDeg) {
    var pa = (Number(paDeg) || 0) * Math.PI / 180;
    var east = -rightDeg * Math.cos(pa) + upDeg * Math.sin(pa);
    var north = rightDeg * Math.sin(pa) + upDeg * Math.cos(pa);
    return offsetRaDec(raHours, decDeg, east, north);
  }
  function cameraCorners(raHours, decDeg, fovH, fovV, paDeg) {
    var hw = Number(fovH) / 2, hh = Number(fovV) / 2;
    var pa = Number(paDeg) || 0;
    return [
      offsetCamera(raHours, decDeg, hw, hh, pa),
      offsetCamera(raHours, decDeg, hw, -hh, pa),
      offsetCamera(raHours, decDeg, -hw, -hh, pa),
      offsetCamera(raHours, decDeg, -hw, hh, pa)
    ];
  }
  function liveGridPanes(raHours, decDeg, payload) {
    var cols = Math.max(1, Number(payload && payload.columns) || 1);
    var rows = Math.max(1, Number(payload && payload.rows) || 1);
    var overlap = Math.max(0, Math.min(0.8, Number(payload && payload.overlap) || 0));
    var fovH = Number(box.fovH), fovV = Number(box.fovV);
    if (!(fovH > 0) || !(fovV > 0) || !isFinite(raHours) || !isFinite(decDeg)) return [];
    var pa = Number(box.pa);
    if (!isFinite(pa)) pa = payload && payload.south_up ? 180 : 0;
    var stepX = fovH * (1 - overlap);
    var stepY = fovV * (1 - overlap);
    var panes = [];
    var index = 0;
    for (var row = 1; row <= rows; row++) {
      var rowOffset = row - (rows + 1) / 2;
      var up = -rowOffset * stepY;
      for (var col = 1; col <= cols; col++) {
        index += 1;
        var colOffset = col - (cols + 1) / 2;
        var right = -colOffset * stepX;
        var centerPt = offsetCamera(raHours, decDeg, right, up, pa);
        panes.push({
          index: index,
          ra_hours: centerPt.ra_hours,
          dec_degrees: centerPt.dec_degrees,
          corners: cameraCorners(centerPt.ra_hours, centerPt.dec_degrees, fovH, fovV, pa)
        });
      }
    }
    return panes;
  }
  function northPixAngle(aladin, raDeg, decDeg) {
    var c = project(aladin, raDeg, decDeg);
    var n = project(aladin, raDeg, decDeg + 0.2);
    if (!c || !n) return null;
    return Math.atan2(n[0] - c[0], c[1] - n[1]) * 180 / Math.PI;
  }
  function overlayPixRoll(aladin, pos) {
    var viewRot = 0;
    try {
      if (aladin && typeof aladin.getRotation === "function")
        viewRot = Number(aladin.getRotation()) || 0;
    } catch (err) {}
    if (!isFinite(viewRot) || Math.abs(viewRot) < 0.4) return 0;
    var north = northPixAngle(aladin, pos[0], pos[1]);
    // world2pix already includes map rotation when north is not screen-up.
    if (north == null || Math.abs(north) > 12) return 0;
    return viewRot;
  }
  function facingName(az) {
    var names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    return names[Math.round(deg(az) / 45) % 8];
  }
  function aladinRef() {
    return window.aladin;
  }
  function project(aladin, raDeg, decDeg) {
    if (!aladin || typeof aladin.world2pix !== "function") return null;
    var xy = null;
    try { xy = aladin.world2pix(Number(raDeg), Number(decDeg)); } catch (err) { xy = null; }
    if (!xy) {
      try { xy = aladin.world2pix(Number(raDeg), Number(decDeg), "ICRS"); } catch (err) { xy = null; }
    }
    if (!xy) return null;
    var x = Number(xy[0] != null ? xy[0] : xy.x);
    var y = Number(xy[1] != null ? xy[1] : xy.y);
    if (!isFinite(x) || !isFinite(y)) return null;
    var size = viewSize(aladin);
    var cssW = window.innerWidth || size[0];
    var cssH = window.innerHeight || size[1];
    if (size[0] > cssW * 1.25 && cssW > 2) {
      x *= cssW / size[0];
      y *= cssH / size[1];
    }
    return [x, y];
  }
  function viewFov(aladin) {
    try {
      var zoom = aladin.getFov();
      var fov = Array.isArray(zoom) ? Number(zoom[0]) : Number(zoom);
      if (isFinite(fov) && fov > 0) return fov;
    } catch (err) {}
    return 70;
  }
  function viewSize(aladin) {
    try {
      var size = aladin.getSize();
      if (size && isFinite(Number(size[0])) && isFinite(Number(size[1])))
        return [Number(size[0]), Number(size[1])];
    } catch (err) {}
    return [window.innerWidth || 800, window.innerHeight || 600];
  }
  function unlockNorth(aladin) {
    try {
      if (aladin.view && aladin.view.wasm && typeof aladin.view.wasm.unlockNorthUp === "function")
        aladin.view.wasm.unlockNorthUp();
    } catch (err) {}
  }
  function currentRotation(aladin) {
    try {
      if (aladin && typeof aladin.getRotation === "function") {
        var rot = Number(aladin.getRotation());
        if (isFinite(rot)) return rot;
      }
    } catch (err) {}
    return 0;
  }
  function nearestAngle(current, target) {
    // Parallactic angle jumps ±180 on the branch cut (meridian, toward the
    // equator from a southern site). Set the nearest equivalent so the view
    // does not spin a full turn.
    var t = Number(target);
    var c = Number(current);
    if (!isFinite(t)) return isFinite(c) ? c : 0;
    if (!isFinite(c)) return t;
    while (t - c > 180) t -= 360;
    while (c - t > 180) t += 360;
    return t;
  }
  function wrapSigned(deg) {
    var n = Number(deg);
    if (!isFinite(n)) return 0;
    return ((n % 360) + 540) % 360 - 180;
  }
  function applyRotation(aladin, rot) {
    unlockNorth(aladin);
    var next = nearestAngle(currentRotation(aladin), rot);
    try {
      if (aladin.view && typeof aladin.view.setRotation === "function")
        aladin.view.setRotation(next);
      else if (typeof aladin.setRotation === "function")
        aladin.setRotation(next);
    } catch (err) {}
  }
  function markMoved() {
    box.userMoved = true;
    box.userMovedAt = Date.now();
  }
  function inscribedFov(aladin) {
    try {
      var zoom = aladin.getFov();
      if (Array.isArray(zoom)) {
        var fx = Number(zoom[0]), fy = Number(zoom[1]);
        if (isFinite(fx) && fx > 0 && isFinite(fy) && fy > 0) return Math.min(fx, fy);
        if (isFinite(fx) && fx > 0) return fx;
      }
      var fov = Number(zoom);
      if (isFinite(fov) && fov > 0) return fov;
    } catch (err) {}
    return 0;
  }
  function applyFov(aladin, fov) {
    var n = Number(fov);
    if (!(n > 0) || !aladin || typeof aladin.setFov !== "function") return;
    box.applyingFov = true;
    try { aladin.setFov(n); } catch (err) {}
    box.applyingFov = false;
    box.setFovValue = n;
  }
  function gotoCenter(aladin, raDeg, decDeg) {
    try { aladin.gotoRaDec(raDeg, decDeg); } catch (err) {}
  }
  function applyLook(aladin, raDeg, decDeg) {
    var rot = box.hasSite ? zenithRotation(raDeg, decDeg, box.lat, box.lon, new Date()) : 0;
    gotoCenter(aladin, raDeg, decDeg);
    applyRotation(aladin, rot);
    drawHorizon();
  }
  function lookPan(dx, dy) {
    var aladin = aladinRef();
    if (!aladin || !box.hasSite || typeof aladin.getRaDec !== "function") return;
    var pos = aladin.getRaDec();
    if (!pos) return;
    var size = viewSize(aladin);
    var degPerPx = viewFov(aladin) / Math.max(1, size[0]);
    var now = new Date();
    var hor = radecToAltaz(pos[0], pos[1], box.lat, box.lon, now);
    var azScale = degPerPx / Math.max(0.12, Math.abs(Math.cos(hor.alt * Math.PI / 180)));
    hor.az = deg(hor.az - dx * azScale);
    hor.alt = clamp(hor.alt + dy * degPerPx, -12, 89.5);
    var eq = altazToRadec(hor.az, hor.alt, box.lat, box.lon, now);
    box.lookEq = eq;
    gotoCenter(aladin, eq[0], eq[1]);
    // Keep zenith up on every step. Waiting for pointerup left the equatorial
    // map on the old roll, so the sky sheared and the FOV spun until release.
    applyRotation(aladin, zenithRotation(eq[0], eq[1], box.lat, box.lon, now));
    markMoved();
    drawHorizon();
  }
  function home() {
    var aladin = aladinRef();
    if (!aladin) return "loading";
    if (!box.hasSite) return "no-site";
    var eq = altazToRadec(180, 28, box.lat, box.lon, new Date());
    applyLook(aladin, eq[0], eq[1]);
    // SKY_MAP_FOV_DEG. Stellarium opens on this same vertical field.
    applyFov(aladin, 70);
    return "ok";
  }
  var syncTimer = 0;
  function requestSync() {
    if (box.dragging) return;
    if (syncTimer) return;
    syncTimer = setTimeout(function() {
      syncTimer = 0;
      if (!box.dragging) syncRotation();
    }, 90);
  }
  function syncRotation() {
    var aladin = aladinRef();
    if (box.dragging) {
      drawHorizon();
      return;
    }
    if (!aladin || !box.hasSite || typeof aladin.getRaDec !== "function") {
      drawHorizon();
      return;
    }
    var pos = aladin.getRaDec();
    if (!pos) return;
    applyRotation(aladin, zenithRotation(pos[0], pos[1], box.lat, box.lon, new Date()));
    drawHorizon();
  }
  function horizonCanvas() {
    var el = document.getElementById("astro-dwarf-horizon");
    if (el) return el;
    el = document.createElement("canvas");
    el.id = "astro-dwarf-horizon";
    el.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:46;";
    document.body.appendChild(el);
    return el;
  }
  function resizeCanvas(canvas) {
    var width = canvas.clientWidth || window.innerWidth || 0;
    var height = canvas.clientHeight || window.innerHeight || 0;
    if (width >= 2 && canvas.width !== width) canvas.width = width;
    if (height >= 2 && canvas.height !== height) canvas.height = height;
    return [canvas.width, canvas.height];
  }
  function drawCompass(ctx, width, angle, facing) {
    var cx = width - 46;
    var cy = 46;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.beginPath();
    ctx.arc(0, 0, 28, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(5,8,14,0.72)";
    ctx.fill();
    ctx.strokeStyle = "rgba(180,220,210,0.7)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.rotate(angle);
    ctx.fillStyle = "#d8f4ee";
    ctx.font = "bold 11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("N", 0, -16);
    ctx.fillStyle = "rgba(216,244,238,0.7)";
    ctx.font = "10px sans-serif";
    ctx.fillText("E", 16, 1);
    ctx.fillText("S", 0, 16);
    ctx.fillText("W", -16, 1);
    ctx.beginPath();
    ctx.moveTo(0, -11);
    ctx.lineTo(4, 8);
    ctx.lineTo(0, 5);
    ctx.lineTo(-4, 8);
    ctx.closePath();
    ctx.fillStyle = "#7ee0d0";
    ctx.fill();
    ctx.restore();
    ctx.beginPath();
    ctx.moveTo(cx, cy + 28);
    ctx.lineTo(cx - 5, cy + 36);
    ctx.lineTo(cx + 5, cy + 36);
    ctx.closePath();
    ctx.fillStyle = "#7ee0d0";
    ctx.fill();
    ctx.fillStyle = "rgba(216,244,238,0.92)";
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(facing, cx, 88);
  }
  function hudInsets() {
    var insets = {bottom: 28};
    var el = document.querySelector(".aladin-status-bar");
    if (el) {
      var r = el.getBoundingClientRect();
      if (r.width > 2 && r.height > 2)
        insets.bottom = Math.max(insets.bottom, Math.round((window.innerHeight || r.bottom) - r.top + 10));
    }
    return insets;
  }
  function rotatedRect(cx, cy, w, h, tilt) {
    var hw = w / 2, hh = h / 2, c = Math.cos(tilt), s = Math.sin(tilt);
    function pt(x, y) { return [cx + x * c - y * s, cy + x * s + y * c]; }
    return [pt(-hw, -hh), pt(hw, -hh), pt(hw, hh), pt(-hw, hh)];
  }
  function labelOnFov(ctx, pts, color) {
    if (!box.payload || !box.payload.label || !pts || pts.length < 2) return;
    var minX = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < pts.length; i++) {
      var x = Number(pts[i][0]), y = Number(pts[i][1]);
      if (!isFinite(x) || !isFinite(y)) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y > maxY) maxY = y;
    }
    if (!isFinite(maxY)) return;
    var text = String(box.payload.label);
    ctx.font = "12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillStyle = color;
    ctx.fillText(text, (minX + maxX) / 2, maxY + 8);
  }
  function paintIndex(ctx, x, y, text, color, span) {
    var size = Math.max(14, Math.min(20, span > 0 ? span * 0.16 : 15));
    ctx.font = size.toFixed(0) + "px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = color;
    ctx.fillText(String(text), x, y);
  }
  function strokeDotLine(ctx, x1, y1, x2, y2, color) {
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.lineCap = "round";
    ctx.setLineDash([1, 6.5]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.2;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineCap = "butt";
  }
  function strokeTargetQuad(ctx, pts, color) {
    if (!pts || pts.length < 4) return;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    ctx.setLineDash([]);
    ctx.lineJoin = "miter";
    ctx.lineCap = "butt";
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.35;
    ctx.stroke();
    ctx.lineCap = "square";
    for (var c = 0; c < 4; c++) {
      var corner = pts[c];
      var prev = pts[(c + 3) % 4];
      var next = pts[(c + 1) % 4];
      var ab = Math.hypot(prev[0] - corner[0], prev[1] - corner[1]) || 1;
      var cb = Math.hypot(next[0] - corner[0], next[1] - corner[1]) || 1;
      var reach = Math.max(14, Math.min(36, 0.28 * Math.min(ab, cb)));
      ctx.beginPath();
      ctx.moveTo(corner[0] + (prev[0] - corner[0]) / ab * reach, corner[1] + (prev[1] - corner[1]) / ab * reach);
      ctx.lineTo(corner[0], corner[1]);
      ctx.lineTo(corner[0] + (next[0] - corner[0]) / cb * reach, corner[1] + (next[1] - corner[1]) / cb * reach);
      ctx.strokeStyle = color;
      ctx.lineWidth = 4.4;
      ctx.stroke();
    }
    ctx.lineCap = "butt";
  }
  function strokeQuad(ctx, pts, color, dashed) {
    if (!pts || pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    ctx.lineJoin = "miter";
    ctx.lineCap = dashed ? "round" : "butt";
    ctx.strokeStyle = color;
    ctx.lineWidth = dashed ? 1.15 : 1.6;
    if (dashed) ctx.setLineDash([1.15, 3.4]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineCap = "butt";
  }
  function paneCenterXY(aladin, pane) {
    if (!aladin || !pane) return null;
    return project(aladin, Number(pane.ra_hours) * 15, Number(pane.dec_degrees));
  }
  function paneQuad(aladin, pane) {
    var corners = pane && pane.corners;
    if (!aladin || !corners || corners.length < 4) return null;
    var pts = [];
    for (var i = 0; i < 4; i++) {
      var xy = project(aladin, Number(corners[i].ra_hours) * 15, Number(corners[i].dec_degrees));
      if (!xy) return null;
      pts.push(xy);
    }
    return pts;
  }
  function collectProjected(aladin, panes) {
    if (!aladin || !panes || !panes.length) return [];
    var out = [];
    for (var i = 0; i < panes.length; i++) {
      var center = paneCenterXY(aladin, panes[i]);
      if (!center) continue;
      out.push({
        quad: paneQuad(aladin, panes[i]),
        center: center,
        index: Number(panes[i].index || (i + 1)),
        row: Number(panes[i].row) || 0,
        column: Number(panes[i].column) || 0
      });
    }
    return out;
  }
  function outerQuad(items) {
    if (!items || !items.length) return [];
    var all = [];
    for (var i = 0; i < items.length; i++) {
      if (items[i].quad && items[i].quad.length)
        all = all.concat(items[i].quad);
      else if (items[i].center)
        all.push(items[i].center);
    }
    if (!all.length) return [];
    if (all.length === 1) return [all[0], all[0], all[0], all[0]];
    var xs = all.map(function(pt) { return pt[0]; });
    var ys = all.map(function(pt) { return pt[1]; });
    var left = Math.min.apply(null, xs), right = Math.max.apply(null, xs);
    var top = Math.min.apply(null, ys), bottom = Math.max.apply(null, ys);
    return [[left, top], [right, top], [right, bottom], [left, bottom]];
  }
  function liveOpacity() {
    var op = Number(box.liveOpacity);
    return isFinite(op) ? Math.max(0, Math.min(1, op)) : 0.65;
  }
  function rememberImage(key, url) {
    if (!url) return null;
    var cache = box.imageCache = box.imageCache || {};
    var entry = cache[key];
    if (!entry || entry.url !== url) {
      var img = new Image();
      img.onload = function() {
        if (box.astro && typeof box.astro.drawHorizon === "function")
          box.astro.drawHorizon();
      };
      img.src = url;
      cache[key] = {url: url, img: img};
      entry = cache[key];
    }
    var ready = entry.img;
    return (ready && ready.complete && ready.width) ? ready : null;
  }
  function paneMedia(index) {
    var urls = box.paneUrls || {};
    var url = urls[String(index)] || urls[index] || "";
    return url ? rememberImage("pane:" + index, url) : null;
  }
  function liveMedia(index) {
    if (!box.liveEnabled || !box.liveUrl) return null;
    var livePane = Number(box.livePane || 0);
    if (livePane !== 0 && livePane !== Number(index)) return null;
    return rememberImage("live", box.liveUrl);
  }
  function mediaCanvas(width, height) {
    var canvas = box.mediaCanvas;
    if (!canvas) {
      canvas = document.createElement("canvas");
      box.mediaCanvas = canvas;
    }
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    return canvas;
  }
  function drawImageIn(ctx, img, pts, opacity) {
    if (!img || !img.width || !pts || pts.length < 4) return;
    ctx.save();
    ctx.globalAlpha = opacity;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    ctx.clip();
    var xs = pts.map(function(pt) { return pt[0]; });
    var ys = pts.map(function(pt) { return pt[1]; });
    var left = Math.min.apply(null, xs);
    var top = Math.min.apply(null, ys);
    var width = Math.max.apply(null, xs) - left;
    var height = Math.max.apply(null, ys) - top;
    if (width > 1 && height > 1)
      ctx.drawImage(img, left, top, width, height);
    ctx.restore();
  }
  function drawPaneMedia(ctx, index, pts, x, y, w, h) {
    var live = liveMedia(index);
    var pane = live ? null : paneMedia(index);
    var img = live || pane;
    if (!img) return;
    if (pts) drawImageIn(ctx, img, pts, 1);
    else if (w > 1 && h > 1) ctx.drawImage(img, x, y, w, h);
  }
  function mediaOverlay() {
    var el = document.getElementById("astro-dwarf-mosaic-media");
    if (el) return el;
    el = document.createElement("canvas");
    el.id = "astro-dwarf-mosaic-media";
    el.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:45;";
    var horizon = document.getElementById("astro-dwarf-horizon");
    if (horizon && horizon.parentNode)
      horizon.parentNode.insertBefore(el, horizon);
    else
      document.body.appendChild(el);
    return el;
  }
  function applyMediaOpacity() {
    var el = document.getElementById("astro-dwarf-mosaic-media");
    if (!el) return false;
    el.style.opacity = String(liveOpacity());
    return true;
  }
  function clearMediaOverlay() {
    var el = document.getElementById("astro-dwarf-mosaic-media");
    if (!el || !(el.width > 0) || !(el.height > 0)) return;
    var octx = el.getContext("2d");
    if (!octx) return;
    octx.setTransform(1, 0, 0, 1, 0, 0);
    octx.clearRect(0, 0, el.width, el.height);
  }
  function blitMosaicMedia(ctx, width, height, paint) {
    var off = mediaCanvas(width, height);
    var mctx = off.getContext("2d");
    mctx.setTransform(1, 0, 0, 1, 0, 0);
    mctx.globalCompositeOperation = "source-over";
    mctx.clearRect(0, 0, width, height);
    mctx.globalCompositeOperation = "lighten";
    paint(mctx);
    var overlay = mediaOverlay();
    if (overlay.width !== width) overlay.width = width;
    if (overlay.height !== height) overlay.height = height;
    var placed = false;
    try {
      var octx = overlay.getContext("2d");
      var t = ctx.getTransform();
      octx.setTransform(1, 0, 0, 1, 0, 0);
      octx.clearRect(0, 0, width, height);
      octx.setTransform(t.a, t.b, t.c, t.d, t.e, t.f);
      octx.drawImage(off, 0, 0);
      octx.setTransform(1, 0, 0, 1, 0, 0);
      overlay.style.opacity = String(liveOpacity());
      placed = true;
    } catch (err) {
      placed = false;
    }
    box.mediaCss = placed;
    if (placed) return;
    ctx.save();
    ctx.globalAlpha = liveOpacity();
    ctx.drawImage(off, 0, 0);
    ctx.restore();
  }
  function strokePaneRect(ctx, x, y, w, h, color, dotted) {
    ctx.lineJoin = "miter";
    ctx.lineCap = dotted ? "round" : "butt";
    ctx.strokeStyle = color;
    ctx.lineWidth = dotted ? 1.15 : 1.6;
    if (dotted) ctx.setLineDash([1.15, 3.4]);
    ctx.strokeRect(x, y, w, h);
    ctx.setLineDash([]);
    ctx.lineCap = "butt";
  }
  function drawScreenMosaic(ctx, width, height, w, h, cols, rows, overlap, tilt, color) {
    var stepX = w * (1 - overlap), stepY = h * (1 - overlap);
    var totalW = stepX * (cols - 1) + w, totalH = stepY * (rows - 1) + h;
    var payload = box.payload || {};
    var pa = Number(box.pa) || 0;
    var southUp = !!payload.south_up;
    var zenithCamera = String(payload.mount_mode || "").toUpperCase() !== "EQ"
      && String(payload.pa_source || "") === "parallactic";
    var chartEdge = (pa > 90 && pa < 270) === southUp;
    var col1OnRight = zenithCamera || chartEdge;
    var row1AtTop = zenithCamera || chartEdge;
    var cells = [];
    var index = 0;
    for (var row = 1; row <= rows; row++) {
      for (var col = 1; col <= cols; col++) {
        index += 1;
        cells.push({
          index: index,
          x: -totalW / 2 + (col1OnRight ? (cols - col) : (col - 1)) * stepX,
          y: -totalH / 2 + (row1AtTop ? (row - 1) : (rows - row)) * stepY
        });
      }
    }
    blitMosaicMedia(ctx, width, height, function(mctx) {
      mctx.translate(width / 2, height / 2);
      mctx.rotate(tilt);
      for (var i = 0; i < cells.length; i++)
        drawPaneMedia(mctx, cells[i].index, null, cells[i].x, cells[i].y, w, h);
    });
    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.rotate(tilt);
    var dotted = cols * rows > 1;
    if (dotted) {
      for (var seamCol = 1; seamCol < cols; seamCol++) {
        var sx = -totalW / 2 + (seamCol - 1) * stepX + (stepX + w) / 2;
        strokeDotLine(ctx, sx, -totalH / 2, sx, totalH / 2, color);
      }
      for (var seamRow = 1; seamRow < rows; seamRow++) {
        var sy = -totalH / 2 + (seamRow - 1) * stepY + (stepY + h) / 2;
        strokeDotLine(ctx, -totalW / 2, sy, totalW / 2, sy, color);
      }
    }
    strokeTargetQuad(ctx, [
      [-totalW / 2, -totalH / 2],
      [totalW / 2, -totalH / 2],
      [totalW / 2, totalH / 2],
      [-totalW / 2, totalH / 2]
    ], color);
    if (dotted) {
      for (var n = 0; n < cells.length; n++)
        paintIndex(ctx, cells[n].x + w / 2, cells[n].y + h / 2, cells[n].index, color, Math.min(w, h));
    }
    ctx.restore();
    return rotatedRect(width / 2, height / 2, totalW, totalH, tilt);
  }
  function paintFov(ctx, width, height) {
    clearMediaOverlay();
    var fovH = Number(box.fovH);
    var fovV = Number(box.fovV);
    if (!(fovH > 0) || !(fovV > 0)) return;
    var aladin = aladinRef();
    var fovX = 70;
    var fovY = 70 * height / Math.max(1, width);
    if (aladin) {
      try {
        var zoom = aladin.getFov();
        fovX = Number(Array.isArray(zoom) ? zoom[0] : zoom) || fovX;
        fovY = Number(Array.isArray(zoom) ? zoom[1] : 0);
        if (!(fovY > 0)) fovY = fovX * height / Math.max(1, width);
      } catch (err) {}
    }
    var w = (fovH / fovX) * width;
    var h = (fovV / fovY) * height;
    if (!(w > 4) || !(h > 4)) return;
    var payload = box.payload || {};
    var cols = Math.max(1, Number(payload.columns) || 1);
    var rows = Math.max(1, Number(payload.rows) || 1);
    var overlap = Math.max(0, Math.min(0.8, Number(payload.overlap) || 0));
    var color = String(payload.color || "#02900A");
    var chartPa = Number(box.pa) || 0;
    var southUp = !!(payload.south_up);
    var chartTilt = ((chartPa - (southUp ? 180 : 0)) % 360 + 360) % 360;
    var viewRot = 0;
    try {
      if (aladin && typeof aladin.getRotation === "function")
        viewRot = Number(aladin.getRotation()) || 0;
    } catch (err) {}
    var panes = (box.fovPanes && box.fovPanes.length) ? box.fovPanes : [];
    var mosaic = cols > 1 || rows > 1 || panes.length > 1;
    var equatorial = String(payload.mount_mode || "").toUpperCase() === "EQ";
    var zenithCamera = !equatorial && String(payload.pa_source || "") === "parallactic";
    var cameraPa = chartPa;
    if (!equatorial && box.hasSite) {
      try {
        var livePos = (box.dragging && box.lookEq) ? box.lookEq
          : (aladin && typeof aladin.getRaDec === "function" ? aladin.getRaDec() : null);
        if (livePos) {
          var liveQ = parallacticDeg(livePos[0], livePos[1], box.lat, box.lon, new Date());
          var pitch = Number(payload.mechanical_altitude);
          var past = isFinite(pitch) && pitch > 90 && pitch < 270;
          if (isFinite(liveQ)) cameraPa = ((liveQ + (past ? 180 : 0)) % 360 + 360) % 360;
        }
      } catch (err) {}
    }
    // Mosaic stays chart tilt; 1x1 uses camera PA (mosaic ? chartTilt : pa).
    // Shortest-angle sum: a ±180 parallactic wrap must not spin the box.
    var tiltPa = mosaic && !zenithCamera ? chartTilt : (equatorial ? chartPa : cameraPa);
    var tilt = wrapSigned(viewRot + tiltPa) * Math.PI / 180;
    var projected = collectProjected(aladin, panes);
    var hasQuads = false;
    for (var qi = 0; qi < projected.length; qi++) {
      if (projected[qi].quad) { hasQuads = true; break; }
    }
    if (mosaic && hasQuads) {
      var pos = null;
      try { pos = aladin && typeof aladin.getRaDec === "function" ? aladin.getRaDec() : null; } catch (err) {}
      var extra = pos ? overlayPixRoll(aladin, pos) : 0;
      ctx.save();
      if (Math.abs(extra) > 0.4) {
        ctx.translate(width / 2, height / 2);
        ctx.rotate(extra * Math.PI / 180);
        ctx.translate(-width / 2, -height / 2);
      }
      blitMosaicMedia(ctx, width, height, function(mctx) {
        for (var i = 0; i < projected.length; i++) {
          if (projected[i].quad)
            drawPaneMedia(mctx, projected[i].index, projected[i].quad, 0, 0, 0, 0);
        }
      });
      for (var i = 0; i < projected.length; i++) {
        if (mosaic) {
          var loc = projected[i].center;
          if (!loc && projected[i].quad) {
            var q = projected[i].quad, px = 0, py = 0;
            for (var n = 0; n < q.length; n++) { px += q[n][0]; py += q[n][1]; }
            loc = [px / q.length, py / q.length];
          }
          if (loc) {
            var span = 0;
            if (projected[i].quad && projected[i].quad.length >= 4) {
              var qn = projected[i].quad;
              span = Math.min(
                Math.hypot(qn[1][0] - qn[0][0], qn[1][1] - qn[0][1]),
                Math.hypot(qn[3][0] - qn[0][0], qn[3][1] - qn[0][1])
              );
            }
            paintIndex(ctx, loc[0], loc[1], projected[i].index, color, span);
          }
        }
      }
      var outer = outerQuad(projected);
      if (mosaic && outer.length >= 4) {
        function seam(p1, p2, q1, q2) {
          if (!p1 || !p2 || !q1 || !q2) return;
          strokeDotLine(ctx, (p1[0] + q1[0]) / 2, (p1[1] + q1[1]) / 2, (p2[0] + q2[0]) / 2, (p2[1] + q2[1]) / 2, color);
        }
        for (var pi = 0; pi < projected.length; pi++) {
          var item = projected[pi];
          if (!item.quad) continue;
          for (var pj = 0; pj < projected.length; pj++) {
            var other = projected[pj];
            if (!other.quad || other === item) continue;
            if (item.row && other.row === item.row && other.column === item.column + 1)
              seam(item.quad[3], item.quad[2], other.quad[0], other.quad[1]);
            else if (item.column && other.column === item.column && other.row === item.row + 1)
              seam(item.quad[1], item.quad[2], other.quad[0], other.quad[3]);
          }
        }
        strokeTargetQuad(ctx, outer, color);
      }
      labelOnFov(ctx, outer, color);
      ctx.restore();
      return;
    }
    var frame = drawScreenMosaic(ctx, width, height, w, h, cols, rows, overlap, tilt, color);
    labelOnFov(ctx, frame, color);
  }
  function drawHeadingLabels(ctx, width, height, heading, fovX) {
    var labels = [
      [0, "N"], [45, "NE"], [90, "E"], [135, "SE"],
      [180, "S"], [225, "SW"], [270, "W"], [315, "NW"]
    ];
    ctx.font = "bold 13px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (var n = 0; n < labels.length; n++) {
      var delta = ((labels[n][0] - heading + 540) % 360) - 180;
      var x = width / 2 + (delta / Math.max(8, fovX)) * width;
      if (x < 28 || x > width - 28) continue;
      var y = height - hudInsets().bottom - 24;
      ctx.fillStyle = "rgba(5,8,14,0.55)";
      ctx.fillRect(x - 14, y - 9, 28, 18);
      ctx.fillStyle = labels[n][1].length === 1 ? "#e8fff8" : "rgba(216,244,238,0.88)";
      ctx.fillText(labels[n][1], x, y + 1);
    }
  }
  function drawHorizon() {
    var canvas = horizonCanvas();
    var size = resizeCanvas(canvas);
    var ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, size[0], size[1]);
    var aladin = aladinRef();
    if (!aladin || !box.hasSite || typeof aladin.getRaDec !== "function") {
      if (!box.hasSite) {
        var pad = hudInsets();
        ctx.fillStyle = "rgba(216,244,238,0.72)";
        ctx.font = "11px sans-serif";
        ctx.fillText("Set the observing site to show the horizon and N E S W", 12, size[1] - pad.bottom);
      }
      paintFov(ctx, size[0], size[1]);
      return;
    }
    var pos = aladin.getRaDec();
    if (!pos) return;
    var now = new Date();
    var hor = radecToAltaz(pos[0], pos[1], box.lat, box.lon, now);
    var width = size[0];
    var height = size[1];
    var pts = [];
    for (var az = 0; az <= 360; az += 2) {
      var eq = altazToRadec(az, 0, box.lat, box.lon, now);
      var xy = project(aladin, eq[0], eq[1]);
      if (xy && xy[0] > -120 && xy[1] > -120 && xy[0] < width + 120 && xy[1] < height + 120)
        pts.push(xy);
    }
    pts.sort(function(a, b) { return a[0] - b[0]; });
    if (pts.length >= 2) {
      ctx.beginPath();
      ctx.moveTo(pts[0][0], height + 8);
      ctx.lineTo(pts[0][0], pts[0][1]);
      for (var i = 1; i < pts.length; i++)
        ctx.lineTo(pts[i][0], pts[i][1]);
      ctx.lineTo(pts[pts.length - 1][0], height + 8);
      ctx.closePath();
      ctx.fillStyle = "rgba(6,8,12,0.78)";
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (var j = 1; j < pts.length; j++)
        ctx.lineTo(pts[j][0], pts[j][1]);
      ctx.strokeStyle = "rgba(196,230,222,0.9)";
      ctx.lineWidth = 1.6;
      ctx.stroke();
    } else if (hor.alt < 0) {
      ctx.fillStyle = "rgba(6,8,12,0.78)";
      ctx.fillRect(0, 0, width, height);
    }
    var labels = [
      [0, "N"], [45, "NE"], [90, "E"], [135, "SE"],
      [180, "S"], [225, "SW"], [270, "W"], [315, "NW"]
    ];
    ctx.font = "bold 13px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    var placed = 0;
    for (var n = 0; n < labels.length; n++) {
      var mark = altazToRadec(labels[n][0], 2.4, box.lat, box.lon, now);
      var loc = project(aladin, mark[0], mark[1]);
      if (!loc || loc[0] < 18 || loc[1] < 18 || loc[0] > width - 18 || loc[1] > height - 18)
        continue;
      placed += 1;
      ctx.fillStyle = "rgba(5,8,14,0.55)";
      ctx.fillRect(loc[0] - 14, loc[1] - 9, 28, 18);
      ctx.fillStyle = labels[n][1].length === 1 ? "#e8fff8" : "rgba(216,244,238,0.88)";
      ctx.fillText(labels[n][1], loc[0], loc[1] + 1);
    }
    if (!placed)
      drawHeadingLabels(ctx, width, height, hor.az, viewFov(aladin));
    drawCompass(ctx, width, (hor.az - 180) * Math.PI / 180, facingName(hor.az));
    paintFov(ctx, width, height);
    var hud = hudInsets();
    ctx.fillStyle = "rgba(5,8,14,0.62)";
    ctx.fillRect(Math.max(0, width / 2 - 92), height - hud.bottom - 20, 184, 20);
    ctx.fillStyle = "rgba(216,244,238,0.92)";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(
      "AZ " + deg(hor.az).toFixed(0) + "°  " + facingName(hor.az)
        + "   ALT " + (hor.alt >= 0 ? "+" : "") + hor.alt.toFixed(0) + "°",
      width / 2,
      height - hud.bottom - 6
    );
  }
  function isChrome(el) {
    var node = el;
    while (node && node !== document.body) {
      var cls = node.className && node.className.baseVal != null
        ? String(node.className.baseVal) : String(node.className || "");
      var id = String(node.id || "");
      if (/aladin-(goto|location|stack|layers|zoom|simbad|control|input|fullscreen|grid|projection|status-bar|fov)/i.test(cls + " " + id))
        return true;
      if (/^(INPUT|BUTTON|SELECT|A|TEXTAREA|LABEL)$/.test(node.tagName || ""))
        return true;
      node = node.parentElement;
    }
    return false;
  }
  function bindLiveOpacityWheel() {
    if (box.wheelBound) return;
    box.wheelBound = true;
    document.addEventListener("wheel", function(ev) {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function")
        ev.stopImmediatePropagation();
      if (!box.liveEnabled) return;
      var delta = -Number(ev.deltaY);
      if (!isFinite(delta) || delta === 0) return;
      if (ev.deltaMode === 1) delta *= 16;
      else if (ev.deltaMode === 2) delta *= 120;
      var cur = liveOpacity();
      var next = Math.max(0, Math.min(1, Math.round((cur + delta / 120 * 0.05) * 100) / 100));
      if (next === cur) return;
      box.liveOpacity = next;
      box.wheelOpacity = true;
      box.opacityAt = Date.now();
      if (box.mediaCss && applyMediaOpacity())
        return;
      drawHorizon();
    }, {capture: true, passive: false});
  }
  function objectName(obj) {
    if (!obj) return "";
    if (typeof obj.name === "string" && obj.name.trim()) return obj.name.trim();
    var data = obj.data || obj;
    var keys = ["main_id", "MAIN_ID", "name", "NAME", "id", "ID", "oid", "target"];
    for (var i = 0; i < keys.length; i++) {
      var value = data[keys[i]];
      if (value != null && String(value).trim()) return String(value).trim();
    }
    return "";
  }
  function objectType(obj) {
    var data = (obj && obj.data) || obj || {};
    var value = data.otype || data.OTYPE || data.type || data.o_type;
    return value != null ? String(value).trim() : "";
  }
  function objectMag(obj) {
    var data = (obj && obj.data) || obj || {};
    var n = Number(data.V || data.mag || data.MAG || data.vmag || data.Vmag);
    return isFinite(n) ? n : null;
  }
  function objectRaDec(obj) {
    if (!obj) return null;
    var ra = obj.ra != null ? Number(obj.ra) : Number(obj.data && obj.data.ra);
    var dec = obj.dec != null ? Number(obj.dec) : Number(obj.data && obj.data.dec);
    if (isFinite(ra) && isFinite(dec)) return [ra, dec];
    return null;
  }
  function selectSky(obj, raDeg, decDeg) {
    var ra = Number(raDeg), dec = Number(decDeg);
    var loc = objectRaDec(obj);
    if ((!isFinite(ra) || !isFinite(dec)) && loc) {
      ra = loc[0];
      dec = loc[1];
    }
    if (!isFinite(ra) || !isFinite(dec)) return;
    var sel = {
      name: objectName(obj),
      ra_hours: ((ra / 15) % 24 + 24) % 24,
      dec_degrees: Math.max(-90, Math.min(90, dec))
    };
    var typ = objectType(obj);
    if (typ) sel.type = typ;
    var mag = objectMag(obj);
    if (mag != null) sel.magnitude = mag;
    box.selected = sel;
  }
  function bindObjects(aladin) {
    if (box.objectsBound || !aladin || typeof aladin.on !== "function") return;
    box.objectsBound = true;
    try {
      aladin.on("objectClicked", function(obj) {
        if (!obj) return;
        box.lastObject = obj;
        box.lastObjectAt = Date.now();
        var loc = objectRaDec(obj);
        if (loc) selectSky(obj, loc[0], loc[1]);
      });
    } catch (err) {}
    try {
      aladin.on("objectHovered", function(obj) {
        box.hoveredObject = obj || null;
      });
    } catch (err) {}
  }
  function bind() {
    bindLiveOpacityWheel();
    var aladin = aladinRef();
    bindObjects(aladin);
    if (box.lookBound) return;
    box.lookBound = true;
    box.lookGen = (Number(box.lookGen) || 0) + 1;
    var gen = box.lookGen;
    var host = document;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;
    host.addEventListener("pointerdown", function(ev) {
      if (box.lookGen !== gen) return;
      if (ev.button !== 0 || isChrome(ev.target)) return;
      box.dismissAt = Date.now();
      if (!box.hasSite) return;
      dragging = true;
      box.dragging = true;
      lastX = ev.clientX;
      lastY = ev.clientY;
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function") ev.stopImmediatePropagation();
    }, true);
    host.addEventListener("pointermove", function(ev) {
      if (box.lookGen !== gen) return;
      if (!dragging) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function") ev.stopImmediatePropagation();
      var dx = ev.clientX - lastX;
      var dy = ev.clientY - lastY;
      lastX = ev.clientX;
      lastY = ev.clientY;
      lookPan(dx, dy);
    }, true);
    function endDrag(ev) {
      if (box.lookGen !== gen) return;
      if (!dragging) return;
      dragging = false;
      box.dragging = false;
      box.lookEq = null;
      ev.stopPropagation();
      syncRotation();
    }
    host.addEventListener("pointerup", endDrag, true);
    host.addEventListener("pointercancel", endDrag, true);
    host.addEventListener("wheel", function(ev) {
      if (box.lookGen !== gen) return;
      if (ev.ctrlKey || ev.metaKey) return;
      if (isChrome(ev.target)) return;
      markMoved();
      box.setFovValue = 0;
    }, true);
    if (aladin && typeof aladin.on === "function") {
      try { aladin.on("positionChanged", function() { if (box.lookGen !== gen) return; requestSync(); }); } catch (err) {}
      try {
        aladin.on("zoomChanged", function() {
          if (box.lookGen !== gen) return;
          if (box.applyingFov) return;
          markMoved();
          box.setFovValue = 0;
          requestSync();
        });
      } catch (err) {}
    }
    window.addEventListener("resize", function() { drawHorizon(); });
  }
  box.astro = {
    bind: bind,
    bindLiveOpacityWheel: bindLiveOpacityWheel,
    sync: syncRotation,
    home: home,
    markMoved: markMoved,
    applyFov: function(fov) {
      applyFov(aladinRef(), fov);
    },
    inscribedFov: function() {
      return inscribedFov(aladinRef());
    },
    selectSky: selectSky,
    applyLook: function(raDeg, decDeg) {
      var aladin = aladinRef();
      if (!aladin) return;
      applyLook(aladin, raDeg, decDeg);
    },
    drawHorizon: drawHorizon,
    applyMediaOpacity: applyMediaOpacity,
    paintFov: paintFov,
    project: project,
    paneCenterXY: paneCenterXY,
    hudInsets: hudInsets,
    labelOnFov: labelOnFov,
    paintIndex: paintIndex,
    strokeTargetQuad: strokeTargetQuad,
    drawScreenMosaic: drawScreenMosaic,
    drawPaneMedia: drawPaneMedia,
    overlayPixRoll: overlayPixRoll,
    horizonOf: function(raDeg, decDeg) {
      if (!box.hasSite) return null;
      return radecToAltaz(raDeg, decDeg, box.lat, box.lon, new Date());
    }
  };
  return box.astro;
})()
"""

ATLAS_BOOT_JS = r"""
(function(){
  try {
    document.documentElement.style.userSelect = "none";
    var aladin = window.aladin;
    if (aladin && typeof aladin.setProjection === "function") {
      try {
        var proj = typeof aladin.getProjectionName === "function" ? String(aladin.getProjectionName() || "") : "";
        if (proj.toUpperCase() !== "STG") aladin.setProjection("STG");
      } catch (err) {}
    }
    try {
      if (aladin && typeof aladin.setCooGrid === "function")
        aladin.setCooGrid({color: "#8ad4c8", opacity: 0.28, labelSize: 11, enabled: true});
    } catch (err) {}
    var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    if (!document.getElementById("astro-dwarf-atlas-tooltip")) {
      var tipStyle = document.createElement("style");
      tipStyle.id = "astro-dwarf-atlas-tooltip";
      tipStyle.textContent = [
        ".aladin-location,.aladin-status-bar,.aladin-fov{overflow:visible!important}",
        ".aladin-widgets-toolbar,.aladin-simbadPointer-control,.aladin-tooltip-container,.aladin-tooltip,#aladin-tooltip-mouse{z-index:90!important;overflow:visible!important}",
        ".aladin-tooltip-container.top .aladin-tooltip,.aladin-tooltip-container.right.top .aladin-tooltip{top:0!important;left:100%!important;transform:none!important}"
      ].join("");
      document.documentElement.appendChild(tipStyle);
    }
    if (aladin && aladin.contextMenu && !box.menuHideWrapped && typeof aladin.contextMenu._hide === "function") {
      box.menuHideWrapped = true;
      var hideMenu = aladin.contextMenu._hide.bind(aladin.contextMenu);
      aladin.contextMenu._hide = function() {
        document.documentElement.classList.remove("astro-dwarf-atlas-menu");
        return hideMenu.apply(this, arguments);
      };
    }
    box.hideAtlasMenu = function() {
      document.documentElement.classList.remove("astro-dwarf-atlas-menu");
      try {
        if (aladin && aladin.contextMenu && typeof aladin.contextMenu._hide === "function")
          aladin.contextMenu._hide();
      } catch (err) {}
    };
    if (!box.menuBound) {
      box.menuBound = true;
      window.addEventListener("contextmenu", function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (typeof ev.stopImmediatePropagation === "function")
          ev.stopImmediatePropagation();
        box.hideAtlasMenu();
        box.dismissAt = 0;
        box.menu = {x: ev.clientX, y: ev.clientY, at: Date.now()};
        box.menuLast = box.menu;
        try {
          var current = String(document.title || "");
          if (current.indexOf("astro-dwarf-host:") !== 0)
            window.__astroDwarfHostTitle = current;
          document.title = "astro-dwarf-host:menu\t" + Number(ev.clientX) + "\t" + Number(ev.clientY) + "\t" + Date.now();
        } catch (err) {}
        return false;
      }, true);
      document.addEventListener("click", function(ev) {
        if (!document.documentElement.classList.contains("astro-dwarf-atlas-menu"))
          return;
        var node = ev.target;
        while (node && node !== document.body) {
          var cls = node.className && node.className.baseVal != null
            ? String(node.className.baseVal) : String(node.className || "");
          if (cls.indexOf("aladin-context-menu") >= 0)
            return;
          node = node.parentElement;
        }
        box.hideAtlasMenu();
      }, true);
    }
    """ + ATLAS_ASTRO_JS.strip() + r"""
    if (box.astro) {
      box.astro.bind();
      box.astro.sync();
    }
    return aladin ? "ok" : "loading";
  } catch (err) {
    return "error";
  }
})()
"""

ATLAS_SITE_JS = r"""
(function(p){
  try {
    var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    box.lat = Number(p && p.lat) || 0;
    box.lon = Number(p && p.lon) || 0;
    box.hasSite = !!(p && p.has_site);
    """ + ATLAS_ASTRO_JS.strip() + r"""
    if (box.astro) {
      box.astro.bind();
      box.astro.sync();
    }
    return box.astro ? "ok" : "loading";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_HOME_JS = r"""
(function(){
  try {
    var box = window.__astroDwarfAtlas;
    if (!box || !box.astro) return "loading";
    return box.astro.home();
  } catch (err) {
    return "error";
  }
})()
"""

ATLAS_READY_JS = r"""
(function(){
  try {
    if (!window.aladin || typeof window.aladin.getRaDec !== "function")
      return "loading";
    return "ok";
  } catch (err) {
    return "loading";
  }
})()
"""

ATLAS_HARVEST_JS = r"""
(function(){
  try {
    var state = window.__astroDwarfAtlas;
    if (!state || !state.selected) return JSON.stringify({});
    var sel = state.selected;
    var ra = Number(sel.ra_hours);
    var dec = Number(sel.dec_degrees);
    if (!isFinite(ra) || !isFinite(dec)) return JSON.stringify({});
    var out = {
      name: String(sel.name || ""),
      ra_hours: ra,
      dec_degrees: dec
    };
    if (sel.type) out.type = String(sel.type);
    var mag = Number(sel.magnitude);
    if (isFinite(mag)) out.magnitude = mag;
    return JSON.stringify(out);
  } catch (err) {
    return JSON.stringify({error: String(err)});
  }
})()
"""

ATLAS_VIEW_POLL_JS = r"""
(function(){
  try {
    var aladin = window.aladin;
    if (!aladin || typeof aladin.getRaDec !== "function") return "";
    var pos = aladin.getRaDec();
    if (!pos || !isFinite(Number(pos[0])) || !isFinite(Number(pos[1]))) return "";
    var box = window.__astroDwarfAtlas;
    var fov = 0;
    if (box && isFinite(Number(box.setFovValue)) && Number(box.setFovValue) > 0)
      fov = Number(box.setFovValue);
    else if (box && box.astro && typeof box.astro.inscribedFov === "function")
      fov = Number(box.astro.inscribedFov());
    else {
      try {
        var zoom = aladin.getFov();
        if (Array.isArray(zoom)) {
          var fx = Number(zoom[0]), fy = Number(zoom[1]);
          if (isFinite(fx) && fx > 0 && isFinite(fy) && fy > 0) fov = Math.min(fx, fy);
          else if (isFinite(fx) && fx > 0) fov = fx;
        } else {
          fov = Number(zoom);
        }
      } catch (err) {}
    }
    var view = {
      ra_hours: ((Number(pos[0]) / 15) % 24 + 24) % 24,
      dec_degrees: Math.max(-90, Math.min(90, Number(pos[1])))
    };
    if (isFinite(fov) && fov > 0) view.fov = fov;
    if (box && box.userMoved) view.user_moved = true;
    if (box && box.astro && typeof box.astro.horizonOf === "function") {
      var hor = box.astro.horizonOf(Number(pos[0]), Number(pos[1]));
      if (hor && isFinite(hor.az) && isFinite(hor.alt)) {
        view.az = hor.az;
        view.alt = hor.alt;
      }
    }
    return JSON.stringify(view);
  } catch (err) {
    return "";
  }
})()
"""

ATLAS_VIEW_APPLY_JS = r"""
(function(p){
  try {
    var aladin = window.aladin;
    if (!aladin) return "loading";
    var ra = Number(p && p.ra_hours);
    var dec = Number(p && p.dec_degrees);
    if (!isFinite(ra) || !isFinite(dec)) return "missing";
    var box = window.__astroDwarfAtlas;
    if (box && box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    else {
      aladin.gotoRaDec(ra * 15, dec);
      if (box && box.astro && typeof box.astro.sync === "function")
        box.astro.sync();
    }
    var fov = Number(p && p.fov);
    if (!(isFinite(fov) && fov > 0)) fov = 70;
    if (box && box.astro && typeof box.astro.applyFov === "function")
      box.astro.applyFov(fov);
    else if (typeof aladin.setFov === "function")
      aladin.setFov(fov);
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_VIEW_POS_JS = r"""
(function(raHours, decDegrees){
  try {
    var aladin = window.aladin;
    if (!aladin) return "loading";
    var ra = Number(raHours);
    var dec = Number(decDegrees);
    if (!isFinite(ra) || !isFinite(dec)) return "missing";
    var box = window.__astroDwarfAtlas;
    if (box && box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    else if (box && box.astro && typeof box.astro.sync === "function") {
      aladin.gotoRaDec(ra * 15, dec);
      box.astro.sync();
    } else {
      aladin.gotoRaDec(ra * 15, dec);
    }
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_PIN_TARGET_JS = r"""
(function(p){
  try {
    var ra = Number(p && p.ra_hours);
    var dec = Number(p && p.dec_degrees);
    if (!isFinite(ra) || !isFinite(dec)) return "missing";
    var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    box.selected = {
      name: String((p && p.name) || "FOV centre"),
      ra_hours: ((ra % 24) + 24) % 24,
      dec_degrees: Math.max(-90, Math.min(90, dec))
    };
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_LOCK_JS = r"""
(function(p){
  try {
    var aladin = window.aladin;
    if (!aladin) return JSON.stringify({status: "loading"});
    var ra = Number(p && p.ra_hours);
    var dec = Number(p && p.dec_degrees);
    var name = String((p && p.name) || "").trim();
    if (!isFinite(ra) || !isFinite(dec))
      return JSON.stringify({status: "missing"});
    var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    if (box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    else
      aladin.gotoRaDec(ra * 15, dec);
    box.selected = {
      name: name,
      ra_hours: ((ra % 24) + 24) % 24,
      dec_degrees: Math.max(-90, Math.min(90, dec))
    };
    return JSON.stringify({status: "locked"});
  } catch (err) {
    return JSON.stringify({status: "error"});
  }
})
"""

ATLAS_FOV_JS = r"""
(function(p){
  function state() {
    var box = window.__astroDwarfAtlas;
    if (!box) box = window.__astroDwarfAtlas = {};
    return box;
  }
  function syntheticPanes(payload) {
    var ra = Number(payload && (payload.target_ra_hours != null ? payload.target_ra_hours : payload.view_ra_hours));
    var dec = Number(payload && (payload.target_dec_degrees != null ? payload.target_dec_degrees : payload.view_dec_degrees));
    if (!isFinite(ra) || !isFinite(dec)) return [];
    return [{index: 1, ra_hours: ra, dec_degrees: dec, corners: []}];
  }
  function skyPoint(ev) {
    var aladin = window.aladin;
    if (!aladin || typeof aladin.pix2world !== "function") return null;
    var host = document.getElementById("aladin-lite-div");
    if (!host) return null;
    var rect = host.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var y = ev.clientY - rect.top;
    if (x < 0 || y < 0 || x > rect.width || y > rect.height) return null;
    try {
      var world = aladin.pix2world(x, y);
      if (!world || !isFinite(Number(world[0])) || !isFinite(Number(world[1]))) return null;
      return world;
    } catch (err) {
      return null;
    }
  }
  function simbadTooltipName() {
    // Only the Simbad pointer's mouse tooltip names an object. Toolbar
    // ".aladin-tooltip" spans hold control help text ("Use the Simbad
    // pointer tool!") and stay in the DOM while hidden.
    var node = document.getElementById("aladin-tooltip-mouse");
    if (!node) return "";
    try {
      var style = window.getComputedStyle(node);
      if (!style || style.display === "none" || style.visibility === "hidden") return "";
    } catch (err) {
      return "";
    }
    var text = String(node.innerText || node.textContent || "").trim();
    var line = text.split("\n")[0].replace(/\s+/g, " ").trim();
    if (!line || line.length > 60 || /simbad pointer|want to know/i.test(line)) return "";
    return line;
  }
  function pickedObject(box) {
    if (box.lastObject && (Date.now() - Number(box.lastObjectAt || 0)) < 500)
      return box.lastObject;
    return box.hoveredObject || null;
  }
  function bindInput(box) {
    if (box.clickBound === 2) return;
    box.clickBound = 2;
    document.addEventListener("dblclick", function(ev) {
      var world = skyPoint(ev);
      if (!world) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function")
        ev.stopImmediatePropagation();
      if (box.astro && typeof box.astro.applyLook === "function")
        box.astro.applyLook(world[0], world[1]);
      else if (window.aladin)
        window.aladin.gotoRaDec(world[0], world[1]);
      var obj = pickedObject(box);
      if (box.astro && typeof box.astro.selectSky === "function")
        box.astro.selectSky(obj, world[0], world[1]);
      else
        box.selected = {
          name: obj ? String(obj.name || "") : simbadTooltipName(),
          ra_hours: ((Number(world[0]) / 15) % 24 + 24) % 24,
          dec_degrees: Math.max(-90, Math.min(90, Number(world[1])))
        };
      if (box.astro && typeof box.astro.markMoved === "function")
        box.astro.markMoved();
      box.trackAt = Date.now();
    }, true);
    document.addEventListener("click", function(ev) {
      var world = skyPoint(ev);
      if (!world) return;
      var obj = pickedObject(box);
      if (!obj && simbadTooltipName())
        obj = {name: simbadTooltipName()};
      if (box.astro && typeof box.astro.selectSky === "function") {
        box.astro.selectSky(obj, world[0], world[1]);
        return;
      }
      box.selected = {
        name: obj ? String(obj.name || simbadTooltipName() || "") : "",
        ra_hours: ((Number(world[0]) / 15) % 24 + 24) % 24,
        dec_degrees: Math.max(-90, Math.min(90, Number(world[1])))
      };
    }, true);
  }
  try {
    var aladin = window.aladin;
    if (!aladin) return "loading";
    var box = state();
    box.payload = p || {};
    box.fovH = Number(p && p.fov_h);
    box.fovV = Number(p && p.fov_v);
    box.pa = Number(p && p.position_angle) || 0;
    if (p && p.live_pane != null)
      box.livePane = Math.max(0, Number(p.live_pane) || 0);
    bindInput(box);
    if (box.astro && typeof box.astro.bind === "function")
      box.astro.bind();
    if (p && p.mode === "hidden") return "hidden";
    var panes = (p && p.panes && p.panes.length) ? p.panes : syntheticPanes(p);
    box.fovPanes = panes;
    var leftover = document.getElementById("astro-dwarf-atlas-overlay");
    if (leftover && leftover.parentNode)
      leftover.parentNode.removeChild(leftover);
    if (box.astro && typeof box.astro.drawHorizon === "function")
      box.astro.drawHorizon();
    if (Number(p && p.columns) > 1 || Number(p && p.rows) > 1)
      return panes.length > 1 ? "panes" : "grid";
    return "center";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_LIVE_JS = r"""
(function(url, enabled, opacity, livePane){
  var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
  var on = !!enabled;
  var href = on ? String(url || "") : "";
  var pane = Math.max(0, Number(livePane) || 0);
  var was = !!box.liveEnabled;
  var hrefChanged = href !== String(box.liveUrl || "");
  var paneChanged = pane !== (Number(box.livePane) || 0);
  box.liveEnabled = on;
  box.liveUrl = href;
  var op = Number(opacity);
  if (!isFinite(op) || op < 0 || op > 1) op = 0.65;
  if (box.wheelOpacity) {
    if (Math.abs(Number(box.liveOpacity) - op) < 0.005)
      box.wheelOpacity = false;
  } else {
    box.liveOpacity = op;
  }
  box.livePane = pane;
  if (!hrefChanged && on === was && !paneChanged) {
    var painted = false;
    try {
      if (box.mediaCss && box.astro && typeof box.astro.applyMediaOpacity === "function")
        painted = !!box.astro.applyMediaOpacity();
    } catch (err) {}
    if (!painted) {
      try {
        if (box.astro && typeof box.astro.drawHorizon === "function")
          box.astro.drawHorizon();
      } catch (err) {}
    }
    return "opacity";
  }
  try {
    if (box.astro && typeof box.astro.drawHorizon === "function")
      box.astro.drawHorizon();
  } catch (err) {}
  return box.liveEnabled ? (box.liveUrl ? "live" : "empty") : "off";
})
"""

ATLAS_PANE_JS = r"""
(function(urls){
  var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
  box.paneUrls = urls && typeof urls === "object" ? urls : {};
  try {
    if (box.astro && typeof box.astro.drawHorizon === "function")
      box.astro.drawHorizon();
  } catch (err) {}
  return "ok";
})
"""

ATLAS_OPEN_MENU_JS = r"""
(function(x, y){
  try {
    var box = window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    var aladin = window.aladin;
    if (!aladin || !aladin.contextMenu || typeof aladin.contextMenu._show !== "function")
      return "missing";
    var last = box.menuLast || box.menu || {};
    var px = Number(x);
    var py = Number(y);
    if (!isFinite(px) || !isFinite(py) || (px === 0 && py === 0 && (last.x || last.y))) {
      px = Number(last.x) || 0;
      py = Number(last.y) || 0;
    }
    var host = aladin.aladinDiv || document.getElementById("aladin-lite-div") || document.body;
    var rect = host.getBoundingClientRect ? host.getBoundingClientRect() : {left: 0, top: 0};
    var left = px - Number(rect.left || 0);
    var top = py - Number(rect.top || 0);
    var ev = new MouseEvent("contextmenu", {
      bubbles: false,
      cancelable: true,
      clientX: px,
      clientY: py,
      view: window
    });
    document.documentElement.classList.add("astro-dwarf-atlas-menu");
    aladin.contextMenu._show({e: ev, position: {left: left, top: top}});
    var themeHost = aladin.aladinDiv || document.querySelector(".aladin-container");
    var theme = (themeHost && themeHost.getAttribute("data-theme")) || "dark";
    var themeStyle = themeHost ? window.getComputedStyle(themeHost) : null;
    var themeKeys = ["--bg-color", "--text-color", "--border-color", "--hover-color", "--error-color", "--border-size"];
    var menus = document.querySelectorAll(".aladin-context-menu, .aladin-lite-context-menu");
    for (var i = 0; i < menus.length; i++) {
      var menu = menus[i];
      menu.setAttribute("data-theme", theme);
      if (themeStyle) {
        for (var k = 0; k < themeKeys.length; k++) {
          var value = themeStyle.getPropertyValue(themeKeys[k]);
          if (value)
            menu.style.setProperty(themeKeys[k], value);
        }
      }
      menu.style.setProperty("z-index", "200", "important");
      menu.style.setProperty("pointer-events", "auto", "important");
      if (menu.parentElement !== document.body)
        document.body.appendChild(menu);
    }
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""

ATLAS_CONTEXT_POLL_JS = r"""
(function(){
  var box = window.__astroDwarfAtlas;
  if (!box || !box.menu) return "";
  var menu = box.menu;
  box.menu = null;
  return JSON.stringify({x: Number(menu.x) || 0, y: Number(menu.y) || 0});
})()
"""

ATLAS_DISMISS_POLL_JS = r"""
(function(){
  var box = window.__astroDwarfAtlas;
  if (!box || !box.dismissAt) return "";
  box.dismissAt = 0;
  return "dismiss";
})()
"""

ATLAS_DBLCLICK_POLL_JS = r"""
(function(){
  var box = window.__astroDwarfAtlas;
  if (!box || !box.trackAt) return "";
  if (Date.now() - Number(box.trackAt) > 2000) return "";
  box.trackAt = 0;
  return "track";
})()
"""

ATLAS_OPACITY_POLL_JS = r"""
(function(){
  var box = window.__astroDwarfAtlas;
  if (!box || !box.opacityAt) return "";
  if (Date.now() - Number(box.opacityAt) > 1500) return "";
  box.opacityAt = 0;
  return JSON.stringify({opacity: Number(box.liveOpacity)});
})()
"""


def sky_atlas_context_poll_script() -> str:
    return ATLAS_CONTEXT_POLL_JS


def sky_atlas_dismiss_poll_script() -> str:
    return ATLAS_DISMISS_POLL_JS


def sky_atlas_dblclick_poll_script() -> str:
    return ATLAS_DBLCLICK_POLL_JS


def sky_atlas_opacity_poll_script() -> str:
    return ATLAS_OPACITY_POLL_JS
