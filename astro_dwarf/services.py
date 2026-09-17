from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta
from math import asin, atan2, ceil, cos, pi, radians, sin, tan
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .version import __version__
from .domain import (
    Camera,
    DeviceModel,
    HardwareProfile,
    Mosaic,
    Session,
    SessionTemplate,
    Target,
    TargetKind,
    Workflow,
    camera_fov,
    new_id,
)

STELLARIUM_WEB_URL = "https://stellarium-web.org/"
# Stellarium Web shows "This site uses cookies... I Agree" and the atlas is WebGL.
SKY_WEB_BOOT_JS = r"""
(function() {
  function labelOf(node) {
    return String(node.innerText || node.textContent || node.value || "")
      .replace(/\s+/g, " ").trim();
  }
  function isAgree(text) {
    return /^i agree$/i.test(text) || /^accept( all)?$/i.test(text) || /^agree$/i.test(text);
  }
  try {
    var clicked = false;
    var nodes = document.querySelectorAll("button, [role='button'], a, input[type='button'], .v-btn, [class*='btn']");
    for (var i = 0; i < nodes.length; i++) {
      if (isAgree(labelOf(nodes[i]))) {
        nodes[i].click();
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      var all = document.querySelectorAll("div, span, p, button, a");
      for (var j = 0; j < all.length; j++) {
        if (isAgree(labelOf(all[j]))) {
          var target = all[j].closest("button, [role='button'], a, .v-btn") || all[j];
          target.click();
          clicked = true;
          break;
        }
      }
    }
    try {
      var app = document.getElementById("app");
      var vue = app && app.__vue_app__;
      var store = vue && vue.config && vue.config.globalProperties && vue.config.globalProperties.$store;
      if (store && store.state) {
        if (store.state.showCookieNotice)
          store.commit("toggleBool", "showCookieNotice");
        if (store.state.showCookies)
          store.commit("toggleBool", "showCookies");
      }
    } catch (err) {}
    var walk = document.querySelectorAll("div, section, aside");
    for (var k = 0; k < walk.length; k++) {
      var blob = labelOf(walk[k]);
      if (/this site uses cookies/i.test(blob) && blob.length < 400) {
        walk[k].style.display = "none";
      }
    }
    var canvas = document.querySelector("canvas");
    var gl = null;
    if (canvas) {
      try { gl = canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl"); }
      catch (err) {}
    }
    return clicked ? "clicked" : (gl ? "ok" : "waiting");
  } catch (err) {
    return "error";
  }
})()
"""
MAX_MOSAIC_AXIS = 10
DEFAULT_TELE_FOV_H, DEFAULT_TELE_FOV_V = camera_fov(DeviceModel.DWARF_3, Camera.TELE)
DEFAULT_WIDE_FOV_H, DEFAULT_WIDE_FOV_V = camera_fov(DeviceModel.DWARF_3, Camera.WIDE)

# Read the object selected in Stellarium Web (Vue store / engine SweObj).
SKY_WEB_HARVEST_JS = r"""
(function() {
  function fail(message) {
    return JSON.stringify({error: message});
  }
  function pad(value, width) {
    var text = String(Math.floor(Math.abs(value)));
    while (text.length < width) text = "0" + text;
    return text;
  }
  function cleanName(raw, stel) {
    var text = String(raw || "");
    if (stel && typeof stel.designationCleanup === "function") {
      try { text = stel.designationCleanup(text, 26) || text; } catch (err) {}
    }
    return text.replace(/^NAME\s+/i, "").replace(/^CON\s+/i, "").trim();
  }
  function uniqueNames(names, stel) {
    var seen = {};
    var list = [];
    (names || []).forEach(function(item) {
      var name = cleanName(item, stel);
      if (!name || seen[name]) return;
      seen[name] = true;
      list.push(name);
    });
    return list;
  }
  function pickName(names) {
    var common = names.find(function(item) {
      return !/^(M|NGC|IC|PGC|UGC|HD|HIP|SAO|GJ|BD|CD|HR|TYC|IRAS|2MASS|WISE)\s/i.test(item);
    });
    if (common) return common;
    var messier = names.find(function(item) { return /^(M|NGC|IC)\s/i.test(item); });
    return messier || names[0] || "Stellarium target";
  }
  function formatRA(hours) {
    var h = ((hours % 24) + 24) % 24;
    var hh = Math.floor(h);
    var m = (h - hh) * 60;
    var mm = Math.floor(m);
    var s = (m - mm) * 60;
    return pad(hh, 2) + "h " + pad(mm, 2) + "m " + s.toFixed(1).padStart(4, "0") + "s";
  }
  function formatDec(degrees) {
    var sign = degrees < 0 ? "-" : "+";
    var d = Math.abs(degrees);
    var dd = Math.floor(d);
    var m = (d - dd) * 60;
    var mm = Math.floor(m);
    var s = (m - mm) * 60;
    return sign + pad(dd, 2) + "\u00b0 " + pad(mm, 2) + "' " + s.toFixed(1).padStart(4, "0") + '"';
  }
  function formatDistance(meters) {
    if (!meters || !isFinite(meters) || meters <= 0) return "";
    var au = meters / 149597870700;
    var ly = au / 63241.077;
    if (ly >= 0.1) return ly.toFixed(2) + " light years";
    if (au >= 0.1) return au.toFixed(2) + " AU";
    if (meters >= 1000) return (meters / 1000).toFixed(2) + " km";
    return meters.toFixed(2) + " m";
  }
  function jsonOf(obj) {
    if (!obj) return {};
    try {
      var data = typeof obj.jsonData === "function" ? obj.jsonData() : obj.jsonData;
      return data && typeof data === "object" ? data : {};
    } catch (err) {
      return {};
    }
  }
  function asSwe(obj, stel) {
    if (!obj) return null;
    if (typeof obj.getPosIcrf === "function") return obj;
    if (typeof obj.v === "number" && stel.SweObj) {
      try {
        var wrapped = new stel.SweObj(obj.v);
        if (wrapped.retain) wrapped.retain();
        return wrapped;
      } catch (err) {
        return null;
      }
    }
    return null;
  }
  function fromSwe(obj, stel) {
    var swe = asSwe(obj, stel);
    if (!swe) return null;
    var observer = stel.observer;
    if (!observer) return null;
    var pos = swe.getPosIcrf(observer);
    if (!pos) return null;
    var sph = stel.c2s(pos);
    if (!sph || sph.length < 2) return null;
    var raHours = ((sph[0] * 12 / Math.PI) % 24 + 24) % 24;
    var decDeg = sph[1] * 180 / Math.PI;
    var names = [];
    try { names = swe.designations() || []; } catch (err) {}
    var json = jsonOf(swe);
    if (!names.length && json.names) names = json.names;
    if (!names.length && obj && obj.names) names = obj.names;
    if (!names.length && obj && (obj.short_name || obj.match)) names = [obj.short_name || obj.match];
    var cleaned = uniqueNames(names, stel);
    var name = pickName(cleaned);
    var aliases = cleaned.filter(function(item) { return item !== name; });
    var model = json.model_data || {};
    var objectType = "";
    try {
      objectType = (stel.otypeToStr && json.otype) ? (stel.otypeToStr(json.otype) || "") : "";
    } catch (err) {}
    var magnitude = null;
    try {
      var mag = typeof swe.getVMag === "function" ? swe.getVMag(observer) : model.Vmag;
      if (mag || mag === 0) magnitude = Number(mag);
    } catch (err) {}
    var distance = "";
    try {
      if (typeof swe.getDistance === "function")
        distance = formatDistance(swe.getDistance(observer));
    } catch (err) {}
    var size = "";
    if (model.dimx && model.dimy)
      size = Number(model.dimx).toFixed(1) + "' \u00d7 " + Number(model.dimy).toFixed(1) + "'";
    return {
      name: name,
      ra_hours: raHours,
      dec_degrees: decDeg,
      ra_text: formatRA(raHours),
      dec_text: formatDec(decDeg),
      type: objectType && objectType !== "Unknown Type" ? objectType : "",
      aliases: aliases.slice(0, 12),
      magnitude: isFinite(magnitude) ? magnitude : null,
      distance: distance,
      spectral_type: model.spect_t || "",
      morphology: model.morpho || "",
      size: size
    };
  }
  function fromAny(obj, stel) {
    var direct = fromSwe(obj, stel);
    if (direct) return direct;
    var uri = obj && (obj.resolve_uri || (obj.jsonData && obj.jsonData.resolve_uri));
    if (uri && stel.resolveObjByUri) {
      try { return fromSwe(stel.resolveObjByUri(uri), stel); } catch (err) {}
    }
    return null;
  }
  try {
    var stel = window._stel;
    if (!stel) return fail("Stellarium Web is still loading");
    var store = null;
    var gp = null;
    try {
      var app = document.getElementById("app");
      var vue = app && app.__vue_app__;
      gp = vue && vue.config && vue.config.globalProperties;
      store = gp && gp.$store;
    } catch (err) {}
    var selected = store && store.state && store.state.selectedObject;
    var core = stel.core || {};
    if (gp && gp.$stel) {
      if (!stel.otypeToStr && gp.$stel.otypeToStr) stel.otypeToStr = gp.$stel.otypeToStr;
      if (!stel.designationCleanup && gp.$stel.designationCleanup)
        stel.designationCleanup = gp.$stel.designationCleanup;
    }
    var result = fromAny(selected, stel)
      || fromAny(core.selection, stel)
      || fromAny(core.lock, stel)
      || fromAny(gp && gp.$stel && gp.$stel.core && gp.$stel.core.selection, stel);
    if (!result) return fail("Select a target in the sky map");
    return JSON.stringify(result);
  } catch (err) {
    return fail("Select a target in the sky map");
  }
})()
"""

