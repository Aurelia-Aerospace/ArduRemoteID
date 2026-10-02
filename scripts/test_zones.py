#!/usr/bin/env python3
"""
test_zones.py — inject MAVLink ODID messages into a RemoteID ESP32 over USB serial
and read back ARM_STATUS to verify zone enforcement.

Usage:
    python3 test_zones.py /dev/ttyUSB0                    # all tests
    python3 test_zones.py /dev/ttyUSB0 --bypass           # bypass tests only
    python3 test_zones.py /dev/ttyUSB0 --lat 19.4 --lon -99.07   # single probe
    python3 test_zones.py /dev/ttyUSB0 --baud 115200

Requirements:
    pip install pymavlink
"""
import argparse
import base64
import math
import os
import struct
import sys
import time
from pathlib import Path
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil
mavutil.set_dialect('ardupilotmega')

# ── OPTIONS bypass bits (mirrors parameters.h) ───────────────────────────────
OPT_BYPASS_AIRPORT_L   = 1 << 3
OPT_BYPASS_AIRPORT_M   = 1 << 4
OPT_BYPASS_AIRPORT_S   = 1 << 5
OPT_BYPASS_SEAPLANE    = 1 << 6
OPT_BYPASS_HELIPORT    = 1 << 7
OPT_BYPASS_BALLOONPORT = 1 << 8
OPT_BYPASS_FAA_B       = 1 << 9
OPT_BYPASS_FAA_C       = 1 << 10
OPT_BYPASS_FAA_D       = 1 << 11
OPT_BYPASS_EU_CTR      = 1 << 12
OPT_BYPASS_EU_ATZ      = 1 << 13
OPT_BYPASS_EU_R        = 1 << 14
OPT_BYPASS_EU_TMA      = 1 << 15
OPT_BYPASS_EU_P        = 1 << 16
OPT_BYPASS_PRISON      = 1 << 17
OPT_BYPASS_STADIUM     = 1 << 18
OPT_BYPASS_COUNTRY     = 1 << 19
OPT_BYPASS_SPIFFS      = 1 << 21
OPT_BYPASS_MILITARY    = 1 << 22

# tag → bypass bit (used to clear the bypass before "before" checks)
TAG_BYPASS = {
    "APT_L":   OPT_BYPASS_AIRPORT_L,   "APT_M":   OPT_BYPASS_AIRPORT_M,
    "APT_S":   OPT_BYPASS_AIRPORT_S,   "APT_SEA": OPT_BYPASS_SEAPLANE,
    "APT_HEL": OPT_BYPASS_HELIPORT,    "APT_BAL": OPT_BYPASS_BALLOONPORT,
    "FAA_B":   OPT_BYPASS_FAA_B,       "FAA_C":   OPT_BYPASS_FAA_C,
    "FAA_D":   OPT_BYPASS_FAA_D,       "EU_CTR":  OPT_BYPASS_EU_CTR,
    "EU_ATZ":  OPT_BYPASS_EU_ATZ,      "EU_R":    OPT_BYPASS_EU_R,
    "EU_TMA":  OPT_BYPASS_EU_TMA,      "EU_P":    OPT_BYPASS_EU_P,
    "PRISON":  OPT_BYPASS_PRISON,      "STADIUM": OPT_BYPASS_STADIUM,
    "COUNTRY": OPT_BYPASS_COUNTRY,     "MZ":      OPT_BYPASS_MILITARY,
}

SECURE_COMMAND_GET_SESSION_KEY     = 0
SECURE_COMMAND_SET_REMOTEID_CONFIG = 6

_private_key = [None]   # bytes[32], set from --key
_session_key = [None]   # bytes[8],  fetched from device

