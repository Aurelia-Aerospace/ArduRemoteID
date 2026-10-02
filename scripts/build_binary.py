#!/usr/bin/env python3
"""
Build zones.bin from data/filtered/zones_all.json → spiffs/zones.bin

Run merge_zones.py first to generate zones_all.json.

Record layout (little-endian, packed):
  Circle:  zone_id(u32) shape=0(u8) floor_m(u16) lat(i32) lon(i32) radius(u16)   17 bytes
  Polygon: zone_id(u32) shape=1(u8) floor_m(u16) n_pts(u8) clat(i32) clon(i32)   16+4·n bytes
           [dy(i16) dx(i16)] × n_pts   — units: 10 m from centroid
  floor_m=0 → ground-level restriction (blocks arming)
  floor_m>0 → altitude floor in metres (blocks flight at/above that altitude)

Tile index: 4°×4° tiles, binary-searchable by (lat_tile, lon_tile).

Country section (flat, appended after tile data — not tiled):
  n_polygons(u16)
  Per polygon: n_pts(u16) [lat5(i32) lon5(i32)] × n_pts   ← absolute coords, closed ring
"""
import json, math, struct, zlib
from collections import defaultdict
from io import BytesIO
from pathlib import Path

HERE      = Path(__file__).parent
RM        = HERE.parent / "RemoteIDModule"
ZONES_ALL = RM / "data" / "filtered" / "zones_all.json"
OUT       = RM / "spiffs" / "zones.bin"

MAGIC    = 0x5A4F4E45
VERSION  = 3  # bumped: category encoding expanded to 5 bits (zone_id >> 27)
TILE_DEG = 3

CAT_NUM = {
    "airport_l":  0, "airport_m": 1, "airport_s":  2,
    "seaplane":   3, "heliport":  4, "balloonport": 5,
    "faa_b":      6, "faa_c":     7, "faa_d":       8,
    "eu_ctr":     9, "eu_atz":   10, "eu_r":        11,
    "eu_tma":    12, "eu_p":     13,
    "prison":    14, "stadium":  15,
    "military":  16,
    # "country": 17  → flat country section, not tiled
}

# Max polygon points per record
_mp = {c: 8 for c in range(6)}  # airports: 8 pts
_mp[16] = 48                     # military: 48 pts
MAX_PTS = defaultdict(lambda: 24, _mp)


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker simplification in degree space."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom  = math.hypot(dx, dy) or 1
    max_d, idx = 0, 0
    for i, (px, py) in enumerate(pts[1:-1], 1):
        d = abs(dy * px - dx * py + bx * ay - by * ax) / denom
        if d > max_d:
            max_d, idx = d, i
    if max_d > eps:
        return _rdp(pts[:idx+1], eps)[:-1] + _rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]

