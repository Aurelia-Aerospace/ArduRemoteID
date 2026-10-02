#!/usr/bin/env python3
"""
Build compact filtered data in data/filtered/ from raw downloads.

Coord encoding: integer (deg * 1e5) → ~1 m precision, ~40% smaller than float strings.
Zone sizing by airport type: large > medium > small > heliport.
"""
import csv, json, math, urllib.request
from pathlib import Path

_RM  = Path(__file__).parent.parent.parent / "RemoteIDModule"
DATA = _RM / "data" / "raw"
OUT  = _RM / "data" / "filtered"
OUT.mkdir(parents=True, exist_ok=True)

# ── Polygon simplification (Ramer-Douglas-Peucker) ────────────────────────────

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom = math.hypot(dx, dy) or 1
    max_d, idx = 0, 0
    for i, (px, py) in enumerate(pts[1:-1], 1):
        d = abs(dy*px - dx*py + bx*ay - by*ax) / denom
        if d > max_d:
            max_d, idx = d, i
    if max_d > eps:
        return rdp(pts[:idx+1], eps)[:-1] + rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]

def compress(pts):
    """[[lon,lat],...] → [[lat5,lon5],...] as integers, deduplicated."""
    out = []
    for lon, lat in pts:
        p = [round(lat * 1e5), round(lon * 1e5)]
        if not out or out[-1] != p:
            out.append(p)
    return out

