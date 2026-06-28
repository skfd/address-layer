"""Load a per-city ``layer.toml`` into a Config object.

The working directory is the city repo (data/, build/ and any asset overrides
live there). Engine default assets live inside this package; a city overrides
one by dropping a file of the same name in its own ``assets/``.

The data-source keys (slug/provider/data_url/access/format/license_name/
source_crs/[fields]) are intentionally byte-compatible with
``ontario-address-changes/datasets/<slug>.toml`` so a config can be lifted from
that registry. Layer-only settings live under a ``[layer]`` table.
"""

import os
import tomllib
from dataclasses import dataclass, field

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_ASSETS_DIR = os.path.join(PACKAGE_DIR, "assets")

_REQUIRED = ("slug", "provider", "data_url", "access", "format")
_VALID_ACCESS = ("arcgis", "static")
_VALID_FORMAT = ("geojson", "shapefile")


@dataclass
class Config:
    # --- data source (shared shape with ontario-address-changes) ---
    slug: str
    provider: str
    data_url: str
    access: str
    format: str
    license_name: str = ""
    source_crs: str = ""                 # e.g. "EPSG:2952"; reproject to WGS84
    fields: dict = field(default_factory=dict)   # canonical -> source property

    # --- layer-only ([layer] table) ---
    title: str = ""
    github_repo: str = ""
    pages_url: str = ""
    dataset_page: str = ""
    license_url: str = ""
    attribution: str = ""
    changes_url: str = ""                 # optional sibling change-tracker site
    head_extra: str = ""                  # raw HTML injected before </head> (e.g. analytics)
    layer_name: str = "addresses"
    wsl_distro: str = "Ubuntu"
    vector_minzoom: int = 12
    vector_maxzoom: int = 19
    raster_zooms: list = field(default_factory=lambda: [16, 17, 18, 19])
    raster_label_zooms: list = field(default_factory=lambda: [17, 18, 19])
    mvt_extra: dict = field(default_factory=dict)  # extra source prop -> short key
    expected_min: int = 0                # optional absolute floor for slim count

    project_dir: str = field(default_factory=os.getcwd)

    # --- derived paths (all under the city repo) ---
    @property
    def data_dir(self):
        return os.path.join(self.project_dir, "data")

    @property
    def build_dir(self):
        return os.path.join(self.project_dir, "build")

    @property
    def site_dir(self):
        return os.path.join(self.build_dir, "site")

    @property
    def logs_dir(self):
        return os.path.join(self.project_dir, "logs")

    @property
    def override_assets_dir(self):
        return os.path.join(self.project_dir, "assets")

    @property
    def mbtiles_path(self):
        return os.path.join(self.build_dir, f"{self.slug}.mbtiles")

    @property
    def slim_path(self):
        return os.path.join(self.data_dir, f"{self.slug}-slim.geojsonl")

    @property
    def meta_path(self):
        return os.path.join(self.data_dir, f"{self.slug}-meta.json")

    @property
    def vector_tile_dir(self):
        return os.path.join(self.site_dir, "tiles", "vector")

    @property
    def raster_tile_dir(self):
        return os.path.join(self.site_dir, "tiles", "raster")

    @property
    def title_or_default(self):
        return self.title or f"{self.provider} Address Points"

    def asset(self, name):
        """Path to an asset, preferring a city override in ./assets/."""
        override = os.path.join(self.override_assets_dir, name)
        if os.path.isfile(override):
            return override
        return os.path.join(ENGINE_ASSETS_DIR, name)


def load(path="layer.toml", project_dir=None):
    """Parse and validate a city config. Raises SystemExit with a clear message."""
    project_dir = os.path.abspath(project_dir or os.getcwd())
    cfg_path = path if os.path.isabs(path) else os.path.join(project_dir, path)
    if not os.path.isfile(cfg_path):
        raise SystemExit(
            f"No config file: {cfg_path}. Run from a city repo containing a "
            f"layer.toml (see 'addresslayerist onboard')."
        )
    with open(cfg_path, "rb") as f:
        raw = tomllib.load(f)

    missing = [k for k in _REQUIRED if not raw.get(k)]
    if missing:
        raise SystemExit(f"{cfg_path}: missing required keys: {missing}")
    if raw["access"] not in _VALID_ACCESS:
        raise SystemExit(f"{cfg_path}: access must be one of {_VALID_ACCESS}")
    if raw["format"] not in _VALID_FORMAT:
        raise SystemExit(f"{cfg_path}: format must be one of {_VALID_FORMAT}")

    layer = raw.get("layer", {})
    return Config(
        slug=raw["slug"],
        provider=raw["provider"],
        data_url=raw["data_url"],
        access=raw["access"],
        format=raw["format"],
        license_name=raw.get("license_name", ""),
        source_crs=raw.get("source_crs", ""),
        fields=raw.get("fields", {}),
        title=layer.get("title", ""),
        github_repo=layer.get("github_repo", ""),
        pages_url=layer.get("pages_url", ""),
        dataset_page=layer.get("dataset_page", ""),
        license_url=layer.get("license_url", ""),
        attribution=layer.get("attribution", ""),
        changes_url=layer.get("changes_url", ""),
        head_extra=layer.get("head_extra", ""),
        layer_name=layer.get("layer_name", "addresses"),
        wsl_distro=layer.get("wsl_distro", "Ubuntu"),
        vector_minzoom=layer.get("vector_minzoom", 12),
        vector_maxzoom=layer.get("vector_maxzoom", 19),
        raster_zooms=layer.get("raster_zooms", [16, 17, 18, 19]),
        raster_label_zooms=layer.get("raster_label_zooms", [17, 18, 19]),
        mvt_extra=layer.get("mvt_extra", {}),
        expected_min=layer.get("expected_min", 0),
        project_dir=project_dir,
    )
