#!/usr/bin/env python3
"""
Fetch military installations from:
  1. HIFLD MIRTA (US - DoD official polygon data)
  2. OSM Overpass (global, named military features — fallback for non-US)
Deduplicates US features (MIRTA wins over OSM within DEDUP_M).
Saves to data/raw/military_raw.json
"""
import json, math, time, urllib.request, urllib.parse
from pathlib import Path

HERE    = Path(__file__).parent
RM      = HERE.parent.parent / "RemoteIDModule"
RAW_OUT = RM / "data" / "raw" / "military_raw.json"

MIRTA_URL = ("https://services2.arcgis.com/FiaPA4ga0iQKduv3/ArcGIS/rest"
             "/services/MIRTA_Polygons_A_view/FeatureServer/0/query")

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

# World regions: (name, south, west, north, east)
REGIONS = [
    ("North America",  15, -170, 72, -52),
    ("South America", -60,  -85, 15, -30),
    ("Europe",         35,  -25, 72,  45),
    ("Africa",        -40,  -20, 40,  55),
    ("Middle East",    10,   30, 45,  65),
    ("Asia West",       0,   40, 55,  90),
    ("Asia East",       0,   90, 55, 180),
    ("Oceania",       -50,  100, -5, 180),
]

DEDUP_M = 2000  # 2 km — large enough to catch duplicate military installations

# Two groups so each Overpass query stays small (6-type union caused silent empty responses)
TYPE_GROUPS = [
    ("base", "airfield", "training_area", "range"),  # original — known to work
    ("airbase", "naval_base"),                        # new types — separate query
]

# ── helpers ───────────────────────────────────────────────────────────────────

def get_json(url, data=None, headers=None, retries=3, timeout=90):
    hdrs = {"User-Agent": "DroneNoFlyZone/1.0 (mauricio.diaz9036@gmail.com)"}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < retries - 1:
                wait = 15 * (attempt + 1)
                print(f"    retry {attempt+1}/{retries-1}: {e}  (wait {wait}s)")
                time.sleep(wait)
            else:
                raise

def centroid(pts):
    """[(lat, lon), ...] → (mean_lat, mean_lon)"""
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

def dist_m(la1, lo1, la2, lo2):
    ml = 111320.0
    mx = ml * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot((lo2 - lo1) * mx, (la2 - la1) * ml)

# ── 1. MIRTA / HIFLD (US official polygons) ──────────────────────────────────

def rings_to_polygon(rings):
    """ArcGIS rings [[lon,lat],...] → outer ring as [(lat, lon), ...]"""
    if not rings:
        return None
    return [(pt[1], pt[0]) for pt in rings[0]]  # first ring = outer; lon,lat → lat,lon

def fetch_mirta():
    features, offset, page = [], 0, 100
    while True:
        params = urllib.parse.urlencode({
            "where":             "1=1",
            "outFields":         "SITENAME,SITEREPORTINGCOMPONENT,FEATUREDESCRIPTION",
            "returnGeometry":    "true",
            "outSR":             "4326",
            "resultOffset":      offset,
            "resultRecordCount": page,
            "f":                 "json",
        })
        data = get_json(f"{MIRTA_URL}?{params}")
        if data.get("error"):
            print("  MIRTA error:", data["error"]); break
        items = data.get("features", [])
        if not items:
            break
        for item in items:
            geom  = item.get("geometry", {})
            attrs = item.get("attributes", {})
            name  = (attrs.get("SITENAME") or "").strip()
            desc  = (attrs.get("FEATUREDESCRIPTION") or "").lower()
            comp  = (attrs.get("SITEREPORTINGCOMPONENT") or "").lower()
            # map component/desc to our mtype
            if "airfield" in desc or "airfield" in comp:
                mtype = "airfield"
            elif "training" in desc or "range" in desc:
                mtype = "training_area"
            else:
                mtype = "base"
            rings = geom.get("rings")
            poly  = rings_to_polygon(rings) if rings else None
            if poly and len(poly) >= 3:
                la, lo = centroid(poly)
            else:
                lo = geom.get("x"); la = geom.get("y")
                if la is None or lo is None:
                    continue
                poly = None
            if not (-90 <= la <= 90 and -180 <= lo <= 180):
                continue
            features.append({
                "id":      f"mirta_{len(features)}",
                "name":    name,
                "mtype":   mtype,
                "source":  "mirta",
                "lat":     round(la, 6),
                "lon":     round(lo, 6),
                "polygon": [[round(p[0], 6), round(p[1], 6)] for p in poly] if poly else None,
            })
        print(f"  MIRTA offset {offset}: +{len(items)}  total={len(features)}", flush=True)
        if not data.get("exceededTransferLimit"):
            break
        offset += page
        time.sleep(1)
    return features

