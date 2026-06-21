"""Fetch a static file (geojson or shapefile, optionally zipped) -> GeoJSON (4326).

Adapted from ontario-address-changes, plus a HEAD smart-cache (from the Toronto
layer's download.py): when the remote's Last-Modified/Content-Length match the
last download, reuse the existing dated file instead of downloading again.

pyshp/pyproj are imported lazily, so a city using plain geojson never needs them.
"""

import glob
import json
import os
import zipfile
from datetime import date

import requests

TIMEOUT = 300


def _int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _download(url, dest):
    """Stream ``url`` to ``dest``; return its response headers of interest."""
    with requests.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 18):
                f.write(chunk)
        return {"last_modified": r.headers.get("Last-Modified"),
                "content_length": _int(r.headers.get("Content-Length"))}


def _head(url):
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        r.raise_for_status()
        return {"last_modified": r.headers.get("Last-Modified"),
                "content_length": _int(r.headers.get("Content-Length"))}
    except requests.RequestException as e:
        print(f"  (HEAD check failed, will download: {e})")
        return {}


def _load_sidecar(cfg):
    if os.path.isfile(cfg.last_download_path):
        with open(cfg.last_download_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_sidecar(cfg, headers, filename):
    with open(cfg.last_download_path, "w", encoding="utf-8") as f:
        json.dump({**headers, "filename": filename}, f, indent=2)


def _cached_if_unchanged(cfg):
    sc = _load_sidecar(cfg)
    if not sc:
        return None
    remote = _head(cfg.data_url)
    if not remote:
        return None
    same = (remote.get("last_modified") == sc.get("last_modified")
            and remote.get("content_length") == sc.get("content_length"))
    path = os.path.join(cfg.data_dir, sc.get("filename", ""))
    return path if same and os.path.isfile(path) else None


def _unzip(path, dest_dir):
    with zipfile.ZipFile(path) as z:
        z.extractall(dest_dir)


def _read_geojson(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("features", [])


def _read_shapefile(shp_path):
    """Read a point shapefile, reprojecting to EPSG:4326 using its .prj."""
    import shapefile  # pyshp
    from pyproj import CRS, Transformer

    prj_path = shp_path[:-4] + ".prj"
    transformer = None
    if os.path.exists(prj_path):
        with open(prj_path, encoding="utf-8", errors="replace") as f:
            crs = CRS.from_wkt(f.read())
        if crs.to_epsg() != 4326:
            transformer = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)

    reader = shapefile.Reader(shp_path)
    field_names = [f[0] for f in reader.fields[1:]]  # drop DeletionFlag
    feats = []
    for sr in reader.iterShapeRecords():
        pts = sr.shape.points
        if not pts:
            continue
        x, y = pts[0]
        if transformer:
            x, y = transformer.transform(x, y)
        props = dict(zip(field_names, sr.record))
        feats.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [x, y]},
        })
    return feats


def _locate(work_dir, pattern):
    hits = glob.glob(os.path.join(work_dir, "**", pattern), recursive=True)
    if not hits:
        raise FileNotFoundError(f"no {pattern} found in {work_dir}")
    return hits[0]


def fetch(cfg, force=False):
    os.makedirs(cfg.data_dir, exist_ok=True)
    if not force:
        cached = _cached_if_unchanged(cfg)
        if cached:
            print(f"  using cached {os.path.basename(cached)} (remote unchanged)")
            return cached, _read_geojson(cached)

    filename = f"{cfg.slug}-{date.today().isoformat()}.geojson"
    filepath = os.path.join(cfg.data_dir, filename)

    work = os.path.join(cfg.data_dir, "_download")
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, "download.bin")
    print(f"  downloading {cfg.data_url}")
    headers = _download(cfg.data_url, raw)

    is_zip = zipfile.is_zipfile(raw)
    if is_zip:
        _unzip(raw, work)

    if cfg.format == "shapefile":
        shp = _locate(work, "*.shp")
        print(f"  reading shapefile {os.path.basename(shp)}")
        features = _read_shapefile(shp)
    else:  # geojson
        if is_zip:
            try:
                src = _locate(work, "*.geojson")
            except FileNotFoundError:
                src = _locate(work, "*.json")
        else:
            src = raw
        features = _read_geojson(src)

    print(f"  parsed {len(features):,} features")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)
    _save_sidecar(cfg, headers, filename)
    return filepath, features
