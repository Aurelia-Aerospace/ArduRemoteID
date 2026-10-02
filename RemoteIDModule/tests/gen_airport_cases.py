#!/usr/bin/env python3
"""
gen_airport_cases.py — Read zones.bin (VERSION=2) and emit valid C++ airport test cases.

Output to stdout:
  Section A: AP() macro lines for all 6 airport types (sorted by type)
  =====
  Section B: boundary-test struct lines, one per type
"""

import struct, math, sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
BIN_PATH = "/home/mauriciodiaz/Projects/aurelia_ArduremoteID/RemoteIDModule/spiffs/zones.bin"

# zone_id >> 28  ->  (type_int, type_name, min_km)
CAT_INFO = {
    0: (0, "LARGE_AIRPORT",       10.15),
    1: (1, "MEDIUM_AIRPORT",       5.00),
    2: (2, "SMALL_AIRPORT",        3.00),
    4: (3, "HELIPORT",             4.50),
    3: (4, "SEAPLANE_BASE",        5.00),
    5: (5, "HOTAIR_BALLOON_BASE",  5.00),
}
TARGET_CATS   = set(CAT_INFO.keys())
MAX_PER_CAT   = 15          # for cats other than seaplane
MAX_SEAPLANE  = 200         # take all seaplane (only 74 unique in dataset)

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
M_PER_DEG_LAT = 111320.0

def cos_lat(lat_deg):
    return math.cos(math.radians(lat_deg))

def check_circle(clat, clon, radius_m, pt_lat, pt_lon):
    """Return True if (pt_lat,pt_lon) is strictly inside circle."""
    dlat = (pt_lat - clat) * M_PER_DEG_LAT
    dlon = (pt_lon - clon) * M_PER_DEG_LAT * cos_lat(clat)
    return math.sqrt(dlat * dlat + dlon * dlon) < radius_m

