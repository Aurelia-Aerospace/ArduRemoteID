#!/usr/bin/env python3
"""
gen_all_cases.py — Read zones.bin and emit all_cases.dat for test_flight_checker.

Each line: lat lon bypass_mask_hex tag
  lat/lon  : inside point (verified inside the zone)
  mask     : OPTIONS bits — bypass ALL categories EXCEPT the one being tested
  tag      : expected substring in is_flying_allowed() result

Run:  python3 gen_all_cases.py [path/to/zones.bin]
Output: all_cases.dat  (same directory as this script)
"""

import struct, math, sys
from pathlib import Path
from collections import defaultdict

SCRIPT_DIR = Path(__file__).parent
BIN_PATH   = Path(sys.argv[1]) if len(sys.argv) > 1 else \
             SCRIPT_DIR / "../spiffs/zones.bin"
OUT_PATH   = SCRIPT_DIR / "all_cases.dat"

# ── OPTIONS bypass bits (must match parameters.h) ────────────────────────────
OPT = {
    "airport_l":   1 << 3,
    "airport_m":   1 << 4,
    "airport_s":   1 << 5,
    "seaplane":    1 << 6,
    "heliport":    1 << 7,
    "balloon":     1 << 8,
    "faa_b":       1 << 9,
    "faa_c":       1 << 10,
    "faa_d":       1 << 11,
    "eu_ctr":      1 << 12,
    "eu_atz":      1 << 13,
    "eu_r":        1 << 14,
    "eu_tma":      1 << 15,
    "eu_p":        1 << 16,
    "prison":      1 << 17,
    "stadium":     1 << 18,
    "country":     1 << 19,
    "military":    1 << 22,
}
ALL_MASK = sum(OPT.values())

# cat number → (cat_name, result_tag)
CAT = {
     0: ("airport_l", "APT_L"),
     1: ("airport_m", "APT_M"),
     2: ("airport_s", "APT_S"),
     3: ("seaplane",  "APT_SEA"),
     4: ("heliport",  "APT_HEL"),
     5: ("balloon",   "APT_BAL"),
     6: ("faa_b",     "FAA_B"),
     7: ("faa_c",     "FAA_C"),
     8: ("faa_d",     "FAA_D"),
     9: ("eu_ctr",    "EU_CTR"),
    10: ("eu_atz",    "EU_ATZ"),
    11: ("eu_r",      "EU_R"),
    12: ("eu_tma",    "EU_TMA"),
    13: ("eu_p",      "EU_P"),
    14: ("prison",    "PRISON"),
    15: ("stadium",   "STADIUM"),
    16: ("military",  "MZ"),
}

M_PER_DEG = 111320.0

# ── Geometry helpers ──────────────────────────────────────────────────────────
def cos_lat(lat): return max(math.cos(math.radians(lat)), 0.001)

def inside_circle(clat, clon, radius_m):
    """Return a point known to be inside the circle."""
    pt_lat = clat + (radius_m * 0.3) / M_PER_DEG
    pt_lon = clon
    dy = (pt_lat - clat) * M_PER_DEG
    dx = (pt_lon - clon) * M_PER_DEG * cos_lat(clat)
    return (pt_lat, pt_lon) if (dy*dy + dx*dx) <= radius_m**2 else None

def inside_poly_deltas(clat, clon, deltas):
    """Centroid of polygon vertices; verify with firmware-exact meter-space ray-casting."""
    n = len(deltas)
    py = sum(dy for dy, dx in deltas) / n * 10.0  # mean delta, meters
    px = sum(dx for dy, dx in deltas) / n * 10.0
    if not _fw_ray_cast(py, px, deltas):
        return None
    coslat = cos_lat(clat)
    return (clat + py / M_PER_DEG, clon + px / (M_PER_DEG * coslat))