# Sync the selected telescope's site into Stellarium Web (engine uses radians).
SKY_WEB_SITE_JS = r"""
(function(p) {
  try {
    var app = document.getElementById("app");
    var vue = app && app.__vue_app__;
    var gp = vue && vue.config && vue.config.globalProperties;
    var store = gp && gp.$store;
    if (!store)
      return "loading";
    if (store.state && store.state.showNavigationDrawer)
      store.commit("toggleBool", "showNavigationDrawer");
    var stel = window._stel;
    if (!stel || !stel.core || !stel.observer || typeof stel.setLocation !== "function")
      return "loading";
    if (p.has_site)
      stel.setLocation(p.lat * Math.PI / 180, p.lon * Math.PI / 180, 0);
    if (p.timezone) stel.core.timezone = p.timezone;
    if (p.name) stel.core.location_name = p.name;
    if (store) {
      store.commit("setUseAutoLocation", false);
      if (p.has_site) {
        store.commit("setCurrentLocation", {
          short_name: p.name,
          country: "",
          lng: p.lon,
          lat: p.lat,
          alt: 0,
          accuracy: 0,
          street_address: ""
        });
      }
    }
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""


def sky_web_site_script(latitude: Any, longitude: Any, timezone: str, name: str) -> str:
    try:
        lat = float(latitude or 0)
        lon = float(longitude or 0)
    except (TypeError, ValueError):
        lat = 0.0
        lon = 0.0
    zone = str(timezone or "UTC").strip() or "UTC"
    label = str(name or "").strip() or zone
    payload = json.dumps({
        "lat": lat,
        "lon": lon,
        "timezone": zone,
        "name": label,
        "has_site": abs(lat) >= 1e-9 or abs(lon) >= 1e-9,
    })
    return f"{SKY_WEB_SITE_JS}({payload})"


# Draw Dwarf FOV / mosaic panes on Stellarium Web (injected overlay, not QML).
# Also binds double-click so a selected object is centered/locked like the
# Stellarium Web star-in-circle control, and flags the click for optional GOTO.
SKY_WEB_FOV_JS = r"""
(function(p) {
  var ID = "astro-dwarf-sky-overlay";
  var CTL = "__astroDwarfFovCtl";
  function skyCanvas() {
    var nodes = document.querySelectorAll("canvas");
    var best = null;
    var area = 0;
    for (var i = 0; i < nodes.length; i++) {
      var box = nodes[i].getBoundingClientRect();
      var next = box.width * box.height;
      if (next > area) {
        area = next;
        best = nodes[i];
      }
    }
    return area > 4 ? best : null;
  }
  function canvasRect() {
    var canvas = skyCanvas();
    return canvas ? canvas.getBoundingClientRect() : null;
  }
  function overlayFor(box) {
    var canvas = skyCanvas();
    var host = canvas && canvas.parentElement;
    var el = document.getElementById(ID);
    if (!el) {
      el = document.createElement("div");
      el.id = ID;
      el.style.cssText = "pointer-events:none;z-index:0;overflow:visible;";
    }
    if (host && el.parentElement !== host) {
      if (canvas.nextSibling)
        host.insertBefore(el, canvas.nextSibling);
      else
        host.appendChild(el);
    } else if (!host && !el.parentElement) {
      document.body.appendChild(el);
    }
    var cs = host ? getComputedStyle(host) : null;
    var contained = !!(host && cs && (cs.position !== "static" || (cs.transform && cs.transform !== "none")));
    if (contained) {
      var origin = host.getBoundingClientRect();
      el.style.position = "absolute";
      el.style.left = (box.left - origin.left) + "px";
      el.style.top = (box.top - origin.top) + "px";
    } else {
      el.style.position = "fixed";
      el.style.left = box.left + "px";
      el.style.top = box.top + "px";
    }
    el.style.width = box.width + "px";
    el.style.height = box.height + "px";
    el.style.display = "block";
    return el;
  }
  function hideOverlay() {
    var el = document.getElementById(ID);
    if (el) el.style.display = "none";
    return "hidden";
  }
  function nightModeOn() {
    try {
      var night = document.getElementById("nightmode");
      if (night) {
        var vis = "";
        try { vis = (night.style && night.style.visibility) || getComputedStyle(night).visibility || ""; } catch (err) {}
        if (String(vis).toLowerCase() === "visible")
          return true;
      }
      var app = document.getElementById("app");
      var vue = app && app.__vue_app__;
      var gp = vue && vue.config && vue.config.globalProperties;
      var store = gp && gp.$store;
      if (store && store.state && store.state.nightmode === true)
        return true;
    } catch (err) {}
    return false;
  }
  function resolvedColor(p) {
    return nightModeOn() ? "#ff2200" : String((p && p.color) || "#7ee0d0");
  }
  function paneStroke(color, dotted) {
    return 'stroke="' + color + '" stroke-width="1.2" stroke-opacity="0.9"'
      + (dotted ? ' stroke-dasharray="2 3.5" stroke-linecap="round"' : "");
  }
  function outerStroke(color) {
    return 'fill="none" stroke="' + color + '" stroke-width="1.35" stroke-opacity="0.95"';
  }
  function viewFovRad(stel) {
    var fov = Number(stel && stel.core && stel.core.fov);
    if (!(fov > 0) || !isFinite(fov)) return 0;
    return fov > Math.PI ? fov * Math.PI / 180 : fov;
  }
  function asVec(value) {
    if (!value) return null;
    if (value.length >= 3) {
      var x = Number(value[0]), y = Number(value[1]), z = Number(value[2]);
      if (!isFinite(x) || !isFinite(y) || !isFinite(z)) return null;
      return [x, y, z, value.length > 3 ? Number(value[3]) || 0 : 0];
    }
    if (value.x !== undefined) {
      var vx = Number(value.x), vy = Number(value.y), vz = Number(value.z);
      if (!isFinite(vx) || !isFinite(vy) || !isFinite(vz)) return null;
      return [vx, vy, vz, 0];
    }
    return null;
  }
  function sphericalToCart(stel, ra, dec) {
    if (typeof stel.s2c === "function") {
      try {
        var v = asVec(stel.s2c(ra, dec));
        if (v) return v;
      } catch (err) {}
    }
    var cdec = Math.cos(dec);
    return [cdec * Math.cos(ra), cdec * Math.sin(ra), Math.sin(dec), 0];
  }
  function xyzToRaDec(xyz) {
    var n = Math.hypot(xyz[0], xyz[1], xyz[2]) || 1;
    var x = xyz[0] / n, y = xyz[1] / n, z = xyz[2] / n;
    return {
      ra_hours: ((Math.atan2(y, x) * 12 / Math.PI) % 24 + 24) % 24,
      dec_degrees: Math.asin(Math.max(-1, Math.min(1, z))) * 180 / Math.PI
    };
  }
  function raDecToXyz(raHours, decDeg) {
    var ra = ((Number(raHours) % 24) + 24) % 24 * Math.PI / 12;
    var dec = Number(decDeg) * Math.PI / 180;
    var c = Math.cos(dec);
    return [c * Math.cos(ra), c * Math.sin(ra), Math.sin(dec)];
  }
  function offsetRaDec(raHours, decDeg, eastDeg, northDeg) {
    var ra = ((Number(raHours) % 24) + 24) % 24 * Math.PI / 12;
    var dec = Number(decDeg) * Math.PI / 180;
    var eastT = Math.tan(eastDeg * Math.PI / 180);
    var northT = Math.tan(northDeg * Math.PI / 180);
    var cosDec = Math.cos(dec), sinDec = Math.sin(dec);
    var cosRa = Math.cos(ra), sinRa = Math.sin(ra);
    return xyzToRaDec([
      cosDec * cosRa - eastT * sinRa - northT * sinDec * cosRa,
      cosDec * sinRa + eastT * cosRa - northT * sinDec * sinRa,
      sinDec + northT * cosDec
    ]);
  }
  function offsetCamera(raHours, decDeg, rightDeg, upDeg, paDeg) {
    var pa = (Number(paDeg) || 0) * Math.PI / 180;
    // North-up sky chart: east is left, so camera-right is west at PA 0.
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
  function densifyCorners(corners, steps) {
    steps = Math.max(1, steps || 8);
    if (!corners || corners.length < 2) return corners || [];
    var out = [];
    for (var i = 0; i < corners.length; i++) {
      var a = raDecToXyz(corners[i].ra_hours, corners[i].dec_degrees);
      var next = corners[(i + 1) % corners.length];
      var b = raDecToXyz(next.ra_hours, next.dec_degrees);
      for (var s = 0; s < steps; s++) {
        var t = s / steps;
        out.push(xyzToRaDec([
          a[0] + (b[0] - a[0]) * t,
          a[1] + (b[1] - a[1]) * t,
          a[2] + (b[2] - a[2]) * t
        ]));
      }
    }
    return out;
  }
  function convertToView(stel, xyz) {
    if (!xyz || !stel.observer || typeof stel.convertFrame !== "function") return null;
    var dir = [xyz[0], xyz[1], xyz[2], 0];
    var frames = ["ICRF", "CIRS", "JNOW"];
    for (var i = 0; i < frames.length; i++) {
      try {
        var view = asVec(stel.convertFrame(stel.observer, frames[i], "VIEW", dir));
        if (view) return view;
      } catch (err) {}
    }
    return null;
  }
  function zSign(stel) {
    var ctl = window[CTL];
    if (ctl && ctl.zSign) return ctl.zSign;
    var sign = -1;
    if (ctl) ctl.zSign = sign;
    return sign;
  }
  function projectPoint(stel, raHours, decDeg, box) {
    var ra = ((Number(raHours) % 24) + 24) % 24 * Math.PI / 12;
    var dec = Number(decDeg) * Math.PI / 180;
    if (!isFinite(ra) || !isFinite(dec)) return null;
    var xyz = sphericalToCart(stel, ra, dec);
    var view = convertToView(stel, xyz);
    if (!view) return null;
    var depth = zSign(stel) * view[2];
    if (!(depth > 1e-6)) return null;
    var fov = viewFovRad(stel);
    if (!(fov > 0)) return null;
    var halfV = Math.tan(fov / 2);
    if (!(halfV > 0)) return null;
    var halfH = halfV * (box.width / box.height);
    var x = box.width * (0.5 + 0.5 * (view[0] / depth) / halfH);
    var y = box.height * (0.5 - 0.5 * (view[1] / depth) / halfV);
    if (!isFinite(x) || !isFinite(y)) return null;
    return {x: x, y: y};
  }
  function projectCorners(stel, corners, box) {
    if (!corners || !corners.length) return null;
    var dense = densifyCorners(corners, 8);
    var pts = [];
    for (var i = 0; i < dense.length; i++) {
      var pt = projectPoint(stel, dense[i].ra_hours, dense[i].dec_degrees, box);
      if (!pt) continue;
      pts.push(pt);
    }
    return pts.length >= 3 ? pts : null;
  }
  function sphToRaDec(sph) {
    if (!sph || sph.length < 2) return null;
    var ra = Number(sph[0]), dec = Number(sph[1]);
    if (!isFinite(ra) || !isFinite(dec)) return null;
    return {
      ra_hours: ((ra * 12 / Math.PI) % 24 + 24) % 24,
      dec_degrees: dec * 180 / Math.PI
    };
  }
  function icrfToRaDec(stel, raw) {
    if (!raw) return null;
    if (typeof stel.c2s === "function") {
      try {
        var fromRaw = sphToRaDec(stel.c2s(raw));
        if (fromRaw) return fromRaw;
      } catch (err) {}
    }
    var icrf = asVec(raw);
    if (!icrf) return null;
    if (typeof stel.c2s === "function") {
      try {
        var fromVec = sphToRaDec(stel.c2s(icrf));
        if (fromVec) return fromVec;
      } catch (err) {}
    }
    var pos = xyzToRaDec(icrf);
    return isFinite(pos.ra_hours) && isFinite(pos.dec_degrees) ? pos : null;
  }
  function vecRaDec(raw) {
    if (!raw) return null;
    var x = Number(raw[0]), y = Number(raw[1]), z = Number(raw[2]);
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) {
      if (raw.x === undefined) return null;
      x = Number(raw.x);
      y = Number(raw.y);
      z = Number(raw.z);
    }
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) return null;
    if (Math.abs(x) + Math.abs(y) + Math.abs(z) < 1e-12) return null;
    var pos = xyzToRaDec([x, y, z]);
    return (isFinite(pos.ra_hours) && isFinite(pos.dec_degrees)) ? pos : null;
  }
  function flattenMat(mat) {
    if (!mat) return null;
    if (typeof mat.length === "number" && mat.length >= 9 && typeof mat[0] !== "object") {
      var flat = [];
      for (var i = 0; i < 9; i++) {
        var n = Number(mat[i]);
        if (!isFinite(n)) return null;
        flat.push(n);
      }
      return flat;
    }
    if (mat.length >= 3 && mat[0] && mat[0].length >= 3) {
      var out = [];
      for (var r = 0; r < 3; r++) {
        for (var c = 0; c < 3; c++) {
          var v = Number(mat[r][c]);
          if (!isFinite(v)) return null;
          out.push(v);
        }
      }
      return out;
    }
    return null;
  }
  function coreAngles(stel) {
    var c = stel && stel.core;
    var yaw = Number(c && c.yaw), pitch = Number(c && c.pitch);
    if (isFinite(yaw) && isFinite(pitch))
      return {yaw: yaw, pitch: pitch};
    try {
      var tree = stel.getTree && stel.getTree();
      c = tree && tree.core;
      yaw = Number(c && c.yaw);
      pitch = Number(c && c.pitch);
      if (isFinite(yaw) && isFinite(pitch))
        return {yaw: yaw, pitch: pitch};
    } catch (err) {}
    return null;
  }
  function observedToIcrf(stel, yaw, pitch) {
    if (!stel || !stel.observer || !isFinite(yaw) || !isFinite(pitch))
      return null;
    if (typeof stel.convertFrame !== "function")
      return null;
    var xyz = sphericalToCart(stel, yaw, pitch);
    if (!xyz) return null;
    var frames = ["OBSERVED", "HORIZONTAL"];
    for (var i = 0; i < frames.length; i++) {
      try {
        var pos = icrfToRaDec(stel, stel.convertFrame(stel.observer, frames[i], "ICRF", xyz));
        if (pos) return pos;
      } catch (err) {}
    }
    return null;
  }
  function viewDirToIcrf(stel) {
    if (!stel || !stel.observer || typeof stel.convertFrame !== "function")
      return null;
    var zs = [zSign(stel), -1, 1];
    for (var i = 0; i < zs.length; i++) {
      try {
        var pos = icrfToRaDec(
          stel, stel.convertFrame(stel.observer, "VIEW", "ICRF", [0, 0, -zs[i], 0])
        );
        if (pos) return pos;
      } catch (err) {}
    }
    return null;
  }
  function viewCenter(stel) {
    var a = coreAngles(stel);
    var pos = a ? observedToIcrf(stel, a.yaw, a.pitch) : null;
    return pos || viewDirToIcrf(stel) || selectedPointing(stel);
  }
  function framePointing(stel) {
    return viewCenter(stel);
  }
  function gridPanes(center, p) {
    var cols = Math.max(1, Number(p.columns) || 1);
    var rows = Math.max(1, Number(p.rows) || 1);
    var overlap = Math.max(0, Math.min(0.8, Number(p.overlap) || 0));
    var fovH = Number(p.fov_h), fovV = Number(p.fov_v);
    if (!(fovH > 0) || !(fovV > 0) || !center) return [];
    var pa = Number(p.position_angle);
    if (!isFinite(pa)) pa = 0;
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
        var centerPt = offsetCamera(center.ra_hours, center.dec_degrees, right, up, pa);
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
  function liveEnabled() {
    var ctl = window[CTL];
    return !!(ctl && ctl.liveEnabled);
  }
  function clampLiveOpacity(op) {
    op = Number(op);
    if (!isFinite(op)) return 0.65;
    if (op < 0) return 0;
    if (op > 1) return 1;
    return Math.round(op * 100) / 100;
  }
  function applyLiveImages(el) {
    var ctl = window[CTL];
    var href = ctl && ctl.liveEnabled ? String(ctl.liveUrl || "") : "";
    var op = clampLiveOpacity(ctl && ctl.liveOpacity);
    var imgs = el ? el.querySelectorAll("image.astro-dwarf-live") : [];
    for (var i = 0; i < imgs.length; i++) {
      if (href) {
        imgs[i].setAttribute("href", href);
        try { imgs[i].setAttributeNS("http://www.w3.org/1999/xlink", "href", href); } catch (err) {}
        imgs[i].setAttribute("opacity", String(op));
      } else {
        imgs[i].removeAttribute("href");
      }
    }
  }
  function livePaneIndex() {
    var ctl = window[CTL];
    var n = Number(ctl && ctl.livePane);
    return n >= 1 ? n : 0;
  }
  function paneImageHref(index) {
    var ctl = window[CTL];
    var urls = ctl && ctl.paneUrls;
    if (!urls) return "";
    return String(urls[String(index)] || urls[index] || "");
  }
  function paneUrlKey() {
    var ctl = window[CTL];
    var urls = ctl && ctl.paneUrls;
    if (!urls) return "";
    return Object.keys(urls).filter(function(key) { return !!urls[key]; }).sort().join(",");
  }
  function mosaicUsesPaneImages() {
    return livePaneIndex() > 0 || paneUrlKey() !== "";
  }
  function imageOpacity() {
    return clampLiveOpacity(window[CTL] && window[CTL].liveOpacity);
  }
  function liveImageRect(x, y, w, h) {
    if (!liveEnabled() || !(w > 2) || !(h > 2)) return "";
    return '<image class="astro-dwarf-live" href="" x="' + Number(x).toFixed(1)
      + '" y="' + Number(y).toFixed(1) + '" width="' + Number(w).toFixed(1)
      + '" height="' + Number(h).toFixed(1)
      + '" opacity="' + imageOpacity() + '" preserveAspectRatio="xMidYMid slice"/>';
  }
  function stillImageRect(x, y, w, h, href) {
    if (!href || !(w > 2) || !(h > 2)) return "";
    return '<image class="astro-dwarf-pane" href="' + href + '" x="' + Number(x).toFixed(1)
      + '" y="' + Number(y).toFixed(1) + '" width="' + Number(w).toFixed(1)
      + '" height="' + Number(h).toFixed(1)
      + '" opacity="' + imageOpacity() + '" preserveAspectRatio="xMidYMid slice"/>';
  }
  function imageMatrix(quad, cls, href) {
    if (!quad || quad.length < 3) return "";
    var w = 100, h = 100;
    var p0 = quad[0], p1 = quad[1], p3 = quad[3] || quad[2];
    if (!p0 || !p1 || !p3) return "";
    var a = (p1.x - p0.x) / w, b = (p3.x - p0.x) / h, c = p0.x;
    var d = (p1.y - p0.y) / w, e = (p3.y - p0.y) / h, f = p0.y;
    return '<image class="' + cls + '" href="' + (href || "") + '" x="0" y="0" width="' + w
      + '" height="' + h + '" opacity="' + imageOpacity() + '" preserveAspectRatio="none" transform="matrix('
      + a.toFixed(3) + " " + d.toFixed(3) + " " + b.toFixed(3) + " " + e.toFixed(3) + " "
      + c.toFixed(2) + " " + f.toFixed(2) + ')"/>';
  }
  function liveImageQuad(quad) {
    if (!liveEnabled() || !quad || quad.length < 3) return "";
    return imageMatrix(quad, "astro-dwarf-live", "");
  }
  function stillImageQuad(quad, href) {
    if (!href || !quad || quad.length < 3) return "";
    return imageMatrix(quad, "astro-dwarf-pane", href);
  }
  function paneFillQuad(quad, index) {
    var live = livePaneIndex();
    if (live && index === live)
      return liveImageQuad(quad);
    return stillImageQuad(quad, paneImageHref(index));
  }
  function paneFillRect(x, y, w, h, index) {
    var live = livePaneIndex();
    if (live && index === live)
      return liveImageRect(x, y, w, h);
    return stillImageRect(x, y, w, h, paneImageHref(index));
  }
  function paintSvg(el, box, inner) {
    el.style.display = "block";
    el.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 '
      + box.width + " " + box.height + '" preserveAspectRatio="none">' + inner + "</svg>";
    applyLiveImages(el);
  }
  function wrapDeg(deg) {
    return ((Number(deg) % 360) + 360) % 360;
  }
  function invertedAngle(deg) {
    var a = wrapDeg(deg);
    return a > 90 && a < 270;
  }
  function uprightAngle(deg) {
    var a = wrapDeg(deg);
    if (a > 90 && a < 270)
      a = wrapDeg(a + 180);
    return a > 180 ? a - 360 : a;
  }
  function textAt(x, y, angle, text, color, extra, fontSize, cls) {
    extra = extra || "";
    var size = Number(fontSize);
    if (!(size > 0)) size = 11;
    var klass = cls ? ' class="' + cls + '"' : "";
    return "<text" + klass + ' x="0" y="0" fill="' + color
      + '" font-size="' + size.toFixed(1) + '" font-family="monospace" text-anchor="middle" dominant-baseline="middle"'
      + extra + ' transform="translate(' + Number(x).toFixed(1) + " " + Number(y).toFixed(1)
      + ") rotate(" + Number(angle).toFixed(2) + ')">' + text + "</text>";
  }
  function hudCorners(cx, cy, w, h, paDeg) {
    if (!(w > 2) || !(h > 2) || !isFinite(cx) || !isFinite(cy)) return [];
    var rad = -Number(paDeg) * Math.PI / 180;
    var c = Math.cos(rad), s = Math.sin(rad);
    var pts = [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]];
    var out = [];
    for (var i = 0; i < 4; i++) {
      out.push({
        x: cx + pts[i][0] * c - pts[i][1] * s,
        y: cy + pts[i][0] * s + pts[i][1] * c
      });
    }
    return out;
  }
  function rotatePoint(cx, cy, x, y, paDeg) {
    var rad = -Number(paDeg) * Math.PI / 180;
    var c = Math.cos(rad), s = Math.sin(rad);
    var dx = x - cx, dy = y - cy;
    return {x: cx + dx * c - dy * s, y: cy + dx * s + dy * c};
  }
  function edgeSpec(a, b) {
    return {
      mx: (a.x + b.x) / 2,
      my: (a.y + b.y) / 2,
      ang: Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI
    };
  }
  function outlineText(size) {
    return ' font-weight="700" stroke="#06120f" stroke-width="' + Math.max(1.8, size * 0.16).toFixed(1)
      + '" paint-order="stroke" stroke-linejoin="round"';
  }
  function formatSkyPos(center) {
    if (!center) return "";
    var ra = Number(center.ra_hours), dec = Number(center.dec_degrees);
    if (!isFinite(ra) || !isFinite(dec)) return "";
    return "RA " + ra.toFixed(3) + "h  DEC " + (dec >= 0 ? "+" : "") + dec.toFixed(3) + "\u00b0";
  }
  function payloadView(p) {
    var ra = Number(p && p.view_ra_hours), dec = Number(p && p.view_dec_degrees);
    return (isFinite(ra) && isFinite(dec)) ? {ra_hours: ra, dec_degrees: dec} : null;
  }
  function payloadPointing(p) {
    var ra = Number(p && p.target_ra_hours), dec = Number(p && p.target_dec_degrees);
    if (isFinite(ra) && isFinite(dec))
      return {ra_hours: ra, dec_degrees: dec};
    var pane = p && p.panes && p.panes[0];
    if (!pane) return null;
    ra = Number(pane.ra_hours);
    dec = Number(pane.dec_degrees);
    return (isFinite(ra) && isFinite(dec)) ? {ra_hours: ra, dec_degrees: dec} : null;
  }
  function selectedPointing(stel) {
    var obj = selectedSwe(stel);
    if (!obj || !stel || !stel.observer) return null;
    try {
      var swe = obj;
      if (typeof swe.getPosIcrf !== "function" && typeof obj.v === "number" && stel.SweObj) {
        swe = new stel.SweObj(obj.v);
        if (swe && swe.retain) swe.retain();
      }
      if (!swe || typeof swe.getPosIcrf !== "function")
        return null;
      return icrfToRaDec(stel, swe.getPosIcrf(stel.observer));
    } catch (err) {
      return null;
    }
  }
  function liveViewPos() {
    var pos = window[CTL] && window[CTL].viewPos;
    var ra = Number(pos && pos.ra_hours), dec = Number(pos && pos.dec_degrees);
    return (isFinite(ra) && isFinite(dec)) ? {ra_hours: ra, dec_degrees: dec} : null;
  }
  function currentPointing(p, stel) {
    var view = framePointing(stel) || liveViewPos() || payloadView(p);
    if (p && String(p.mode || "") === "panes" && p.panes && p.panes.length)
      return payloadPointing(p) || selectedPointing(stel) || view;
    var locked = null;
    try {
      if (stel && stel.core && stel.core.lock)
        locked = selectedPointing(stel);
    } catch (err) {}
    return locked || view || payloadPointing(p) || selectedPointing(stel);
  }
  function pointingKey(p, stel) {
    var pos = currentPointing(p, stel);
    if (!pos) return "";
    return Number(pos.ra_hours).toFixed(4) + "," + Number(pos.dec_degrees).toFixed(3);
  }
  function frameCaption(p, stel) {
    var head = String(p.label || "").replace(/\s*PA\s+[-+]?\d+(?:\.\d+)?°/i, "").replace(/\s+/g, " ").trim();
    var pa = Number(p && p.position_angle);
    if (!isFinite(pa)) pa = 0;
    var spec = [];
    if (head) spec.push(head);
    spec.push("PA " + (((pa % 360) + 360) % 360).toFixed(0) + "°");
    return {spec: spec.join("  "), pos: formatSkyPos(currentPointing(p, stel))};
  }
  function labelFontSize(span) {
    if (!(span > 0)) return 11;
    return Math.max(10, Math.min(12, span * 0.035));
  }
  function labelOnFrame(p, pts, stel, box) {
    var cap = frameCaption(p, stel);
    var color = String(p.color || "#7ee0d0");
    if ((!cap.spec && !cap.pos) || !pts || !pts.length) return "";
    var size = labelFontSize(paneSpan(pts));
    var extra = outlineText(size);
    function stacked(x, y, ang, ox, oy) {
      var svg = "";
      if (cap.pos)
        svg += textAt(x + ox * 13, y + oy * 13, ang, cap.pos, color, extra, size, "astro-dwarf-pos");
      if (cap.spec)
        svg += textAt(x, y, ang, cap.spec, color, extra, size);
      return svg;
    }
    if (pts.length === 4 && pts[0] && pts[1] && pts[2] && pts[3]) {
      var top = edgeSpec(pts[0], pts[1]);
      var edge = invertedAngle(top.ang) ? edgeSpec(pts[2], pts[3]) : top;
      var cx = (pts[0].x + pts[1].x + pts[2].x + pts[3].x) / 4;
      var cy = (pts[0].y + pts[1].y + pts[2].y + pts[3].y) / 4;
      var dx = edge.mx - cx, dy = edge.my - cy;
      var len = Math.hypot(dx, dy) || 1;
      var ox = dx / len, oy = dy / len;
      return stacked(edge.mx + ox * 12, edge.my + oy * 12, uprightAngle(edge.ang), ox, oy);
    }
    var minX = Infinity, minY = Infinity;
    for (var i = 0; i < pts.length; i++) {
      if (!pts[i] || !isFinite(pts[i].x) || !isFinite(pts[i].y)) continue;
      if (pts[i].x < minX) minX = pts[i].x;
      if (pts[i].y < minY) minY = pts[i].y;
    }
    if (!isFinite(minX) || !isFinite(minY)) return "";
    return stacked(minX, minY - 4, 0, 0, -1);
  }
  function mosaicOuterQuad(drawn) {
    var quads = [];
    (drawn || []).forEach(function(item) {
      if (item && item.quad && item.quad.length === 4)
        quads.push(item.quad);
    });
    if (!quads.length) return [];
    if (quads.length === 1) return quads[0];
    var q0 = quads[0];
    var ux = q0[1].x - q0[0].x, uy = q0[1].y - q0[0].y;
    var vx = q0[3].x - q0[0].x, vy = q0[3].y - q0[0].y;
    var ulen = Math.hypot(ux, uy) || 1, vlen = Math.hypot(vx, vy) || 1;
    ux /= ulen; uy /= ulen; vx /= vlen; vy /= vlen;
    var minU = Infinity, maxU = -Infinity, minV = Infinity, maxV = -Infinity;
    quads.forEach(function(quad) {
      quad.forEach(function(pt) {
        var u = (pt.x - q0[0].x) * ux + (pt.y - q0[0].y) * uy;
        var v = (pt.x - q0[0].x) * vx + (pt.y - q0[0].y) * vy;
        if (u < minU) minU = u; if (u > maxU) maxU = u;
        if (v < minV) minV = v; if (v > maxV) maxV = v;
      });
    });
    function at(u, v) {
      return {x: q0[0].x + ux * u + vx * v, y: q0[0].y + uy * u + vy * v};
    }
    return [at(minU, minV), at(maxU, minV), at(maxU, maxV), at(minU, maxV)];
  }
  function mosaicCenterFovQuad(drawn) {
    var quads = [];
    (drawn || []).forEach(function(item) {
      if (item && item.quad && item.quad.length === 4)
        quads.push(item.quad);
    });
    if (!quads.length) return [];
    if (quads.length === 1) return quads[0];
    var q0 = quads[0];
    var ux = (q0[1].x - q0[0].x) / 2, uy = (q0[1].y - q0[0].y) / 2;
    var vx = (q0[3].x - q0[0].x) / 2, vy = (q0[3].y - q0[0].y) / 2;
    var outer = mosaicOuterQuad(drawn);
    if (outer.length !== 4) return q0;
    var cx = (outer[0].x + outer[1].x + outer[2].x + outer[3].x) / 4;
    var cy = (outer[0].y + outer[1].y + outer[2].y + outer[3].y) / 4;
    return [
      {x: cx - ux - vx, y: cy - uy - vy},
      {x: cx + ux - vx, y: cy + uy - vy},
      {x: cx + ux + vx, y: cy + uy + vy},
      {x: cx - ux + vx, y: cy - uy + vy}
    ];
  }
  function paneSpan(quad) {
    if (!quad || quad.length < 4) return 0;
    var w = Math.hypot(quad[1].x - quad[0].x, quad[1].y - quad[0].y);
    var h = Math.hypot(quad[3].x - quad[0].x, quad[3].y - quad[0].y);
    return Math.min(w, h);
  }
  function indexFontSize(span) {
    if (!(span > 0)) return 12;
    return Math.max(12, Math.min(18, span * 0.08));
  }
  function indexText(x, y, index, color, angle, span) {
    var size = indexFontSize(span);
    return textAt(x, y, uprightAngle(angle || 0), String(index), color, outlineText(size), size);
  }
  function paneSize(box, p, stel) {
    var fov = viewFovRad(stel);
    if (!(fov > 0)) return null;
    var fovV = fov * 180 / Math.PI;
    var fovH = fovV * (box.width / box.height);
    var w = (Number(p.fov_h) / fovH) * box.width;
    var h = (Number(p.fov_v) / fovV) * box.height;
    if (!(w > 2) || !(h > 2)) return null;
    return {w: w, h: h};
  }
  function framePa(p) {
    var pa = Number(p && p.position_angle);
    if (isFinite(pa)) return ((pa % 360) + 360) % 360;
    return 0;
  }
  function rotateGroup(box, p, inner) {
    var pa = framePa(p);
    var cx = (box.width / 2).toFixed(1);
    var cy = (box.height / 2).toFixed(1);
    return '<g transform="rotate(' + (-pa).toFixed(2) + " " + cx + " " + cy + ')">' + inner + "</g>";
  }
  function upTick(cx, top, color) {
    return '<line x1="' + cx.toFixed(1) + '" y1="' + top.toFixed(1) + '" x2="' + cx.toFixed(1)
      + '" y2="' + (top - 10).toFixed(1) + '" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round"/>';
  }
  function edgeTick(a, b, color) {
    if (!a || !b) return "";
    var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    var dx = b.x - a.x, dy = b.y - a.y;
    var len = Math.hypot(dx, dy) || 1;
    var nx = -dy / len, ny = dx / len;
    return '<line x1="' + mx.toFixed(1) + '" y1="' + my.toFixed(1) + '" x2="' + (mx + nx * 10).toFixed(1)
      + '" y2="' + (my + ny * 10).toFixed(1) + '" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round"/>';
  }
  function drawCenterBox(el, box, p, stel) {
    var size = paneSize(box, p, stel);
    if (!size) return "error";
    var color = String(p.color || "#7ee0d0");
    var left = (box.width - size.w) / 2;
    var top = (box.height - size.h) / 2;
    paintSvg(el, box, rotateGroup(box, p,
      liveImageRect(left, top, size.w, size.h)
      + '<rect x="' + left.toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + size.w.toFixed(1)
      + '" height="' + size.h.toFixed(1) + '" fill="none" stroke="' + color
      + '" stroke-width="1.25" stroke-opacity="0.9"/>'
      + upTick(box.width / 2, top, color))
      + labelOnFrame(p, hudCorners(box.width / 2, box.height / 2, size.w, size.h, framePa(p)), stel, box));
    return "center";
  }
  function drawScreenGrid(el, box, p, stel) {
    var size = paneSize(box, p, stel);
    var cols = Math.max(1, Number(p.columns) || 1);
    var rows = Math.max(1, Number(p.rows) || 1);
    if (!size) return drawCenterBox(el, box, p, stel);
    if (cols <= 1 && rows <= 1)
      return drawCenterBox(el, box, p, stel);
    var overlap = Math.max(0, Math.min(0.8, Number(p.overlap) || 0));
    var stepX = size.w * (1 - overlap);
    var stepY = size.h * (1 - overlap);
    var totalW = stepX * (cols - 1) + size.w;
    var totalH = stepY * (rows - 1) + size.h;
    var originX = (box.width - totalW) / 2;
    var originY = (box.height - totalH) / 2;
    var color = String(p.color || "#7ee0d0");
    var pa = framePa(p);
    // Pane 1 is camera-right. Stellarium and stacked JPEGs are N-up, so that
    // is the right edge at PA 0°. Near PA 180° camera-right is east / left.
    var col1OnRight = !(pa > 90 && pa < 270);
    var svg = "";
    var labels = "";
    var index = 0;
    for (var row = 1; row <= rows; row++) {
      for (var col = 1; col <= cols; col++) {
        index += 1;
        var x = originX + (col1OnRight ? (cols - col) : (col - 1)) * stepX;
        var y = originY + (row - 1) * stepY;
        svg += paneFillRect(x, y, size.w, size.h, index);
        svg += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + size.w.toFixed(1)
          + '" height="' + size.h.toFixed(1) + '" fill="' + color + '" fill-opacity="0.05" '
          + paneStroke(color, cols * rows > 1) + '/>';
        if (cols * rows > 1) {
          var pc = rotatePoint(box.width / 2, box.height / 2, x + size.w / 2, y + size.h / 2, pa);
          labels += indexText(pc.x, pc.y, index, color, -pa, Math.min(size.w, size.h));
        }
      }
    }
    if (cols * rows > 1) {
      svg += '<rect x="' + originX.toFixed(1) + '" y="' + originY.toFixed(1) + '" width="' + totalW.toFixed(1)
        + '" height="' + totalH.toFixed(1) + '" ' + outerStroke(color) + '/>';
    }
    if (!mosaicUsesPaneImages())
      svg += liveImageRect((box.width - size.w) / 2, (box.height - size.h) / 2, size.w, size.h);
    svg += upTick(box.width / 2, originY, color);
    paintSvg(el, box, rotateGroup(box, p, svg)
      + labels
      + labelOnFrame(p, hudCorners(box.width / 2, box.height / 2, totalW, totalH, pa), stel, box));
    return "grid";
  }
  function drawPanes(el, box, p, stel, panes) {
    var color = String(p.color || "#7ee0d0");
    var drawn = [];
    for (var i = 0; i < panes.length; i++) {
      var pts = projectCorners(stel, panes[i].corners, box);
      if (!pts) continue;
      var points = pts.map(function(pt) { return pt.x.toFixed(1) + "," + pt.y.toFixed(1); }).join(" ");
      var cx = 0, cy = 0;
      pts.forEach(function(pt) { cx += pt.x; cy += pt.y; });
      cx /= pts.length;
      cy /= pts.length;
      var tick = "";
      var quad = [];
      var corners = panes[i].corners || [];
      if (corners.length >= 4) {
        var upA = projectPoint(stel, corners[3].ra_hours, corners[3].dec_degrees, box);
        var upB = projectPoint(stel, corners[0].ra_hours, corners[0].dec_degrees, box);
        tick = edgeTick(upA, upB, color);
        var order = [3, 0, 1, 2];
        for (var q = 0; q < 4; q++) {
          var cpt = projectPoint(stel, corners[order[q]].ra_hours, corners[order[q]].dec_degrees, box);
          if (cpt) quad.push(cpt);
        }
      }
      drawn.push({
        points: points, cx: cx, cy: cy, tick: tick,
        quad: quad.length === 4 ? quad : null,
        index: panes[i].index || (i + 1)
      });
    }
    if (!drawn.length)
      return "";
    var svg = "";
    var mosaic = drawn.length > 1;
    if (mosaic && mosaicUsesPaneImages()) {
      drawn.forEach(function(item) {
        svg += paneFillQuad(item.quad, item.index);
      });
    } else if (mosaic) {
      svg += liveImageQuad(mosaicCenterFovQuad(drawn));
    } else if (drawn[0] && drawn[0].quad) {
      svg += liveImageQuad(drawn[0].quad);
    }
    drawn.forEach(function(item) {
      svg += '<polygon points="' + item.points + '" fill="' + color
        + '" fill-opacity="0.05" ' + paneStroke(color, mosaic) + '/>';
      if (!mosaic)
        svg += item.tick || "";
    });
    if (mosaic) {
      var outer = mosaicOuterQuad(drawn);
      if (outer.length === 4) {
        svg += '<polygon points="' + outer.map(function(pt) {
          return pt.x.toFixed(1) + "," + pt.y.toFixed(1);
        }).join(" ") + '" ' + outerStroke(color) + '/>';
        svg += edgeTick(outer[0], outer[1], color);
      }
      drawn.forEach(function(item) {
        var ang = 0;
        if (item.quad)
          ang = edgeSpec(item.quad[0], item.quad[1]).ang;
        svg += indexText(item.cx, item.cy, item.index, color, ang, paneSpan(item.quad));
      });
    }
    svg += labelOnFrame(p, mosaicOuterQuad(drawn), stel, box);
    paintSvg(el, box, svg);
    return "panes";
  }
  function resolvePanes(stel, p) {
    var panes = (p && p.panes) || [];
    if (panes.length)
      return panes;
    if (String(p.mode || "") === "center")
      return [];
    var center = viewCenter(stel);
    if (!center) return [];
    return gridPanes(center, p);
  }
  function viewKey(stel, box) {
    var a = coreAngles(stel) || {};
    var o = stel.observer || {};
    return [
      a.yaw, a.pitch, o.roll, stel.core && stel.core.fov,
      box && box.width, box && box.height,
      nightModeOn() ? "N" : "D"
    ].join("|");
  }
  function writePosLabels(text) {
    if (!text) return 0;
    var el = document.getElementById(ID);
    var nodes = el ? el.querySelectorAll("text.astro-dwarf-pos") : [];
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].textContent !== text)
        nodes[i].textContent = text;
    }
    return nodes.length;
  }
  function draw(force) {
    var stel = window._stel;
    var box = canvasRect();
    var ctl = window[CTL];
    if (!ctl) return "loading";
    var p = Object.assign({}, ctl.payload || {});
    p.color = resolvedColor(p);
    if (!stel || !stel.core || !box)
      return "loading";
    if (String(p.mode || "") === "hidden")
      return hideOverlay();
    var posText = "";
    try { posText = formatSkyPos(currentPointing(p, stel)); } catch (err) {}
    var base = viewKey(stel, box) + "|" + ctl.payloadKey + "|" + (ctl.liveEnabled ? "L" : "n")
      + "|" + livePaneIndex() + "|" + paneUrlKey();
    if (!force && base === ctl.lastBase && writePosLabels(posText))
      return ctl.lastStatus || "center";
    var key = base + "|" + posText;
    if (!force && key === ctl.lastKey && writePosLabels(posText))
      return ctl.lastStatus || "center";
    ctl.lastBase = base;
    ctl.lastPosKey = posText;
    ctl.lastKey = key;
    var el = overlayFor(box);
    var panes = [];
    try { panes = resolvePanes(stel, p); } catch (err) { panes = []; }
    if (panes.length) {
      try {
        var projected = drawPanes(el, box, p, stel, panes);
        if (projected) {
          ctl.lastStatus = projected;
          return projected;
        }
      } catch (err) {}
    }
    ctl.lastStatus = drawScreenGrid(el, box, p, stel);
    return ctl.lastStatus;
  }
  function tick() {
    var ctl = window[CTL];
    if (!ctl) return;
    ctl.raf = requestAnimationFrame(function() {
      var next = window[CTL];
      if (next && typeof next.tick === "function") next.tick();
    });
    try { (ctl.draw || draw)(false); } catch (err) {}
  }
  function asSweObj(obj) {
    return obj && typeof obj.v === "number" ? obj : null;
  }
  function selectedSwe(stel) {
    if (!stel) return null;
    var obj = asSweObj(stel.core && stel.core.selection);
    if (obj) return obj;
    try {
      var app = document.getElementById("app");
      var vue = app && app.__vue_app__;
      var gp = vue && vue.config && vue.config.globalProperties;
      var store = gp && gp.$store;
      obj = asSweObj(store && store.state && store.state.selectedObject);
      if (obj) return obj;
      obj = asSweObj(gp && gp.$stel && gp.$stel.core && gp.$stel.core.selection);
    } catch (err) {}
    return obj || null;
  }
  function onSky(el) {
    if (!el) return false;
    if (el.tagName === "CANVAS") return true;
    if (el.closest && el.closest("canvas")) return true;
    if (el.closest && el.closest("button, a, input, textarea, select, [role=button], .v-card, .v-navigation-drawer, .v-menu, .v-dialog"))
      return false;
    return true;
  }
  function centerOn(stel, obj) {
    if (!stel || !obj) return;
    try {
      if (typeof stel.pointAndLock === "function" && typeof obj.v === "number")
        stel.pointAndLock(obj, 1.0);
      else if (stel.core)
        stel.core.lock = obj;
    } catch (err) {}
  }
  function bindDoubleClick(ctl) {
    if (!ctl || ctl.dblBound) return;
    ctl.dblBound = true;
    ctl.lastPick = null;
    ctl.lastPickAt = 0;
    document.addEventListener("click", function(e) {
      if (!onSky(e.target)) return;
      setTimeout(function() {
        var obj = selectedSwe(window._stel);
        if (!obj) return;
        ctl.lastPick = obj;
        ctl.lastPickAt = Date.now();
      }, 0);
    }, true);
    document.addEventListener("dblclick", function(e) {
      if (!onSky(e.target)) return;
      var stel = window._stel;
      if (!stel || !stel.core) return;
      var obj = selectedSwe(stel);
      if (!obj && ctl.lastPick && (Date.now() - ctl.lastPickAt) < 500)
        obj = ctl.lastPick;
      if (!obj) return;
      centerOn(stel, obj);
      ctl.trackAt = Date.now();
    }, true);
  }
  function bindContextMenu(ctl) {
    if (!ctl || ctl.ctxBound) return;
    ctl.ctxBound = true;
    document.addEventListener("contextmenu", function(e) {
      if (!onSky(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      ctl.menuAt = Date.now();
      ctl.menuX = e.clientX;
      ctl.menuY = e.clientY;
    }, true);
  }
  function bindLiveOpacityWheel(ctl) {
    if (!ctl || ctl.wheelBound) return;
    ctl.wheelBound = true;
    document.addEventListener("wheel", function(e) {
      if (!e.ctrlKey || !onSky(e.target) || !ctl.liveEnabled) return;
      e.preventDefault();
      e.stopPropagation();
      if (typeof e.stopImmediatePropagation === "function")
        e.stopImmediatePropagation();
      var delta = -Number(e.deltaY);
      if (!isFinite(delta) || delta === 0) return;
      if (e.deltaMode === 1) delta *= 16;
      else if (e.deltaMode === 2) delta *= 120;
      var next = clampLiveOpacity(ctl.liveOpacity + delta / 120 * 0.05);
      if (next === clampLiveOpacity(ctl.liveOpacity)) return;
      ctl.liveOpacity = next;
      ctl.wheelOpacity = true;
      ctl.opacityAt = Date.now();
      try { applyLiveImages(document.getElementById("astro-dwarf-sky-overlay")); } catch (err) {}
    }, {capture: true, passive: false});
  }
  try {
    var stel = window._stel;
    if (!stel || !stel.core)
      return "loading";
    var ctl = window[CTL];
    if (ctl && ctl.raf)
      cancelAnimationFrame(ctl.raf);
    if (!ctl) {
      ctl = window[CTL] = {
        payload: p, payloadKey: "", lastKey: "", lastBase: "", lastPosKey: "", lastStatus: "", zSign: 0, raf: 0,
        liveEnabled: false, liveUrl: "", liveOpacity: 0.65, livePane: 0, paneUrls: {},
        menuAt: 0, menuX: 0, menuY: 0,
        trackAt: 0
      };
    }
    ctl.draw = draw;
    ctl.tick = tick;
    if (typeof stel.change === "function") {
      try {
        stel.change(function() {
          var live = window[CTL];
          if (live && typeof live.draw === "function") live.draw(true);
        });
      } catch (err) {}
    }
    bindDoubleClick(ctl);
    bindContextMenu(ctl);
    bindLiveOpacityWheel(ctl);
    ctl.payload = p;
    ctl.payloadKey = [
      p.mode, p.label, p.color, p.fov_h, p.fov_v, p.columns, p.rows, p.overlap, p.south_up, p.position_angle,
      (p.panes || []).length,
      p.panes && p.panes[0] && p.panes[0].ra_hours,
      p.panes && p.panes[0] && p.panes[0].dec_degrees,
      p.target_ra_hours, p.target_dec_degrees,
      p.view_ra_hours, p.view_dec_degrees
    ].join("|");
    tick();
    return draw(true);
  } catch (err) {
    return "error";
  }
})
"""


def sky_web_fov_script(payload: dict[str, Any]) -> str:
    return f"{SKY_WEB_FOV_JS}({json.dumps(payload)})"


SKY_WEB_LIVE_JS = r"""
(function(url, enabled, opacity, livePane) {
  var CTL = "__astroDwarfFovCtl";
  var ctl = window[CTL];
  if (!ctl) return "loading";
  var on = !!enabled;
  var op = Number(opacity);
  if (!isFinite(op) || op < 0 || op > 1) op = 0.65;
  var href = on ? String(url || "") : "";
  var pane = Math.max(0, Number(livePane) || 0);
  var was = !!ctl.liveEnabled;
  var paneChanged = pane !== (Number(ctl.livePane) || 0);
  ctl.liveEnabled = on;
  ctl.liveUrl = href;
  if (ctl.wheelOpacity) {
    if (Math.abs(Number(ctl.liveOpacity) - op) < 0.005)
      ctl.wheelOpacity = false;
  } else {
    ctl.liveOpacity = op;
  }
  ctl.livePane = pane;
  var el = document.getElementById("astro-dwarf-sky-overlay");
  var imgs = el ? el.querySelectorAll("image.astro-dwarf-live") : [];
  op = Number(ctl.liveOpacity);
  if (!isFinite(op) || op < 0 || op > 1) op = 0.65;
  if (on !== was || paneChanged || (on && !imgs.length)) {
    ctl.lastKey = "";
    try { if (typeof ctl.draw === "function") ctl.draw(true); } catch (err) {}
    return on ? "shown" : "hidden";
  }
  for (var i = 0; i < imgs.length; i++) {
    if (href) {
      imgs[i].setAttribute("href", href);
      try { imgs[i].setAttributeNS("http://www.w3.org/1999/xlink", "href", href); } catch (err) {}
      imgs[i].setAttribute("opacity", String(op));
    } else {
      imgs[i].removeAttribute("href");
    }
  }
  return href ? "updated" : "empty";
})
"""


def sky_web_live_script(
    data_url: str,
    enabled: bool,
    opacity: float = 0.65,
    live_pane: int = 0,
) -> str:
    return (
        f"{SKY_WEB_LIVE_JS}({json.dumps(str(data_url or ''))}, {json.dumps(bool(enabled))}, "
        f"{float(opacity)}, {int(live_pane or 0)})"
    )


SKY_WEB_PANE_JS = r"""
(function(paneUrls) {
  var CTL = "__astroDwarfFovCtl";
  var ctl = window[CTL];
  if (!ctl) return "loading";
  ctl.paneUrls = paneUrls || {};
  ctl.lastKey = "";
  try { if (typeof ctl.draw === "function") ctl.draw(true); } catch (err) {}
  return "panes";
})
"""


def sky_web_pane_script(pane_urls: dict[str, str] | None) -> str:
    payload = {
        str(key): str(value)
        for key, value in dict(pane_urls or {}).items()
        if str(value or "").startswith("data:image/")
    }
    return f"{SKY_WEB_PANE_JS}({json.dumps(payload)})"


SKY_WEB_CONTEXT_POLL_JS = r"""
(function(){
  var ctl = window.__astroDwarfFovCtl;
  if (!ctl || !ctl.menuAt) return "";
  var payload = JSON.stringify({x: ctl.menuX || 0, y: ctl.menuY || 0, at: ctl.menuAt});
  ctl.menuAt = 0;
  return payload;
})()
"""


SKY_WEB_DBLCLICK_POLL_JS = r"""
(function(){
  var ctl = window.__astroDwarfFovCtl;
  if (!ctl || !ctl.trackAt) return "";
  var payload = JSON.stringify({at: ctl.trackAt});
  ctl.trackAt = 0;
  return payload;
})()
"""


SKY_WEB_OPACITY_POLL_JS = r"""
(function(){
  var ctl = window.__astroDwarfFovCtl;
  if (!ctl || !ctl.opacityAt) return "";
  var payload = JSON.stringify({opacity: Number(ctl.liveOpacity), at: ctl.opacityAt});
  ctl.opacityAt = 0;
  return payload;
})()
"""


SKY_WEB_VIEW_POS_JS = r"""
(function(ra, dec) {
  var ctl = window.__astroDwarfFovCtl;
  ra = Number(ra);
  dec = Number(dec);
  if (!ctl || !isFinite(ra) || !isFinite(dec)) return "skip";
  ctl.viewPos = {ra_hours: ra, dec_degrees: dec};
  var text = "RA " + ra.toFixed(3) + "h  DEC " + (dec >= 0 ? "+" : "") + dec.toFixed(3) + "\u00b0";
  var el = document.getElementById("astro-dwarf-sky-overlay");
  var nodes = el ? el.querySelectorAll("text.astro-dwarf-pos") : [];
  for (var i = 0; i < nodes.length; i++) nodes[i].textContent = text;
  return "ok";
})
"""


def sky_web_view_pos_script(ra_hours: float, dec_degrees: float) -> str:
    return f"{SKY_WEB_VIEW_POS_JS}({float(ra_hours)}, {float(dec_degrees)})"


SKY_WEB_VIEW_POLL_JS = r"""
(function(){
  function asVec(value) {
    if (!value) return null;
    if (value.length >= 3) {
      var x = Number(value[0]), y = Number(value[1]), z = Number(value[2]);
      if (!isFinite(x) || !isFinite(y) || !isFinite(z)) return null;
      return [x, y, z, value.length > 3 ? Number(value[3]) || 0 : 0];
    }
    if (value.x === undefined) return null;
    var vx = Number(value.x), vy = Number(value.y), vz = Number(value.z);
    if (!isFinite(vx) || !isFinite(vy) || !isFinite(vz)) return null;
    return [vx, vy, vz, 0];
  }
  function icrfToRaDec(stel, raw) {
    if (!raw) return null;
    if (typeof stel.c2s === "function") {
      try {
        var sph = stel.c2s(raw);
        var ra = Number(sph && sph[0]), dec = Number(sph && sph[1]);
        if (isFinite(ra) && isFinite(dec))
          return {
            ra_hours: ((ra * 12 / Math.PI) % 24 + 24) % 24,
            dec_degrees: dec * 180 / Math.PI
          };
      } catch (err) {}
    }
    var icrf = asVec(raw);
    if (!icrf) return null;
    var n = Math.hypot(icrf[0], icrf[1], icrf[2]) || 1;
    var x = icrf[0] / n, y = icrf[1] / n, z = icrf[2] / n;
    return {
      ra_hours: ((Math.atan2(y, x) * 12 / Math.PI) % 24 + 24) % 24,
      dec_degrees: Math.asin(Math.max(-1, Math.min(1, z))) * 180 / Math.PI
    };
  }
  function observedToIcrf(stel, yaw, pitch) {
    if (!stel || !stel.observer || typeof stel.convertFrame !== "function")
      return null;
    if (!isFinite(yaw) || !isFinite(pitch)) return null;
    var xyz = null;
    if (typeof stel.s2c === "function") {
      try { xyz = asVec(stel.s2c(yaw, pitch)); } catch (err) {}
    }
    if (!xyz) {
      var c = Math.cos(pitch);
      xyz = [c * Math.cos(yaw), c * Math.sin(yaw), Math.sin(pitch), 0];
    }
    var frames = ["OBSERVED", "HORIZONTAL"];
    for (var i = 0; i < frames.length; i++) {
      try {
        var pos = icrfToRaDec(stel, stel.convertFrame(stel.observer, frames[i], "ICRF", xyz));
        if (pos) return pos;
      } catch (err) {}
    }
    return null;
  }
  function viewCenter(stel) {
    var c = stel && stel.core;
    var yaw = Number(c && c.yaw), pitch = Number(c && c.pitch);
    if (!isFinite(yaw) || !isFinite(pitch)) {
      try {
        var tree = stel.getTree && stel.getTree();
        c = tree && tree.core;
        yaw = Number(c && c.yaw);
        pitch = Number(c && c.pitch);
      } catch (err) {}
    }
    if (!isFinite(yaw) || !isFinite(pitch)) return null;
    var pos = observedToIcrf(stel, yaw, pitch);
    if (!pos) return null;
    pos.yaw = yaw;
    pos.pitch = pitch;
    return pos;
  }
  try {
    var stel = window._stel;
    if (!stel || !stel.core || !stel.observer) return "";
    var pos = viewCenter(stel);
    if (!pos) return "";
    return JSON.stringify({
      ra_hours: pos.ra_hours,
      dec_degrees: pos.dec_degrees,
      fov: Number(stel.core.fov),
      yaw: pos.yaw,
      pitch: pos.pitch,
      roll: Number(stel.core.roll)
    });
  } catch (err) {
    return "";
  }
})()
"""


SKY_WEB_VIEW_APPLY_JS = r"""
(function(p) {
  function setAngle(obj, key, value) {
    if (!obj || !isFinite(value)) return;
    try { obj[key] = value; } catch (err) {}
  }
  try {
    var stel = window._stel;
    if (!stel || !stel.core || !stel.observer) return "loading";
    var fov = Number(p && p.fov);
    if (fov > 0 && isFinite(fov))
      stel.core.fov = fov;
    try { stel.core.lock = null; } catch (err) {}
    var raHours = Number(p && p.ra_hours);
    var decDeg = Number(p && p.dec_degrees);
    var yaw = Number(p && p.yaw);
    var pitch = Number(p && p.pitch);
    var roll = Number(p && p.roll);
    if (isFinite(raHours) && isFinite(decDeg) && (!isFinite(yaw) || !isFinite(pitch))) {
      var ra = (((raHours % 24) + 24) % 24) * Math.PI / 12;
      var dec = decDeg * Math.PI / 180;
      var xyz = [Math.cos(dec) * Math.cos(ra), Math.cos(dec) * Math.sin(ra), Math.sin(dec), 0];
      var frames = ["OBSERVED", "HORIZONTAL"];
      if (typeof stel.convertFrame === "function" && typeof stel.c2s === "function") {
        for (var i = 0; i < frames.length; i++) {
          try {
            var sph = stel.c2s(stel.convertFrame(stel.observer, "ICRF", frames[i], xyz));
            var nextYaw = Number(sph && sph[0]), nextPitch = Number(sph && sph[1]);
            if (isFinite(nextYaw) && isFinite(nextPitch)) {
              yaw = nextYaw;
              pitch = nextPitch;
              break;
            }
          } catch (err) {}
        }
      }
    }
    if (!isFinite(yaw) || !isFinite(pitch))
      return "pending";
    setAngle(stel.core, "yaw", yaw);
    setAngle(stel.core, "pitch", pitch);
    setAngle(stel.observer, "yaw", yaw);
    setAngle(stel.observer, "pitch", pitch);
    if (isFinite(roll)) {
      setAngle(stel.core, "roll", roll);
      setAngle(stel.observer, "roll", roll);
    }
    return "ok";
  } catch (err) {
    return "error";
  }
})
"""


def sky_web_view_script(payload: dict[str, Any]) -> str:
    return f"{SKY_WEB_VIEW_APPLY_JS}({json.dumps(payload)})"


SKY_WEB_LOCK_TARGET_JS = r"""
(function(p) {
  function asSwe(stel, obj) {
    if (!obj) return null;
    if (typeof obj.getPosIcrf === "function") return obj;
    if (typeof obj.v === "number" && stel && stel.SweObj) {
      try {
        var wrapped = new stel.SweObj(obj.v);
        if (wrapped.retain) wrapped.retain();
        return wrapped;
      } catch (err) {
        return null;
      }
    }
    return null;
  }
  function vueBits() {
    try {
      var app = document.getElementById("app");
      var vue = app && app.__vue_app__;
      var gp = vue && vue.config && vue.config.globalProperties;
      return {gp: gp, store: gp && gp.$store, stel: gp && gp.$stel};
    } catch (err) {
      return {gp: null, store: null, stel: null};
    }
  }
    function nameCandidates(raw, aliases) {
    var name = String(raw || "").replace(/\s+/g, " ").trim();
    var out = [];
    function add(value) {
      value = String(value || "").replace(/\s+/g, " ").trim();
      if (value && out.indexOf(value) < 0) out.push(value);
    }
    (aliases || []).forEach(add);
    if (!name) return out;
    add(name);
    add(name.replace(/[_-]+/g, " "));
    var gaia = name.match(/gaia\s*(e?dr[123])?\s*(\d{15,19})/i);
    if (gaia) {
      var rel = (gaia[1] || "DR3").toUpperCase();
      add("Gaia " + rel + " " + gaia[2]);
      add("GaiaDR3 " + gaia[2]);
      add("Gaia DR3 " + gaia[2]);
    }
    var match = name.match(/^(M|NGC|IC|PGC|UGC|HD|HIP|SAO|HR|SH2|LBN|LDN)\s*[-_]?(\d+[a-zA-Z]?)$/i);
    if (match) {
      var cat = match[1].toUpperCase();
      var num = match[2];
      add(cat + " " + num);
      add(cat + num);
      if (cat === "M") add("Messier " + num);
    }
    add("NAME " + name);
    return out;
  }
  function tryGet(stel, id) {
    if (!stel || !id) return null;
    var names = ["getObj", "lookupObj", "getObject"];
    for (var i = 0; i < names.length; i++) {
      if (typeof stel[names[i]] !== "function") continue;
      try {
        var obj = asSwe(stel, stel[names[i]](id));
        if (obj) return obj;
      } catch (err) {}
    }
    return null;
  }
  function findObject(stel, extra, name, aliases) {
    var ids = nameCandidates(name, aliases);
    var sources = [stel, extra].filter(Boolean);
    for (var s = 0; s < sources.length; s++) {
      for (var i = 0; i < ids.length; i++) {
        var obj = tryGet(sources[s], ids[i]);
        if (obj) return obj;
      }
    }
    return null;
  }
  function selectObject(stel, store, obj) {
    if (!obj) return;
    try { if (stel && stel.core) stel.core.selection = obj; } catch (err) {}
    if (!store) return;
    try { store.commit("setSelectedObject", obj); return; } catch (err) {}
    try { store.state.selectedObject = obj; } catch (err) {}
  }
  function lockObject(stel, obj) {
    if (!stel || !obj) return false;
    try {
      if (typeof stel.pointAndLock === "function" && typeof obj.v === "number") {
        stel.pointAndLock(obj, 1.0);
        return true;
      }
    } catch (err) {}
    try {
      if (stel.core) {
        stel.core.lock = obj;
        return true;
      }
    } catch (err) {}
    return false;
  }
  function lookAtIcrf(stel, raHours, decDeg) {
    if (!stel || !stel.core || !stel.observer) return false;
    raHours = Number(raHours);
    decDeg = Number(decDeg);
    if (!isFinite(raHours) || !isFinite(decDeg)) return false;
    var ra = (((raHours % 24) + 24) % 24) * Math.PI / 12;
    var dec = decDeg * Math.PI / 180;
    var cdec = Math.cos(dec);
    var xyz = [cdec * Math.cos(ra), cdec * Math.sin(ra), Math.sin(dec), 0];
    var frames = ["OBSERVED", "HORIZONTAL", "CIRS", "JNOW"];
    if (typeof stel.convertFrame !== "function" || typeof stel.c2s !== "function")
      return false;
    for (var i = 0; i < frames.length; i++) {
      try {
        var observed = stel.convertFrame(stel.observer, "ICRF", frames[i], xyz);
        var sph = stel.c2s(observed);
        var yaw = Number(sph && sph[0]), pitch = Number(sph && sph[1]);
        if (!isFinite(yaw) || !isFinite(pitch)) continue;
        try { stel.core.lock = null; } catch (err) {}
        stel.core.yaw = yaw;
        stel.core.pitch = pitch;
        stel.observer.yaw = yaw;
        stel.observer.pitch = pitch;
        return true;
      } catch (err) {}
    }
    return false;
  }
  try {
    var stel = window._stel;
    var bits = vueBits();
    if (bits.stel && !stel) stel = bits.stel;
    if (!stel || !stel.core) return JSON.stringify({status: "loading"});
    var name = String((p && p.name) || "").trim();
    var aliases = (p && p.aliases) || [];
    var obj = findObject(stel, bits.stel, name, aliases);
    if (obj) {
      selectObject(stel, bits.store, obj);
      lockObject(stel, obj);
      return JSON.stringify({status: "locked", name: name});
    }
    if (lookAtIcrf(stel, p && p.ra_hours, p && p.dec_degrees))
      return JSON.stringify({status: "view", name: name});
    return JSON.stringify({status: "missing", name: name});
  } catch (err) {
    return JSON.stringify({status: "error"});
  }
})
"""


def sky_web_lock_target_script(payload: dict[str, Any] | None = None) -> str:
    data = payload if isinstance(payload, dict) else {}
    name = str(data.get("name") or "").strip()
    aliases = [
        str(item).strip()
        for item in (data.get("aliases") or [])
        if str(item or "").strip()
    ]
    body: dict[str, Any] = {"name": name, "aliases": aliases[:16]}
    try:
        ra = float(data.get("ra_hours"))
        dec = float(data.get("dec_degrees"))
    except (TypeError, ValueError):
        ra = dec = float("nan")
    if ra == ra and dec == dec:
        body["ra_hours"] = ra
        body["dec_degrees"] = dec
    return f"{SKY_WEB_LOCK_TARGET_JS}({json.dumps(body)})"


_GAIA_SOURCE_RE = re.compile(r"(?:gaia\s*(?:e?dr[123])?\s*)(\d{15,19})", re.IGNORECASE)
_SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
_GAIA_TAP_URL = "https://gea.esac.esa.int/tap-server/tap/sync"


def _sky_catalog_headers() -> dict[str, str]:
    return {"User-Agent": f"AstroDwarf/{__version__}"}


def gaia_source_id(name: str) -> int | None:
    candidates = gaia_source_candidates(name)
    return candidates[0] if candidates else None


def gaia_source_candidates(name: str) -> list[int]:
    """Possible Gaia source ids encoded in a firmware target name."""
    text = str(name or "").strip()
    found: list[int] = []
    seen: set[int] = set()

    def add(value: int) -> None:
        if value <= 0 or value in seen or value > 2**63 - 1:
            return
        seen.add(value)
        found.append(value)

    for match in re.finditer(r"\d+", text):
        run = match.group(0)
        if 15 <= len(run) <= 19:
            add(int(run))
            continue
        if len(run) < 15:
            continue
        for width in (19, 18, 17, 16):
            if len(run) < width:
                continue
            add(int(run[:width]))
            add(int(run[-width:]))
            for index in range(1, len(run) - width):
                add(int(run[index:index + width]))
    if not found:
        match = _GAIA_SOURCE_RE.search(text)
        if match:
            add(int(match.group(1)))
    return found


def _tap_rows(url: str, query: str, *, simbad: bool = False) -> list[list[Any]]:
    if simbad:
        payload = {"request": "doQuery", "lang": "ADQL", "format": "json", "query": query}
    else:
        payload = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": query}
    response = requests.post(url, data=payload, headers=_sky_catalog_headers(), timeout=12)
    response.raise_for_status()
    data = response.json()
    rows = data.get("data") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def _catalog_hit(name: str, ra_deg: float, dec_deg: float, aliases: list[str] | None = None) -> dict[str, Any]:
    ra_hours = ((float(ra_deg) / 15.0) % 24.0 + 24.0) % 24.0
    dec = max(-90.0, min(90.0, float(dec_deg)))
    label = str(name or "").strip() or "Catalog target"
    seen = {label.lower()}
    extra: list[str] = []
    for item in aliases or []:
        text = str(item or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        extra.append(text)
    return {
        "name": label,
        "ra_hours": round(ra_hours, 6),
        "dec_degrees": round(dec, 6),
        "aliases": extra[:16],
        "source": "catalog",
    }


def _gaia_lookup(source_id: int) -> dict[str, Any] | None:
    return _gaia_lookup_many([source_id])


def _gaia_lookup_many(source_ids: list[int]) -> dict[str, Any] | None:
    ordered: list[int] = []
    seen: set[int] = set()
    for item in source_ids:
        sid = int(item)
        if sid in seen:
            continue
        seen.add(sid)
        ordered.append(sid)
    for start in range(0, len(ordered), 8):
        chunk = ordered[start:start + 8]
        joined = ",".join(str(item) for item in chunk)
        rows = _tap_rows(
            _GAIA_TAP_URL,
            f"SELECT source_id, ra, dec FROM gaiadr3.gaia_source WHERE source_id IN ({joined})",
        )
        if not rows:
            rows = _tap_rows(
                _GAIA_TAP_URL,
                f"SELECT source_id, ra, dec FROM gaiadr2.gaia_source WHERE source_id IN ({joined})",
            )
        by_id: dict[int, list[Any]] = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 3:
                continue
            try:
                by_id[int(row[0])] = row
            except (TypeError, ValueError):
                continue
        for sid in chunk:
            row = by_id.get(sid)
            if row is None:
                continue
            return _catalog_hit(f"Gaia DR3 {sid}", float(row[1]), float(row[2]))
    return None


def _simbad_aliases(ids_text: str) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[|]+", str(ids_text or "")):
        ident = re.sub(r"\s+", " ", part).strip()
        if not ident:
            continue
        keep = bool(re.match(r"^(HIP|HD|HR|SAO|TYC|NAME)\s+\S+", ident, re.IGNORECASE))
        keep = keep or ident.startswith("*")
        if not keep:
            continue
        key = ident.lower()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(ident)
        if ident.startswith("*"):
            bare = ident.lstrip("*").strip()
            if bare and bare.lower() not in seen:
                seen.add(bare.lower())
                aliases.append(bare)
    return aliases[:16]


def _simbad_lookup(name: str) -> dict[str, Any] | None:
    candidates = [name]
    compact = re.sub(r"\s+", " ", name).strip()
    if compact not in candidates:
        candidates.append(compact)
    match = re.match(r"^(M|NGC|IC|HIP|HD|HR|SAO)\s*(\d+)$", compact, re.IGNORECASE)
    if match:
        candidates.append(f"{match.group(1).upper()} {match.group(2)}")
    for ident in candidates:
        escaped = ident.replace("'", "''")
        query = (
            "SELECT TOP 1 basic.ra, basic.dec, basic.main_id, ids.ids "
            "FROM basic JOIN ident ON ident.oidref = basic.oid "
            "JOIN ids ON ids.oidref = basic.oid "
            f"WHERE ident.id = '{escaped}'"
        )
        rows = _tap_rows(_SIMBAD_TAP_URL, query, simbad=True)
        if not rows:
            query = (
                "SELECT TOP 1 ra, dec, main_id FROM basic JOIN ident "
                f"ON ident.oidref = basic.oid WHERE id = '{escaped}'"
            )
            rows = _tap_rows(_SIMBAD_TAP_URL, query, simbad=True)
        if not rows:
            continue
        row = rows[0]
        if not isinstance(row, list) or len(row) < 3:
            continue
        main = str(row[2] or ident).strip() or ident
        extras = [ident, name]
        if len(row) > 3:
            extras.extend(_simbad_aliases(str(row[3] or "")))
        return _catalog_hit(main, float(row[0]), float(row[1]), extras)
    return None


def resolve_sky_catalog_target(name: str) -> dict[str, Any] | None:
    """Resolve a firmware/catalog name to ICRS RA/Dec when Stellarium cannot."""
    text = str(name or "").strip()
    if not text:
        return None
    source_ids = gaia_source_candidates(text)
    if source_ids:
        try:
            hit = _gaia_lookup_many(source_ids)
        except (TypeError, ValueError, requests.RequestException):
            hit = None
        if hit:
            return hit
    try:
        return _simbad_lookup(text)
    except (TypeError, ValueError, requests.RequestException):
        return None


def _sky_web_payload(raw: Any) -> dict[str, Any]:
    data: Any = raw
    for _ in range(2):
        if isinstance(data, str):
            text = data.strip()
            if not text:
                raise ValueError("Select a target in the sky map")
            data = json.loads(text)
            continue
        break
    if not isinstance(data, dict):
        raise ValueError("Select a target in the sky map")
    error = str(data.get("error") or "").strip()
    if error:
        raise ValueError(error)
    return data


def parse_sky_web_target(raw: Any) -> Target:
    data = _sky_web_payload(raw)
    try:
        ra_hours = float(data.get("ra_hours"))
        dec_degrees = float(data.get("dec_degrees"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Select a target in the sky map") from exc
    if ra_hours != ra_hours or dec_degrees != dec_degrees:
        raise ValueError("Select a target in the sky map")
    name = str(data.get("name") or "").strip() or "Stellarium target"
    return Target(
        name=name,
        kind=TargetKind.EQUATORIAL,
        ra_hours=round((ra_hours % 24.0 + 24.0) % 24.0, 6),
        dec_degrees=round(max(-90.0, min(90.0, dec_degrees)), 6),
    )


def sky_web_template_notes(raw: Any) -> str:
    try:
        data = _sky_web_payload(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    lines: list[str] = []
    object_type = str(data.get("type") or "").strip()
    if object_type:
        lines.append(object_type)
    aliases = [
        str(item).strip()
        for item in (data.get("aliases") or [])
        if str(item).strip()
    ]
    if aliases:
        lines.append("Also known as: " + ", ".join(aliases[:12]))
    try:
        magnitude = float(data.get("magnitude"))
    except (TypeError, ValueError):
        magnitude = None
    if magnitude is not None and magnitude == magnitude:
        lines.append(f"Magnitude: {magnitude:.2f}")
    distance = str(data.get("distance") or "").strip()
    if distance:
        lines.append(f"Distance: {distance}")
    spectral = str(data.get("spectral_type") or "").strip()
    if spectral:
        lines.append(f"Spectral type: {spectral}")
    morph = str(data.get("morphology") or "").strip()
    if morph:
        lines.append(f"Morphology: {morph}")
    size = str(data.get("size") or "").strip()
    if size:
        lines.append(f"Size: {size}")
    ra_text = str(data.get("ra_text") or "").strip()
    dec_text = str(data.get("dec_text") or "").strip()
    if ra_text and dec_text:
        lines.append(f"Ra/Dec: {ra_text}  /  {dec_text}")
    return "  ·  ".join(lines)


PANE_INDEX_RE = re.compile(r"pane\s+(\d+)(?:\s+of\s+(\d+))?", re.I)
PANE_TITLE_RE = re.compile(r"\s*[-–:]?\s*pane\s+\d+(?:\s+of\s+\d+)?\s*$", re.I)


def is_mosaic_pane_name(name: str) -> bool:
    """True for commanded mosaic labels such as 'I 212 pane 1'."""
    return bool(PANE_TITLE_RE.search(str(name or "")))


def mosaic_pane_index(name: str) -> int | None:
    match = PANE_INDEX_RE.search(str(name or ""))
    if not match:
        return None
    try:
        return max(1, int(match.group(1)))
    except (TypeError, ValueError):
        return None


def sky_names_related(left: str, right: str) -> bool:
    """True when one label is a mosaic pane of the other object."""
    first = str(left or "").strip()
    second = str(right or "").strip()
    if not first or not second:
        return False
    parent_a = mosaic_group_title(first)
    parent_b = mosaic_group_title(second)
    if not parent_a or not parent_b or parent_a.casefold() != parent_b.casefold():
        return False
    return is_mosaic_pane_name(first) or is_mosaic_pane_name(second)


def pane_sort_key(name: str) -> tuple[int, str]:
    match = PANE_INDEX_RE.search(name or "")
    return (int(match.group(1)) if match else 10**6, name or "")


def mosaic_grid_size(*mosaics: Mosaic | None) -> tuple[int, int]:
    rows = 1
    columns = 1
    for mosaic in mosaics:
        if mosaic is None:
            continue
        rows = max(rows, int(mosaic.grid_rows or 0), int(mosaic.row or 0), int(mosaic.rows or 0))
        columns = max(
            columns, int(mosaic.grid_columns or 0), int(mosaic.column or 0), int(mosaic.columns or 0)
        )
    return max(1, rows), max(1, columns)


def mosaic_pane_number(mosaic: Mosaic | None, columns: int = 0, name: str = "") -> int:
    cols = max(1, int(columns or 0))
    if mosaic is not None:
        if not columns:
            cols = max(
                1,
                int(mosaic.grid_columns or 0),
                int(mosaic.columns or 0),
                int(mosaic.column or 0),
            )
        if int(mosaic.row or 0) >= 1 and int(mosaic.column or 0) >= 1:
            return (int(mosaic.row) - 1) * cols + int(mosaic.column)
    match = PANE_INDEX_RE.search(name or "")
    if match:
        return max(1, int(match.group(1)))
    return 1


def mosaic_session_footprints(
    sessions: list[Any],
    fov_h: float,
    fov_v: float,
    position_angle: float = 0.0,
) -> list[dict[str, Any]]:
    """One FOV footprint per mosaic session, using that pane's stored pointing."""
    rows, columns = mosaic_grid_size(*(getattr(item, "mosaic", None) for item in sessions))
    pa = float(position_angle) % 360.0
    panes: list[dict[str, Any]] = []
    ordered = sorted(
        sessions,
        key=lambda item: (
            int(getattr(getattr(item, "mosaic", None), "row", 0) or 0),
            int(getattr(getattr(item, "mosaic", None), "column", 0) or 0),
            pane_sort_key(getattr(item, "name", "")),
        ),
    )
    for item in ordered:
        mosaic = getattr(item, "mosaic", None)
        target = getattr(item, "target", None)
        ra = getattr(target, "ra_hours", None)
        dec = getattr(target, "dec_degrees", None)
        if ra is None or dec is None:
            continue
        index = mosaic_pane_number(mosaic, columns, getattr(item, "name", ""))
        panes.append(
            {
                "index": index,
                "row": int(getattr(mosaic, "row", 0) or 0),
                "column": int(getattr(mosaic, "column", 0) or 0),
                "ra_hours": round(((float(ra) % 24.0) + 24.0) % 24.0, 6),
                "dec_degrees": round(float(dec), 6),
                "position_angle": round(pa, 3),
                "corners": _pane_corners(float(ra), float(dec), fov_h, fov_v, pa),
            }
        )
    panes.sort(key=lambda item: int(item.get("index") or 0))
    return panes