def check_polygon_deltas(clat, clon, deltas, pt_lat, pt_lon):
    """
    deltas: list of (dy, dx) int16 values (delta * 10.0 => metres from centroid).
    Ray-casting algorithm: cast ray east from pt and count crossings.
    """
    verts = []
    coslat = cos_lat(clat)
    for dy, dx in deltas:
        vy = clat + (dy * 10.0) / M_PER_DEG_LAT
        vx = clon + (dx * 10.0) / (M_PER_DEG_LAT * coslat)
        verts.append((vy, vx))

    n = len(verts)
    inside = False
    pLat, pLon = pt_lat, pt_lon
    j = n - 1
    for i in range(n):
        yi, xi = verts[i]
        yj, xj = verts[j]
        if ((yi > pLat) != (yj > pLat)) and \
           (pLon < (xj - xi) * (pLat - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside

# ---------------------------------------------------------------------------
# Parse binary — deduplicate by zone_id, track first tile encountered
# ---------------------------------------------------------------------------
def parse_zones_bin(path):
    """
    Returns dict:  cat -> list of unique zone dicts (deduplicated by zone_id).
    Each zone dict has keys: zone_id, shape, floor_m, clat, clon, tile_key,
      and either: radius_m   (circle)
      or:         deltas     (polygon, list of (dy,dx))
    Only zones with floor_m == 0 and cat in TARGET_CATS are kept.
    """
    with open(path, "rb") as f:
        raw = f.read()

    magic, ver, tile_deg, _pad, n_tiles, _pad2, data_offset = \
        struct.unpack_from("<IHBBHHI", raw, 0)

    if magic != 0x5A4F4E45 or ver != 2:
        raise ValueError(f"Unexpected header: magic=0x{magic:08X} ver={ver}")

    # zone_id -> zone dict  (first encounter wins)
    seen_ids = {}

    for ti in range(n_tiles):
        hdr_off = 16 + ti * 8
        lat_tile, lon_tile, _dummy, tile_off = struct.unpack_from("<bbHI", raw, hdr_off)
        tile_key = (lat_tile, lon_tile)

        abs_off = data_offset + tile_off
        n_rec = struct.unpack_from("<H", raw, abs_off)[0]
        abs_off += 2

        for _ in range(n_rec):
            zone_id, shape = struct.unpack_from("<IB", raw, abs_off)
            cat = zone_id >> 28

            if shape == 0:   # circle
                fmt = "<IBHiiH"
                sz  = struct.calcsize(fmt)
                zone_id, shape, floor_m, clat_i, clon_i, radius = \
                    struct.unpack_from(fmt, raw, abs_off)
                abs_off += sz
                if cat in TARGET_CATS and floor_m == 0 and zone_id not in seen_ids:
                    z = {
                        "zone_id":  zone_id,
                        "shape":    0,
                        "floor_m":  floor_m,
                        "clat":     clat_i * 1e-5,
                        "clon":     clon_i * 1e-5,
                        "radius_m": radius,
                        "tile_key": tile_key,
                    }
                    seen_ids[zone_id] = z
            else:            # polygon
                hdr_fmt = "<IBHBii"
                hdr_sz  = struct.calcsize(hdr_fmt)
                zone_id2, shape, floor_m, n_pts, clat_i, clon_i = \
                    struct.unpack_from(hdr_fmt, raw, abs_off)
                abs_off += hdr_sz
                pt_fmt = "<" + "hh" * n_pts
                pt_sz  = struct.calcsize(pt_fmt)
                pt_flat = struct.unpack_from(pt_fmt, raw, abs_off)
                abs_off += pt_sz
                deltas = [(pt_flat[k], pt_flat[k + 1]) for k in range(0, len(pt_flat), 2)]
                if cat in TARGET_CATS and floor_m == 0 and zone_id not in seen_ids:
                    z = {
                        "zone_id":  zone_id,
                        "shape":    1,
                        "floor_m":  floor_m,
                        "clat":     clat_i * 1e-5,
                        "clon":     clon_i * 1e-5,
                        "deltas":   deltas,
                        "tile_key": tile_key,
                    }
                    seen_ids[zone_id] = z

    # Group by cat
    zones_by_cat = defaultdict(list)
    for z in seen_ids.values():
        cat = z["zone_id"] >> 28
        zones_by_cat[cat].append(z)

    return zones_by_cat

# ---------------------------------------------------------------------------
# Select diverse samples (spread across tiles, round-robin)
# ---------------------------------------------------------------------------
def diverse_sample(zones, max_count):
    """
    Pick up to max_count zones, preferring geographic diversity via tile
    round-robin.
    """
    by_tile = defaultdict(list)
    for z in zones:
        by_tile[z["tile_key"]].append(z)

    tile_lists = list(by_tile.values())
    result = []
    indices = [0] * len(tile_lists)
    while len(result) < max_count:
        added = False
        for ti, tl in enumerate(tile_lists):
            if indices[ti] < len(tl):
                result.append(tl[indices[ti]])
                indices[ti] += 1
                added = True
                if len(result) >= max_count:
                    break
        if not added:
            break
    return result

# ---------------------------------------------------------------------------
# Compute in_point and verify it is actually inside the zone
# ---------------------------------------------------------------------------
def make_test_case(z):
    """
    Returns (ap_lat, ap_lon, in_lat, in_lon, out_lat, out_lon) or None if
    the in_point verification fails.
    """
    clat = z["clat"]
    clon = z["clon"]
    out_lat = clat + 0.5
    out_lon = clon

    if z["shape"] == 0:  # circle
        radius_m = z["radius_m"]
        # 30% of radius north of centre
        in_lat = clat + (radius_m * 0.3) / M_PER_DEG_LAT
        in_lon = clon
        if not check_circle(clat, clon, radius_m, in_lat, in_lon):
            return None
    else:                # polygon
        deltas = z["deltas"]
        mean_dy = sum(d[0] for d in deltas) / len(deltas)
        mean_dx = sum(d[1] for d in deltas) / len(deltas)
        in_lat = clat + (mean_dy * 10.0) / M_PER_DEG_LAT
        in_lon = clon + (mean_dx * 10.0) / (M_PER_DEG_LAT * cos_lat(clat))
        if not check_polygon_deltas(clat, clon, deltas, in_lat, in_lon):
            return None

    return (clat, clon, in_lat, in_lon, out_lat, out_lon)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    zones_by_cat = parse_zones_bin(BIN_PATH)

    # type_int -> list of valid test-case tuples
    cases_by_type = defaultdict(list)

    for cat, info in sorted(CAT_INFO.items()):
        type_int, type_name, min_km = info
        raw_zones = zones_by_cat.get(cat, [])
        max_count = MAX_SEAPLANE if cat == 3 else MAX_PER_CAT
        # oversample candidates to account for geometry check failures
        candidates = diverse_sample(raw_zones, max_count * 5)

        kept = 0
        for z in candidates:
            tc = make_test_case(z)
            if tc is not None:
                cases_by_type[type_int].append(tc)
                kept += 1
                if kept >= max_count:
                    break

        print(f"// cat={cat} ({type_name}): {len(raw_zones)} unique zones, "
              f"{len(candidates)} candidates, {kept} kept",
              file=sys.stderr)

    # ------------------------------------------------------------------
    # Section A: AP() macro lines
    # ------------------------------------------------------------------
    ap_lines = []
    for type_int in sorted(cases_by_type.keys()):
        _, type_name, min_km = CAT_INFO[
            next(c for c, i in CAT_INFO.items() if i[0] == type_int)
        ]
        for (ap_lat, ap_lon, in_lat, in_lon, out_lat, out_lon) in cases_by_type[type_int]:
            ap_lines.append(
                f"        AP({type_int},\"{type_name}\",{min_km:.2f},"
                f"{ap_lat:.7f},{ap_lon:.7f},"
                f"{in_lat:.7f},{in_lon:.7f},"
                f"{out_lat:.7f},{out_lon:.7f}),"
            )

    # ------------------------------------------------------------------
    # Section B: boundary struct lines (one per type)
    # ------------------------------------------------------------------
    b_lines = []
    for type_int in sorted(cases_by_type.keys()):
        _, type_name, min_km = CAT_INFO[
            next(c for c, i in CAT_INFO.items() if i[0] == type_int)
        ]
        if cases_by_type[type_int]:
            ap_lat, ap_lon, _, _, _, _ = cases_by_type[type_int][0]
            b_lines.append(
                f"        {{{ap_lat:.7f}, {ap_lon:.7f}, {min_km:.2f}f, \"{type_name}\"}},"
            )

    print("\n".join(ap_lines))
    print("=====")
    print("\n".join(b_lines))

    # Summary to stderr
    total = sum(len(v) for v in cases_by_type.values())
    print(f"\n// Generated {total} airport test cases across {len(cases_by_type)} types",
          file=sys.stderr)
    for type_int in sorted(cases_by_type.keys()):
        _, type_name, _ = CAT_INFO[
            next(c for c, i in CAT_INFO.items() if i[0] == type_int)
        ]
        print(f"//   type={type_int} {type_name}: {len(cases_by_type[type_int])} cases",
              file=sys.stderr)

if __name__ == "__main__":
    main()
