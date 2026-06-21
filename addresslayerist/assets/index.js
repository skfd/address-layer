// Address-layerist landing page: preview map + copy buttons.
// City-specific values (centre, zoom range, raster URL) come from data-*
// attributes on #preview-map, written by the site template.

(function () {
  "use strict";

  function num(value, fallback) {
    var n = parseFloat(value);
    return isNaN(n) ? fallback : n;
  }

  function initMap() {
    var el = document.getElementById("preview-map");
    if (!el || typeof L === "undefined" || !el.dataset.rasterUrl) {
      return;
    }

    var lat = num(el.dataset.centerLat, 0);
    var lon = num(el.dataset.centerLon, 0);
    var zoom = num(el.dataset.centerZoom, 16);
    var rasterMin = num(el.dataset.rasterMin, 16);
    var rasterMax = num(el.dataset.rasterMax, 19);

    var map = L.map(el, { minZoom: 14, maxZoom: rasterMax }).setView(
      [lat, lon], zoom
    );

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: rasterMax,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">' +
        "OpenStreetMap</a> contributors",
    }).addTo(map);

    L.tileLayer(el.dataset.rasterUrl, {
      minZoom: rasterMin,
      maxNativeZoom: rasterMax,
      maxZoom: rasterMax,
      attribution: el.dataset.attribution || "",
    }).addTo(map);
  }

  function initCopyButtons() {
    var blocks = document.querySelectorAll("pre.url");
    Array.prototype.forEach.call(blocks, function (pre) {
      var wrap = document.createElement("div");
      wrap.className = "url-wrap";
      pre.parentNode.insertBefore(wrap, pre);
      wrap.appendChild(pre);

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.textContent = "Copy";
      wrap.appendChild(btn);

      btn.addEventListener("click", function () {
        navigator.clipboard.writeText(pre.textContent).then(
          function () {
            flash(btn, "Copied");
          },
          function () {
            flash(btn, "Press Ctrl+C");
          }
        );
      });
    });
  }

  function flash(btn, message) {
    btn.textContent = message;
    setTimeout(function () {
      btn.textContent = "Copy";
    }, 1500);
  }

  document.addEventListener("DOMContentLoaded", function () {
    initMap();
    initCopyButtons();
  });
})();
