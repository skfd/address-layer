"""Fetch dispatch: pick the access path declared by the city config.

Both paths return ``(filepath, features)`` and write a date-named
``data/<slug>-YYYY-MM-DD.geojson`` (WGS84).
"""

from . import arcgis, static


def fetch(cfg, force=False):
    if cfg.access == "arcgis":
        return arcgis.fetch(cfg, force=force)
    if cfg.access == "static":
        return static.fetch(cfg, force=force)
    raise ValueError(f"unknown access: {cfg.access!r}")
