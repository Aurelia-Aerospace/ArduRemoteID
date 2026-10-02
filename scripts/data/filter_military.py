#!/usr/bin/env python3
"""
Filter military_raw.json → military_filtered.json (unified zone format).

Polygon features are simplified to ≤24 pts (binary max).
Point-only features use type-based circle radii.
"""
import json, math
from pathlib import Path

HERE    = Path(__file__).parent
RM      = HERE.parent.parent / "RemoteIDModule"
RAW_IN  = RM / "data" / "raw"  / "military_raw.json"
OUT     = RM / "data" / "filtered" / "military_filtered.json"

MAX_PTS = 200        # high-res for visualize_zones.py; build_binary.py reduces further
MIN_EXTENT_M = 300   # skip zones whose bounding box is smaller than this in all dimensions

# Default circle radius per military type (metres)
RADIUS = {
    "base":          1500,
    "airbase":       3000,
    "airfield":      2000,
    "naval_base":    2000,
    "training_area": 10000,
    "range":         10000,
}

# ── Ramer-Douglas-Peucker ─────────────────────────────────────────────────────

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]; bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    denom  = math.hypot(dx, dy) or 1
    max_d, idx = 0, 0
    for i, (px, py) in enumerate(pts[1:-1], 1):
        d = abs(dy * px - dx * py + bx * ay - by * ax) / denom
        if d > max_d:
            max_d, idx = d, i
    if max_d > eps:
        return rdp(pts[:idx+1], eps)[:-1] + rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]

def simplify_poly(pts, max_pts=MAX_PTS):
    """[(lat, lon), ...] → simplified list, ≤max_pts points."""
    lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
    dlat = (max(lats) - min(lats)) * 111320
    dlon = (max(lons) - min(lons)) * 111320 * math.cos(math.radians(sum(lats) / len(lats)))
    diag = math.hypot(dlat, dlon) or 1
    eps  = max(diag * 0.005, 1) / 111320
    simplified = rdp(pts, eps)
    if len(simplified) < 4:  # RDP collapsed it
        step = max(1, len(pts) // max_pts)
        simplified = pts[::step]
    if len(simplified) > max_pts:
        step = math.ceil(len(simplified) / max_pts)
        simplified = simplified[::step][:max_pts]
    return simplified

def to_lat5(pts):
    """[(lat, lon)] → [[lat5, lon5]] integers."""
    return [[round(p[0] * 1e5), round(p[1] * 1e5)] for p in pts]

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    raw  = json.loads(RAW_IN.read_text())
    feats = raw["features"]
    out  = []
    counts = {"polygon": 0, "circle": 0}

    for f in feats:
        fid   = f["id"]
        name  = f.get("name", "")
        mtype = f.get("mtype", "base")
        la, lo = f["lat"], f["lon"]
        poly  = f.get("polygon")

        if poly and len(poly) >= 3:
            pts = [(p[0], p[1]) for p in poly]
            lats = [p[0] for p in pts]; lons = [p[1] for p in pts]
            clat = sum(lats) / len(lats)
            dlat_m = (max(lats) - min(lats)) * 111320
            dlon_m = (max(lons) - min(lons)) * 111320 * math.cos(math.radians(clat))
            if max(dlat_m, dlon_m) < MIN_EXTENT_M:
                continue
            simplified = simplify_poly(pts)
            shape = {"type": "polygon", "pts": to_lat5(simplified)}
            counts["polygon"] += 1
        else:
            r   = RADIUS.get(mtype, 1500)
            shape = {"type": "circle",
                     "c": [round(la * 1e5), round(lo * 1e5)],
                     "r": r}
            counts["circle"] += 1

        out.append({
            "cat":    "military",
            "id":     fid,
            "name":   name,
            "floor":  0,
            "shapes": [shape],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"  military: {len(out)} zones "
          f"({counts['polygon']} polygon, {counts['circle']} circle)"
          f"  → {OUT.name}  ({OUT.stat().st_size // 1024} KB)")

main()
