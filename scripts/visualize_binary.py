#!/usr/bin/env python3
"""
Visualize zones.bin on an interactive map.

Hover: full zone type · ESP32 tag · zone ID (all overlapping zones).
Right-click visible zone: hide it.  Right-click hidden zone location: restore it.
Ctrl+Z / Restore button: restore all hidden zones.

Usage:
  python visualize_binary.py              (world view)
  python visualize_binary.py LAT LON      (centered on coordinates)
"""
import json, math, struct, sys, webbrowser
from pathlib import Path
import folium
from _zone_viewer import make_extras

HERE  = Path(__file__).parent
RM    = HERE.parent / "RemoteIDModule"
ZONES = RM / "spiffs" / "zones.bin"
OUT   = HERE / "test_result" / "zones_binary_map.html"
MAGIC = 0x5A4F4E45

CAT_FULL = {
     0: "Large airport",    1: "Medium airport",   2: "Small airport",
     3: "Seaplane base",    4: "Heliport",          5: "Balloonport",
     6: "FAA Class B",      7: "FAA Class C",        8: "FAA Class D",
     9: "EU CTR",          10: "EU ATZ",            11: "EU Restricted",
    12: "EU TMA",          13: "EU Prohibited",     14: "Prison",
    15: "Stadium",         16: "Military base",     17: "Banned country",
}
CAT_TAG = {
     0: "APT_L",  1: "APT_M",  2: "APT_S",  3: "APT_SEA", 4: "APT_HEL", 5: "APT_BAL",
     6: "FAA_B",  7: "FAA_C",  8: "FAA_D",
     9: "EU_CTR",10: "EU_ATZ",11: "EU_R",  12: "EU_TMA",  13: "EU_P",
    14: "PRISON",15: "STADIUM",16: "MZ",   17: "COUNTRY",
}
CAT_LABEL = {
     0: "Large airport",      1: "Medium airport",
     2: "Small airport",      3: "Seaplane base",
     4: "Heliport",           5: "Balloonport",
     6: "FAA Class B",        7: "FAA Class C",
     8: "FAA Class D",        9: "EU CTR",
    10: "EU ATZ",            11: "EU Restricted",
    12: "EU TMA",            13: "EU Prohibited",
    14: "Prison",            15: "Stadium",
    16: "Military base",     17: "Banned country",
}


def _read_zones(data):
    """Yield (cat, zid, floor_m, shape, geo) deduplicated."""
    magic, _, _, _, n_tiles, _, data_off = struct.unpack_from('<IHBBHHI', data, 0)
    if magic != MAGIC:
        raise ValueError(f"Bad magic {magic:#010x}")
    seen = set()
    for i in range(n_tiles):
        _, _, _, t_off = struct.unpack_from('<bbHI', data, 16 + i*8)
        pos = data_off + t_off
        n_z = struct.unpack_from('<H', data, pos)[0]; pos += 2
        for _ in range(n_z):
            zid, sh = struct.unpack_from('<IB', data, pos)
            cat = (zid >> 27) & 0x1F
            if sh == 0:
                size = 17
                rec = data[pos:pos+size]
                if rec not in seen:
                    seen.add(rec)
                    _, _, floor_m, lat5, lon5, r = struct.unpack_from('<IBHiiH', data, pos)
                    yield cat, zid, floor_m, 'circle', (lat5/1e5, lon5/1e5, r)
            else:
                n_pts = data[pos+7]; size = 16 + n_pts*4
                rec = data[pos:pos+size]
                if rec not in seen:
                    seen.add(rec)
                    _, _, floor_m, _, clat5, clon5 = struct.unpack_from('<IBHBii', data, pos)
                    ds = struct.unpack_from('<' + 'h'*(n_pts*2), data, pos+16)
                    clat = clat5/1e5; clon = clon5/1e5
                    mx = math.cos(math.radians(clat)) or 0.001
                    ring = [[round(clat + ds[j*2]*10/111320, 4),
                             round(clon + ds[j*2+1]*10/(111320*mx), 4)] for j in range(n_pts)]
                    yield cat, zid, floor_m, 'polygon', ring
            pos += size
    print(f"  {len(seen)} unique records")


