#!/usr/bin/env python3
"""
Visualize data/filtered/zones_all.json on an interactive map.
Run merge_zones.py first to generate zones_all.json.

Hover: full zone type · ESP32 tag · zone ID (all overlapping zones).
Right-click visible zone: hide it.  Right-click hidden zone location: restore it.
Ctrl+Z / Restore button: restore all hidden zones.

Usage:
  python visualize_zones.py              (world view)
  python visualize_zones.py ICAO         (centered on zone by id, e.g. MMGL)
  python visualize_zones.py LAT LON      (decimal degrees)
"""
import json, math, sys, webbrowser, zlib
from pathlib import Path
import folium
from _zone_viewer import make_extras

_RM       = Path(__file__).parent.parent / "RemoteIDModule"
ZONES_ALL = _RM / "data" / "filtered" / "zones_all.json"
OUT       = Path(__file__).parent / "test_result" / "zones_map.html"

CAT_FULL = {
    "airport_l": "Large airport",   "airport_m": "Medium airport",
    "airport_s": "Small airport",   "seaplane":  "Seaplane base",
    "heliport":  "Heliport",        "balloonport":"Balloonport",
    "faa_b":     "FAA Class B",     "faa_c":     "FAA Class C",
    "faa_d":     "FAA Class D",     "eu_ctr":    "EU CTR",
    "eu_atz":    "EU ATZ",          "eu_r":      "EU Restricted",
    "eu_tma":    "EU TMA",          "eu_p":      "EU Prohibited",
    "prison":    "Prison",          "stadium":   "Stadium",
    "military":  "Military base",   "country":   "Banned country",
}
CAT_TAG = {
    "airport_l": "APT_L",  "airport_m": "APT_M",  "airport_s": "APT_S",
    "seaplane":  "APT_SEA","heliport":  "APT_HEL", "balloonport":"APT_BAL",
    "faa_b":     "FAA_B",  "faa_c":     "FAA_C",   "faa_d":     "FAA_D",
    "eu_ctr":    "EU_CTR", "eu_atz":    "EU_ATZ",  "eu_r":      "EU_R",
    "eu_tma":    "EU_TMA", "eu_p":      "EU_P",
    "prison":    "PRISON", "stadium":   "STADIUM",
    "military":  "MZ",     "country":   "COUNTRY",
}
CAT_LABEL = {
    "airport_l": "Large airport",    "airport_m": "Medium airport",
    "airport_s": "Small airport",    "seaplane":  "Seaplane base",
    "heliport":  "Heliport",         "balloonport":"Balloonport",
    "faa_b":     "FAA Class B",      "faa_c":     "FAA Class C",
    "faa_d":     "FAA Class D",      "eu_ctr":    "EU CTR",
    "eu_atz":    "EU ATZ",           "eu_r":      "EU Restricted",
    "eu_tma":    "EU TMA",           "eu_p":      "EU Prohibited",
    "prison":    "Prison",           "stadium":   "Stadium",
    "military":  "Military base",    "country":   "Banned country",
}
CAT_NUM = {
    "airport_l": 0, "airport_m": 1, "airport_s": 2, "seaplane":  3,
    "heliport":  4, "balloonport":5, "faa_b":     6, "faa_c":     7,
    "faa_d":     8, "eu_ctr":     9, "eu_atz":   10, "eu_r":     11,
    "eu_tma":   12, "eu_p":      13, "prison":   14, "stadium":  15,
    "military": 16, "country":   17,
}


def _make_id(cat_str, key):
    cat = CAT_NUM.get(cat_str, 31)
    return (cat << 27) | (zlib.crc32(key.encode()) & 0x07FFFFFF)


