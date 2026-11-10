#!/usr/bin/env python3
"""zone_id stability: python3 scripts/test_zone_ids.py (no data files needed)."""
from build_binary import assign_ids, make_id, CAT_NUM

def prison(lat5, lon5):
    return {"cat": "prison", "id": f"{lat5},{lon5}", "shapes": [{"type": "circle", "c": [lat5, lon5], "r": 400}]}

def apt(key):
    return {"cat": "airport_s", "id": key, "shapes": [{"type": "circle", "c": [0, 0], "r": 1}]}

P = CAT_NUM["prison"]
reg = assign_ids([prison(2066000, -10330000), apt("KJFK")], {})
pid, jfk = reg["prison|2066000,-10330000"][0], reg["airport_s|KJFK"][0]
assert pid == make_id(P, "2066000,-10330000") and jfk == make_id(CAT_NUM["airport_s"], "KJFK")  # first build = plain crc

# rebuild, same data: same ids
assert assign_ids([prison(2066000, -10330000), apt("KJFK")], dict(reg)) == reg

# prison moved 100 m (new key): keeps its id, old key retired
reg2 = assign_ids([prison(2066090, -10330000), apt("KJFK")], dict(reg))
assert reg2["prison|2066090,-10330000"][0] == pid and "prison|2066000,-10330000" not in reg2

# moved 1 km: a new zone, new id; the old id is never reused
reg3 = assign_ids([prison(2066900, -10330000)], dict(reg))
assert reg3["prison|2066900,-10330000"][0] != pid

# the same key elsewhere later can't take a retired id either
reg4 = assign_ids([prison(2066000, -10330000)], {"x|y": (make_id(P, "2066000,-10330000"), None)})
assert reg4["prison|2066000,-10330000"][0] != make_id(P, "2066000,-10330000")

# crc collision: both zones get distinct ids, and the bumped one stays bumped
reg5 = assign_ids([apt("A"), apt("B")], {"airport_s|A": (make_id(CAT_NUM["airport_s"], "B"), None)})
assert reg5["airport_s|A"][0] != reg5["airport_s|B"][0]
assert assign_ids([apt("A"), apt("B")], dict(reg5)) == reg5
print("zone_id: OK")