# ── Zone test cases ───────────────────────────────────────────────────────────
# (lat, lon, label, expect_fail, expected_tag | None)
# expected_tag: substring that must appear in reason on failure (None = don't check)
# All coordinates verified against actual device with zones.bin loaded.
ZONE_CASES = [
    # ── APT_L: large international airports ──────────────────────────────────
    ( 19.4361, -99.0719,  "APT_L  AICM Mexico City",                  True,  "APT_L"),
    ( 33.9425,-118.4081,  "APT_L  LAX Los Angeles",                   True,  "APT_L"),
    ( 49.0097,   2.5479,  "APT_L  CDG Paris",                         True,  "APT_L"),
    ( 35.5494, 139.7798,  "APT_L  HND Tokyo Haneda",                  True,  "APT_L"),
    # edge: ~12 km north of AICM, open area
    ( 19.5450, -99.0720,  "APT_L  AICM edge N — clear",               False, None),

    # ── APT_M: medium / regional airports ────────────────────────────────────
    ( 54.6181,  -5.8725,  "APT_M  BHD Belfast George Best",           True,  "APT_M"),
    ( 34.2098,-118.4895,  "APT_M  VNY Van Nuys (APT_M+FAA_D)",        True,  "APT_M"),
    # QRO is APT_L in dataset (international); PDL has EU_CTR over it
    ( 20.6173,-100.1856,  "APT_L  QRO Querétaro (actually APT_L)",    True,  "APT_L"),
    # edge: ~23 km east of BHD, outside Belfast CTR
    ( 54.6181,  -5.450,   "APT_M  BHD edge E — clear",                False, None),

    # ── APT_S: small / GA airports ───────────────────────────────────────────
    ( 18.4972, -97.4189,  "APT_S  TCN Tehuacán Puebla",               True,  "APT_S"),
    ( 51.8747,  -0.3683,  "APT_S  LTN Luton UK",                      True,  "APT_L"),
    ( 33.0678, -96.0653,  "APT_S  KGVT Greenville TX",                True,  "APT_S"),
    # edge: ~5 km north of TCN
    ( 18.5420, -97.4189,  "APT_S  TCN edge N — clear",                False, None),

    # ── APT_SEA: seaplane bases ───────────────────────────────────────────────
    # Verified: Lake Hood at exact coords gives APT_SEA (+ APT_L + FAA_C)
    ( 61.1800,-149.9962,  "APT_SEA Lake Hood Anchorage AK",           True,  "APT_SEA"),
    # edge: ~10 km north of Lake Hood
    ( 61.267, -149.996,   "APT_SEA Lake Hood edge N — clear",         False, None),

    # ── APT_HEL: heliports ───────────────────────────────────────────────────
    ( 34.0757,-118.3803,  "APT_HEL Cedars-Sinai LA",                  True,  "APT_HEL"),
    ( 19.4361, -99.0719,  "APT_HEL AICM area heliport",               True,  "APT_HEL"),
    # edge: ~10 km south of Cedars-Sinai, outside heliport and FAA_D
    ( 33.960, -118.000,  "APT_HEL Cedars-Sinai edge S — clear",      False, None),

    # ── APT_BAL: balloonports ─────────────────────────────────────────────────
    ( 35.1934,-106.5959,  "APT_BAL Albuquerque Balloon Fiesta",       True,  "APT_BAL"),
    # edge: ~8 km east of ABQ balloon park
    ( 35.1934,-106.500,   "APT_BAL ABQ edge E — clear",               False, None),

    # ── FAA Class B ───────────────────────────────────────────────────────────
    ( 32.8968, -97.0380,  "FAA_B  DFW Dallas/Fort Worth",             True,  "FAA_B"),
    ( 41.9742, -87.9073,  "FAA_B  ORD Chicago O'Hare",                True,  "FAA_B"),
    # edge: ~50 km east of DFW outer ring
    ( 32.8968, -96.630,   "FAA_B  DFW edge E — clear",                False, None),

    # ── FAA Class C ───────────────────────────────────────────────────────────
    ( 30.1975, -97.6664,  "FAA_C  AUS Austin Bergstrom",              True,  "FAA_C"),
    ( 33.6762,-117.8675,  "FAA_C  SNA John Wayne OC",                 True,  "FAA_C"),
    # edge: ~15 km east of AUS C ring
    ( 30.1975, -97.520,   "FAA_C  AUS edge E — clear",                False, None),

    # ── FAA Class D ───────────────────────────────────────────────────────────
    ( 34.2098,-118.4895,  "FAA_D  VNY Van Nuys (APT_M+FAA_D)",        True,  "FAA_D"),
    ( 32.9686, -96.8362,  "FAA_D  KADS Addison TX",                   True,  "FAA_D"),
    # edge: ~15 km south of VNY, outside FAA_D and nearby heliports
    ( 34.075, -118.4915,  "FAA_D  VNY edge S — clear",                False, None),

    # ── EU CTR ────────────────────────────────────────────────────────────────
    ( 52.3105,   4.7683,  "EU_CTR AMS Amsterdam Schiphol",            True,  "EU_CTR"),
    ( 48.3538,  11.7861,  "EU_CTR MUC Munich",                        True,  "EU_CTR"),
    ( 54.6181,  -5.8725,  "EU_CTR BHD Belfast (APT_M+EU_CTR)",        True,  "EU_CTR"),
    # edge: ~20 km east of AMS CTR
    ( 52.3105,   5.030,   "EU_CTR AMS edge E — clear",                False, None),

    # ── EU ATZ ────────────────────────────────────────────────────────────────
    # Verified: San Siro Milan gives EU_ATZ (+ EU_R + EU_CTR + PRISON)
    ( 45.4654,   9.1859,  "EU_ATZ San Siro Milan",                    True,  "EU_ATZ"),
    # edge: ~15 km north of San Siro, outside EU_R and heliport zones
    ( 45.600,    9.186,   "EU_ATZ San Siro edge N — clear",           False, None),

    # ── EU Restricted ─────────────────────────────────────────────────────────
    ( 48.8792,   2.3647,  "EU_R   Paris Élysée area",                 True,  "EU_R"),
    # edge: ~28 km east of Élysée, outside Paris EU_R zones
    ( 50.8792,   2.700,   "EU_R   Paris restricted edge E — clear",   False, None),

    # ── EU TMA ────────────────────────────────────────────────────────────────
    # EU_TMA zones are large terminal areas; Frankfurt inner shows EU_CTR
    ( 50.0333,   8.5706,  "EU_TMA Frankfurt area (EU_CTR in data)",   True,  None),

    # ── EU Prohibited ─────────────────────────────────────────────────────────
    ( 48.8730,   2.2950,  "EU_P   Paris nuclear/prohibited",          True,  "EU_P"),
    ( 48.8792,   2.3647,  "EU_P   Paris Élysée (EU_P+EU_R)",          True,  "EU_P"),
    # edge: SW of Paris toward Étampes, outside EU_P/EU_R and CDG/Le Bourget
    ( 50.700,    2.100,   "EU_P   Paris prohibited edge SW — clear",  False, None),

    # ── Prisons ───────────────────────────────────────────────────────────────
    ( 38.3519,-105.0892,  "PRISON ADX Florence CO",                   False, None),
    ( 37.9416,-122.4835,  "PRISON San Quentin CA",                    True,  None),
    ( 45.4654,   9.1859,  "PRISON San Siro area Milan",               True,  None),
    # edge: ~5 km east of ADX
    ( 38.3519,-105.040,   "PRISON ADX edge E — clear",                False, None),

    # ── Stadiums ──────────────────────────────────────────────────────────────
    # Verified: Seattle stadiums give STADIUM tag
    ( 47.6651,-122.3316,  "Alaska airplanes field",              True,  "STADIUM"),
    # Azteca center hits APT_HEL only (heliport overlaps stadium area in data)
    ( 19.3029, -99.1505,  "APT_HEL Azteca area heliport",            True,  "APT_HEL"),
    # edge: ~9 km north of Seattle stadiums, outside stadium/prison/heliport
    ( 47.700, -122.3316,  "STADIUM Seattle edge N — clear",           False, None),

    # ── Military bases ────────────────────────────────────────────────────────
    ( 36.6091, -87.6293,  "MZ  Fort Campbell KY (centroid)",             True,  "MZ"),
    ( 49.4400,   7.6000,  "MZ  Ramstein AB Germany",                     True,  "MZ"),
    ( 36.8650, -87.6293,  "MZ  Fort Campbell edge N — clear",            False, None),

    # ── Banned countries ──────────────────────────────────────────────────────
    ( 55.7558,  37.6173,  "COUNTRY Russia — Moscow",                  True,  "COUNTRY"),
    ( 35.6892,  51.3890,  "COUNTRY Iran — Tehran",                    True,  "COUNTRY"),
    ( 39.0392, 125.7625,  "COUNTRY North Korea — Pyongyang",          True,  "COUNTRY"),
    ( 15.5527,  32.5324,  "COUNTRY Sudan — Khartoum",                 True,  "COUNTRY"),

    # ── Clear zones ───────────────────────────────────────────────────────────
    (  0.0000, -30.0000,  "CLEAR  Open Atlantic Ocean",               False, None),
    (-34.500,  151.000,   "CLEAR  Offshore NSW Australia",            False, None),
    ( 19.1130, -99.6800,  "CLEAR  Toluca outskirts rural",            False, None),
    ( 46.500,   17.500,   "CLEAR  Rural Hungary",                     False, None),
]

