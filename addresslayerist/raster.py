"""Render address points into labelled raster (PNG) map tiles using Pillow.

Pure Python -- no native dependencies, runs the same on Windows and Linux.

Label placement is greedy with 20 candidate slots per point, in priority order:
  1) 4 inner slots hugging the dot (right, left, above, below) -- no leader.
  2) Outer ring at radius LEADER_R1, 8 compass directions -- with a leader line.
  3) Outer ring at radius LEADER_R2, same 8 directions -- with a leader line.
A leader is a thin line from the dot edge to the label-box edge.  Leader-line
bounding boxes are included in the collision check, so leaders won't cross
other labels.  If even the outer rings collide, the label is dropped.

Placement is run once globally per zoom so seam-straddling labels render in the
same slot in every tile they touch.

Street identity is conveyed by colour: hash(street_name) -> stable hue.  House
number labels and their leader lines use that colour.  In every tile, each
street that has at least STREET_LABEL_MIN_DOTS dots gets one floating street
name label placed in free space, in the same colour, so the dot and the name
are visually linked even when several streets meet at a corner.
"""

import hashlib
import json
import math
import os
from collections import defaultdict

from PIL import Image, ImageDraw, ImageFont

from .tilemath import TILE_SIZE, lonlat_to_pixel

DOT_COLOR = (224, 33, 138, 255)        # magenta -- visible over aerial imagery
DOT_RADIUS = 2
LABEL_COLOR = (0, 0, 0, 255)           # fallback when a point has no street
HALO_COLOR = (255, 255, 255, 235)
FONT_SIZE = 11
STROKE_WIDTH = 1                       # white halo width, in pixels
LABEL_GAP = 2                          # gap between the dot and the inner label
LEADER_WIDTH = 1
LEADER_R1 = 16.0                       # first fallback ring radius (px)
LEADER_R2 = 28.0                       # second fallback ring radius (px)

# Floating street-name labels (per tile, per street).
STREET_FONT_SIZE = 12
STREET_LABEL_MIN_DOTS = 2              # don't label streets with a lone dot
STREET_TILE_MARGIN = 2                 # keep the label fully inside the tile

# Accessibility-vetted palette.  Each entry passes WCAG AA (>=4.5:1 contrast)
# against the white halo, and the set is distinguishable under common forms
# of colour vision deficiency (no red/green or blue/indigo collisions).
# Vivid Material Design tones at L700/L800 -- bright but readable as text.
_PALETTE = (
    (194,  24,  91, 255),   # pink
    (123,  31, 162, 255),   # purple
    ( 25, 118, 210, 255),   # blue
    (  0, 121, 107, 255),   # teal
    ( 46, 125,  50, 255),   # green
    ( 93,  64,  55, 255),   # brown
    (211,  47,  47, 255),   # red
)
_FALLBACK_COLOR = (66, 66, 66, 255)    # neutral grey when street is missing

_SQRT_HALF = math.sqrt(0.5)
# 8 compass directions for outer rings: E, W, N, S, NE, SE, NW, SW.
_RING_DIRS = (
    (1.0, 0.0), (-1.0, 0.0), (0.0, -1.0), (0.0, 1.0),
    (_SQRT_HALF, -_SQRT_HALF), (_SQRT_HALF, _SQRT_HALF),
    (-_SQRT_HALF, -_SQRT_HALF), (-_SQRT_HALF, _SQRT_HALF),
)

# Spatial-hash cell size for collision lookups.
_GRID_CELL = 64

_index_cache = {}


def _street_index(name):
    """Stable preferred palette index for a street name."""
    cached = _index_cache.get(name)
    if cached is not None:
        return cached
    h = int.from_bytes(hashlib.md5(name.encode("utf-8")).digest()[:4], "big")
    idx = h % len(_PALETTE)
    _index_cache[name] = idx
    return idx


def _assign_tile_colors(streets):
    """Map each street in this tile to a unique palette colour.

    Each street's preferred index is its hash mod len(_PALETTE).  When two
    streets in the same tile prefer the same slot, the one with the higher
    md5 hash keeps the slot and the other shifts to the next free slot.
    Cross-tile consistency: a street that never collides stays one colour
    everywhere; one that does, shifts only in tiles where the collision
    actually occurs.
    """
    # Higher md5 wins -- deterministic and independent of iteration order.
    ordered = sorted(
        (s for s in streets if s),
        key=lambda s: hashlib.md5(s.encode("utf-8")).digest(),
        reverse=True,
    )
    used = set()
    result = {}
    for st in ordered:
        preferred = _street_index(st)
        for offset in range(len(_PALETTE)):
            idx = (preferred + offset) % len(_PALETTE)
            if idx not in used:
                result[st] = _PALETTE[idx]
                used.add(idx)
                break
        else:
            # More streets in tile than palette slots -- fall back to preferred.
            result[st] = _PALETTE[preferred]
    return result


