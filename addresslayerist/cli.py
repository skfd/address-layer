"""CLI for the address-layerist engine. Run from a city repo that has a layer.toml.

    addresslayerist fetch     # fetch latest address GeoJSON (arcgis or static)
    addresslayerist slim      # stream it into a slim GeoJSONL + meta
    addresslayerist vector    # build vector (MVT) tiles via WSL tippecanoe
    addresslayerist raster    # build labelled raster (PNG) tiles
    addresslayerist site      # render the landing page
    addresslayerist publish   # force-push build/site to gh-pages
    addresslayerist build     # fetch + slim + vector + raster + site
    addresslayerist update    # build + publish (the daily entry point)
    addresslayerist onboard   # how to add a new city (prints guidance)

Raw address data is fetched from and stored in address-vault (the central tiered
store), not pulled here. Set ADDRESSVAULT_DIR to the vault folder: 'fetch' pulls
the latest dump into the vault, the build steps read it back. Inspect or restore
archived days with the 'addressvault' CLI.
"""

import argparse

from addresslayerist import config as _config
from addresslayerist.slim import slim as _slim
from addresslayerist.vector import build_vector
from addresslayerist.raster import build_raster
from addresslayerist.site import build_site
from addresslayerist.publish import publish as _publish


def _banner(text):
    print(f"\n=== {text} ===")


def _vault(cfg):
    """A Vault handle with this city's source registered from its layer.toml.

    The data-source keys are byte-compatible, so the engine seeds the vault from
    the same layer.toml it already loads -- no separate registration step."""
    from addressvault import Source, Vault
    v = Vault()  # uses ADDRESSVAULT_DIR
    v.add_source(Source(
        slug=cfg.slug, provider=cfg.provider, data_url=cfg.data_url,
        access=cfg.access, format=cfg.format, source_crs=cfg.source_crs,
        fields=cfg.fields, license_name=cfg.license_name,
    ))
    return v


def _latest_geojson(cfg):
    """Hot path to the latest vault snapshot, thawing it if it has gone cold."""
    from addressvault import Archived
    v = _vault(cfg)
    try:
        return v.path(cfg.slug, "latest")
    except Archived:
        v.thaw(cfg.slug, v.snapshot(cfg.slug, "latest").date)
        return v.path(cfg.slug, "latest")
    except LookupError:
        raise SystemExit(f"No vault data for {cfg.slug}. Run 'fetch' first.")


def cmd_fetch(cfg, args):
    _banner("Fetch")
    snap = _vault(cfg).pull(cfg.slug, force=args.force)
    print(f"  {snap.features:,} features -> vault {cfg.slug} {snap.date}")


def cmd_slim(cfg, args):
    _banner("Slim")
    _slim(cfg, _latest_geojson(cfg))


def cmd_vector(cfg, args):
    _banner("Vector tiles")
    build_vector(cfg)


def cmd_raster(cfg, args):
    _banner("Raster tiles")
    counts = build_raster(cfg)
    for zoom, n in sorted(counts.items()):
        print(f"  z{zoom}: {n:,} tiles")
        if n == 0:
            raise RuntimeError(f"Raster zoom {zoom} produced no tiles.")


def cmd_site(cfg, args):
    _banner("Site")
    build_site(cfg)


def cmd_publish(cfg, args):
    _banner("Publish")
    _publish(cfg)


def cmd_build(cfg, args):
    cmd_fetch(cfg, args)
    cmd_slim(cfg, args)
    cmd_vector(cfg, args)
    cmd_raster(cfg, args)
    cmd_site(cfg, args)


def cmd_update(cfg, args):
    cmd_build(cfg, args)
    cmd_publish(cfg, args)


COMMANDS = {
    "fetch": (cmd_fetch, "Fetch the latest address GeoJSON (arcgis or static)"),
    "slim": (cmd_slim, "Stream it into a slim GeoJSONL + meta"),
    "vector": (cmd_vector, "Build vector (MVT) tiles via WSL tippecanoe"),
    "raster": (cmd_raster, "Build labelled raster (PNG) tiles"),
    "site": (cmd_site, "Render the landing page"),
    "publish": (cmd_publish, "Force-push build/site to the gh-pages branch"),
    "build": (cmd_build, "fetch + slim + vector + raster + site"),
    "update": (cmd_update, "build + publish (daily scheduled-task entry point)"),
}

ONBOARD_HELP = """\
Onboarding a new city is a Claude Code task, not a script. See the skill:

  skills/onboard-city/SKILL.md   (in the address-layerist engine repo)

It walks through: find the data source (reuse
ontario-address-changes/datasets/<slug>.toml if it exists), map which source
fields are number/street/unit/full, probe the feature count, set license +
attribution + dataset page, write layer.toml, run a build, and capture iD/JOSM
screenshots.
"""


def main():
    parser = argparse.ArgumentParser(
        prog="addresslayerist", description="Address tile-layer builder"
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("onboard", help="How to onboard a new city (prints guidance)")
    for name, (_, help_text) in COMMANDS.items():
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "-c", "--config", default="layer.toml",
            help="Path to the city config (default: layer.toml)",
        )
        if name in ("fetch", "build", "update"):
            p.add_argument(
                "--force", action="store_true",
                help="Re-fetch even if the remote is unchanged",
            )

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return
    if args.command == "onboard":
        print(ONBOARD_HELP)
        return
    if not hasattr(args, "force"):
        args.force = False

    cfg = _config.load(getattr(args, "config", "layer.toml"))
    COMMANDS[args.command][0](cfg, args)


if __name__ == "__main__":
    main()
