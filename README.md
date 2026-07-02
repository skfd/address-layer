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

- **Locked (this engine, deterministic):** registry/config load, slim (of an
  input GeoJSON), tile math, vector (tippecanoe via WSL), raster (Pillow
  labeller), site templating, publish (orphan gh-pages). The engine does **not**
  acquire data -- it slims whatever GeoJSON it is pointed at (see *Data input*).
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
pip install -e ../address-layerist      # once
addressvault pull <slug> --wait      # acquire the data (separate tool; not the engine)
python run.py build                  # slim + vector + raster + site
python run.py update                 # build + publish (daily entry point)
```

Individual steps: `slim vector raster site publish`. Run
`addresslayerist onboard` for onboarding guidance.

### Data input

The engine never downloads. `slim` reads, in order: `--input PATH`; else the
newest `<slug>-DATE.geojson` in `input_dir` (a `layer.toml` key); else the newest
such file in `$ADDRESSVAULT_DIR`. It treats that directory as a plain folder of
dated dumps -- it has no knowledge of `address-vault`. Whatever populates it (the
`addressvault pull <slug>` step above, a manual download, anything) is the
caller's concern, so the daily scheduled task is `addressvault pull <slug> --wait
&& python run.py update` (`--wait` coalesces onto an in-flight pull instead of
racing or erroring).

## Key locked-in rules

- **Slim/MVT schema is derived** from canonical `[fields]`
  (`number->housenumber`, `street->street`, `full->addr`, `unit->unit`,
  `name=housenumber` for iD), so raster/vector need no per-city code. Extra
  source props ship via `[layer].mvt_extra`.
- **Slim sanity is source-relative:** fail if fewer than 95% of the input features
  survive (no per-city magic count bounds).

## Requirements

- Python >= 3.11. Installs `Pillow`, `ijson` (see pyproject). The engine has no
  data-acquisition dependency.
- An input GeoJSON the engine can find (see *Data input*) -- e.g. `ADDRESSVAULT_DIR`
  set to a folder of `<slug>-DATE.geojson` dumps, or `--input PATH`.
- WSL2 + tippecanoe for the vector step -- see [wsl-setup.md](wsl-setup.md).

## Tests

```
python -m pytest          # tile math + slim property-map contract
```