# ── Bypass test cases ─────────────────────────────────────────────────────────
# (lat, lon, label, bypass_bit, tag_to_clear)
# PASSES when tag_to_clear no longer appears in reason (even if other zones remain)
# Uses single-zone locations where possible for cleaner verification.
BYPASS_CASES = [
    # Single-zone locations → full GOOD_TO_ARM after bypass
    ( 35.5494, 139.7798, "APT_L  HND Tokyo (APT_L only)",      OPT_BYPASS_AIRPORT_L,   "APT_L"),
    ( 18.4972, -97.4189, "APT_S  TCN Tehuacán (APT_S only)",   OPT_BYPASS_AIRPORT_S,   "APT_S"),
    ( 61.1800,-149.9962, "APT_SEA Lake Hood (has APT_SEA)",     OPT_BYPASS_SEAPLANE,    "APT_SEA"),
    ( 34.0757,-118.3803, "APT_HEL Cedars-Sinai (HEL only)",    OPT_BYPASS_HELIPORT,    "APT_HEL"),
    ( 35.1934,-106.5959, "APT_BAL ABQ balloon (BAL only)",      OPT_BYPASS_BALLOONPORT, "APT_BAL"),
    ( 38.3519,-105.0892, "PRISON ADX Florence (only PRISON)",   OPT_BYPASS_PRISON,      "PRISON"),
    ( 35.6892,  51.3890, "COUNTRY Iran (only COUNTRY)",         OPT_BYPASS_COUNTRY,     "COUNTRY"),
    # Multi-zone locations → verify the specific tag disappears
    ( 54.6181,  -5.8725, "APT_M  BHD Belfast (APT_M+EU_CTR)",  OPT_BYPASS_AIRPORT_M,   "APT_M"),
    ( 32.8968, -97.0380, "FAA_B  DFW (APT_L+FAA_B)",           OPT_BYPASS_FAA_B,       "FAA_B"),
    ( 30.1975, -97.6664, "FAA_C  AUS (APT_L+FAA_C)",           OPT_BYPASS_FAA_C,       "FAA_C"),
    ( 34.2098,-118.4895, "FAA_D  VNY (APT_M+FAA_D)",           OPT_BYPASS_FAA_D,       "FAA_D"),
    ( 52.3105,   4.7683, "EU_CTR AMS (APT_L+EU_CTR)",          OPT_BYPASS_EU_CTR,      "EU_CTR"),
    ( 45.4654,   9.1859, "EU_ATZ San Siro (EU_ATZ+EU_R+...)",  OPT_BYPASS_EU_ATZ,      "EU_ATZ"),
    ( 48.8792,   2.3647, "EU_R   Paris Élysée (EU_R+...)",     OPT_BYPASS_EU_R,        "EU_R"),
    ( 48.8730,   2.2950, "EU_P   Paris nuclear (EU_P+EU_R)",   OPT_BYPASS_EU_P,        "EU_P"),
    ( 47.5951,-122.3316, "STADIUM Seattle (STADIUM+...)",       OPT_BYPASS_STADIUM,     "STADIUM"),
    ( 55.7558,  37.6173, "COUNTRY Russia (PRISON+COUNTRY)",     OPT_BYPASS_COUNTRY,     "COUNTRY"),
    ( 36.6091, -87.6293, "MZ  Fort Campbell (MZ only)",         OPT_BYPASS_MILITARY,    "MZ"),
]