def _read_countries(data):
    _, _, _, _, n_tiles, _, data_off = struct.unpack_from('<IHBBHHI', data, 0)
    end = 0
    for i in range(n_tiles):
        _, _, _, t_off = struct.unpack_from('<bbHI', data, 16 + i*8)
        pos = data_off + t_off
        n = struct.unpack_from('<H', data, pos)[0]; pos += 2
        for _ in range(n):
            sh = data[pos+4]
            pos += 17 if sh == 0 else 16 + data[pos+7]*4
        end = max(end, pos)
    if end + 2 > len(data):
        return
    n_polys = struct.unpack_from('<H', data, end)[0]; pos = end + 2
    print(f"  {n_polys} country polygons")
    for _ in range(n_polys):
        n_pts = struct.unpack_from('<H', data, pos)[0]; pos += 2
        ring = []
        for _ in range(n_pts):
            lat5, lon5 = struct.unpack_from('<ii', data, pos); pos += 8
            ring.append([round(lat5/1e5, 4), round(lon5/1e5, 4)])
        yield ring


def _build_zone_data(data):
    zone_data = []
    counts = {}

    for cat, zid, floor_m, stype, geo in _read_zones(data):
        if stype == 'circle':
            lat, lon, r = geo
            ml = 111320.0; mx = ml * math.cos(math.radians(lat))
            dr = r / ml; dlon = r / mx
            rec = {"f": CAT_FULL.get(cat, f"cat{cat}"),
                   "tag": CAT_TAG.get(cat, f"C{cat}"),
                   "zid": f"0x{zid:08X}",
                   "cat": cat, "fl": floor_m,
                   "t": "c",
                   "clat": round(lat, 5), "clon": round(lon, 5), "r": r,
                   "b": [round(lat-dr, 4), round(lat+dr, 4),
                         round(lon-dlon, 4), round(lon+dlon, 4)]}
        else:
            ring = geo
            lats = [p[0] for p in ring]; lons = [p[1] for p in ring]
            rec = {"f": CAT_FULL.get(cat, f"cat{cat}"),
                   "tag": CAT_TAG.get(cat, f"C{cat}"),
                   "zid": f"0x{zid:08X}",
                   "cat": cat, "fl": floor_m,
                   "t": "p", "pts": ring,
                   "b": [round(min(lats), 4), round(max(lats), 4),
                         round(min(lons), 4), round(max(lons), 4)]}
        zone_data.append(rec)
        counts[cat] = counts.get(cat, 0) + 1

    for ring in _read_countries(data):
        if not ring:
            continue
        lats = [p[0] for p in ring]; lons = [p[1] for p in ring]
        rec = {"f": "Banned country", "tag": "COUNTRY", "zid": "N/A",
               "cat": 17, "fl": 0, "t": "p", "pts": ring,
               "b": [round(min(lats), 4), round(max(lats), 4),
                     round(min(lons), 4), round(max(lons), 4)]}
        zone_data.append(rec)
        counts[17] = counts.get(17, 0) + 1

    return zone_data, counts


def main():
    clat, clon, zoom = 30.0, 0.0, 5
    if len(sys.argv) == 3:
        try:
            clat, clon, zoom = float(sys.argv[1]), float(sys.argv[2]), 10
        except ValueError:
            pass

    # Map with no tile layers initially (we'll add two)
    m = folium.Map(location=[clat, clon], zoom_start=zoom,
                   tiles=None, prefer_canvas=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Streets", max_zoom=19).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite", max_zoom=19).add_to(m)
    # Layer control is created in JS (unified base maps + zone categories)

    print(f"Reading {ZONES}…")
    data = ZONES.read_bytes()
    zone_data, counts = _build_zone_data(data)

    for cat, cnt in sorted(counts.items()):
        print(f"  {CAT_LABEL.get(cat, f'cat{cat}')}: {cnt}")

    _cat_group = {
        0:"Global",1:"Global",2:"Global",3:"Global",4:"Global",5:"Global",
        6:"USA",7:"USA",8:"USA",
        9:"EU",10:"EU",11:"EU",12:"EU",13:"EU",
        14:"Global",15:"Global",16:"Global",17:"Global",
    }
    _group_order = ["Global","USA","EU"]
    zone_cats = sorted(
        [{"cat": c, "label": CAT_LABEL[c], "group": _cat_group.get(c, "Global")}
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