def inside_poly_raw(pts_deg):
    """Centroid of raw (lat,lon) vertex list; verify with degree-space ray-casting."""
    mean_lat = sum(p[0] for p in pts_deg) / len(pts_deg)
    mean_lon = sum(p[1] for p in pts_deg) / len(pts_deg)
    return (mean_lat, mean_lon) if _ray_cast(mean_lat, mean_lon, pts_deg) else None

def _fw_ray_cast(py, px, deltas):
    """Firmware-exact meter-space ray-casting (matches check_polygon_deltas in C++)."""
    n = len(deltas)
    crossings = 0
    for i in range(n):
        j = (i + 1) % n
        y1, x1 = deltas[i][0] * 10.0, deltas[i][1] * 10.0
        y2, x2 = deltas[j][0] * 10.0, deltas[j][1] * 10.0
        if (y1 > py) != (y2 > py):
            xi = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
            if px < xi:
                crossings += 1
    return (crossings & 1) == 1

def _ray_cast(plat, plon, verts):
    inside = False
    n = len(verts)
    j = n - 1
    for i in range(n):
        yi, xi = verts[i]
        yj, xj = verts[j]
        if ((yi > plat) != (yj > plat)) and \
           (plon < (xj - xi) * (plat - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside

# ── Parse tiled zones (cats 0-15) ─────────────────────────────────────────────
def parse_tiled(raw, data_off, n_tiles):
    """Return dict: zone_id -> (clat, clon, shape_info) — deduplicated."""
    seen = {}
    for ti in range(n_tiles):
        _, _, _, tile_off = struct.unpack_from('<bbHI', raw, 16 + ti*8)
        off = data_off + tile_off
        n_rec = struct.unpack_from('<H', raw, off)[0]; off += 2
        for _ in range(n_rec):
            zid, shape = struct.unpack_from('<IB', raw, off)
            if zid in seen:
                if shape == 0:
                    off += struct.calcsize('<IBHiiH')
                else:
                    _, _, _, n_pts, _, _ = struct.unpack_from('<IBHBii', raw, off)
                    off += struct.calcsize('<IBHBii') + n_pts * 4
                continue
            if shape == 0:
                fmt = '<IBHiiH'
                zid2, _, floor_m, clat_i, clon_i, radius = struct.unpack_from(fmt, raw, off)
                off += struct.calcsize(fmt)
                if floor_m == 0:  # skip elevated-floor zones (firmware skips at alt=0)
                    seen[zid] = ('circle', clat_i*1e-5, clon_i*1e-5, radius)
            else:
                hfmt = '<IBHBii'
                zid2, _, floor_m, n_pts, clat_i, clon_i = struct.unpack_from(hfmt, raw, off)
                off += struct.calcsize(hfmt)
                flat = struct.unpack_from('<' + 'hh'*n_pts, raw, off)
                off += n_pts * 4
                if floor_m == 0:
                    deltas = [(flat[k], flat[k+1]) for k in range(0, len(flat), 2)]
                    seen[zid] = ('poly', clat_i*1e-5, clon_i*1e-5, deltas)
    return seen

# ── Parse country flat section ────────────────────────────────────────────────
def parse_countries(raw, data_off, n_tiles):
    """Find country section (after tile data) and parse polygons."""
    # Scan past all tile data to find country section offset
    max_off = data_off
    for ti in range(n_tiles):
        _, _, _, tile_off = struct.unpack_from('<bbHI', raw, 16 + ti*8)
        off = data_off + tile_off
        n_rec = struct.unpack_from('<H', raw, off)[0]; off += 2
        for _ in range(n_rec):
            _, shape = struct.unpack_from('<IB', raw, off)
            if shape == 0:
                off += struct.calcsize('<IBHiiH')
            else:
                _, _, _, n_pts, _, _ = struct.unpack_from('<IBHBii', raw, off)
                off += struct.calcsize('<IBHBii') + n_pts * 4
            max_off = max(max_off, off)

    country_off = max_off
    if country_off + 2 > len(raw):
        return []
    n_countries = struct.unpack_from('<H', raw, country_off)[0]
    off = country_off + 2
    polys = []
    for _ in range(n_countries):
        if off + 2 > len(raw): break
        n_pts = struct.unpack_from('<H', raw, off)[0]; off += 2
        pts = []
        for _ in range(n_pts):
            lat5, lon5 = struct.unpack_from('<ii', raw, off); off += 8
            pts.append((lat5*1e-5, lon5*1e-5))
        polys.append(pts)
    return polys

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    with open(BIN_PATH, 'rb') as f:
        raw = f.read()

    magic, ver, tile_deg_b, _, n_tiles, _, data_off = struct.unpack_from('<IHBBHHI', raw, 0)
    tile_deg = tile_deg_b if tile_deg_b > 0 else 4
    if ver != 3:
        raise ValueError(f"Unexpected zones.bin version {ver}")

    zones = parse_tiled(raw, data_off, n_tiles)
    countries = parse_countries(raw, data_off, n_tiles)

    lines = []
    stats = defaultdict(lambda: [0, 0])  # cat -> [kept, skipped]

    for zid, info in zones.items():
        cat = zid >> 27
        if cat not in CAT:
            continue
        cat_name, tag = CAT[cat]
        bypass = ALL_MASK & ~OPT[cat_name]

        shape = info[0]
        if shape == 'circle':
            _, clat, clon, radius = info
            pt = inside_circle(clat, clon, radius)
        else:
            _, clat, clon, deltas = info
            pt = inside_poly_deltas(clat, clon, deltas)

        if pt is None:
            stats[cat][1] += 1
            continue

        stats[cat][0] += 1
        lines.append(f"{pt[0]:.6f} {pt[1]:.6f} 0x{bypass:08X} {tag}")

    # Countries
    bypass_country = ALL_MASK & ~OPT["country"]
    for poly in countries:
        if len(poly) < 3:
            continue
        pt = inside_poly_raw(poly)
        if pt is None:
            stats["country"][1] += 1
            continue
        stats["country"][0] += 1
        lines.append(f"{pt[0]:.6f} {pt[1]:.6f} 0x{bypass_country:08X} COUNTRY")

    # ── Clear zones: points in empty tiles, not inside any country ───────────
    existing_tiles = set()
    for ti in range(n_tiles):
        lt, ln, _, _ = struct.unpack_from('<bbHI', raw, 16 + ti*8)
        existing_tiles.add((lt, ln))

    clear_lines = []
    for lt in range(-60 // tile_deg, 72 // tile_deg + 1):
        for ln in range(-180 // tile_deg, 180 // tile_deg):
            if (lt, ln) in existing_tiles:
                continue
            clat = lt * tile_deg + tile_deg / 2.0
            clon = ln * tile_deg + tile_deg / 2.0
            if any(_ray_cast(clat, clon, poly) for poly in countries if len(poly) >= 3):
                continue
            clear_lines.append(f"{clat:.6f} {clon:.6f} 0x00000000 OK")
            if len(clear_lines) >= 300:
                break
        if len(clear_lines) >= 300:
            break

    with open(OUT_PATH, 'w') as f:
        f.write('\n'.join(lines + clear_lines) + '\n')

    total_kept = sum(v[0] for v in stats.values())
    total_skip = sum(v[1] for v in stats.values())
    print(f"Generated {OUT_PATH}")
    print(f"  {total_kept} blocked cases  ({total_skip} skipped — centroid outside polygon)")
    print(f"  {len(clear_lines)} clear (OK) cases")
    for k, (kept, skipped) in sorted(stats.items(), key=lambda x: str(x[0])):
        name = CAT.get(k, ("?","?"))[0] if isinstance(k, int) else k
        print(f"  {str(k):3} ({name:12}): {kept:6d} kept, {skipped:4d} skipped")

if __name__ == "__main__":
    main()
