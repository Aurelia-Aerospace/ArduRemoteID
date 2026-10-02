#!/usr/bin/env python3
"""
Re-fetch Middle East and Asia West with longer sleeps and merge into existing
military_raw.json. Run when those regions returned unexpectedly low counts.
"""
import json, math, time, urllib.request, urllib.parse
from pathlib import Path

HERE    = Path(__file__).parent
RM      = HERE.parent.parent / "RemoteIDModule"
RAW_OUT = RM / "data" / "raw" / "military_raw.json"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

PATCH_REGIONS = [
    ("Middle East", 10, 30, 45, 65),
    ("Asia West",    0, 40, 55, 90),
]

TYPE_GROUPS = [
    ("base", "airfield", "training_area", "range"),
    ("airbase", "naval_base"),
]

DEDUP_M = 2000

def dist_m(la1, lo1, la2, lo2):
    ml = 111320.0
    mx = ml * math.cos(math.radians((la1 + la2) / 2))
    return math.hypot((lo2 - lo1) * mx, (la2 - la1) * ml)

def centroid(pts):
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

def _overpass_query(bbox, types):
    s, w, n, e = bbox
    bb = f"({s},{w},{n},{e})"
    lines = [f'  way["military"="{t}"]["name"]{bb};' for t in types]
    lines += [f'  relation["military"="{t}"]["name"]{bb};' for t in types]
    return (f'[out:json][timeout:90][maxsize:134217728];\n(\n'
            + "\n".join(lines) + '\n);\nout geom qt;')

def _post(query, timeout=95):
    data = urllib.parse.urlencode({"data": query}).encode()
    hdrs = {"User-Agent": "DroneNoFlyZone/1.0 (mauricio.diaz9036@gmail.com)",
            "Content-Type": "application/x-www-form-urlencoded"}
    last_err = None
    for server in OVERPASS_SERVERS:
        try:
            req = urllib.request.Request(server, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                result = json.loads(r.read())
            if not result.get("elements") and "remark" in result:
                raise RuntimeError(f"Server error: {result['remark'][:120]}")
            return result
        except RuntimeError:
            raise
        except Exception as e:
            last_err = e; time.sleep(5)
    raise RuntimeError(f"All servers failed: {last_err}")

def _osm_poly(el):
    if el["type"] == "way":
        geom = el.get("geometry", [])
        return [(g["lat"], g["lon"]) for g in geom] if len(geom) >= 3 else None
    pts = []
    for m in el.get("members", []):
        if m.get("role") == "outer" and "geometry" in m:
            pts += [(g["lat"], g["lon"]) for g in m["geometry"]]
    return pts if len(pts) >= 3 else None

def main():
    raw = json.loads(RAW_OUT.read_text())
    existing = raw["features"]
    existing_pts = [(f["lat"], f["lon"]) for f in existing]
    existing_ids = {f["id"] for f in existing}
    print(f"Existing: {len(existing)} features")

    new_feats = []
    seen_osm_ids = set()

    for reg_name, s, w, n, e in PATCH_REGIONS:
        print(f"\n  Re-fetching {reg_name}…")
        time.sleep(10)  # extra pause before starting each region
        reg_feats = []
        for group in TYPE_GROUPS:
            try:
                result = _post(_overpass_query((s, w, n, e), group))
                els = result.get("elements", [])
                for el in els:
                    if el["id"] in seen_osm_ids:
                        continue
                    seen_osm_ids.add(el["id"])
                    tags  = el.get("tags", {})
                    mtype = tags.get("military", "base")
                    fname = tags.get("name", "").strip()
                    poly  = _osm_poly(el)
                    if not poly:
                        continue
                    la, lo = centroid(poly)
                    if not (-90 <= la <= 90 and -180 <= lo <= 180):
                        continue
                    fid = f"osm_{el['id']}"
                    if fid in existing_ids:
                        continue
                    if any(dist_m(la, lo, ep[0], ep[1]) < DEDUP_M for ep in existing_pts):
                        continue
                    reg_feats.append({
                        "id": fid, "name": fname, "mtype": mtype,
                        "source": "osm",
                        "lat": round(la, 6), "lon": round(lo, 6),
                        "polygon": [[round(p[0], 6), round(p[1], 6)] for p in poly],
                    })
                    existing_pts.append((la, lo))
                    existing_ids.add(fid)
                print(f"    {group}: +{len(els)} raw → {len(reg_feats)} total so far")
                time.sleep(8)  # longer sleep between groups
            except Exception as e:
                print(f"    {group}: FAILED: {e}")
                time.sleep(10)
        new_feats.extend(reg_feats)
        print(f"  {reg_name}: +{len(reg_feats)} new features")
        time.sleep(10)  # longer sleep between regions

    print(f"\nAdding {len(new_feats)} new features to existing {len(existing)}")
    merged = existing + new_feats
    raw["features"] = merged
    raw["total"] = len(merged)
    raw["sources"]["osm"] = raw["sources"].get("osm", 0) + len(new_feats)
    RAW_OUT.write_text(json.dumps(raw, indent=2, ensure_ascii=False))
    print(f"  → {RAW_OUT}  ({RAW_OUT.stat().st_size // 1024} KB)  total={len(merged)}")

main()