def _color_of(color_map, name):
    """Look up the tile-local colour for a street, with grey fallback."""
    if not name:
        return _FALLBACK_COLOR
    return color_map.get(name, _FALLBACK_COLOR)


def build_raster(cfg):
    """Render PNG tiles for every zoom in cfg.raster_zooms.

    Returns a dict {zoom: tile_count}.
    """
    slim_path = cfg.slim_path
    if not os.path.isfile(slim_path):
        raise RuntimeError(f"Slim GeoJSONL not found: {slim_path}. Run 'slim' first.")
    font = ImageFont.truetype(cfg.asset(os.path.join("font", "DejaVuSans.ttf")), FONT_SIZE)
    street_font = ImageFont.truetype(
        cfg.asset(os.path.join("font", "DejaVuSans-Bold.ttf")), STREET_FONT_SIZE
    )
    label_zooms = set(cfg.raster_label_zooms)
    return {z: _render_zoom(cfg, slim_path, z, font, street_font, label_zooms)
            for z in cfg.raster_zooms}


def _render_zoom(cfg, slim_path, zoom, font, street_font, label_zooms):
    label = zoom in label_zooms
    print(f"Raster z{zoom}: reading points ...")
    points = _read_points(slim_path, zoom)

    if label:
        print(f"Raster z{zoom}: placing {len(points):,} labels ...")
        placements, stats = _place_labels(points, font)
        print(f"Raster z{zoom}: placed inner={stats['inner']:,} "
              f"leadered={stats['leadered']:,} dropped={stats['dropped']:,} "
              f"of {len(points):,}")
    else:
        placements = [None] * len(points)

    print(f"Raster z{zoom}: bucketing into tiles ...")
    tiles = defaultdict(list)
    for (gx, gy, hn, st), placement in zip(points, placements):
        _bucket_point(tiles, gx, gy, hn, st, placement, font)

    out_dir = os.path.join(cfg.raster_tile_dir, str(zoom))
    print(f"Raster z{zoom}: rendering {len(tiles):,} tiles (labels={label}) ...")

    made_dirs = set()
    for (tx, ty), entries in tiles.items():
        img = _render_tile(entries, font, street_font, draw_street=label)
        tdir = os.path.join(out_dir, str(tx))
        if tdir not in made_dirs:
            os.makedirs(tdir, exist_ok=True)
            made_dirs.add(tdir)
        img.save(os.path.join(tdir, f"{ty}.png"), optimize=True)
    return len(tiles)


def _read_points(slim_path, zoom):
    """Return [(gx, gy, housenumber, street), ...] in zoom-level pixels."""
    points = []
    with open(slim_path, encoding="utf-8") as f:
        for line in f:
            feat = json.loads(line)
            lon, lat = feat["geometry"]["coordinates"]
            props = feat["properties"]
            hn = props.get("housenumber", "")
            st = props.get("street", "")
            gx, gy = lonlat_to_pixel(lon, lat, zoom)
            points.append((gx, gy, hn, st))
    return points


