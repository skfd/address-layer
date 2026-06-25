"""CLI for the address-layerist engine. Run from a city repo that has a layer.toml.

    addresslayerist fetch     # fetch latest address GeoJSON (arcgis or static)
    addresslayerist slim      # stream it into a slim GeoJSONL + meta
    addresslayerist vector    # build vector (MVT) tiles via WSL tippecanoe
    addresslayerist raster    # build labelled raster (PNG) tiles
    addresslayerist site      # render the landing page
    addresslayerist publish   # force-push build/site to gh-pages
    addresslayerist build     # fetch + slim + vector + raster + site
    addresslayerist update    # build + publish (the daily entry point)
    addresslayerist cache ls|restore <slug> [date]   # shared-cache archive
    addresslayerist onboard   # how to add a new city (prints guidance)

Set ADDRESSLAYERIST_CACHE to a shared folder to dedupe downloads across sibling
city repos (and the ontario-address-changes tracker): the first job per source
per day downloads, the rest reuse it. Snapshots older than 2 days are then moved
into a restic archive (kept forever, restorable via 'cache restore').
"""

import argparse
import os
import re
import sys

from addresslayerist import cache as _cache
from addresslayerist import config as _config
from addresslayerist.fetch import fetch as _fetch
from addresslayerist.slim import slim as _slim
from addresslayerist.vector import build_vector
from addresslayerist.raster import build_raster
from addresslayerist.site import build_site
from addresslayerist.publish import publish as _publish


def _banner(text):
    print(f"\n=== {text} ===")


def _latest_geojson(cfg):
    if not os.path.isdir(cfg.download_dir):
        raise SystemExit("No download dir. Run 'fetch' first.")
    files = sorted(
        f for f in os.listdir(cfg.download_dir)
        if f.startswith(f"{cfg.slug}-") and f.endswith(".geojson")
        and re.search(r"\d{4}-\d{2}-\d{2}", f)
    )
    if not files:
        raise SystemExit("No address GeoJSON in download dir. Run 'fetch' first.")
    return os.path.join(cfg.download_dir, files[-1])


def cmd_fetch(cfg, args):
    _banner("Fetch")
    path, count = _fetch(cfg, force=args.force)
    print(f"  {count:,} features -> {path}")
    _cache.sweep(cfg.download_dir)  # archive snapshots >2 days old (shared cache only)


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


def cmd_cache(cfg, args):
    _banner("Cache")
    if args.action == "ls":
        dates = _cache.list_archived(cfg.download_dir, args.slug)
        if not dates:
            print(f"  no archived snapshots for {args.slug}")
        for d in dates:
            print(f"  {args.slug} {d}")
    else:  # restore
        if not args.date:
            raise SystemExit("restore needs a date: cache restore <slug> <YYYY-MM-DD>")
        path = _cache.restore(cfg.download_dir, args.slug, args.date)
        print(f"  restored -> {path}")


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

    pc = sub.add_parser("cache", help="Inspect/restore the shared download archive")
    pc.add_argument("-c", "--config", default="layer.toml",
                    help="Path to the city config (default: layer.toml)")
    pc.add_argument("action", choices=["ls", "restore"], help="ls or restore")
    pc.add_argument("slug", help="City slug (the shared cache holds many)")
    pc.add_argument("date", nargs="?", help="YYYY-MM-DD (required for restore)")

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
    if args.command == "cache":
        cmd_cache(cfg, args)
        return
    COMMANDS[args.command][0](cfg, args)


if __name__ == "__main__":
    main()