def live_mosaic_owns_target(live_label: str, group: str, target: str) -> bool:
    """True when firmware's capture/tracking name belongs to this live mosaic."""
    name = str(target or "").strip()
    if not name:
        return False
    label = str(live_label or "").strip()
    parent = mosaic_group_title(label, group)
    other = mosaic_group_title(name)
    if parent and other and parent.casefold() == other.casefold():
        return True
    return bool(label) and (
        label.casefold() == name.casefold() or sky_names_related(label, name)
    )


def live_mosaic_resume_plan(
    phase: str,
    current_index: int,
    total: int,
    capturing: bool,
) -> tuple[int, bool] | None:
    """Where to resume a persisted live mosaic after the app restarts.

    Returns ``(start_index, join_current)``, or ``None`` when every pane is done.
    A pane that was stacking when the app died is joined if the telescope is
    still capturing. If capture has already stopped, that pane is retried
    unless progress already recorded it as complete — otherwise a mid-stack
    crash skips the pane and leaves a hole in the mosaic.

    GOTO progress is persisted before GoLive releases the previous pane, so
    ``capture_active`` during phase ``goto`` or ``complete`` is leftover from
    the prior pane. Joining that leftover would mark the next pane complete
    without slewing.
    """
    try:
        index = max(1, int(current_index or 1))
    except (TypeError, ValueError):
        index = 1
    try:
        panes = max(0, int(total or 0))
    except (TypeError, ValueError):
        panes = 0
    label = str(phase or "").strip().lower()
    if capturing:
        if panes and index > panes:
            return None
        if label == "complete":
            start = index + 1
            if panes and start > panes:
                return None
            return start, False
        if label == "goto":
            return index, False
        return index, True
    if label == "complete":
        start = index + 1
    else:
        start = index
    if panes and start > panes:
        return None
    return start, False