def simplify(coords, max_pts=48):
    """
    Simplify a polygon coordinate list to at most max_pts unique points.
    Strategy: try RDP with decreasing epsilon; if result < 4 pts (circle
    collapse), fall back to uniform decimation.
    coords = [[lon,lat],...] (closed or open ring)
    Returns [[lon,lat],...] simplified.
    """
    pts = [(p[0], p[1]) for p in coords]
    # Compute extent to pick a sane eps (1% of bbox diagonal, min 1m)
    lons = [p[0] for p in pts]; lats = [p[1] for p in pts]
    dlat = (max(lats) - min(lats)) * 111320
    dlon = (max(lons) - min(lons)) * 111320 * math.cos(math.radians(sum(lats)/len(lats)))
    diag_m = math.hypot(dlat, dlon) or 1
    eps_deg = max(diag_m * 0.005, 1) / 111320   # 0.5% of diagonal, min 1 m

    simplified = rdp(pts, eps_deg)
    # If RDP collapses the polygon (smooth circles), fall back to decimation
    unique = list(dict.fromkeys(simplified))
    if len(unique) < 4:
        step = max(1, len(pts) // max_pts)
        simplified = pts[::step]

    # Final cap at max_pts via decimation if still too many
    if len(simplified) > max_pts:
        step = len(simplified) // max_pts
        simplified = simplified[::step]

    return [[p[0], p[1]] for p in simplified]

# ── Zone sizes — match firmware parameters.cpp exactly ────────────────────────
# Firmware key   → param name        → value (km)
# MIN_LG_AIRPORT → large_airport     → 10.15 km  (approach extension)
# MIN_MD_AIRPORT → medium_airport    →  5.00 km
# MIN_SM_AIRPORT → small_airport     →  3.00 km
# MIN_SP_AIRPORT → seaplane_base     →  5.00 km
# MIN_HB_AIRPORT → balloonport       →  5.00 km  (no runway → circle)
# MIN_HP_AIRPORT → heliport          →  4.50 km  (no runway → circle)
# MIN_TEST_AIRPORT                   →  0.00 km  (skip)
# MIN_PRISON                         →  2.40 km  (circle)
#
# Octagon: app_m = approach extension; widths proportional (~20% and ~7% of app_m)
# (approach_m, approach_half_width_m, side_half_width_m)
ZONE_PARAMS = {
    "large_airport":  (10150, 2000, 700),
    "medium_airport": ( 5000, 1000, 350),
    "small_airport":  ( 3000,  600, 210),
    "seaplane_base":  ( 5000, 1000, 350),
    "balloonport":    None,   # circle — no directional runway
    "heliport":       None,   # circle
    "closed":         None,   # skip
}
# Firmware circle radii (m)
CIRCLE_R = {
    "balloonport": 5000,
    "heliport":    1500,
}
PRISON_R_M = 1500   # MIN_PRISON = 1.5 km

def zone_octagon(la1, lo1, la2, lo2, app_m, app_w, side_w):
    lat0, lon0 = (la1+la2)/2, (lo1+lo2)/2
    ml = 111320.0
    mx = ml * math.cos(math.radians(lat0))
    def to_m(la, lo):  return (lo-lon0)*mx, (la-lat0)*ml
    def to_ll(x, y):   return lat0 + y/ml, lon0 + x/mx

    ax, ay = to_m(la1, lo1)
    bx, by = to_m(la2, lo2)
    L = math.hypot(bx-ax, by-ay) or 1
    ex, ey = (bx-ax)/L, (by-ay)/L
    px, py = -ey, ex

    ring = [
        to_ll(ax - app_m*ex + app_w*px,  ay - app_m*ey + app_w*py),
        to_ll(ax + side_w*px,             ay + side_w*py),
        to_ll(bx + side_w*px,             by + side_w*py),
        to_ll(bx + app_m*ex + app_w*px,  by + app_m*ey + app_w*py),
        to_ll(bx + app_m*ex - app_w*px,  by + app_m*ey - app_w*py),
        to_ll(bx - side_w*px,             by - side_w*py),
        to_ll(ax - side_w*px,             ay - side_w*py),
        to_ll(ax - app_m*ex - app_w*px,  ay - app_m*ey - app_w*py),
    ]
    return [[round(la*1e5), round(lo*1e5)] for la, lo in ring]

# ── 1. Airport runway zones ────────────────────────────────────────────────────

def filter_airports():
    rwy_src = DATA / "world_runways.csv"
    apt_src = DATA / "airports.csv"

    if not apt_src.exists():
        print("  fetching airports.csv…")
        raw = urllib.request.urlopen(
            "https://davidmegginson.github.io/ourairports-data/airports.csv",
            timeout=30).read()
        apt_src.write_bytes(raw)
        print(f"  → airports.csv  ({apt_src.stat().st_size//1024} KB)")

    # Load airports: ident → (type, lat, lon)
    apt_info = {}
    with open(apt_src, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["latitude_deg"])
                lon = float(row["longitude_deg"])
            except (ValueError, KeyError):
                lat = lon = None
            apt_info[row["ident"]] = (row["type"], lat, lon)

    TYPE_CODE = {"large_airport": "l", "medium_airport": "m",
                 "small_airport": "s", "seaplane_base": "sp"}

    # ── Pass 1: airports that have runway geometry in world_runways.csv ────────
    runways = {}
    with open(rwy_src, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("closed") == "1":
                continue
            try:
                la1, lo1 = float(row["le_latitude_deg"]), float(row["le_longitude_deg"])
                la2, lo2 = float(row["he_latitude_deg"]), float(row["he_longitude_deg"])
            except (ValueError, KeyError):
                continue
            mx = 111320 * math.cos(math.radians((la1 + la2) / 2))
            if math.hypot((lo2 - lo1) * mx, (la2 - la1) * 111320) > 15000:
                continue  # corrupt coordinates (e.g. endpoints on opposite sides of the globe)
            runways.setdefault(row["airport_ident"], []).append((la1, lo1, la2, lo2))

    out = []
    seen = set()
    for icao, rwys in runways.items():
        atype = apt_info.get(icao, ("small_airport", None, None))[0]
        params = ZONE_PARAMS.get(atype)
        r_m    = CIRCLE_R.get(atype)

        if params is None and r_m:
            lats = [c for rwy in rwys for c in (rwy[0], rwy[2])]
            lons = [c for rwy in rwys for c in (rwy[1], rwy[3])]
            out.append({"k": icao, "r": r_m,
                        "c": [round(sum(lats)/len(lats)*1e5),
                              round(sum(lons)/len(lons)*1e5)]})
            seen.add(icao); continue

        if params is None:
            seen.add(icao); continue

        out.append({"k": icao, "t": TYPE_CODE.get(atype, "s"),
                    "z": [zone_octagon(*rwy, *params) for rwy in rwys],
                    "rc": [[round((r[0]+r[2])/2*1e5), round((r[1]+r[3])/2*1e5),
                            round(math.hypot((r[2]-r[0])*111320,
                                  (r[3]-r[1])*111320*math.cos(math.radians((r[0]+r[2])/2))) / 2)]
                           for r in rwys]})
        seen.add(icao)

    # ── Pass 2: heliports & balloonports with NO runway entries ────────────────
    # These only exist in airports.csv with their own lat/lon
    for icao, (atype, lat, lon) in apt_info.items():
        if icao in seen or atype not in CIRCLE_R:
            continue
        if lat is None or lon is None:
            continue
        out.append({"k": icao, "r": CIRCLE_R[atype],
                    "c": [round(lat*1e5), round(lon*1e5)]})

    dest = OUT / "airport_zones.json"
    dest.write_text(json.dumps(out, separators=(",", ":")))
    n_rwys  = sum(len(a["z"]) for a in out if "z" in a)
    n_circs = sum(1 for a in out if "r" in a)
    print(f"  airports: {len(out)} total  ({n_rwys} runway octagons, {n_circs} circles)")
    print(f"  → airport_zones.json  {dest.stat().st_size//1024} KB")

# ── 2. FAA airspace (USA) ──────────────────────────────────────────────────────

DRONE_ALT_FT = 400   # 122 m — FAA recreational/Part 107 max
DRONE_ALT_M  = 300   # theoretical drone ceiling; CTR/ATZ floor=0 always kept

def filter_faa():
    src = DATA / "usa_faa.json"
    if not src.exists() or src.stat().st_size < 1000:
        print("  usa_faa.json not ready — skipping")
        return
    data = json.loads(src.read_text())
    zones = []
    for z in data["zones"]:
        if z["lower_ft"] >= DRONE_ALT_FT:
            continue
        coords = z["geometry"]["coordinates"][0]
        simplified = simplify(coords)
        zones.append({
            "n": z["name"][:28],
            "c": z["class"],
            "f": z["lower_ft"],          # floor ft (useful to show on map)
            "p": compress(simplified),
        })
    dest = OUT / "faa_zones.json"
    dest.write_text(json.dumps({"zones": zones}, separators=(",", ":")))
    print(f"  faa: {len(zones)}/{data['count']} zones relevant for drones")
    print(f"  → faa_zones.json  {dest.stat().st_size//1024} KB")

# ── 3. OpenAIP Europe ──────────────────────────────────────────────────────────

TYPE_LABEL = {1: "R", 3: "P", 4: "CTR", 7: "TMA", 13: "ATZ"}

def filter_openaip():
    src = DATA / "europe_openaip.json"
    if not src.exists():
        print("  europe_openaip.json not found — skipping")
        return
    data = json.loads(src.read_text())
    zones = []
    for z in data["zones"]:
        if z.get("lower_m", 0) > DRONE_ALT_M:
            continue
        coords = z["geometry"]["coordinates"][0]
        simplified = simplify(coords)
        zones.append({
            "n": z["name"][:28],
            "t": TYPE_LABEL.get(z["type"], str(z["type"])),
            "f": round(z.get("lower_m", 0)),
            "p": compress(simplified),
        })
    dest = OUT / "eu_zones.json"
    dest.write_text(json.dumps({"zones": zones}, separators=(",", ":")))
    print(f"  openaip: {len(zones)}/{data['count']} zones relevant for drones")
    print(f"  → eu_zones.json  {dest.stat().st_size//1024} KB")

# ── 4. Stadiums (US, 3 nm TFR radius) ─────────────────────────────────────────

STADIUM_R_M = 5556   # 3 nautical miles

def filter_stadiums():
    src = DATA / "Stadiums.csv"
    if not src.exists():
        print("  Stadiums.csv not found — skipping")
        return
    pts = []
    with open(src, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                pts.append([round(float(row["Y"])*1e5), round(float(row["X"])*1e5)])
            except (ValueError, KeyError):
                continue
    dest = OUT / "stadiums.json"
    dest.write_text(json.dumps({"r_m": STADIUM_R_M, "pts": pts}, separators=(",", ":")))
    print(f"  stadiums: {len(pts)} venues  r={STADIUM_R_M}m")
    print(f"  → stadiums.json  {dest.stat().st_size//1024} KB")

# ── 5. Prisons (worldwide, MIN_PRISON = 2.4 km radius) ───────────────────────

PRISON_SRC = _RM / "airport_check" / "world_prison_list.txt"  # legacy; replaced by data/raw/ once firmware migrates

PRISON_DEDUP_M = 400

def _dedup_exact(raw):
    # ponytail: O(n*k) with lat-sorted early exit; upgrade to rtree if n > 100k
    if not raw:
        return []
    lat_tol = PRISON_DEDUP_M / 111320
    srt = sorted(raw)
    out = [srt[0]]
    for la, lo in srt[1:]:
        too_close = False
        for pla, plo in reversed(out):
            if pla < la - lat_tol:
                break
            mx = 111320 * math.cos(math.radians((la + pla) / 2))
            if math.hypot((lo - plo) * mx, (la - pla) * 111320) < PRISON_DEDUP_M:
                too_close = True
                break
        if not too_close:
            out.append((la, lo))
    return out

def filter_prisons():
    if not PRISON_SRC.exists():
        print(f"  world_prison_list.txt not found at {PRISON_SRC}")
        return
    raw = []
    for line in PRISON_SRC.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lat, lon = map(float, line.split(","))
            raw.append((lat, lon))
        except ValueError:
            continue
    deduped = _dedup_exact(raw)
    pts = [[round(la*1e5), round(lo*1e5)] for la, lo in deduped]
    dest = OUT / "prisons.json"
    dest.write_text(json.dumps({"r_m": PRISON_R_M, "pts": pts}, separators=(",", ":")))
    print(f"  prisons: {len(pts)} locations  r={PRISON_R_M}m  (raw={len(raw)}, deduped at {PRISON_DEDUP_M}m)")
    print(f"  → prisons.json  {dest.stat().st_size//1024} KB")

# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Building filtered data ===\n[1/5] Airports")
    filter_airports()
    print("[2/5] FAA airspace")
    filter_faa()
    print("[3/5] OpenAIP Europe")
    filter_openaip()
    print("[4/5] Stadiums")
    filter_stadiums()
    print("[5/5] Prisons")
    filter_prisons()
    print(f"\nFiltered files in {OUT}/")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name:30s} {f.stat().st_size//1024:>6} KB")