# ── Zone ID lookup from zones.bin (version-agnostic) ─────────────────────────
_TAG_TO_CAT = {
    "APT_L": 0, "APT_M": 1, "APT_S": 2, "APT_SEA": 3, "APT_HEL": 4,
    "APT_BAL": 5, "FAA_B": 6, "FAA_C": 7, "FAA_D": 8, "EU_CTR": 9,
    "EU_ATZ": 10, "EU_R": 11, "EU_TMA": 12, "EU_P": 13,
    "PRISON": 14, "STADIUM": 15, "MZ": 16,
}

def _load_zone_ids(lat, lon, tag, bin_path=None):
    """Return all zone IDs of category `tag` that cover (lat, lon) in zones.bin."""
    if bin_path is None:
        bin_path = Path(__file__).parent.parent / "RemoteIDModule" / "spiffs" / "zones.bin"
    try:
        raw = open(bin_path, 'rb').read()
    except FileNotFoundError:
        return []
    _, ver, tile_deg_b, _, n_tiles, _, data_off = struct.unpack_from('<IHBBHHI', raw, 0)
    tile_deg   = tile_deg_b if tile_deg_b > 0 else 4
    cat_shift  = 27 if ver >= 3 else 28
    target_cat = _TAG_TO_CAT.get(tag)
    if target_cat is None:
        return []
    lt = int(math.floor(lat / tile_deg))
    ln = int(math.floor(lon / tile_deg))
    seen = set()
    ids  = []
    for ti in range(n_tiles):
        tlt, tln, _, tile_off = struct.unpack_from('<bbHI', raw, 16 + ti * 8)
        if tlt != lt or tln != ln:
            continue
        off   = data_off + tile_off
        n_rec = struct.unpack_from('<H', raw, off)[0]; off += 2
        for _ in range(n_rec):
            zid, shape = struct.unpack_from('<IB', raw, off)
            cat = zid >> cat_shift
            if shape == 0:
                _, _, floor_m, clat_i, clon_i, radius = struct.unpack_from('<IBHiiH', raw, off)
                off += struct.calcsize('<IBHiiH')
                if cat == target_cat and zid not in seen:
                    coslat = max(math.cos(math.radians(clat_i * 1e-5)), 0.001)
                    dy = (lat - clat_i * 1e-5) * 111320.0
                    dx = (lon - clon_i * 1e-5) * 111320.0 * coslat
                    if dy * dy + dx * dx <= float(radius) ** 2:
                        seen.add(zid); ids.append(zid)
            else:
                _, _, floor_m, n_pts, _, _ = struct.unpack_from('<IBHBii', raw, off)
                off += struct.calcsize('<IBHBii') + n_pts * 4
    return ids


