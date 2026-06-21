"""Build vector (MVT) tiles by driving tippecanoe inside WSL.

tippecanoe has no native Windows build, so this shells out to ``wsl.exe``.
See wsl-setup.md for the one-time WSL + tippecanoe install.
"""

import os
import shutil
import subprocess


def build_vector(cfg):
    """Run tippecanoe + tile-join -> build/site/tiles/vector/{z}/{x}/{y}.pbf.

    Returns the number of .pbf files produced.
    """
    slim_path = cfg.slim_path
    if not os.path.isfile(slim_path):
        raise RuntimeError(f"Slim GeoJSONL not found: {slim_path}. Run 'slim' first.")
    os.makedirs(cfg.build_dir, exist_ok=True)

    # tile-join writes thousands of small files; doing that on the WSL filesystem
    # and copying the tree out afterwards is far faster than writing onto /mnt/c.
    wsl_pbf_dir = f"/tmp/{cfg.slug}-vector-tiles"
    slim_wsl = win_to_wsl(slim_path)
    mbtiles_wsl = win_to_wsl(cfg.mbtiles_path)
    attribution = cfg.attribution or f"(c) {cfg.provider}"

    tippecanoe = (
        f"tippecanoe -o '{mbtiles_wsl}' "
        f"-Z{cfg.vector_minzoom} -z{cfg.vector_maxzoom} "
        f"--no-tile-size-limit --no-feature-limit "
        f"-l {cfg.layer_name} -n '{cfg.title_or_default}' "
        f"-A '{attribution}' --force '{slim_wsl}'"
    )
    print("Running tippecanoe ...")
    stderr = _wsl(cfg, tippecanoe)
    dropped = [ln for ln in stderr.splitlines() if "dropping" in ln.lower()]
    if dropped:
        print("WARNING: tippecanoe reported dropped features:")
        for line in dropped:
            print(f"  {line}")

    print("Exploding mbtiles to a pbf directory ...")
    _wsl(
        cfg,
        f"rm -rf '{wsl_pbf_dir}' && "
        f"tile-join -e '{wsl_pbf_dir}' --no-tile-compression '{mbtiles_wsl}'"
    )

    if os.path.isdir(cfg.vector_tile_dir):
        shutil.rmtree(cfg.vector_tile_dir)
    os.makedirs(cfg.vector_tile_dir, exist_ok=True)
    print("Copying tiles from WSL to the build output ...")
    _wsl(cfg, f"cp -r '{wsl_pbf_dir}/.' '{win_to_wsl(cfg.vector_tile_dir)}/'")

    pbf_count = sum(
        1
        for _, _, files in os.walk(cfg.vector_tile_dir)
        for name in files
        if name.endswith(".pbf")
    )
    print(f"Vector tiles: {pbf_count:,} .pbf files in {cfg.vector_tile_dir}")
    if pbf_count == 0:
        raise RuntimeError("tippecanoe produced no vector tiles.")
    return pbf_count


def win_to_wsl(path):
    """Convert a Windows path to its /mnt/<drive> WSL equivalent."""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return f"/mnt/{drive.rstrip(':').lower()}{rest.replace(chr(92), '/')}"


def _wsl(cfg, command):
    """Run a bash command inside WSL. Returns stderr; raises on failure."""
    result = subprocess.run(
        ["wsl", "-d", cfg.wsl_distro, "bash", "-lc", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        print(result.stderr.rstrip())
        raise RuntimeError(
            f"WSL command failed (exit {result.returncode}). "
            f"Is WSL + tippecanoe set up? See wsl-setup.md."
        )
    return result.stderr or ""