def _place_labels(points, font):
    """Greedy multi-slot placement against a spatial hash.

    Returns (placements, stats).  Each placement is None (dropped) or a
    (anchor, dx, dy, leader) tuple where (dx, dy) is the offset of the text
    anchor point from the dot centre and ``leader`` says whether to draw a
    connecting line.
    """
    width_cache = {}

    def text_w(t):
        w = width_cache.get(t)
        if w is None:
            w = font.getlength(t)
            width_cache[t] = w
        return w

    grid = defaultdict(list)

    def cells(x0, y0, x1, y1):
        cx0, cx1 = int(x0 // _GRID_CELL), int(x1 // _GRID_CELL)
        cy0, cy1 = int(y0 // _GRID_CELL), int(y1 // _GRID_CELL)
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                yield (cx, cy)

    def collides(box):
        x0, y0, x1, y1 = box
        seen = set()
        for key in cells(x0, y0, x1, y1):
            if key in seen:
                continue
            seen.add(key)
            for ox0, oy0, ox1, oy1 in grid.get(key, ()):
                if x0 < ox1 and x1 > ox0 and y0 < oy1 and y1 > oy0:
                    return True
        return False

    def add(box):
        for key in cells(*box):
            grid[key].append(box)

    placements = [None] * len(points)
    stats = {"inner": 0, "leadered": 0, "dropped": 0}
    order = sorted(range(len(points)), key=lambda i: (points[i][1], points[i][0]))
    for i in order:
        gx, gy, hn, _st = points[i]
        if not hn:
            continue
        w = text_w(hn)
        for placement in _candidate_placements():
            box = _placement_footprint(placement, gx, gy, w)
            if not collides(box):
                add(box)
                placements[i] = placement
                if placement[3]:
                    stats["leadered"] += 1
                else:
                    stats["inner"] += 1
                break
        else:
            stats["dropped"] += 1
    return placements, stats


def _candidate_placements():
    r = DOT_RADIUS + LABEL_GAP
    yield ("lm",  r, 0.0, False)
    yield ("rm", -r, 0.0, False)
    yield ("mb", 0.0, -r, False)
    yield ("mt", 0.0,  r, False)
    for radius in (LEADER_R1, LEADER_R2):
        for ux, uy in _RING_DIRS:
            yield ("mm", radius * ux, radius * uy, True)


def _anchor_bbox(anchor, ax, ay, w, h):
    if anchor == "lm":
        return (ax, ay - h / 2, ax + w, ay + h / 2)
    if anchor == "rm":
        return (ax - w, ay - h / 2, ax, ay + h / 2)
    if anchor == "mb":
        return (ax - w / 2, ay - h, ax + w / 2, ay)
    if anchor == "mt":
        return (ax - w / 2, ay, ax + w / 2, ay + h)
    return (ax - w / 2, ay - h / 2, ax + w / 2, ay + h / 2)  # "mm"


def _leader_endpoints(gx, gy, label_bb):
    cx = (label_bb[0] + label_bb[2]) / 2
    cy = (label_bb[1] + label_bb[3]) / 2
    dx, dy = cx - gx, cy - gy
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    start = (gx + DOT_RADIUS * ux, gy + DOT_RADIUS * uy)
    x0, y0, x1, y1 = label_bb
    ts = []
    if dx:
        for bx in (x0, x1):
            t = (bx - gx) / dx
            y = gy + t * dy
            if t > 0 and y0 - 0.5 <= y <= y1 + 0.5:
                ts.append(t)
    if dy:
        for by in (y0, y1):
            t = (by - gy) / dy
            x = gx + t * dx
            if t > 0 and x0 - 0.5 <= x <= x1 + 0.5:
                ts.append(t)
    end = (gx + min(ts) * dx, gy + min(ts) * dy) if ts else (cx, cy)
    return start, end


def _placement_footprint(placement, gx, gy, w):
    anchor, dx, dy, leader = placement
    ax, ay = gx + dx, gy + dy
    label_bb = _anchor_bbox(anchor, ax, ay, w, FONT_SIZE)
    x0, y0, x1, y1 = label_bb
    if leader:
        (lx0, ly0), (lx1, ly1) = _leader_endpoints(gx, gy, label_bb)
        x0 = min(x0, lx0, lx1)
        x1 = max(x1, lx0, lx1)
        y0 = min(y0, ly0, ly1)
        y1 = max(y1, ly0, ly1)
    pad = STROKE_WIDTH
    return (x0 - pad, y0 - pad, x1 + pad, y1 + pad)


def _bucket_point(tiles, gx, gy, hn, st, placement, font):
    half = DOT_RADIUS + STROKE_WIDTH
    x0, y0, x1, y1 = gx - half, gy - half, gx + half, gy + half
    if placement is not None and hn:
        bx0, by0, bx1, by1 = _placement_footprint(
            placement, gx, gy, font.getlength(hn)
        )
        x0, y0 = min(x0, bx0), min(y0, by0)
        x1, y1 = max(x1, bx1), max(y1, by1)
    tx0, tx1 = int(x0 // TILE_SIZE), int(x1 // TILE_SIZE)
    ty0, ty1 = int(y0 // TILE_SIZE), int(y1 // TILE_SIZE)
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            tiles[(tx, ty)].append(
                (gx - tx * TILE_SIZE, gy - ty * TILE_SIZE, hn, st, placement)
            )


def _render_tile(entries, font, street_font, draw_street):
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color_map = _assign_tile_colors({st for _, _, _, st, _ in entries})
    occupied = []  # bboxes (x0, y0, x1, y1) that floating street labels avoid

    # Leader lines first so dots cover their endpoints cleanly.
    for ox, oy, hn, st, placement in entries:
        if placement is None or not hn or not placement[3]:
            continue
        anchor, dx, dy, _ = placement
        ax, ay = ox + dx, oy + dy
        label_bb = _anchor_bbox(anchor, ax, ay, font.getlength(hn), FONT_SIZE)
        (sx, sy), (ex, ey) = _leader_endpoints(ox, oy, label_bb)
        draw.line([(sx, sy), (ex, ey)],
                  fill=_color_of(color_map, st), width=LEADER_WIDTH)

    # Dots (magenta -- unchanged so the visual field stays calm).
    for ox, oy, _, _, _ in entries:
        draw.ellipse(
            [ox - DOT_RADIUS, oy - DOT_RADIUS, ox + DOT_RADIUS, oy + DOT_RADIUS],
            fill=DOT_COLOR,
        )
        occupied.append((ox - DOT_RADIUS, oy - DOT_RADIUS,
                         ox + DOT_RADIUS, oy + DOT_RADIUS))

    # House number labels -- tinted by street.
    for ox, oy, hn, st, placement in entries:
        if placement is None or not hn:
            continue
        anchor, dx, dy, _ = placement
        ax, ay = ox + dx, oy + dy
        draw.text(
            (ax, ay), hn, font=font, fill=_color_of(color_map, st),
            stroke_width=STROKE_WIDTH, stroke_fill=HALO_COLOR, anchor=anchor,
        )
        bb = _anchor_bbox(anchor, ax, ay, font.getlength(hn), FONT_SIZE)
        occupied.append((bb[0] - STROKE_WIDTH, bb[1] - STROKE_WIDTH,
                         bb[2] + STROKE_WIDTH, bb[3] + STROKE_WIDTH))

    if draw_street:
        _draw_street_labels(draw, entries, street_font, occupied, color_map)

    return img


def _draw_street_labels(draw, entries, street_font, occupied, color_map):
    """Place one floating street-name label per street per tile, in free space.

    Streets with fewer than STREET_LABEL_MIN_DOTS dots in this tile are
    skipped (likely just bucket-spillover from a neighbour).  If no free
    spot fits, the street is skipped here; the same name will be tried
    again in adjacent tiles.
    """
    # Group by street, but only count dots whose centre is inside the tile so
    # we don't promote spillover entries.
    by_street = defaultdict(list)
    for ox, oy, _hn, st, _pl in entries:
        if not st:
            continue
        if 0 <= ox < TILE_SIZE and 0 <= oy < TILE_SIZE:
            by_street[st].append((ox, oy))

    # Largest streets first -- they're the ones the user most wants oriented.
    for st, dots in sorted(by_street.items(), key=lambda kv: -len(kv[1])):
        if len(dots) < STREET_LABEL_MIN_DOTS:
            continue
        w = street_font.getlength(st)
        h = STREET_FONT_SIZE
        cx = sum(d[0] for d in dots) / len(dots)
        cy = sum(d[1] for d in dots) / len(dots)
        for ax, ay in _street_candidates(cx, cy, w, h):
            bb = (ax - w / 2 - STROKE_WIDTH, ay - h / 2 - STROKE_WIDTH,
                  ax + w / 2 + STROKE_WIDTH, ay + h / 2 + STROKE_WIDTH)
            if _bbox_collides(bb, occupied):
                continue
            draw.text(
                (ax, ay), st, font=street_font, fill=_color_of(color_map, st),
                stroke_width=STROKE_WIDTH, stroke_fill=HALO_COLOR, anchor="mm",
            )
            occupied.append(bb)
            break
        # If nothing fits: silently skip.  The dot colour still identifies it.


def _street_candidates(cx, cy, w, h):
    """Yield (ax, ay) anchor points spiralling out from the dots' centroid.

    Anchor is the label centre (anchor="mm").  Points are clamped so the label
    bbox stays inside the tile with STREET_TILE_MARGIN.
    """
    min_x = w / 2 + STROKE_WIDTH + STREET_TILE_MARGIN
    max_x = TILE_SIZE - w / 2 - STROKE_WIDTH - STREET_TILE_MARGIN
    min_y = h / 2 + STROKE_WIDTH + STREET_TILE_MARGIN
    max_y = TILE_SIZE - h / 2 - STROKE_WIDTH - STREET_TILE_MARGIN
    if min_x > max_x or min_y > max_y:
        return  # label too wide to ever fit in a tile
    seen = set()

    def clamp(x, y):
        return (max(min_x, min(max_x, x)), max(min_y, min(max_y, y)))

    def emit(x, y):
        key = (round(x), round(y))
        if key in seen:
            return None
        seen.add(key)
        return (x, y)

    # Centroid first.
    p = emit(*clamp(cx, cy))
    if p:
        yield p
    # Spiral outwards in 8 directions.
    for radius in (24, 48, 72, 100):
        for ux, uy in _RING_DIRS:
            p = emit(*clamp(cx + radius * ux, cy + radius * uy))
            if p:
                yield p


def _bbox_collides(box, others):
    x0, y0, x1, y1 = box
    for ox0, oy0, ox1, oy1 in others:
        if x0 < ox1 and x1 > ox0 and y0 < oy1 and y1 > oy0:
            return True
    return False