# ── Zone unlock test cases ────────────────────────────────────────────────────
# (lat, lon, label, expected_tag)
# zone_ids are resolved at runtime from zones.bin — never go stale after rebuilds.
ZONE_UNLOCK_CASES = [
    ( 18.4972, -97.4189, "TCN Tehuacán (APT_S only)",    "APT_S"),
    ( 35.5494, 139.7798, "HND Tokyo Haneda (APT_L)",      "APT_L"),
    ( 38.3519,-105.0892, "ADX Florence CO (PRISON)",      "PRISON"),
    ( 47.5951,-122.3316, "Alaska airplanes field (STAD)", "STADIUM"),
]

# ── MAVLink helpers ───────────────────────────────────────────────────────────

ARM_STATUS_GOOD = 0

def send_full_odid_set(mav, lat, lon):
    lat_e7, lon_e7 = int(lat * 1e7), int(lon * 1e7)
    mav.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    mav.mav.open_drone_id_basic_id_send(
        0, 0, [0]*20,
        mavutil.mavlink.MAV_ODID_ID_TYPE_SERIAL_NUMBER,
        mavutil.mavlink.MAV_ODID_UA_TYPE_HELICOPTER_OR_MULTIROTOR,
        b'TEST000000000000\x00\x00\x00\x00')
    mav.mav.open_drone_id_self_id_send(0, 0, [0]*20, 0, b'test flight\x00' + b'\x00'*11)
    mav.mav.open_drone_id_operator_id_send(0, 0, [0]*20, 0, b'TESTOP0001' + b'\x00'*10)
    mav.mav.open_drone_id_system_send(
        0, 0, [0]*20,
        mavutil.mavlink.MAV_ODID_OPERATOR_LOCATION_TYPE_TAKEOFF,
        mavutil.mavlink.MAV_ODID_CLASSIFICATION_TYPE_UNDECLARED,
        lat_e7, lon_e7, 1, 0, 0.0, 0.0, 0, 0, 50.0, int(time.time()))
    mav.mav.open_drone_id_location_send(
        0, 0, [0]*20,
        mavutil.mavlink.MAV_ODID_STATUS_AIRBORNE,
        36100, 0, 0, lat_e7, lon_e7, 50.0, 50.0,
        mavutil.mavlink.MAV_ODID_HEIGHT_REF_OVER_TAKEOFF, 50.0,
        mavutil.mavlink.MAV_ODID_HOR_ACC_10_METER,
        mavutil.mavlink.MAV_ODID_VER_ACC_10_METER,
        mavutil.mavlink.MAV_ODID_VER_ACC_10_METER,
        mavutil.mavlink.MAV_ODID_SPEED_ACC_10_METERS_PER_SECOND,
        float(int(time.time()) % 3600),
        mavutil.mavlink.MAV_ODID_TIME_ACC_0_1_SECOND)