# ── 2. OSM Overpass (global, chunked by region) ───────────────────────────────

def _overpass_query(region_bbox, types):
    s, w, n, e = region_bbox
    bbox = f"({s},{w},{n},{e})"
    lines = [f'  way["military"="{t}"]["name"]{bbox};' for t in types]
    lines += [f'  relation["military"="{t}"]["name"]{bbox};' for t in types]
    return (f'[out:json][timeout:90][maxsize:134217728];\n(\n'
            + "\n".join(lines)
            + '\n);\nout geom qt;')

def _osm_poly(element):
    if element["type"] == "way":
        geom = element.get("geometry", [])
        return [(g["lat"], g["lon"]) for g in geom] if len(geom) >= 3 else None
    pts = []
    for m in element.get("members", []):
        if m.get("role") == "outer" and "geometry" in m:
            pts += [(g["lat"], g["lon"]) for g in m["geometry"]]
    return pts if len(pts) >= 3 else None

def _overpass_post(query, timeout=95):
    data = urllib.parse.urlencode({"data": query}).encode()
    hdrs = {"User-Agent": "DroneNoFlyZone/1.0 (mauricio.diaz9036@gmail.com)",
            "Content-Type": "application/x-www-form-urlencoded"}
    last_err = None
    for server in OVERPASS_SERVERS:
        try:
            req = urllib.request.Request(server, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                result = json.loads(r.read())
            # Overpass returns 200 OK but with a remark and no elements on server-side error
            if not result.get("elements") and "remark" in result:
                raise RuntimeError(f"Overpass server error: {result['remark'][:120]}")
            return result
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e
            time.sleep(5)
    raise RuntimeError(f"All Overpass servers failed: {last_err}")

def fetch_osm():
    all_features = []
    seen_ids = set()
    for reg_name, s, w, n, e in REGIONS:
        print(f"  OSM {reg_name}…", end=" ", flush=True)
        region_feats = []
        for group in TYPE_GROUPS:
            try:
                query = _overpass_query((s, w, n, e), group)
                result = _overpass_post(query)
                for el in result.get("elements", []):
                    if el["id"] in seen_ids:
                        continue
                    seen_ids.add(el["id"])
                    tags  = el.get("tags", {})
                    mtype = tags.get("military", "base")
                    fname = tags.get("name", "").strip()
                    poly  = _osm_poly(el)
                    if not poly:
                        continue
                    la, lo = centroid(poly)
                    if not (-90 <= la <= 90 and -180 <= lo <= 180):
                        continue
                    region_feats.append({
                        "id":      f"osm_{el['id']}",
                        "name":    fname,
                        "mtype":   mtype,
                        "source":  "osm",
                        "lat":     round(la, 6),
                        "lon":     round(lo, 6),
                        "polygon": [[round(p[0], 6), round(p[1], 6)] for p in poly],
                    })
                time.sleep(2)
            except Exception as e:
                print(f"\n    {group}: FAILED: {e}", end="")
        print(f" {len(region_feats)} features")
        all_features.extend(region_feats)
        time.sleep(3)
    return all_features

# ── 3. Dedup (MIRTA wins in US, grid-cell dedup globally) ─────────────────────

def dedup(mirta, osm):
    out = list(mirta)
    mirta_pts = [(f["lat"], f["lon"]) for f in mirta]
    added = 0
    for f in osm:
        la, lo = f["lat"], f["lon"]
        if not any(dist_m(la, lo, m[0], m[1]) < DEDUP_M for m in mirta_pts):
            out.append(f)
            mirta_pts.append((la, lo))  # prevent OSM-OSM duplicates too
            added += 1
    return out, added

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("[1/2] Fetching MIRTA (US DoD)")
    try:
        mirta = fetch_mirta()
        print(f"  MIRTA: {len(mirta)} installations")
    except Exception as e:
        print(f"  MIRTA failed: {e}"); mirta = []

    print("[2/2] Fetching OSM (global, chunked by region)")
    try:
        osm = fetch_osm()
        print(f"  OSM total: {len(osm)} features")
    except Exception as e:
        print(f"  OSM failed: {e}"); osm = []

    print("\nDeduplicating…")
    merged, osm_added = dedup(mirta, osm)
    print(f"  MIRTA={len(mirta)}  OSM raw={len(osm)}  OSM added={osm_added}  total={len(merged)}")

    RAW_OUT.parent.mkdir(parents=True, exist_ok=True)
    RAW_OUT.write_text(json.dumps({
        "sources": {"mirta": len(mirta), "osm": len(osm)},
        "total":   len(merged),
        "features": merged,
    }, indent=2, ensure_ascii=False))
    print(f"  → {RAW_OUT}  ({RAW_OUT.stat().st_size // 1024} KB)")

main()
