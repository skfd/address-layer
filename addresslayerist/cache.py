"""Cold-tier archive for the shared download cache (opt-in via ADDRESSLAYERIST_CACHE).

Dated snapshots older than ``keep_days`` are moved into a restic repo -- chunk
dedup means near-identical daily address dumps cost almost nothing to keep
forever -- and then dropped from the hot cache. ``restore`` brings any archived
day back to full size on demand.

Everything here is best-effort: if restic is missing or its repo is busy,
archiving is skipped with a warning and the next daily run retries. A build never
fails because of the archive tier.
"""

import json
import os
import re
import secrets
import shutil
import subprocess
from datetime import date, datetime, timedelta

_DATED = re.compile(r"^(?P<slug>.+)-(?P<date>\d{4}-\d{2}-\d{2})\.geojson$")


def _restic():
    return shutil.which("restic")


def _repo_dir(cache_dir):
    return os.environ.get("RESTIC_REPOSITORY") or os.path.join(cache_dir, "restic")


def _env(cache_dir):
    """restic env: repo + a password file kept next to the cache (local dedup,
    not an encryption-at-rest boundary). Returns (env, repo_dir, pass_file)."""
    repo = _repo_dir(cache_dir)
    pf = os.path.join(cache_dir, "restic.pass")
    return {**os.environ, "RESTIC_REPOSITORY": repo, "RESTIC_PASSWORD_FILE": pf}, repo, pf


def _run(args, env):
    return subprocess.run(["restic", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


def _initialized(repo):
    return os.path.exists(os.path.join(repo, "config"))


def _ensure_repo(cache_dir):
    """Create the password file and init the repo if needed; return env or None."""
    env, repo, pf = _env(cache_dir)
    if not os.path.exists(pf):
        os.makedirs(os.path.dirname(pf), exist_ok=True)
        with open(pf, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(16))
    if not _initialized(repo):
        r = _run(["init"], env)
        if not _initialized(repo):  # tolerate a concurrent init that won the race
            print(f"  [archive] restic init failed: {r.stderr.strip()}")
            return None
    return env


def sweep(cache_dir, keep_days=2, today=None):
    """Archive dated snapshots older than keep_days, then drop them from the cache.

    No-op unless the shared cache is in use; best-effort if restic is unavailable.
    """
    if not os.environ.get("ADDRESSLAYERIST_CACHE"):
        return  # archiving is a feature of the shared cache only
    if not _restic():
        print("  [archive] restic not found; leaving old snapshots uncompressed")
        return

    today = today or date.today()
    cutoff = today - timedelta(days=keep_days)
    stale = []
    for name in os.listdir(cache_dir):
        m = _DATED.match(name)
        if not m:
            continue
        try:
            d = datetime.strptime(m["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if d <= cutoff:
            stale.append((name, m["slug"], m["date"]))
    if not stale:
        return

    env = _ensure_repo(cache_dir)
    if env is None:
        return
    for name, slug, d in sorted(stale):
        path = os.path.join(cache_dir, name)
        r = _run(["backup", path, "--tag", f"slug={slug},date={d},addresslayerist"], env)
        if r.returncode == 0:
            os.remove(path)
            print(f"  [archive] {name} -> restic (removed from cache)")
        else:
            tail = (r.stderr.strip().splitlines() or [str(r.returncode)])[-1]
            print(f"  [archive] backup failed for {name}, kept on disk: {tail}")


def list_archived(cache_dir, slug):
    """Return the sorted archived dates for a slug (empty if no repo yet)."""
    if not _restic():
        raise SystemExit("restic not found.")
    env, repo, _ = _env(cache_dir)
    if not _initialized(repo):
        return []
    r = _run(["snapshots", "--tag", f"slug={slug}", "--json"], env)
    if r.returncode != 0:
        raise SystemExit(f"restic snapshots failed: {r.stderr.strip()}")
    dates = set()
    for s in json.loads(r.stdout or "[]"):
        for t in s.get("tags", []):
            if t.startswith("date="):
                dates.add(t[len("date="):])
    return sorted(dates)


def restore(cache_dir, slug, d):
    """Bring <slug>-<d>.geojson back into the hot cache from the archive.

    Uses ``restic dump`` (stream the one file to the target) rather than
    ``restic restore`` -- the latter recreates the original absolute path and
    trips over Windows timestamp permissions on the synthesised parent dirs.
    """
    if not _restic():
        raise SystemExit("restic not found.")
    env, repo, _ = _env(cache_dir)
    if not _initialized(repo):
        raise SystemExit("No archive repo yet.")
    name = f"{slug}-{d}.geojson"

    # Find the file's stored path inside the matching snapshot.
    r = _run(["ls", "latest", "--tag", f"slug={slug},date={d}", "--json"], env)
    if r.returncode != 0:
        raise SystemExit(f"restic ls failed: {r.stderr.strip()}")
    stored = None
    for line in r.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "file" and obj.get("path", "").replace("\\", "/").endswith(name):
            stored = obj["path"]
            break
    if not stored:
        raise SystemExit(f"archived snapshot for {slug} {d} not found")

    os.makedirs(cache_dir, exist_ok=True)
    target = os.path.join(cache_dir, name)
    tmp = target + ".tmp"
    with open(tmp, "wb") as out:
        r = subprocess.run(["restic", "dump", "latest", "--tag", f"slug={slug},date={d}",
                            stored], stdout=out, stderr=subprocess.PIPE, env=env)
    if r.returncode != 0:
        os.remove(tmp)
        raise SystemExit(f"restic dump failed: {r.stderr.decode(errors='replace').strip()}")
    os.replace(tmp, target)
    return target