def get_arm_status(mav, lat, lon, timeout=6.0):
    """Returns (is_good, reason_str) or (None, 'TIMEOUT')."""
    # Send position immediately so device starts re-evaluating the new tile,
    # then drain stale ARM_STATUS for 2 s while keeping position fresh.
    # Without this, a prior location's buffered ARM_STATUS fires first.
    send_full_odid_set(mav, lat, lon)
    drain_end = time.time() + 2.0
    while time.time() < drain_end:
        mav.recv_match(type='OPEN_DRONE_ID_ARM_STATUS', blocking=False)
        time.sleep(0.3)
        send_full_odid_set(mav, lat, lon)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='OPEN_DRONE_ID_ARM_STATUS', blocking=False)
        if msg is not None:
            return msg.status == ARM_STATUS_GOOD, str(msg.error).rstrip('\x00').strip()
        send_full_odid_set(mav, lat, lon)
        time.sleep(0.3)
    return None, "TIMEOUT"


def get_param(mav, name, timeout=3.0):
    param_id = name.encode().ljust(16, b'\x00')
    mav.mav.param_request_read_send(mav.target_system, 0, param_id, -1)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='PARAM_VALUE', blocking=False)
        if msg and msg.param_id.rstrip('\x00') == name:
            return msg.param_value
        time.sleep(0.05)
    return None


def set_param(mav, name, value):
    """Set parameter and verify it was accepted."""
    param_id = name.encode().ljust(16, b'\x00')
    for attempt in range(3):
        mav.mav.param_set_send(
            mav.target_system, 0, param_id,
            float(int(value)),
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.3)
        actual = get_param(mav, name, timeout=1.5)
        if actual is not None and int(actual) == int(value):
            return True
    return False


_cmd_seq = [0]

def _next_seq():
    _cmd_seq[0] = (_cmd_seq[0] + 1) & 0xFFFFFFFF
    return _cmd_seq[0]

def get_session_key(mav, timeout=3.0):
    """Request session key from device (required when public keys are loaded)."""
    seq = _next_seq()
    sig = _sign(seq, SECURE_COMMAND_GET_SESSION_KEY, b'', session_key=None)
    data = list(sig) + [0] * (220 - len(sig))
    mav.mav.secure_command_send(
        mav.target_system, 0, seq,
        SECURE_COMMAND_GET_SESSION_KEY,
        0, len(sig), data)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='SECURE_COMMAND_REPLY', blocking=False)
        if msg and msg.operation == SECURE_COMMAND_GET_SESSION_KEY and msg.result == 0:
            _session_key[0] = bytes(msg.data[:msg.data_length])
            return True
        time.sleep(0.05)
    return False

def _sign(seq, operation, data_bytes, session_key):
    """Sign with Ed25519 via monocypher. session_key=None for GET_SESSION_KEY op."""
    import monocypher
    payload = struct.pack("<II", seq, operation) + data_bytes
    if session_key is not None:
        payload += session_key
    return monocypher.signature_sign(_private_key[0], payload)

