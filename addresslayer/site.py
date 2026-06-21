"""Render the GitHub Pages landing page into build/site/.

City-specific strings come from the config; the preview-map centre comes from
the slim meta bbox; screenshots/license link are optional (a first build works
before they exist).
"""

import json
import os
import re
import shutil
from datetime import date

from PIL import Image

SCREENSHOTS = ["iD.png", "JOSM.png"]
SCREENSHOT_MAX_WIDTH = 1500
PREVIEW_ZOOM = 16

_FIGURE_CAPTIONS = {
    "iD.png": "The vector layer in iD -- a clicked point's address tags in the inspector.",
    "JOSM.png": "The raster layer in JOSM -- house numbers over aerial imagery.",
}


def build_site(cfg):
    """Render index.html, copy assets and screenshots into build/site/."""
    os.makedirs(cfg.site_dir, exist_ok=True)
    meta = _load_meta(cfg)
    point_count = f"{meta['count']:,}" if meta.get("count") else "many"
    build_date = date.today().isoformat()
    clat, clon = _center(meta)
    raster_min, raster_max = min(cfg.raster_zooms), max(cfg.raster_zooms)

    with open(cfg.asset("index.html.tmpl"), encoding="utf-8") as f:
        html = f.read()

    replacements = {
        "{{TITLE}}": cfg.title_or_default,
        "{{PROVIDER}}": cfg.provider,
        "{{ATTRIBUTION}}": cfg.attribution,
        "{{POINT_COUNT}}": point_count,
        "{{BUILD_DATE}}": build_date,
        "{{DATA_DATE}}": _data_date(cfg, build_date),
        "{{PAGES_URL}}": cfg.pages_url,
        "{{VECTOR_URL}}": f"{cfg.pages_url}/tiles/vector/{{z}}/{{x}}/{{y}}.pbf",
        "{{RASTER_URL}}": f"{cfg.pages_url}/tiles/raster/{{z}}/{{x}}/{{y}}.png",
        "{{VECTOR_URL_JOSM}}": f"{cfg.pages_url}/tiles/vector/{{zoom}}/{{x}}/{{y}}.pbf",
        "{{RASTER_URL_JOSM}}": f"{cfg.pages_url}/tiles/raster/{{zoom}}/{{x}}/{{y}}.png",
        "{{GITHUB_REPO}}": cfg.github_repo,
        "{{DATASET_PAGE}}": cfg.dataset_page,
        "{{LICENSE_BLOCK}}": _license_block(cfg),
        "{{VECTOR_MAXZOOM}}": str(cfg.vector_maxzoom),
        "{{RASTER_MINZOOM}}": str(raster_min),
        "{{RASTER_MAXZOOM}}": str(raster_max),
        "{{CENTER_LAT}}": f"{clat:.5f}",
        "{{CENTER_LON}}": f"{clon:.5f}",
        "{{CENTER_ZOOM}}": str(PREVIEW_ZOOM),
        "{{ID_FIGURE}}": _figure(cfg, "iD.png"),
        "{{JOSM_FIGURE}}": _figure(cfg, "JOSM.png"),
        "{{FOOTER_EXTRA}}": _footer_extra(cfg),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    with open(os.path.join(cfg.site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    for name in ("index.css", "index.js"):
        shutil.copy(cfg.asset(name), os.path.join(cfg.site_dir, name))
    for name in SCREENSHOTS:
        src = os.path.join(cfg.override_assets_dir, name)
        if os.path.isfile(src):
            _copy_image(src, os.path.join(cfg.site_dir, name), SCREENSHOT_MAX_WIDTH)
    # .nojekyll stops GitHub Pages running Jekyll over the tile directories.
    open(os.path.join(cfg.site_dir, ".nojekyll"), "w").close()
    print(f"Site rendered: {cfg.site_dir}")


def _load_meta(cfg):
    if os.path.isfile(cfg.meta_path):
        with open(cfg.meta_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _center(meta):
    if "min_lat" in meta:
        return ((meta["min_lat"] + meta["max_lat"]) / 2,
                (meta["min_lon"] + meta["max_lon"]) / 2)
    return 0.0, 0.0


def _data_date(cfg, fallback):
    """Date (YYYY-MM-DD) of the source snapshot, from the newest dated file."""
    if os.path.isdir(cfg.data_dir):
        dated = sorted(
            f for f in os.listdir(cfg.data_dir)
            if f.startswith(f"{cfg.slug}-") and f.endswith(".geojson")
            and re.search(r"\d{4}-\d{2}-\d{2}", f)
        )
        if dated:
            return re.search(r"\d{4}-\d{2}-\d{2}", dated[-1]).group(0)
    return fallback


def _license_block(cfg):
    name = cfg.license_name or "the source licence"
    if cfg.license_url:
        return f'<a href="{cfg.license_url}">{name}</a>'
    return name


def _figure(cfg, name):
    if not os.path.isfile(os.path.join(cfg.override_assets_dir, name)):
        return ""
    caption = _FIGURE_CAPTIONS.get(name, "")
    return (
        f'<figure><img src="{name}" loading="lazy" alt="{caption}">'
        f'<figcaption>{caption}</figcaption></figure>'
    )


def _footer_extra(cfg):
    if cfg.changes_url:
        return (f'&nbsp;&middot;&nbsp; <a href="{cfg.changes_url}">'
                f'Address change tracker</a>')
    return ""


def _copy_image(src, dst, max_width):
    """Copy an image into the site, downscaling it if wider than max_width."""
    with Image.open(src) as img:
        if img.width > max_width:
            height = round(img.height * max_width / img.width)
            resized = img.resize((max_width, height), Image.LANCZOS)
            resized.save(dst, optimize=True)
            print(f"  {os.path.basename(src)}: {img.width}px -> {max_width}px")
        else:
            shutil.copy(src, dst)
