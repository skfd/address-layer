# address-layerist

A reusable engine that turns any municipal **address-point** dataset into map
tiles for OpenStreetMap editors:

- **Vector tiles** (MVT) -- interactive in iD; click a point for its address tags.
- **Raster tiles** (PNG) -- house numbers drawn as text; a readable JOSM backdrop.
- A **landing page** with copy-paste "add this layer" instructions, published to
  GitHub Pages.

It generalizes [`toronto-addresses-layer`](../toronto-addresses-layer) and shares
its data-acquisition design with
[`ontario-address-changes`](../ontario-address-changes). Each city is a thin repo
(e.g. `oakville-address-layer`) that depends on this engine and carries one
`layer.toml`. Per-city repos (not one monorepo) because a single published site
can approach GitHub Pages' ~1 GB limit (Toronto alone is ~1 GB; raster is ~94%).

## Locked vs fuzzy

- **Locked (this engine, deterministic):** registry/config load, fetch (pulls the
  latest snapshot from `address-vault`, which owns the `arcgis`/`static`
  acquisition + reproject and the restic archive), slim, tile math, vector
  (tippecanoe via WSL), raster (Pillow labeller), site templating, publish
  (orphan gh-pages).
- **Fuzzy (a Claude Code skill):** onboarding a new city -- find the source, map
  number/street/unit/full, set licence/attribution, write `layer.toml`. See
  [`skills/onboard-city/SKILL.md`](skills/onboard-city/SKILL.md).

The `layer.toml` is the contract between the two halves. The data-source keys are
byte-compatible with `ontario-address-changes/datasets/<slug>.toml`, so a config
can be lifted from that registry.

## How a city repo uses it

```
oakville-address-layer/
  layer.toml            # the one per-city config (see the skill)
  run.py                # from addresslayerist.cli import main; main()
  requirements.txt      # -e ../address-layerist
  assets/               # optional overrides + iD.png / JOSM.png
```

```
pip install -e ../address-layerist      # once (add [shapefile] for shapefile sources)
python run.py build                  # fetch + slim + vector + raster + site
python run.py update                 # build + publish (daily entry point)
```

Individual steps: `fetch slim vector raster site publish`. Run
`addresslayerist onboard` for onboarding guidance.

## Key locked-in rules

- **Slim/MVT schema is derived** from canonical `[fields]`
  (`number->housenumber`, `street->street`, `full->addr`, `unit->unit`,
  `name=housenumber` for iD), so raster/vector need no per-city code. Extra
  source props ship via `[layer].mvt_extra`.
- **Slim sanity is source-relative:** fail if fewer than 95% of fetched features
  survive (no per-city magic count bounds).
- **Fetch dispatches on `access`** (`arcgis` | `static`); nothing else changes
  per city.

## Requirements

- Python >= 3.11. Installs `addressvault`, `Pillow`, `ijson` (see pyproject);
  shapefile/zip sources and reprojection are handled inside `address-vault`.
- `ADDRESSVAULT_DIR` set to the vault folder -- raw address dumps are fetched into
  and read from `address-vault`, not stored in the city repo.
- WSL2 + tippecanoe for the vector step -- see [wsl-setup.md](wsl-setup.md).

## Tests

```
python -m pytest          # tile math + slim property-map contract
```
