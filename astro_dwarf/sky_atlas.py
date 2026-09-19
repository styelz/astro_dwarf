from __future__ import annotations

import json
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
    name = str(data.get("name") or "").strip()
    return {
        "name": name,
        "ra_hours": round(((ra % 24.0) + 24.0) % 24.0, 6),
        "dec_degrees": round(max(-90.0, min(90.0, dec)), 6),
    }


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
      && typeof box.astro.paneCenterXY === "function")
    return box.astro;
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
  function applyRotation(aladin, rot) {
    unlockNorth(aladin);
    try {
      if (aladin.view && typeof aladin.view.setRotation === "function")
        aladin.view.setRotation(rot);
      else if (typeof aladin.setRotation === "function")
        aladin.setRotation(rot);
    } catch (err) {}
  }
  function applyLook(aladin, raDeg, decDeg) {
    var rot = box.hasSite ? zenithRotation(raDeg, decDeg, box.lat, box.lon, new Date()) : 0;
    try { aladin.gotoRaDec(raDeg, decDeg); } catch (err) {}
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
    applyLook(aladin, eq[0], eq[1]);
  }
  function home() {
    var aladin = aladinRef();
    if (!aladin) return "loading";
    if (!box.hasSite) return "no-site";
    var eq = altazToRadec(180, 28, box.lat, box.lon, new Date());
    applyLook(aladin, eq[0], eq[1]);
    if (typeof aladin.setFov === "function") {
      try { aladin.setFov(70); } catch (err) {}
    }
    return "ok";
  }
  function syncRotation() {
    var aladin = aladinRef();
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
    var a = 0, bestY = Infinity;
    if (pts.length >= 4) {
      for (var i = 0; i < 4; i++) {
        var my = (pts[i][1] + pts[(i + 1) % 4][1]) / 2;
        if (my < bestY) { bestY = my; a = i; }
      }
    }
    var ax = pts[a][0], ay = pts[a][1], bx = pts[(a + 1) % pts.length][0], by = pts[(a + 1) % pts.length][1];
    var mx = (ax + bx) / 2, my = (ay + by) / 2, cx = 0, cy = 0;
    for (var k = 0; k < pts.length; k++) { cx += pts[k][0]; cy += pts[k][1]; }
    cx /= pts.length; cy /= pts.length;
    var dx = mx - cx, dy = my - cy, len = Math.hypot(dx, dy) || 1;
    var ang = Math.atan2(by - ay, bx - ax);
    if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;
    ctx.save();
    ctx.translate(mx + dx / len * 12, my + dy / len * 12);
    ctx.rotate(ang);
    ctx.fillStyle = color;
    ctx.strokeStyle = "rgba(5,8,14,0.85)";
    ctx.lineWidth = 3;
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.strokeText(String(box.payload.label), 0, 0);
    ctx.fillText(String(box.payload.label), 0, 0);
    ctx.restore();
  }
  function strokeQuad(ctx, pts, color, dashed) {
    if (!pts || pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
    ctx.closePath();
    ctx.strokeStyle = "rgba(5,8,14,0.85)";
    ctx.lineWidth = dashed ? 2 : 4;
    ctx.stroke();
    ctx.strokeStyle = color;
    ctx.lineWidth = dashed ? 1.5 : 2;
    if (dashed) ctx.setLineDash([5, 4]);
    ctx.stroke();
    ctx.setLineDash([]);
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
        index: Number(panes[i].index || (i + 1))
      });
    }
    return out;
  }
  function northIsDown(aladin) {
    if (!aladin || typeof aladin.getRaDec !== "function") return false;
    var pos = aladin.getRaDec();
    if (!pos) return false;
    var a = project(aladin, pos[0], pos[1]);
    var b = project(aladin, pos[0], Math.min(90, Number(pos[1]) + Math.max(0.2, viewFov(aladin) * 0.05)));
    return !!(a && b && b[1] > a[1]);
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
    var pane = paneMedia(index);
    var live = liveMedia(index);
    if (pane) {
      if (pts) drawImageIn(ctx, pane, pts, 0.85);
      else if (w > 1 && h > 1) {
        ctx.save();
        ctx.globalAlpha = 0.85;
        ctx.drawImage(pane, x, y, w, h);
        ctx.restore();
      }
    }
    if (live) {
      if (pts) drawImageIn(ctx, live, pts, liveOpacity());
      else if (w > 1 && h > 1) {
        ctx.save();
        ctx.globalAlpha = liveOpacity();
        ctx.drawImage(live, x, y, w, h);
        ctx.restore();
      }
    }
  }
  function drawScreenMosaic(ctx, width, height, w, h, cols, rows, overlap, tilt, color) {
    var stepX = w * (1 - overlap), stepY = h * (1 - overlap);
    var totalW = stepX * (cols - 1) + w, totalH = stepY * (rows - 1) + h;
    var pa = Number(box.pa) || 0;
    var col1OnRight = !(pa > 90 && pa < 270);
    var row1AtTop = !northIsDown(aladinRef());
    ctx.save();
    ctx.translate(width / 2, height / 2);
    ctx.rotate(tilt);
    var index = 0;
    for (var row = 1; row <= rows; row++) {
      for (var col = 1; col <= cols; col++) {
        index += 1;
        var x = -totalW / 2 + (col1OnRight ? (cols - col) : (col - 1)) * stepX;
        var y = -totalH / 2 + (row1AtTop ? (row - 1) : (rows - row)) * stepY;
        drawPaneMedia(ctx, index, null, x, y, w, h);
        ctx.strokeStyle = "rgba(5,8,14,0.85)";
        ctx.lineWidth = 4;
        ctx.strokeRect(x, y, w, h);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        if (cols * rows > 1) {
          ctx.fillStyle = color;
          ctx.font = "12px sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(index), x + w / 2, y + h / 2);
        }
      }
    }
    if (cols * rows > 1) {
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(-totalW / 2, -totalH / 2, totalW, totalH);
      ctx.setLineDash([]);
    }
    ctx.beginPath();
    ctx.moveTo(0, -totalH / 2);
    ctx.lineTo(0, -totalH / 2 - 10);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
    return rotatedRect(width / 2, height / 2, totalW, totalH, tilt);
  }
  function paintFov(ctx, width, height) {
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
    var color = String(payload.color || "#7ee0d0");
    var pa = Number(box.pa) || 0;
    var viewRot = 0;
    try {
      if (aladin && typeof aladin.getRotation === "function")
        viewRot = Number(aladin.getRotation()) || 0;
    } catch (err) {}
    var tilt = (viewRot + pa) * Math.PI / 180;
    var panes = (box.fovPanes && box.fovPanes.length) ? box.fovPanes : [];
    var mosaic = cols > 1 || rows > 1 || panes.length > 1;
    var projected = collectProjected(aladin, panes);
    if (projected.length) {
      for (var i = 0; i < projected.length; i++) {
        if (projected[i].quad) {
          drawPaneMedia(ctx, projected[i].index, projected[i].quad, 0, 0, 0, 0);
          strokeQuad(ctx, projected[i].quad, color, false);
        }
        if (mosaic) {
          var loc = projected[i].center;
          if (!loc && projected[i].quad) {
            var q = projected[i].quad, px = 0, py = 0;
            for (var n = 0; n < q.length; n++) { px += q[n][0]; py += q[n][1]; }
            loc = [px / q.length, py / q.length];
          }
          if (loc) {
            ctx.fillStyle = color;
            ctx.font = "12px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(String(projected[i].index), loc[0], loc[1]);
          }
        }
      }
      var outer = outerQuad(projected);
      if (mosaic) strokeQuad(ctx, outer, color, true);
      labelOnFov(ctx, outer, color);
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
      drawHorizon();
    }, {capture: true, passive: false});
  }
  function bind() {
    bindLiveOpacityWheel();
    if (box.lookBound) return;
    box.lookBound = true;
    var host = document;
    var dragging = false;
    var lastX = 0;
    var lastY = 0;
    host.addEventListener("pointerdown", function(ev) {
      if (ev.button !== 0 || !box.hasSite || isChrome(ev.target)) return;
      dragging = true;
      lastX = ev.clientX;
      lastY = ev.clientY;
      ev.preventDefault();
      ev.stopPropagation();
      if (typeof ev.stopImmediatePropagation === "function") ev.stopImmediatePropagation();
    }, true);
    host.addEventListener("pointermove", function(ev) {
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
      if (!dragging) return;
      dragging = false;
      ev.stopPropagation();
    }
    host.addEventListener("pointerup", endDrag, true);
    host.addEventListener("pointercancel", endDrag, true);
    var aladin = aladinRef();
    if (aladin && typeof aladin.on === "function") {
      try { aladin.on("positionChanged", function() { syncRotation(); }); } catch (err) {}
      try { aladin.on("zoomChanged", function() { syncRotation(); }); } catch (err) {}
    }
    window.addEventListener("resize", function() { drawHorizon(); });
  }
  box.astro = {
    bind: bind,
    bindLiveOpacityWheel: bindLiveOpacityWheel,
    sync: syncRotation,
    home: home,
    applyLook: function(raDeg, decDeg) {
      var aladin = aladinRef();
      if (!aladin) return;
      applyLook(aladin, raDeg, decDeg);
    },
    drawHorizon: drawHorizon,
    paintFov: paintFov,
    project: project,
    paneCenterXY: paneCenterXY,
    hudInsets: hudInsets,
    labelOnFov: labelOnFov,
    drawScreenMosaic: drawScreenMosaic,
    drawPaneMedia: drawPaneMedia,
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
        box.menu = {x: ev.clientX, y: ev.clientY, at: Date.now()};
        box.menuLast = box.menu;
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
    return JSON.stringify({
      name: String(sel.name || ""),
      ra_hours: ra,
      dec_degrees: dec
    });
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
    var fov = 0;
    try {
      var zoom = aladin.getFov();
      fov = Array.isArray(zoom) ? Number(zoom[0]) : Number(zoom);
    } catch (err) {}
    var view = {
      ra_hours: ((Number(pos[0]) / 15) % 24 + 24) % 24,
      dec_degrees: Math.max(-90, Math.min(90, Number(pos[1])))
    };
    if (isFinite(fov) && fov > 0) view.fov = fov;
    var box = window.__astroDwarfAtlas;
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
    aladin.gotoRaDec(ra * 15, dec);
    var fov = Number(p && p.fov);
    if (isFinite(fov) && fov > 0 && typeof aladin.setFov === "function")
      aladin.setFov(fov);
    var box = window.__astroDwarfAtlas;
    if (box && box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    else if (box && box.astro && typeof box.astro.sync === "function")
      box.astro.sync();
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
    aladin.gotoRaDec(ra * 15, dec);
    var box = window.__astroDwarfAtlas;
    if (box && box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    else if (box && box.astro && typeof box.astro.sync === "function")
      box.astro.sync();
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
    aladin.gotoRaDec(ra * 15, dec);
    window.__astroDwarfAtlas = window.__astroDwarfAtlas || {};
    var box = window.__astroDwarfAtlas;
    if (box.astro && typeof box.astro.applyLook === "function")
      box.astro.applyLook(ra * 15, dec);
    window.__astroDwarfAtlas.selected = {
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
  function bindInput(box) {
    if (box.bound) return;
    box.bound = true;
    document.addEventListener("dblclick", function() {
      box.trackAt = Date.now();
    }, true);
    document.addEventListener("click", function(ev) {
      var aladin = window.aladin;
      if (!aladin || typeof aladin.pix2world !== "function") return;
      var host = document.getElementById("aladin-lite-div");
      if (!host) return;
      var rect = host.getBoundingClientRect();
      var x = ev.clientX - rect.left;
      var y = ev.clientY - rect.top;
      if (x < 0 || y < 0 || x > rect.width || y > rect.height) return;
      try {
        var world = aladin.pix2world(x, y);
        if (!world || !isFinite(Number(world[0])) || !isFinite(Number(world[1]))) return;
        box.selected = {
          name: "",
          ra_hours: ((Number(world[0]) / 15) % 24 + 24) % 24,
          dec_degrees: Math.max(-90, Math.min(90, Number(world[1])))
        };
      } catch (err) {}
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
  box.liveEnabled = !!enabled;
  box.liveUrl = enabled ? String(url || "") : "";
  var op = Number(opacity);
  if (!isFinite(op) || op < 0 || op > 1) op = 0.65;
  if (box.wheelOpacity) {
    if (Math.abs(Number(box.liveOpacity) - op) < 0.005)
      box.wheelOpacity = false;
  } else {
    box.liveOpacity = op;
  }
  box.livePane = Math.max(0, Number(livePane) || 0);
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


def sky_atlas_dblclick_poll_script() -> str:
    return ATLAS_DBLCLICK_POLL_JS


def sky_atlas_opacity_poll_script() -> str:
    return ATLAS_OPACITY_POLL_JS
