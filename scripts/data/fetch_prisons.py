#!/usr/bin/env python3
"""
Fetch worldwide prison locations from HIFLD (USA) and Wikidata (global),
merge with the existing world_prison_list.txt, deduplicate within 500 m,
and overwrite world_prison_list.txt + data/prisons_raw.json.
"""
import json, math, time, urllib.request, urllib.parse
from pathlib import Path

HERE      = Path(__file__).parent
RM        = HERE.parent.parent / "RemoteIDModule"
EXISTING  = RM / "airport_check" / "world_prison_list.txt"
RAW_OUT   = RM / "data" / "raw" / "prisons_raw.json"

HIFLD_URL = ("https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest"
             "/services/Prison_Points/FeatureServer/0/query")
WIKIDATA_URL = "https://query.wikidata.org/sparql"

DEDUP_M = 800   # two points within 800 m → same facility

# ── helpers ───────────────────────────────────────────────────────────────────

def get_json(url, headers=None, retries=4):
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt < retries - 1:
                print(f"    retry {attempt+1}: {e}")
                time.sleep(10)
            else:
                raise

def dist_m(la1, lo1, la2, lo2):
    """Flat-earth distance in metres between two lat/lon points."""
    ml = 111320.0
    mx = ml * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot((lo2 - lo1) * mx, (la2 - la1) * ml)

# ── 1. Load existing list ─────────────────────────────────────────────────────

def load_existing():
    pts = []
    if EXISTING.exists():
        for line in EXISTING.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                la, lo = map(float, line.split(","))
                pts.append((la, lo))
            except ValueError:
                pass
    print(f"  existing: {len(pts)} points")
    return pts

# ── 2. HIFLD (USA — federal + state + local jails) ───────────────────────────

def fetch_hifld():
    pts, offset, page = [], 0, 500
    while True:
        params = urllib.parse.urlencode({
            "where": "STATUS='OPEN'",
            "outFields": "NAME",
            "returnGeometry": "true",
            "outSR": "4326",
            "resultOffset": offset,
            "resultRecordCount": page,
            "f": "json",
        })
        data = get_json(f"{HIFLD_URL}?{params}")
        if data.get("error"):
            print("  HIFLD error:", data["error"]); break
        features = data.get("features", [])
        if not features:
            break
        for f in features:
            g = f.get("geometry", {})
            try:
                lo, la = float(g["x"]), float(g["y"])
                if -90 <= la <= 90 and -180 <= lo <= 180:
                    pts.append((la, lo))
            except (KeyError, TypeError, ValueError):
                pass
        print(f"  HIFLD offset {offset}: +{len(features)}  total={len(pts)}", flush=True)
        if len(features) < page:
            break
        offset += page
        time.sleep(2)
    return pts

# ── 3. Wikidata SPARQL (global prisons with coordinates) ─────────────────────

SPARQL = """
SELECT ?lat ?lon WHERE {
  ?item wdt:P31/wdt:P279* wd:Q40357 .
  ?item wdt:P625 ?coord .
  BIND(geof:latitude(?coord)  AS ?lat)
  BIND(geof:longitude(?coord) AS ?lon)
}
"""

def fetch_wikidata():
    params = urllib.parse.urlencode({"query": SPARQL, "format": "json"})
    headers = {
        "User-Agent": "DroneNoFlyZone/1.0 (mauricio.uavsystems@gmail.com)",
        "Accept": "application/sparql-results+json",
    }
    data = get_json(f"{WIKIDATA_URL}?{params}", headers=headers)
    pts = []
    for row in data.get("results", {}).get("bindings", []):
        try:
            la = float(row["lat"]["value"])
            lo = float(row["lon"]["value"])
            if -90 <= la <= 90 and -180 <= lo <= 180:
                pts.append((la, lo))
        except (KeyError, ValueError):
            pass
    return pts

# ── 4. Deduplicate ────────────────────────────────────────────────────────────

def dedup(all_pts):
    """Grid-cell dedup: bucket by DEDUP_M-sized cells, keep one point per cell."""
    cell = DEDUP_M / 111320
    seen = {}
    out  = []
    for la, lo in all_pts:
        key = (round(la / cell), round(lo / cell))
        if key not in seen:
            seen[key] = True
            out.append((la, lo))
    return out

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("[1/3] Loading existing list")
    existing = load_existing()

    print("[2/3] Fetching HIFLD (USA)")
    try:
        hifld = fetch_hifld()
        print(f"  HIFLD: {len(hifld)} facilities")
    except Exception as e:
        print(f"  HIFLD failed: {e}"); hifld = []

    print("[3/3] Fetching Wikidata (global)")
    try:
        wiki = fetch_wikidata()
        print(f"  Wikidata: {len(wiki)} prisons")
    except Exception as e:
        print(f"  Wikidata failed: {e}"); wiki = []

    print("\nMerging + deduplicating…")
    merged = dedup(existing + hifld + wiki)
    print(f"  before: {len(existing)+len(hifld)+len(wiki)}  after dedup: {len(merged)}")

    # Save raw JSON with source tags for auditing
    RAW_OUT.write_text(json.dumps({
        "sources": {"existing": len(existing), "hifld": len(hifld), "wikidata": len(wiki)},
        "total": len(merged),
        "pts": [[round(la, 6), round(lo, 6)] for la, lo in merged],
    }, indent=2))
    print(f"  → {RAW_OUT}  ({RAW_OUT.stat().st_size // 1024} KB)")

    # Overwrite the firmware source file
    EXISTING.write_text(
        "\n".join(f"{la},{lo}" for la, lo in merged) + "\n"
    )
    print(f"  → {EXISTING}  ({EXISTING.stat().st_size // 1024} KB, {len(merged)} entries)")

main()
