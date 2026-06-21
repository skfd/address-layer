---
name: onboard-city
description: Onboard a new municipality into an address tile layer. Use when asked to "add a city", "create an address layer for <place>", or set up a new <city>-address-layer repo. Produces a layer.toml the locked engine consumes.
---

# Onboard a city into an address layer

This is the **fuzzy** half of address-layerist: the judgement work that turns a
municipality into a `layer.toml`. The engine (fetch/slim/vector/raster/site/
publish) is locked and deterministic; everything below is what only a human or
Claude can decide. The `layer.toml` you produce is the contract between them.

Work through the steps in order. Stop and ask the user only when a fact is
genuinely unavailable (e.g. no open data source exists, or the licence forbids
redistribution).

## 1. Find the data source (reuse first)

1. **Check the sibling registry first.** If
   `../ontario-address-changes/datasets/<slug>.toml` exists, copy its data-source
   block verbatim (`slug`, `provider`, `data_url`, `access`, `format`,
   `license_name`, `source_crs`, and `[fields]`). That registry is the single
   source of truth for Ontario data sources; do not re-derive what it already has.
2. **Otherwise discover it.** Search the municipality's open-data portal for an
   address-point dataset. Prefer, in order:
   - an **ArcGIS REST** FeatureServer/MapServer layer (`access = "arcgis"`),
   - a static **GeoJSON** download (`access = "static"`, `format = "geojson"`),
   - a **shapefile** export (`access = "static"`, `format = "shapefile"`; pulls
     in the `shapefile` extra: `pip install address-layerist[shapefile]`).
   For an ArcGIS layer, the `data_url` is the layer endpoint (no `/query`), e.g.
   `https://.../MapServer/15`. Probe `"<data_url>?f=json"` to confirm it is a
   point layer and read its field list.

## 2. Map the fields

Inspect a few sample features (ArcGIS: `"<data_url>/query?where=1=1&outFields=*&resultRecordCount=5&f=json"`).
Identify which **source** properties hold each canonical value and write them
under `[fields]` (canonical name -> SOURCE_PROPERTY):

- `number` -- the house/civic number (REQUIRED; the raster labeller needs it).
- `street` -- the full street name (incl. type/direction if combined).
- `unit`   -- unit/suite, if present.
- `full`   -- the full single-line address, if present.

Only `number` is strictly required. Components you don't map still ship inside
the vector tiles only if you add them to `[layer].mvt_extra`
(`SOURCE_PROP = "shortkey"`); otherwise they are dropped from the slim output.

## 3. Confirm size, licence, attribution

- **Count:** ArcGIS `"<data_url>/query?where=1=1&returnCountOnly=true&f=json"`.
  Sanity-check it's plausible for the place. (Optionally set
  `[layer].expected_min` as a floor; the engine already fails if slim keeps
  < 95% of fetched features.)
- **Licence:** find the open-data licence; set `license_name` and, if there is a
  licence page, `[layer].license_url`. If redistribution/derived tiles are not
  permitted, STOP and tell the user.
- **Attribution:** set `[layer].attribution` to a plain-ASCII string (it passes
  through the WSL shell), e.g. `(c) Town of Oakville, Open Government Licence`.
- **Dataset page:** set `[layer].dataset_page` to the human-facing source page.

## 4. Write layer.toml

Create `<city>-address-layer/layer.toml`. Keep the data-source block
byte-compatible with the ontario-address-changes registry; add a `[layer]` table:

```toml
slug = "oakville"
provider = "Town of Oakville"
data_url = "https://maps.oakville.ca/oakgis/rest/services/.../MapServer/15"
access = "arcgis"
format = "geojson"
license_name = "Open Government Licence - Town of Oakville"

[fields]
number = "STREET_NUM"
street = "SNAME"
unit   = "UNIT"
full   = "ADDRESS"

[layer]
title        = "Oakville Address Points"
github_repo  = "<account>/oakville-address-layer"
pages_url    = "https://<account>.github.io/oakville-address-layer"
dataset_page = "https://...open-data-page..."
attribution  = "(c) Town of Oakville, Open Government Licence"
# vector_minzoom/maxzoom, raster_zooms, raster_label_zooms, layer_name,
# wsl_distro, mvt_extra, expected_min all have sensible defaults -- only set to override.
```

Confirm `github_repo`/`pages_url` (the account) with the user if unknown.

## 5. Scaffold the city repo

A city repo is thin. Alongside `layer.toml`:
- `run.py` -> `from addresslayerist.cli import main; main()`
- `requirements.txt` -> `-e ../address-layerist` (or the git URL of the engine)
- `.gitignore` -> `data/`, `build/`, `logs/`, `__pycache__/`
- optional `assets/` for overrides + `iD.png`/`JOSM.png` screenshots
- optional `schedule-add.ps1` / `schedule-remove.ps1` for a daily task

## 6. Build, verify, screenshot

```
pip install -e ../address-layerist      # once
python run.py build                  # fetch + slim + vector + raster + site
```

Open `build/site/index.html`; confirm the city strings, the preview map centred
on the city, and the tile URLs. Add the vector + raster layers in iD/JOSM and
capture `iD.png` / `JOSM.png` into `assets/`, then rebuild the `site` step.

## 7. Publish (only when the user asks)

Needs a GitHub repo with an `origin` remote. `python run.py publish` force-pushes
`build/site/` to an orphan `gh-pages` branch; set Pages source to that branch.
Mind the **~1 GB per-site** GitHub Pages limit -- if a big city's raster pyramid
approaches it, trim `[layer].raster_zooms`.
