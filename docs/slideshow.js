(function () {
  const slides = [
    {
      src: "screens/control.jpg",
      thumb: "screens/thumbs/control.jpg",
      label: "Control",
      alt: "Astro Dwarf Control page during a DSO stack on a Dwarf 3, showing live tele view, stacking progress, and command pad.",
      cap: "Control HUD during a DSO stack on a Dwarf 3 — live tele view, stacking progress, and command pad.",
    },
    {
      src: "screens/control-live.jpg",
      thumb: "screens/thumbs/control-live.jpg",
      label: "Live",
      alt: "Control page with live video ready, motion pad, upcoming mosaic panes, and command deck.",
      cap: "Between stacks: live preview, motion pad, upcoming queue, and the command deck.",
    },
    {
      src: "screens/calendar-night.jpg",
      thumb: "screens/thumbs/calendar-night.jpg",
      label: "Night",
      alt: "Night calendar listing Alcyone and mosaic panes on the selected night.",
      cap: "Night calendar — the selected night as a timeline with edit and run on each session.",
    },
    {
      src: "screens/calendar-month.jpg",
      thumb: "screens/thumbs/calendar-month.jpg",
      label: "Month",
      alt: "Month calendar with session chips on a night and the selected-night list on the right.",
      cap: "Month view with the session list beside the grid.",
    },
    {
      src: "screens/sessions.jpg",
      thumb: "screens/thumbs/sessions.jpg",
      label: "Sessions",
      alt: "Sessions page listing a scheduled target and an imported Telescopius mosaic plan.",
      cap: "Scheduled sessions, including an imported Telescopius mosaic plan.",
    },
    {
      src: "screens/session-edit.jpg",
      thumb: "screens/thumbs/session-edit.jpg",
      label: "Edit",
      alt: "Edit Session dialog for a mosaic pane with camera, coordinates, and workflow checks.",
      cap: "Edit a pane: camera, coordinates, mosaic grid, and workflow (calibrate, autofocus, GOTO).",
    },
    {
      src: "screens/templates.jpg",
      thumb: "screens/thumbs/templates.jpg",
      label: "Templates",
      alt: "Session templates for Alcyone and a Telescopius mosaic plan.",
      cap: "Reusable session recipes — schedule or edit without rebuilding capture settings.",
    },
    {
      src: "screens/history.jpg",
      thumb: "screens/thumbs/history.jpg",
      label: "History",
      alt: "History page with empty completed-run stats for the selected telescope.",
      cap: "History of completed runs, scoped to this telescope or all devices.",
    },
    {
      src: "screens/media.jpg",
      thumb: "screens/thumbs/media.jpg",
      label: "Media",
      alt: "Media album of astro sessions stored on the connected Dwarf 3.",
      cap: "Astro sessions on the telescope — thumbnails, capture details, stacked-frame download.",
    },
    {
      src: "screens/media-viewer.jpg",
      thumb: "screens/thumbs/media-viewer.jpg",
      label: "Viewer",
      alt: "Stacked-frame viewer open on Gaia DR3 with enhance and download actions.",
      cap: "Stacked-frame viewer with enhance, deep clean, and download.",
    },
    {
      src: "screens/sky.jpg",
      thumb: "screens/thumbs/sky.jpg",
      label: "Sky",
      alt: "Sky page with Stellarium Web and a mosaic grid over the Andromeda Galaxy.",
      cap: "Sky map via Stellarium Web. Pick a target, set a mosaic grid, create the session.",
    },
    {
      src: "screens/settings-device.jpg",
      thumb: "screens/thumbs/settings-device.jpg",
      label: "Device",
      alt: "Device settings for name, colour, model, camera, timezone, and site coordinates.",
      cap: "Telescope identity, model, default camera, timezone, and site coordinates.",
    },
    {
      src: "screens/settings-add-device.jpg",
      thumb: "screens/thumbs/settings-add-device.jpg",
      label: "Add",
      alt: "Add Device dialog with Bluetooth password, IP, timezone, and coordinates.",
      cap: "Add another Dwarf: Bluetooth scan to fill IP, then Wi-Fi mode for the live stream.",
    },
    {
      src: "screens/settings-interface.jpg",
      thumb: "screens/thumbs/settings-interface.jpg",
      label: "Interface",
      alt: "Interface settings with theme presets, hue, and colour tokens.",
      cap: "Console look on this computer — nav layout, HUD art, and theme hue.",
    },
    {
      src: "screens/settings-image.jpg",
      thumb: "screens/thumbs/settings-image.jpg",
      label: "Image",
      alt: "Image settings for stacked-frame enhance strength and where filters apply.",
      cap: "Display-only stacked-frame enhance. Nothing is written back to the telescope.",
    },
  ];

  const img = document.getElementById("slide-img");
  const cap = document.getElementById("slide-cap");
  const count = document.getElementById("slide-count");
  const thumbs = document.getElementById("slide-thumbs");
  const root = document.getElementById("screens");
  if (!img || !thumbs) return;

  let index = 0;
  let timer = 0;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function show(next) {
    index = (next + slides.length) % slides.length;
    const slide = slides[index];
    img.src = slide.src;
    img.alt = slide.alt;
    cap.textContent = slide.cap;
    count.textContent = index + 1 + " / " + slides.length;
    thumbs.querySelectorAll("button").forEach(function (btn, i) {
      btn.setAttribute("aria-selected", i === index ? "true" : "false");
    });
    const selected = thumbs.children[index];
    if (selected && selected.scrollIntoView) {
      selected.scrollIntoView({ inline: "nearest", block: "nearest", behavior: reduced ? "auto" : "smooth" });
    }
  }

  function arm() {
    if (reduced) return;
    window.clearInterval(timer);
    timer = window.setInterval(function () {
      show(index + 1);
    }, 4500);
  }

  slides.forEach(function (slide, i) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-label", slide.label);
    btn.setAttribute("aria-selected", i === 0 ? "true" : "false");
    const thumb = document.createElement("img");
    thumb.src = slide.thumb;
    thumb.alt = "";
    thumb.width = 90;
    thumb.height = 56;
    btn.appendChild(thumb);
    btn.addEventListener("click", function () {
      show(i);
      arm();
    });
    thumbs.appendChild(btn);
  });

  document.getElementById("slide-prev").addEventListener("click", function () {
    show(index - 1);
    arm();
  });
  document.getElementById("slide-next").addEventListener("click", function () {
    show(index + 1);
    arm();
  });

  root.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      show(index - 1);
      arm();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      show(index + 1);
      arm();
    }
  });
  root.setAttribute("tabindex", "0");

  let touchX = null;
  root.addEventListener("touchstart", function (event) {
    if (event.changedTouches.length) touchX = event.changedTouches[0].clientX;
  }, { passive: true });
  root.addEventListener("touchend", function (event) {
    if (touchX == null || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) < 40) return;
    show(index + (dx < 0 ? 1 : -1));
    arm();
  }, { passive: true });

  root.addEventListener("mouseenter", function () {
    window.clearInterval(timer);
  });
  root.addEventListener("mouseleave", arm);

  arm();
})();