def _get_center(zones):
    if len(sys.argv) == 3:
        try:
            return float(sys.argv[1]), float(sys.argv[2]), 10
        except ValueError:
            pass
    if len(sys.argv) == 2:
        key = sys.argv[1].upper()
        for z in zones:
            if z["id"].upper() == key:
                s = z["shapes"][0]
                if s["type"] == "circle":
                    return s["c"][0]/1e5, s["c"][1]/1e5, 11
                lats = [p[0]/1e5 for p in s["pts"]]
                lons = [p[1]/1e5 for p in s["pts"]]
                return sum(lats)/len(lats), sum(lons)/len(lons), 11
        print(f"  '{sys.argv[1]}' not found, using default center")
    return 30.0, 0.0, 5


def _build_zone_data(zones):
    zone_data = []
    counts = {}

    for z in zones:
        cat = z["cat"]
        zid_int = _make_id(cat, z["id"])
        zid_hex = f"0x{zid_int:08X}"
        floor_m = int(z.get("floor", 0))
        cat_num = CAT_NUM.get(cat, 31)

        for shape in z["shapes"]:
            if shape["type"] == "circle":
                lat = shape["c"][0] / 1e5; lon = shape["c"][1] / 1e5; r = shape["r"]
                ml = 111320.0; mx = ml * math.cos(math.radians(lat))
                dr = r / ml; dlon = r / mx
                rec = {"f": CAT_FULL.get(cat, cat),
                       "tag": CAT_TAG.get(cat, cat.upper()),
                       "zid": zid_hex,
                       "cat": cat_num, "fl": floor_m,
                       "t": "c",
                       "clat": round(lat, 5), "clon": round(lon, 5), "r": r,
                       "b": [round(lat-dr, 4), round(lat+dr, 4),
                             round(lon-dlon, 4), round(lon+dlon, 4)]}
            else:
                pts = [[round(p[0]/1e5, 4), round(p[1]/1e5, 4)] for p in shape["pts"]]
                lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
                rec = {"f": CAT_FULL.get(cat, cat),
                       "tag": CAT_TAG.get(cat, cat.upper()),
                       "zid": zid_hex,
                       "cat": cat_num, "fl": floor_m,
                       "t": "p", "pts": pts,
                       "b": [round(min(lats), 4), round(max(lats), 4),
                             round(min(lons), 4), round(max(lons), 4)]}
            zone_data.append(rec)
            counts[cat] = counts.get(cat, 0) + 1

    return zone_data, counts


def main():
    zones = json.loads(ZONES_ALL.read_text())
    clat, clon, zoom = _get_center(zones)

    m = folium.Map(location=[clat, clon], zoom_start=zoom,
                   tiles=None, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Streets", max_zoom=19).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite", max_zoom=19).add_to(m)

    zone_data, counts = _build_zone_data(zones)

    for cat, cnt in sorted(counts.items()):
        print(f"  {CAT_LABEL.get(cat, cat)}: {cnt}")

    _cat_group = {
        "airport_l":"Global","airport_m":"Global","airport_s":"Global",
        "seaplane":"Global","heliport":"Global","balloonport":"Global",
        "faa_b":"USA","faa_c":"USA","faa_d":"USA",
        "eu_ctr":"EU","eu_atz":"EU","eu_r":"EU","eu_tma":"EU","eu_p":"EU",
        "prison":"Global","stadium":"Global","military":"Global","country":"Global",
    }
    _group_order = ["Global","USA","EU"]
    zone_cats = sorted(
        [{"cat": CAT_NUM[c], "label": CAT_LABEL[c], "group": _cat_group.get(c,"Global")}
         for c in CAT_LABEL],
        key=lambda x: (_group_order.index(x["group"]), x["cat"])
    )
    zone_data_json = json.dumps(zone_data, separators=(',', ':'))
    zone_cats_json = json.dumps(zone_cats, separators=(',', ':'))

    m.get_root().html.add_child(
        folium.Element(make_extras(m.get_name(), zone_data_json, zone_cats_json))
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(OUT))
    print(f"\nSaved → {OUT}")
    webbrowser.open(f"file://{OUT.resolve()}")


main()