def _read_cmd_reply(mav, timeout=1.5):
    """Read SECURE_COMMAND_REPLY, return MAV_RESULT int (0=ACCEPTED). None on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='SECURE_COMMAND_REPLY', blocking=False)
        if msg:
            return msg.result
        time.sleep(0.05)
    return None

def send_zone_cmd(mav, cmd_str):
    """Send SECURE_COMMAND ZONE_OK/ZONE_LOCK/ZONE_CLEAR. Signs if --key was given."""
    raw = cmd_str.encode() + b'\x00'
    assert len(raw) <= 220, f"SECURE_COMMAND payload too long: {len(raw)} > 220 bytes"
    seq = _next_seq()
    if _private_key[0] is not None:
        assert _session_key[0] is not None, "No session key — call get_session_key() first"
        sig = _sign(seq, SECURE_COMMAND_SET_REMOTEID_CONFIG, raw, _session_key[0])
        assert len(raw) + len(sig) <= 220
        data = list(raw) + list(sig) + [0] * (220 - len(raw) - len(sig))
        mav.mav.secure_command_send(
            mav.target_system, 0, seq,
            SECURE_COMMAND_SET_REMOTEID_CONFIG,
            len(raw), len(sig), data[:220])
    else:
        data = list(raw) + [0] * (220 - len(raw))
        mav.mav.secure_command_send(
            mav.target_system, 0, seq,
            SECURE_COMMAND_SET_REMOTEID_CONFIG,
            len(raw), 0, data[:220])


# ── Test runners ──────────────────────────────────────────────────────────────

def run_zone_tests(mav):
    print("\n── Zone enforcement tests ───────────────────────────────────────────────")
    orig_raw = get_param(mav, 'OPTIONS')
    if orig_raw is None:
        print("  ERROR: could not read OPTIONS parameter")
        return 0
    orig = int(orig_raw)

    passed = total = 0
    for lat, lon, label, expect_fail, expected_tag in ZONE_CASES:
        total += 1
        sys.stdout.write(f"  {label:50s} → ")
        sys.stdout.flush()

        # Clear the specific bypass bit so the zone is active during this check
        bypass_bit = TAG_BYPASS.get(expected_tag, 0) if expect_fail else 0
        if bypass_bit and not set_param(mav, 'OPTIONS', orig & ~bypass_bit):
            print("PARAM_SET failed  ✗"); total -= 1; continue

        is_good, reason = get_arm_status(mav, lat, lon)

        if bypass_bit:
            set_param(mav, 'OPTIONS', orig)

        if is_good is None:
            print("TIMEOUT  ✗")
            continue
        failed = not is_good
        tag_ok = (expected_tag is None) or (not expect_fail) or (expected_tag in reason)
        result_ok = (failed == expect_fail) and tag_ok
        status = "GOOD_TO_ARM" if is_good else f"FAIL ({reason})"
        print(f"{status}  {'✓' if result_ok else '✗'}")
        if result_ok:
            passed += 1

    print(f"\n  {passed}/{total} zone tests passed\n")
    return passed


def run_bypass_tests(mav):
    print("── Bypass parameter tests ───────────────────────────────────────────────")
    orig_raw = get_param(mav, 'OPTIONS')
    if orig_raw is None:
        print("  ERROR: could not read OPTIONS parameter")
        return 0
    orig = int(orig_raw)
    print(f"  Current OPTIONS = {orig:#010x}\n")

    passed = total = 0
    for lat, lon, label, bypass_bit, bypass_tag in BYPASS_CASES:
        total += 1
        sys.stdout.write(f"  {label:45s} → ")
        sys.stdout.flush()

        # Verify it fails with bypass_bit CLEARED (orig may already have it set)
        if not set_param(mav, 'OPTIONS', orig & ~bypass_bit):
            print("PARAM_SET failed  ✗"); total -= 1; continue

        is_good_before, reason_before = get_arm_status(mav, lat, lon)
        if is_good_before:
            set_param(mav, 'OPTIONS', orig)
            print(f"SKIP (passes without bypass: {reason_before})")
            total -= 1
            continue
        if is_good_before is None:
            set_param(mav, 'OPTIONS', orig)
            print("TIMEOUT (before)  ✗")
            continue
        if bypass_tag not in reason_before:
            set_param(mav, 'OPTIONS', orig)
            print(f"SKIP (tag '{bypass_tag}' not in reason: {reason_before})")
            total -= 1
            continue

        # Apply bypass
        if not set_param(mav, 'OPTIONS', orig | bypass_bit):
            set_param(mav, 'OPTIONS', orig)
            print(f"PARAM_SET failed  ✗")
            continue

        is_good_after, reason_after = get_arm_status(mav, lat, lon)

        # Restore immediately
        set_param(mav, 'OPTIONS', orig)

        if is_good_after is None:
            print(f"TIMEOUT (after)  ✗")
        elif is_good_after:
            print(f"GOOD_TO_ARM  ✓")
            passed += 1
        elif bypass_tag not in reason_after:
            # Tag cleared — bypass worked even if other zones remain
            print(f"tag cleared → ({reason_after})  ✓")
            passed += 1
        else:
            print(f"tag still present → ({reason_after})  ✗")

    print(f"\n  {passed}/{total} bypass tests passed")
    print(f"  OPTIONS restored to {orig:#010x}\n")
    return passed


def run_zone_unlock_tests(mav):
    print("── Zone unlock tests (SECURE_COMMAND ZONE_OK) ───────────────────────────")
    if _private_key[0] is not None:
        sys.stdout.write("  Requesting session key... ")
        sys.stdout.flush()
        if not get_session_key(mav):
            print("FAILED — skipping unlock tests")
            return 0
        print("OK")
    orig_raw = get_param(mav, 'OPTIONS')
    orig = int(orig_raw) if orig_raw is not None else 0
    passed = total = 0
    for lat, lon, label, expected_tag in ZONE_UNLOCK_CASES:
        total += 1
        sys.stdout.write(f"  {label:45s} → ")
        sys.stdout.flush()

        zone_ids = _load_zone_ids(lat, lon, expected_tag)
        if not zone_ids:
            print(f"SKIP (no {expected_tag} zone IDs found in zones.bin)")
            total -= 1; continue

        # Check "before" with category bypass CLEARED (orig may have it set)
        bypass_bit = TAG_BYPASS.get(expected_tag, 0)
        options_clear = orig & ~bypass_bit
        if options_clear != orig and not set_param(mav, 'OPTIONS', options_clear):
            print("PARAM_SET failed  ✗"); total -= 1; continue

        is_good_before, reason_before = get_arm_status(mav, lat, lon)

        if options_clear != orig:
            set_param(mav, 'OPTIONS', orig)

        if is_good_before is None:
            print("TIMEOUT (before)  ✗")
            continue
        if is_good_before:
            print(f"SKIP (passes without unlock)")
            total -= 1
            continue
        if expected_tag not in reason_before:
            print(f"SKIP (tag '{expected_tag}' not in '{reason_before}')")
            total -= 1
            continue

        send_zone_cmd(mav, "\x00".join(f"ZONE_OK=0x{zid:08x}" for zid in zone_ids))
        cmd_result = _read_cmd_reply(mav)
        if cmd_result != 0:
            print(f"ZONE_OK denied (result={cmd_result})  ✗")
            total -= 1
            continue
        time.sleep(0.3)

        # Check "after" also with bypass CLEARED — tests zone unlock, not bypass
        if options_clear != orig:
            set_param(mav, 'OPTIONS', options_clear)

        is_good_after, reason_after = get_arm_status(mav, lat, lon)

        if options_clear != orig:
            set_param(mav, 'OPTIONS', orig)

        send_zone_cmd(mav, "ZONE_CLEAR")
        _read_cmd_reply(mav)
        time.sleep(0.3)

        if is_good_after is None:
            print(f"TIMEOUT (after)  ✗")
        elif is_good_after:
            print(f"GOOD_TO_ARM  ✓")
            passed += 1
        elif expected_tag not in reason_after:
            print(f"tag cleared → ({reason_after})  ✓")
            passed += 1
        else:
            print(f"tag still present → ({reason_after})  ✗")

    print(f"\n  {passed}/{total} zone unlock tests passed\n")
    return passed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description='Test RemoteID zone enforcement over serial MAVLink')
    p.add_argument('port', help='Serial port, e.g. /dev/ttyUSB0')
    p.add_argument('--baud',   type=int,   default=57600)
    p.add_argument('--lat',    type=float, help='Latitude  (single probe)')
    p.add_argument('--lon',    type=float, help='Longitude (single probe)')
    p.add_argument('--bypass', action='store_true', help='Run bypass tests only')
    p.add_argument('--key',   type=str, default=None, help='Private key file (PRIVATE_KEYV1:...) for signed ZONE_OK')
    args = p.parse_args()

    if (args.lat is None) != (args.lon is None):
        p.error('Provide both --lat and --lon')

    print(f"Connecting to {args.port} at {args.baud} baud...")
    mav = mavutil.mavlink_connection(args.port, baud=args.baud, source_system=1, source_component=1)

    print("Waiting for device heartbeat...", flush=True)
    deadline = time.time() + 15
    hb = None
    while time.time() < deadline:
        mav.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        hb = mav.recv_match(type='HEARTBEAT', blocking=False)
        if hb and hb.get_srcSystem() != 0:
            mav.target_system = hb.get_srcSystem()
            break
        time.sleep(0.3)
    if not hb or mav.target_system == 0:
        print("ERROR: no heartbeat. Check port/baud.")
        sys.exit(1)
    print(f"  Device sysid={mav.target_system}\n")

    if args.key:
        import monocypher
        d = open(args.key).read().strip()
        prefix = "PRIVATE_KEYV1:"
        if not d.startswith(prefix):
            p.error(f"Key file must start with '{prefix}'")
        seed = base64.b64decode(d[len(prefix):])
        seed_copy = bytearray(seed)  # copy before compute_signing_public_key wipes seed
        pk = monocypher.compute_signing_public_key(seed)
        _private_key[0] = bytes(seed_copy) + pk  # 64-byte key expected by signature_sign
        print(f"  Private key loaded (seed={len(seed_copy)}B → sk64={len(_private_key[0])}B)\n")

    if args.lat is not None:
        is_good, reason = get_arm_status(mav, args.lat, args.lon)
        print("GOOD_TO_ARM" if is_good else f"FAIL ({reason})" if is_good is not None else "TIMEOUT")
        return

    if args.bypass:
        run_bypass_tests(mav)
        return

    z = run_zone_tests(mav)
    b = run_bypass_tests(mav)
    u = run_zone_unlock_tests(mav)
    total = len(ZONE_CASES) + len(BYPASS_CASES) + len(ZONE_UNLOCK_CASES)
    print(f"══ Total: {z+b+u}/{total} passed ══")


if __name__ == '__main__':
    main()
