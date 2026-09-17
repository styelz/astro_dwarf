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
    var east = rightDeg * Math.cos(pa) + upDeg * Math.sin(pa);
    var north = -rightDeg * Math.sin(pa) + upDeg * Math.cos(pa);
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
    try {
      var icrf = asVec(stel.convertFrame(stel.observer, "VIEW", "ICRF", [0, 0, -1, 0]));
      var back = icrf ? asVec(stel.convertFrame(stel.observer, "ICRF", "VIEW", [icrf[0], icrf[1], icrf[2], 0])) : null;
      if (back && isFinite(back[2]) && back[2] > 0) sign = 1;
    } catch (err) {}
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
  function viewCenter(stel) {
    if (!stel || !stel.observer) return null;
    var dirs = [[0, 0, zSign(stel), 0], [0, 0, -zSign(stel), 0], [0, 0, -1, 0], [0, 0, 1, 0], [0, 0, -1], [0, 0, 1]];
    var frames = ["ICRF", "CIRS", "JNOW"];
    if (typeof stel.convertFrame === "function") {
      for (var f = 0; f < frames.length; f++) {
        for (var i = 0; i < dirs.length; i++) {
          try {
            var pos = icrfToRaDec(stel, stel.convertFrame(stel.observer, "VIEW", frames[f], dirs[i]));
            if (pos) return pos;
          } catch (err) {}
        }
      }
    }
    var o = stel.observer;
    var mats = [o.rc2v, o.ri2v];
    for (var m = 0; m < mats.length; m++) {
      var mat = mats[m];
      if (!mat || mat.length < 9) continue;
      try {
        var vx = Number(mat[2]), vy = Number(mat[5]), vz = Number(mat[8]);
        if (isFinite(vx) && isFinite(vy) && isFinite(vz)) {
          var fromCol = xyzToRaDec([-vx, -vy, -vz]);
          if (isFinite(fromCol.ra_hours) && isFinite(fromCol.dec_degrees))
            return fromCol;
        }
      } catch (err) {}
    }
    return null;
  }
  function framePointing(stel) {
    var ctl = window[CTL];
    var live = viewCenter(stel);
    if (live && ctl) ctl.heldPos = live;
    return live || (ctl && ctl.heldPos) || null;
  }
  function gridPanes(center, p) {
    var cols = Math.max(1, Number(p.columns) || 1);
    var rows = Math.max(1, Number(p.rows) || 1);
    var overlap = Math.max(0, Math.min(0.8, Number(p.overlap) || 0));
    var fovH = Number(p.fov_h), fovV = Number(p.fov_v);
    if (!(fovH > 0) || !(fovV > 0) || !center) return [];
    var pa = Number(p.position_angle);
    if (!isFinite(pa)) pa = p.south_up ? 180 : 0;
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
  function textAt(x, y, angle, text, color, extra, fontSize) {
    extra = extra || "";
    var size = Number(fontSize);
    if (!(size > 0)) size = 11;
    return '<text x="0" y="0" fill="' + color
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
    return "RA " + ra.toFixed(3) + "h  DEC " + (dec >= 0 ? "+" : "") + dec.toFixed(3) + "°";
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
  function currentPointing(p, stel) {
    return payloadPointing(p) || selectedPointing(stel) || framePointing(stel);
  }
  function frameCaption(p, stel) {
    var head = String(p.label || "").replace(/\s*PA\s+[-+]?\d+(?:\.\d+)?°/i, "").replace(/\s+/g, " ").trim();
    var pa = Number(p && p.position_angle);
    if (!isFinite(pa)) pa = p && p.south_up ? 180 : 0;
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
        svg += textAt(x + ox * 13, y + oy * 13, ang, cap.pos, color, extra, size);
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
    return p && p.south_up ? 180 : 0;
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
    var svg = "";
    var labels = "";
    var index = 0;
    for (var row = 1; row <= rows; row++) {
      for (var col = 1; col <= cols; col++) {
        index += 1;
        var x = originX + (cols - col) * stepX;
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
      svg += liveImageRect(originX, originY, totalW, totalH);
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
      svg += liveImageQuad(mosaicOuterQuad(drawn));
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
    var center = viewCenter(stel);
    if (!center) return [];
    return gridPanes(center, p);
  }
  function viewKey(stel, box) {
    var o = stel.observer || {};
    return [o.yaw, o.pitch, o.roll, stel.core && stel.core.fov, box && box.width, box && box.height,
      nightModeOn() ? "N" : "D"].join("|");
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
    var key = viewKey(stel, box) + "|" + ctl.payloadKey + "|" + (ctl.liveEnabled ? "L" : "n")
      + "|" + livePaneIndex() + "|" + paneUrlKey();
    if (!force && key === ctl.lastKey)
      return ctl.lastStatus || "panes";
    ctl.lastKey = key;
    var el = overlayFor(box);
    var panes = resolvePanes(stel, p);
    if (panes.length) {
      var projected = drawPanes(el, box, p, stel, panes);
      if (projected) {
        ctl.lastStatus = projected;
        return projected;
      }
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
        payload: p, payloadKey: "", lastKey: "", lastStatus: "", zSign: 0, raf: 0,
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
      p.target_ra_hours, p.target_dec_degrees
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


def mosaic_position_angle(south_up: bool, position_angle: Any = None) -> float:
    if position_angle is None or position_angle == "":
        return 180.0 if south_up else 0.0
    try:
        return float(position_angle) % 360.0
    except (TypeError, ValueError):
        return 180.0 if south_up else 0.0


def device_mosaic_pa(latitude: Any, position_angle: Any = None) -> float:
    """Resolved camera PA: stored offset, or 180° S-up / 0° N-up from site latitude."""
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
    """Offset in the camera plane. PA is east of north, same as Telescopius."""
    pa = radians(float(position_angle) % 360.0)
    east = right_deg * cos(pa) + up_deg * sin(pa)
    north = -right_deg * sin(pa) + up_deg * cos(pa)
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
    heading = "S-up" if south_up else "N-up"
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