def _simplify(pts, max_n):
    if len(pts) <= max_n:
        return pts
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    clat = sum(lats) / len(lats)
    diag = math.hypot((max(lats)-min(lats))*111320,
                      (max(lons)-min(lons))*111320*math.cos(math.radians(clat))) or 1
    eps = diag * 0.005 / 111320
    simplified = _rdp(pts, eps)
    if len(simplified) < 4:
        step = max(1, len(pts) // max_n)
        simplified = pts[::step]
    if len(simplified) > max_n:
        step = math.ceil(len(simplified) / max_n)
        simplified = simplified[::step][:max_n]
    return simplified


def _crc27(s):
    return zlib.crc32(s.encode()) & 0x07FFFFFF

def make_id(cat, key):
    return (cat << 27) | _crc27(key)

def _tiles(lat_min, lat_max, lon_min, lon_max):
    t0l = int(math.floor(lat_min / TILE_DEG))
    t1l = int(math.floor(lat_max / TILE_DEG))
    t0n = int(math.floor(lon_min / TILE_DEG))
    t1n = int(math.floor(lon_max / TILE_DEG))
    return [(tl, tn) for tl in range(t0l, t1l + 1) for tn in range(t0n, t1n + 1)]

def _bbox_pts(pts):
    lats = [p[0] / 1e5 for p in pts]
    lons = [p[1] / 1e5 for p in pts]
    return min(lats), max(lats), min(lons), max(lons)

def _bbox_circle(lat, lon, r_m):
    dr  = r_m / 111320
    mx  = max(math.cos(math.radians(lat)), 0.001)
    return lat - dr, lat + dr, lon - r_m/(111320*mx), lon + r_m/(111320*mx)

def enc_circle(zid, floor_m, lat, lon, r_m):
    return struct.pack('<IBHiiH', zid, 0, floor_m,
                      round(lat * 1e5), round(lon * 1e5),
                      min(65535, max(0, round(r_m))))

def enc_polygon(zid, floor_m, pts, max_pts):
    """pts = [(lat, lon), ...] in degrees."""
    if len(pts) > max_pts:
        pts = _simplify(pts, max_pts)
    n    = len(pts)
    clat = sum(p[0] for p in pts) / n
    clon = sum(p[1] for p in pts) / n
    mx   = math.cos(math.radians(clat)) or 0.001
    deltas = []
    for lat, lon in pts:
        dy = round((lat - clat) * 111320 / 10)
        dx = round((lon - clon) * 111320 * mx / 10)
        deltas += [max(-32768, min(32767, dy)),
                   max(-32768, min(32767, dx))]
    return struct.pack('<IBHBii' + 'h' * len(deltas),
                      zid, 1, floor_m, n, round(clat * 1e5), round(clon * 1e5), *deltas)


def collect_zones(zones):
    recs   = []
    counts = defaultdict(int)
    for z in zones:
        cat_str = z["cat"]
        cat = CAT_NUM.get(cat_str)
        if cat is None:
            continue  # "country" goes to flat section
        zid     = make_id(cat, z["id"])
        mp      = MAX_PTS[cat]
        floor_m = min(65535, max(0, int(z.get("floor", 0))))
        for shape in z["shapes"]:
            if shape["type"] == "circle":
                lat = shape["c"][0] / 1e5
                lon = shape["c"][1] / 1e5
                r   = shape["r"]
                recs.append((*_bbox_circle(lat, lon, r), enc_circle(zid, floor_m, lat, lon, r)))
            else:
                pts = [(p[0] / 1e5, p[1] / 1e5) for p in shape["pts"]]
                recs.append((*_bbox_pts(shape["pts"]), enc_polygon(zid, floor_m, pts, mp)))
        counts[cat_str] += 1
    for cat_str, cnt in sorted(counts.items()):
        print(f"  {cat_str:<14} {cnt:>7}")
    return recs


def collect_countries(zones):
    polys = [z for z in zones if z["cat"] == "country"]
    if not polys:
        return b''
    buf = struct.pack('<H', len(polys))
    for z in polys:
        for shape in z["shapes"]:
            pts = shape["pts"]
            if pts[0] != pts[-1]:
                pts = pts + [pts[0]]
            buf += struct.pack('<H', len(pts))
            for lat5, lon5 in pts:
                buf += struct.pack('<ii', lat5, lon5)
    total_pts = sum(len(s["pts"]) for z in polys for s in z["shapes"])
    print(f"  {'country':<14} {len(polys):>7} polygons, {total_pts} pts → {len(buf)//1024} KB")
    return buf


def main():
    print("=== Building zones.bin ===")
    zones          = json.loads(ZONES_ALL.read_text())
    recs           = collect_zones(zones)
    country_section = collect_countries(zones)

    buckets = defaultdict(list)
    for lat_min, lat_max, lon_min, lon_max, rec_bytes in recs:
        for t in _tiles(lat_min, lat_max, lon_min, lon_max):
            buckets[t].append(rec_bytes)

    sorted_tiles = sorted(buckets.keys())
    n_tiles      = len(sorted_tiles)
    data_offset  = 16 + n_tiles * 8

    tile_buf = BytesIO()
    offsets  = {}
    for t in sorted_tiles:
        offsets[t] = tile_buf.tell()
        entries    = buckets[t]
        tile_buf.write(struct.pack('<H', len(entries)))
        for e in entries:
            tile_buf.write(e)

    tile_data  = tile_buf.getvalue()
    total_size = data_offset + len(tile_data) + len(country_section)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, 'wb') as f:
        f.write(struct.pack('<IHBBHHI',
                            MAGIC, VERSION, TILE_DEG, 0,
                            n_tiles, 0, data_offset))
        for t in sorted_tiles:
            f.write(struct.pack('<bbHI', t[0], t[1], 0, offsets[t]))
        f.write(tile_data)
        f.write(country_section)

    n_tile_refs = sum(len(v) for v in buckets.values())
    print(f"\n  {len(recs)} records  →  {n_tile_refs} tile refs  across {n_tiles} tiles")
    print(f"  + country section: {len(country_section)//1024} KB")
    print(f"  → {OUT}  ({total_size // 1024} KB)")
    assert total_size < 4 * 1024 * 1024, f"OVERFLOW: {total_size//1024} KB > 4096 KB"


if __name__ == "__main__":
    main()
