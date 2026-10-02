#!/usr/bin/env python3
"""
Download airspace + runway data to data/.

Sources:
  1. OurAirports  → world_runways.csv   (global runway coordinates)
  2. FAA ArcGIS   → usa_faa.json        (USA Class B/C/D airspace polygons)
  3. OpenAIP      → europe_openaip.json (EU CTR/TMA/restricted polygons)

Usage: python fetch_data.py
"""
import json, time, urllib.request, urllib.parse
from pathlib import Path

HERE     = Path(__file__).parent
RM       = HERE.parent.parent / "RemoteIDModule"
DATA_DIR = RM / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── API keys ───────────────────────────────────────────────────────────────────
OPENAIP_KEY = ""
env = HERE / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if line.startswith("OPENAIP_API_KEY="):
            OPENAIP_KEY = line.split("=", 1)[1].strip()

OPENAIP_HEADERS = {
    "x-openaip-api-key": OPENAIP_KEY,
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# European ISO-2 country codes
EU_COUNTRIES = [
    "GB","DE","FR","ES","IT","NL","BE","PL","CZ","CH","AT","DK",
    "NO","SE","FI","SK","SI","HR","RS","BG","RO","GR","PT","LT",
    "LV","EE","HU","IE","LU","MT","CY","UA","TR","IS","AL","MK",
    "BA","ME","XK","MD","BY",
]

# OpenAIP type codes we care about
RELEVANT_TYPES = [1, 3, 4, 7, 13]   # RESTRICTED, PROHIBITED, CTR, TMA, ATZ

FAA_URL    = ("https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest"
              "/services/Class_Airspace/FeatureServer/0/query")
RWY_URL    = "https://davidmegginson.github.io/ourairports-data/runways.csv"
OPENAIP_URL = "https://api.core.openaip.net/api/airspaces"


# ── helpers ───────────────────────────────────────────────────────────────────

def get(url, headers=None, retries=4, backoff=15):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                wait = backoff * (attempt + 1)
                print(f"    [{e.code}] rate limited — waiting {wait}s…")
                time.sleep(wait)
            else:
                raise
        except TimeoutError:
            if attempt < retries - 1:
                print(f"    timeout, retrying…")
            else:
                raise
    raise RuntimeError(f"Failed: {url}")


def save_json(name, data):
    p = DATA_DIR / name
    p.write_text(json.dumps(data, indent=2))
    print(f"  → {name}  ({p.stat().st_size // 1024} KB)")


def save_raw(name, raw):
    p = DATA_DIR / name
    p.write_bytes(raw)
    print(f"  → {name}  ({p.stat().st_size // 1024} KB)")


# ── 1. OurAirports runways ────────────────────────────────────────────────────

def fetch_ourairports():
    print("\n[1/3] OurAirports — world_runways.csv")
    raw = get(RWY_URL)
    save_raw("world_runways.csv", raw)
    lines = raw.decode().count("\n")
    print(f"  {lines:,} rows")


# ── 2. FAA airspace (USA) ──────────────────────────────────────────────────────

def fetch_faa():
    from http.client import IncompleteRead
    print("\n[2/3] FAA — USA Class B/C/D airspace (50 features/page, 6s sleep)")
    zones, offset, page_size = [], 0, 50

    def faa_get(url, retries=8):
        for attempt in range(retries):
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 504 and attempt < retries-1:
                    print(f"    504, retry {attempt+1}"); time.sleep(20); continue
                raise
            except IncompleteRead:
                if attempt < retries-1:
                    print(f"    IncompleteRead, retry {attempt+1}"); time.sleep(10); continue
                raise
            if data.get("error", {}).get("code") == 429:
                print("    JSON 429, waiting 70s…"); time.sleep(70); continue
            return data
        raise RuntimeError("FAA: too many retries")

    while True:
        params = urllib.parse.urlencode({
            "where":             "CLASS IN ('B','C','D')",
            "outFields":         "NAME,CLASS,LOWER_VAL,UPPER_VAL",
            "returnGeometry":    "true",
            "resultOffset":      offset,
            "resultRecordCount": page_size,
            "f":                 "json",
        })
        data = faa_get(f"{FAA_URL}?{params}")
        if data.get("error"):
            print("ERROR:", data["error"]); break
        features = data.get("features", [])
        if not features:
            break
        for f in features:
            a    = f["attributes"]
            ring = f["geometry"].get("rings", [[]])[0]
            zones.append({
                "name":     a["NAME"],
                "class":    a["CLASS"],
                "lower_ft": a.get("LOWER_VAL", 0),
                "upper_ft": a.get("UPPER_VAL", 99999),
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[p[0], p[1]] for p in ring]],
                },
            })
        print(f"  offset {offset}: +{len(features)}  total={len(zones)}", flush=True)
        if len(features) < page_size:
            break
        offset += page_size
        time.sleep(6)

    save_json("usa_faa.json", {"source": "faa", "count": len(zones), "zones": zones})
    print(f"  {len(zones)} airspace sections total")


# ── 3. OpenAIP (Europe) ────────────────────────────────────────────────────────

def fetch_openaip_country(country):
    """Fetch all relevant airspace zones for one country, paginating."""
    types   = ",".join(str(t) for t in RELEVANT_TYPES)
    zones   = []
    page    = 1
    total   = None
    while True:
        url = (f"{OPENAIP_URL}?page={page}&limit=100"
               f"&country={country}&type={types}")
        raw  = get(url, headers=OPENAIP_HEADERS)
        data = json.loads(raw)
        if total is None:
            total = data.get("totalCount", 0)
        items = data.get("items", [])
        if not items:
            break
        for item in items:
            geo = item.get("geometry", {})
            if geo.get("type") != "Polygon":
                continue
            zones.append({
                "name":     item["name"],
                "type":     item["type"],
                "country":  country,
                "lower_m":  item.get("lowerLimit", {}).get("value", 0),
                "upper_m":  item.get("upperLimit", {}).get("value", 9999),
                "geometry": geo,
            })
        if len(items) < 100:
            break
        page += 1
        time.sleep(1)
    return zones


def fetch_openaip():
    if not OPENAIP_KEY:
        print("\n[3/3] OpenAIP — skipped (no API key in .env)")
        return

    print(f"\n[3/3] OpenAIP — Europe ({len(EU_COUNTRIES)} countries)")
    all_zones = []
    for i, country in enumerate(EU_COUNTRIES):
        try:
            zones = fetch_openaip_country(country)
            if zones:
                all_zones.extend(zones)
                print(f"  {country}: {len(zones)} zone(s)  [{i+1}/{len(EU_COUNTRIES)}]")
            else:
                print(f"  {country}: —                [{i+1}/{len(EU_COUNTRIES)}]")
            time.sleep(1.5)
        except Exception as e:
            print(f"  {country}: error — {e}")
            time.sleep(5)

    save_json("europe_openaip.json", {
        "source": "openaip",
        "count":  len(all_zones),
        "zones":  all_zones,
    })
    print(f"  total: {len(all_zones)} zones across Europe")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Downloading airspace data ===")
    fetch_ourairports()
    fetch_faa()
    fetch_openaip()
    print(f"\nDone. Files in {DATA_DIR}/")
    for f in sorted(DATA_DIR.iterdir()):
        print(f"  {f.name:30s} {f.stat().st_size // 1024:>6} KB")


main()