def live_mosaic_scheduler_action(
    phase: str,
    worker_running: bool,
    capturing: bool,
    session_due: bool,
) -> str:
    """How the fleet scheduler should treat a persisted live mosaic.

    Recovery state stays on disk after a failure so reconnect can retry. A
    leftover that is not running must not hold the overnight queue: only a
    worker that still owns the telescope, or a stack the firmware is still
    exposing, blocks the next due session.
    """
    if worker_running:
        return "wait"
    if capturing:
        return "resume" if str(phase or "").strip() else "wait"
    if not str(phase or "").strip():
        return "idle"
    if session_due:
        return "yield"
    return "idle"


def mosaic_group_title(name: str, group_id: str = "") -> str:
    stripped = PANE_TITLE_RE.sub("", name or "").strip()
    if stripped:
        return stripped
    return (group_id or "Mosaic").replace("_", " ").replace("-", " ").strip()


def zoneinfo_from_name(name: str | None) -> ZoneInfo:
    text = str(name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def parse_in_zone(value: str, tz: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def store_local_iso(value: datetime, tz: ZoneInfo) -> str:
    if value.tzinfo is None:
        local = value.replace(tzinfo=tz)
    else:
        local = value.astimezone(tz)
    return local.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def observing_date(scheduled_start: str, cutoff_hour: int = 12, tz: ZoneInfo | str | None = None) -> str:
    zone = tz if isinstance(tz, ZoneInfo) else zoneinfo_from_name(tz) if tz else None
    if zone is None:
        value = datetime.fromisoformat(str(scheduled_start).replace("Z", "+00:00"))
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    else:
        value = parse_in_zone(scheduled_start, zone)
    if value.hour < cutoff_hour:
        value -= timedelta(days=1)
    return value.date().isoformat()


def mosaic_pane_workflow(workflow: Workflow, index: int) -> Workflow:
    if index <= 0:
        return workflow
    return replace(workflow, calibrate=False, polar_align=False)


def _mosaic_group_slug(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(name or "target").strip())
    return text.strip("-")[:40] or "mosaic"


def mosaic_south_up(latitude: Any) -> bool:
    try:
        return float(latitude or 0) < 0
    except (TypeError, ValueError):
        return False


def mosaic_column_one_on_right(south_up: bool, position_angle: Any = None) -> bool:
    """True when pane 1 belongs on the right of an N-up sky chart / contact sheet.

    Pane 1 is camera-right. Stellarium and the stacked JPEGs are N-up, so west
    is on the right at PA 0°. A south-up camera (PA near 180°) puts camera-right
    on the east, which is the left edge of that N-up chart. Latitude does not
    flip the sheet; south_up only remains for callers that still pass it.
    """
    pa = mosaic_position_angle(south_up, position_angle)
    camera_right_is_east = 90.0 < pa < 270.0
    return not camera_right_is_east


def mosaic_sheet_column(index: int, columns: int, *, south_up: bool = False, position_angle: Any = None) -> int:
    """0-based contact-sheet column for a 1-based pane index."""
    cols = max(1, int(columns or 1))
    raw = (max(1, int(index or 1)) - 1) % cols
    if mosaic_column_one_on_right(south_up, position_angle):
        return (cols - 1) - raw
    return raw


def mosaic_position_angle(south_up: bool, position_angle: Any = None) -> float:
    # Camera PA is east of celestial north. 0° is N-up in both hemispheres.
    # south_up only orients the chart / contact sheet, not the camera default.
    _ = south_up
    if position_angle is None or position_angle == "":
        return 0.0
    try:
        return float(position_angle) % 360.0
    except (TypeError, ValueError):
        return 0.0


def device_mosaic_pa(latitude: Any, position_angle: Any = None) -> float:
    """Resolved camera PA: stored offset, or 0° N-up when unset."""
    return mosaic_position_angle(mosaic_south_up(latitude), position_angle)


def _mosaic_grid_args(
    target: Target,
    columns: int,
    rows: int,
    fov_h: float,
    fov_v: float,
    overlap: float,
) -> tuple[int, int, float, float, float, float, float]:
    if target.kind == TargetKind.SOLAR or target.ra_hours is None or target.dec_degrees is None:
        raise ValueError("Select an equatorial target in Stellarium before generating a mosaic")
    try:
        columns = int(columns)
        rows = int(rows)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mosaic grid must be between 1×1 and 10×10") from exc
    if columns < 1 or rows < 1 or columns > MAX_MOSAIC_AXIS or rows > MAX_MOSAIC_AXIS:
        raise ValueError("Mosaic grid must be between 1×1 and 10×10")
    try:
        fov_h = float(fov_h)
        fov_v = float(fov_v)
        overlap = float(overlap)
    except (TypeError, ValueError) as exc:
        raise ValueError("Field of view must be greater than zero") from exc
    if fov_h <= 0 or fov_v <= 0:
        raise ValueError("Field of view must be greater than zero")
    overlap = min(0.8, max(0.0, overlap))
    center_ra_deg = (float(target.ra_hours) % 24.0) * 15.0
    center_dec = max(-90.0, min(90.0, float(target.dec_degrees)))
    return columns, rows, fov_h, fov_v, overlap, center_ra_deg, center_dec


def _offset_radec(ra_deg: float, dec_deg: float, east_deg: float, north_deg: float) -> tuple[float, float]:
    """Gnomonic offset along local east/north, matching a camera rectangle on the sky."""
    ra = radians(ra_deg)
    dec = radians(dec_deg)
    east_t = tan(radians(east_deg))
    north_t = tan(radians(north_deg))
    cos_dec = cos(dec)
    sin_dec = sin(dec)
    cos_ra = cos(ra)
    sin_ra = sin(ra)
    x = cos_dec * cos_ra - east_t * sin_ra - north_t * sin_dec * cos_ra
    y = cos_dec * sin_ra + east_t * cos_ra - north_t * sin_dec * sin_ra
    z = sin_dec + north_t * cos_dec
    norm = (x * x + y * y + z * z) ** 0.5
    if norm <= 0:
        return ra_deg, dec_deg
    x /= norm
    y /= norm
    z /= norm
    out_ra = (atan2(y, x) * 180.0 / pi) % 360.0
    out_dec = max(-90.0, min(90.0, asin(max(-1.0, min(1.0, z))) * 180.0 / pi))
    return out_ra, out_dec


def _offset_camera(
    ra_deg: float,
    dec_deg: float,
    right_deg: float,
    up_deg: float,
    position_angle: float,
) -> tuple[float, float]:
    """Offset in the camera plane. PA is east of north for camera-up.

    At PA 0° the frame is north-up. A sky chart has east on the left, so
    camera-right is west. The previous east=right mapping mirrored the
    mosaic: pane 1 was drawn on the right and the GOTO went left.
    """
    pa = radians(float(position_angle) % 360.0)
    east = -right_deg * cos(pa) + up_deg * sin(pa)
    north = right_deg * sin(pa) + up_deg * cos(pa)
    return _offset_radec(ra_deg, dec_deg, east, north)


def _pane_corners(
    ra_hours: float,
    dec_degrees: float,
    fov_h: float,
    fov_v: float,
    position_angle: float = 0.0,
) -> list[dict[str, float]]:
    ra_deg = ((ra_hours % 24.0) + 24.0) % 24.0 * 15.0
    half_w = float(fov_h) / 2.0
    half_h = float(fov_v) / 2.0
    pa = float(position_angle) % 360.0
    corners = (
        _offset_camera(ra_deg, dec_degrees, half_w, half_h, pa),
        _offset_camera(ra_deg, dec_degrees, half_w, -half_h, pa),
        _offset_camera(ra_deg, dec_degrees, -half_w, -half_h, pa),
        _offset_camera(ra_deg, dec_degrees, -half_w, half_h, pa),
    )
    return [
        {
            "ra_hours": round(((ra % 360.0) + 360.0) % 360.0 / 15.0, 6),
            "dec_degrees": round(dec, 6),
        }
        for ra, dec in corners
    ]


def mosaic_pane_footprints(
    target: Target,
    columns: int,
    rows: int,
    fov_h: float,
    fov_v: float,
    overlap: float = 0.2,
    south_up: bool = False,
    position_angle: Any = None,
) -> list[dict[str, Any]]:
    columns, rows, fov_h, fov_v, overlap, center_ra_deg, center_dec = _mosaic_grid_args(
        target, columns, rows, fov_h, fov_v, overlap
    )
    pa = mosaic_position_angle(south_up, position_angle)
    step_x = fov_h * (1.0 - overlap)
    step_y = fov_v * (1.0 - overlap)
    panes: list[dict[str, Any]] = []
    index = 0
    for row in range(1, rows + 1):
        row_offset = row - (rows + 1) / 2
        up = -row_offset * step_y
        for column in range(1, columns + 1):
            index += 1
            col_offset = column - (columns + 1) / 2
            right = -col_offset * step_x
            ra_deg, dec = _offset_camera(center_ra_deg, center_dec, right, up, pa)
            ra_hours = ra_deg / 15.0
            panes.append(
                {
                    "index": index,
                    "row": row,
                    "column": column,
                    "ra_hours": round(((ra_hours % 24.0) + 24.0) % 24.0, 6),
                    "dec_degrees": round(dec, 6),
                    "position_angle": round(pa, 3),
                    "corners": _pane_corners(ra_hours, dec, fov_h, fov_v, pa),
                }
            )
    return panes


def generate_mosaic_plan(
    target: Target,
    columns: int,
    rows: int,
    fov_h: float,
    fov_v: float,
    overlap: float = 0.2,
    south_up: bool = False,
    position_angle: Any = None,
) -> list[SessionTemplate]:
    """Build Telescopius-shaped pane templates around an equatorial target."""
    pa = mosaic_position_angle(south_up, position_angle)
    panes = mosaic_pane_footprints(
        target, columns, rows, fov_h, fov_v, overlap, south_up=south_up, position_angle=pa
    )
    grid_rows = max(item["row"] for item in panes)
    grid_columns = max(item["column"] for item in panes)
    group_id = f"{_mosaic_group_slug(target.name)}-{new_id()[:8]}"
    heading = "S-up" if 90.0 < (pa % 360.0) < 270.0 else "N-up"
    notes = (
        f"Generated mosaic {grid_columns}×{grid_rows}, {overlap:.0%} overlap, "
        f"FOV {float(fov_h):.2f}° × {float(fov_v):.2f}°, {heading}, PA {pa:.1f}° E"
    )
    templates: list[SessionTemplate] = []
    for pane in panes:
        templates.append(
            SessionTemplate(
                name=f"{target.name} pane {pane['index']}",
                target=Target(
                    name=target.name,
                    kind=TargetKind.EQUATORIAL,
                    ra_hours=pane["ra_hours"],
                    dec_degrees=pane["dec_degrees"],
                ),
                workflow=mosaic_pane_workflow(Workflow(), pane["index"] - 1),
                mosaic=Mosaic(
                    group_id=group_id,
                    grid_rows=grid_rows,
                    grid_columns=grid_columns,
                    row=pane["row"],
                    column=pane["column"],
                ),
                notes=notes,
            )
        )
    return templates


def stagger_mosaic_sessions(sessions: list[Session], start: datetime, profile: HardwareProfile) -> list[Session]:
    cursor = start.replace(second=0, microsecond=0)
    result: list[Session] = []
    for index, session in enumerate(sorted(sessions, key=lambda item: pane_sort_key(item.name))):
        workflow = mosaic_pane_workflow(session.workflow, index)
        duration = DurationEngine.calculate(replace(session, workflow=workflow), profile)
        result.append(replace(
            session,
            workflow=workflow,
            scheduled_start=cursor.isoformat(timespec="minutes"),
            planned_duration_seconds=duration,
        ))
        cursor += timedelta(minutes=max(1, ceil(duration / 60.0)))
    return result


def occupied_minutes(session: Session) -> int:
    return max(1, int(ceil(max(0, session.planned_duration_seconds) / 60.0)))


def session_window(session: Session, tz) -> tuple[datetime, datetime]:
    start = parse_in_zone(session.scheduled_start, tz).replace(second=0, microsecond=0)
    return start, start + timedelta(minutes=occupied_minutes(session))


def sessions_overlap(left: Session, right: Session, tz) -> bool:
    left_start, left_end = session_window(left, tz)
    right_start, right_end = session_window(right, tz)
    return left_start < right_end and right_start < left_end


def next_free_start(
    occupied: list[tuple[datetime, datetime]],
    start: datetime,
    duration: timedelta,
) -> datetime:
    cursor = start.replace(second=0, microsecond=0)
    span = duration if duration > timedelta(0) else timedelta(minutes=1)
    blocks = sorted(occupied, key=lambda item: item[0])
    while True:
        end = cursor + span
        hit = next((block_end for block_start, block_end in blocks if cursor < block_end and block_start < end), None)
        if hit is None:
            return cursor
        cursor = hit.replace(second=0, microsecond=0)


class DurationEngine:
    @staticmethod
    def calculate(session: Session | SessionTemplate, profile: HardwareProfile) -> float:
        workflow = session.workflow
        setup = profile.startup_seconds + workflow.wait_before_seconds + workflow.wait_after_seconds
        setup += profile.calibration_seconds if workflow.calibrate else 0
        setup += profile.autofocus_seconds if workflow.autofocus else 0
        setup += profile.infinite_focus_seconds if workflow.infinite_focus else 0
        setup += profile.polar_seconds if workflow.polar_align else 0
        setup += profile.slew_seconds + profile.settle_seconds if workflow.goto else 0
        panes = session.mosaic.panes
        imaging = (session.camera.exposure_seconds + profile.readout_seconds) * session.camera.frame_count * panes
        return round(setup + imaging + profile.pane_slew_seconds * max(0, panes - 1), 1)


class StellariumClient:
    def __init__(self, base_url: str = "http://localhost:8090"):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, timeout: float = 3.0, **kwargs: Any):
        return requests.get(f"{self.base_url}{path}", timeout=timeout, **kwargs)

    def _post(self, path: str, data: dict[str, Any], timeout: float = 3.0):
        response = requests.post(f"{self.base_url}{path}", data=data, timeout=timeout)
        response.raise_for_status()
        return response

    def available(self) -> bool:
        try:
            response = self._get("/api/main/status", timeout=1.0)
            return bool(response.ok)
        except Exception:
            return False

    def current_target(self) -> Target:
        response = self._get("/api/objects/info", params={"format": "json"}, timeout=3)
        response.raise_for_status()
        data = response.json()
        name = data.get("localized-name") or data.get("name") or "Stellarium target"
        ra_degrees = data.get("raJ2000")
        dec = data.get("decJ2000")
        if ra_degrees is None or dec is None:
            raise ValueError("Select a target in Stellarium before importing")
        return Target(name=name, ra_hours=(float(ra_degrees) % 360) / 15, dec_degrees=float(dec))

    def set_location(self, latitude: float, longitude: float, name: str = "", altitude: float = 0) -> None:
        data: dict[str, Any] = {
            "latitude": str(float(latitude)),
            "longitude": str(float(longitude)),
            "altitude": str(float(altitude)),
        }
        label = str(name or "").strip()
        if label:
            data["name"] = label
        self._post("/api/location/setlocationfields", data)

    def focus_target(self, name: str) -> None:
        target = str(name or "").strip()
        if not target:
            raise ValueError("Select a target in Stellarium before importing")
        self._post("/api/main/focus", {"target": target, "mode": "center"})

    def focus_j2000(self, ra_hours: float, dec_degrees: float) -> None:
        ra_rad = ((float(ra_hours) % 24.0) + 24.0) % 24.0 * 15.0 * pi / 180.0
        dec_rad = max(-90.0, min(90.0, float(dec_degrees))) * pi / 180.0
        vec = [
            cos(dec_rad) * cos(ra_rad),
            cos(dec_rad) * sin(ra_rad),
            sin(dec_rad),
        ]
        self._post("/api/main/focus", {"position": json.dumps(vec)})

    def set_fov(self, degrees: float) -> None:
        fov = float(degrees)
        if fov <= 0:
            return
        self._post("/api/main/fov", {"fov": str(fov)})

    def set_time_now(self) -> None:
        for action_id in ("actionReturn_To_Current_Time", "actionSet_Time_Now"):
            try:
                self._post("/api/stelaction/do", {"id": action_id})
                return
            except Exception:
                continue
        julian_day = time.time() / 86400.0 + 2440587.5
        self._post("/api/main/time", {"time": str(julian_day), "timerate": str(1.0 / 86400.0)})

    def push_view(
        self,
        target: Target,
        latitude: float | None = None,
        longitude: float | None = None,
        name: str = "",
        fov_degrees: float = 0.0,
    ) -> None:
        if latitude is not None and longitude is not None:
            self.set_location(latitude, longitude, name)
        try:
            self.set_time_now()
        except Exception:
            pass
        focused = False
        label = str(target.name or "").strip()
        if label:
            try:
                self.focus_target(label)
                focused = True
            except Exception:
                focused = False
        if not focused:
            if target.ra_hours is None or target.dec_degrees is None:
                raise ValueError("Select a target in Stellarium before importing")
            self.focus_j2000(target.ra_hours, target.dec_degrees)
        if fov_degrees > 0:
            self.set_fov(fov_degrees)


def _parse_ra(value: str) -> float:
    text = value.strip().lower().replace("hr", "").replace("hours", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return float(text)
    values = [float(part) for part in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        raise ValueError(f"Invalid right ascension: {value}")
    return values[0] + (values[1] if len(values) > 1 else 0) / 60 + (values[2] if len(values) > 2 else 0) / 3600


def _parse_dec(value: str) -> float:
    text = value.strip().lower().replace("º", " ").replace("°", " ")
    sign = -1 if text.startswith("-") else 1
    values = [float(part) for part in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        raise ValueError(f"Invalid declination: {value}")
    return sign * (values[0] + (values[1] if len(values) > 1 else 0) / 60 + (values[2] if len(values) > 2 else 0) / 3600)


def _parse_grid_index(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def import_telescopius(path: Path) -> list[SessionTemplate]:
    templates: list[SessionTemplate] = []
    group = path.stem
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle), 1):
            lowered = {str(k).strip().lower(): v for k, v in row.items()}
            name = (
                lowered.get("target")
                or lowered.get("name")
                or lowered.get("familiar name")
                or lowered.get("catalogue entry")
                or lowered.get("pane")
                or f"{group} pane {index}"
            )
            ra = (
                lowered.get("ra")
                or lowered.get("right ascension")
                or lowered.get("ra (hours)")
                or lowered.get("right ascension (j2000)")
            )
            dec = (
                lowered.get("dec")
                or lowered.get("declination")
                or lowered.get("dec (degrees)")
                or lowered.get("declination (j2000)")
            )
            if ra in (None, "") or dec in (None, ""):
                continue
            if str(lowered.get("pane", "")).strip().lower() == "center":
                continue
            templates.append(
                SessionTemplate(
                    name=str(name),
                    target=Target(name=str(name), ra_hours=_parse_ra(str(ra)), dec_degrees=_parse_dec(str(dec))),
                    mosaic=Mosaic(
                        group_id=group,
                        row=_parse_grid_index(lowered.get("row")),
                        column=_parse_grid_index(lowered.get("column")),
                    ),
                    notes=f"Imported from Telescopius: {path.name}",
                )
            )
    templates.sort(key=lambda item: pane_sort_key(item.name))
    # the plan grid is whatever the pane positions span; a plain target list has none
    grid_rows = max((item.mosaic.row for item in templates), default=0)
    grid_columns = max((item.mosaic.column for item in templates), default=0)
    return [
        replace(
            template,
            workflow=mosaic_pane_workflow(template.workflow, index),
            mosaic=replace(template.mosaic, grid_rows=grid_rows, grid_columns=grid_columns),
        )
        for index, template in enumerate(templates)
    ]
