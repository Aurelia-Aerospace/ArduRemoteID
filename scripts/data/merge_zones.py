#!/usr/bin/env python3
"""
Convert all filtered source files to unified format and merge into zones_all.json.

Unified zone object:
  {
    "cat":   str,    # airport_l/m/s, seaplane, heliport, balloonport,
                     # faa_b/c/d, eu_ctr/atz/r/tma/p, prison, stadium, country
    "id":    str,    # stable unique key
    "name":  str,    # optional display name
    "floor": int,    # optional altitude floor in metres
    "shapes": [
      {"type": "circle",  "c": [lat5, lon5], "r": radius_m},
      {"type": "polygon", "pts": [[lat5, lon5], ...]}
    ]
  }

Run after filter_data.py / filter_military.py whenever source files change:
  python merge_zones.py

Outputs (data/filtered/):
  airport_zones.json  faa_zones.json  eu_zones.json
  prisons.json  stadiums.json  military_filtered.json  banned_countries.json   ← all unified
  zones_all.json                                        ← combined feed
"""
import json
from pathlib import Path

_RM      = Path(__file__).parent.parent.parent / "RemoteIDModule"
FILTERED = _RM / "data" / "filtered"
OUT      = FILTERED / "zones_all.json"

APT_CAT = {"l":  "airport_l", "m": "airport_m", "s": "airport_s",
           "sp": "seaplane",  "hp": "heliport",  "hb": "balloonport"}
FAA_CAT = {"B": "faa_b", "C": "faa_c", "D": "faa_d"}
EU_CAT  = {"CTR": "eu_ctr", "ATZ": "eu_atz", "R": "eu_r",
           "TMA": "eu_tma", "P":   "eu_p"}
FT_TO_M = 0.3048


def _unified(data):
    """True if data is already in unified format."""
    return isinstance(data, list) and bool(data) and "cat" in data[0]


def from_airports(src):
    raw = json.loads(src.read_text())
    if _unified(raw):
        return raw
    out = []
    for apt in raw:
        if "r" in apt and "c" in apt:
            cat = "balloonport" if apt["r"] == 5000 else "heliport"
            out.append({"cat": cat, "id": apt["k"],
                        "shapes": [{"type": "circle", "c": apt["c"], "r": apt["r"]}]})
        elif "z" in apt:
            cat = APT_CAT.get(apt.get("t", "s"), "airport_s")
            shapes = [{"type": "polygon", "pts": ring} for ring in apt["z"]]
            shapes += [{"type": "circle", "c": [rc[0], rc[1]], "r": rc[2]}
                       for rc in apt.get("rc", [])]
            out.append({"cat": cat, "id": apt["k"], "shapes": shapes})
    return out


def from_faa(src):
    if not src.exists() or src.stat().st_size < 100:
        return []
    raw = json.loads(src.read_text())
    if _unified(raw):
        return raw
    out = []
    for z in raw["zones"]:
        cat = FAA_CAT.get(z["c"], "faa_d")
        out.append({"cat": cat,
                    "id": z["n"] + "-" + z["c"],
                    "name": z["n"],
                    "floor": round(z["f"] * FT_TO_M),
                    "shapes": [{"type": "polygon", "pts": z["p"]}]})
    return out


def from_eu(src):
    if not src.exists():
        return []
    raw = json.loads(src.read_text())
    if _unified(raw):
        return raw
    out = []
    for z in raw["zones"]:
        cat = EU_CAT.get(z["t"], "eu_ctr")
        out.append({"cat": cat,
                    "id": z["n"] + "-" + z["t"],
                    "name": z["n"],
                    "floor": z["f"],
                    "shapes": [{"type": "polygon", "pts": z["p"]}]})
    return out


def from_circles(src, cat):
    if not src.exists():
        return []
    raw = json.loads(src.read_text())
    if _unified(raw):
        return raw
    r = raw["r_m"]
    return [{"cat": cat,
             "id": f"{pt[0]},{pt[1]}",
             "shapes": [{"type": "circle", "c": pt, "r": r}]}
            for pt in raw["pts"]]


def from_military(src):
    if not src.exists():
        return []
    data = json.loads(src.read_text())
    return data if _unified(data) else []


def from_countries(src):
    """Reads banned_countries.txt (decimal lat/lon) → unified polygon list."""
    if not src.exists():
        return []
    out = []
    idx  = 0
    pts  = []
    name = ""

    def flush():
        nonlocal idx
        if len(pts) >= 3:
            out.append({"cat": "country", "id": f"country_{idx}",
                        "name": name,
                        "shapes": [{"type": "polygon",
                                    "pts": [[round(p[0]*1e5), round(p[1]*1e5)]
                                            for p in pts]}]})
            idx += 1

    for line in src.read_text().splitlines():
        line = line.strip()
        if line.startswith("#"):
            flush(); pts = []; name = line[1:].strip()
            continue
        if not line:
            continue
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            pts.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    flush()
    return out


def _write(path, zones):
    path.write_text(json.dumps(zones, separators=(",", ":"), ensure_ascii=False))


def main():
    print("=== Merging zones ===")

    SOURCES = [
        ("airport_zones", from_airports,
         FILTERED / "airport_zones.json",   FILTERED / "airport_zones.json"),
        ("faa_zones",     from_faa,
         FILTERED / "faa_zones.json",        FILTERED / "faa_zones.json"),
        ("eu_zones",      from_eu,
         FILTERED / "eu_zones.json",         FILTERED / "eu_zones.json"),
        ("prisons",       lambda s: from_circles(s, "prison"),
         FILTERED / "prisons.json",          FILTERED / "prisons.json"),
        ("stadiums",      lambda s: from_circles(s, "stadium"),
         FILTERED / "stadiums.json",         FILTERED / "stadiums.json"),
        ("military_zones", from_military,
         FILTERED / "military_filtered.json", FILTERED / "military_filtered.json"),
        ("banned_countries", from_countries,
         FILTERED / "banned_countries.txt",  FILTERED / "banned_countries.json"),
    ]

    all_zones = []
    for name, fn, src, dst in SOURCES:
        if not src.exists():
            print(f"  {name:<22} not found, skipping")
            continue
        zones = fn(src)
        _write(dst, zones)
        print(f"  {name:<22} {len(zones):>7} zones  → {dst.name}")
        all_zones.extend(zones)

    _write(OUT, all_zones)
    print(f"\n  Total: {len(all_zones)} zones → {OUT.name}  "
          f"({OUT.stat().st_size // 1024} KB)")


main()
