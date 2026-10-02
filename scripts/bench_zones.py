#!/usr/bin/env python3
"""
bench_zones.py — benchmark zone scan performance on a live ESP32-S3 RemoteID device.

Reports per point (averaged over --reps runs):
  scan_us   — firmware scan time (micros), via NAMED_VALUE_FLOAT (requires rebuild w/ OPTIONS_BENCH_MODE)
  rtt_ms    — Python round-trip: last send → ARM_STATUS received
  free_heap — free heap bytes after scan
  min_heap  — historical minimum free heap (watermark)

Usage:
    python3 bench_zones.py /dev/ttyUSB0 [--baud 57600] [--reps 3]

Requirements:
    pip install pymavlink
"""
import argparse, datetime, json, os, sys, time
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil
mavutil.set_dialect('ardupilotmega')

OPT_BENCH_MODE = 1 << 20

# (lat, lon, label, tile_4deg)
BENCH_POINTS = [
    # ── Baseline ─────────────────────────────────────────────────────────────
    (  0.0000, -30.0000, "Océano Atlántico (baseline)",          "empty"),
    # ── Tiles más densos ─────────────────────────────────────────────────────
    ( 35.6762, 139.6503, "Tokyo — 1430 zonas",                   "JP(32,136)"),
    ( 40.7789, -73.8717, "NYC LaGuardia — 1306 zonas",           "NE-US(40,-76)"),
    ( 33.9425, -118.408, "LAX Los Angeles — 1250 zonas",         "SoCal(32,-120)"),
    ( 48.3538,  11.7861, "Munich — 1134 zonas",                  "C-EU(48,8)"),
    (-23.5480, -46.6380, "São Paulo — 957 zonas",                "BR(-24,-48)"),
    # ── Cruce de tile (mide costo de swap) ───────────────────────────────────
    ( 43.9000, -75.0000, "Tile NE-US — justo dentro (lat 44)",   "NE-US(40,-76)"),
    ( 44.1000, -75.0000, "Tile NE-US — justo fuera  (lat 44)",   "NE-US(44,-76)"),
    ( 35.9900, 139.9900, "Tile Japón — justo dentro  (lat 36)",  "JP(32,136)"),
    ( 36.0100, 140.0100, "Tile Japón — justo fuera   (lat 36)",  "JP(36,140)"),
    # ── Zona ligera (1 sola zona) ─────────────────────────────────────────────
    ( 38.3519, -105.089, "ADX Florence CO (solo PRISON)",        "US(36,-108)"),
    ( 18.4972,  -97.419, "TCN Tehuacán (solo APT_S)",            "MX(16,-100)"),
]


def send_full_odid_set(mav, lat, lon):
    lat_e7, lon_e7 = int(lat * 1e7), int(lon * 1e7)
    mav.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    mav.mav.open_drone_id_basic_id_send(
        0, 0, [0]*20,
        mavutil.mavlink.MAV_ODID_ID_TYPE_SERIAL_NUMBER,
        mavutil.mavlink.MAV_ODID_UA_TYPE_HELICOPTER_OR_MULTIROTOR,
        b'BENCH00000000000\x00\x00\x00\x00')
    mav.mav.open_drone_id_self_id_send(0, 0, [0]*20, 0, b'bench\x00' + b'\x00'*17)
    mav.mav.open_drone_id_operator_id_send(0, 0, [0]*20, 0, b'BENCHOP001' + b'\x00'*10)
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


def get_param(mav, name, timeout=3.0):
    mav.mav.param_request_read_send(mav.target_system, 0,
                                    name.encode().ljust(16, b'\x00'), -1)
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='PARAM_VALUE', blocking=False)
        if msg and msg.param_id.rstrip('\x00') == name:
            return msg.param_value
        time.sleep(0.05)
    return None


def set_param(mav, name, value):
    for _ in range(3):
        mav.mav.param_set_send(
            mav.target_system, 0, name.encode().ljust(16, b'\x00'),
            float(int(value)), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.3)
        v = get_param(mav, name, timeout=1.5)
        if v is not None and int(v) == int(value):
            return True
    return False


TYPES = ['OPEN_DRONE_ID_ARM_STATUS', 'NAMED_VALUE_FLOAT']

def bench_point(mav, lat, lon, timeout=4.0):
    """Send coords, collect ARM_STATUS + NVF. Returns (ok, reason, rtt_ms, nvf_dict)."""
    # Drain stale messages
    send_full_odid_set(mav, lat, lon)
    drain_end = time.time() + 1.5
    while time.time() < drain_end:
        mav.recv_match(type=TYPES, blocking=False)
        time.sleep(0.1)
        send_full_odid_set(mav, lat, lon)

    send_full_odid_set(mav, lat, lon)
    t0 = time.time()

    arm = None
    nvf = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type=TYPES, blocking=False)
        if msg:
            mt = msg.get_type()
            if mt == 'OPEN_DRONE_ID_ARM_STATUS' and arm is None:
                arm = (msg.status == 0,
                       str(msg.error).rstrip('\x00').strip(),
                       (time.time() - t0) * 1000)
            elif mt == 'NAMED_VALUE_FLOAT':
                nvf[msg.name.rstrip('\x00')] = msg.value
        if arm and len(nvf) >= 3:
            break
        send_full_odid_set(mav, lat, lon)
        time.sleep(0.1)

    return arm, nvf


def main():
    p = argparse.ArgumentParser(description='Benchmark zone scan on ESP32-S3 RemoteID')
    p.add_argument('port')
    p.add_argument('--baud', type=int, default=57600)
    p.add_argument('--reps', type=int, default=3)
    args = p.parse_args()

    print(f"Conectando a {args.port} @ {args.baud}...")
    mav = mavutil.mavlink_connection(args.port, baud=args.baud,
                                     source_system=1, source_component=1)
    deadline = time.time() + 15
    while time.time() < deadline:
        mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                               mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        hb = mav.recv_match(type='HEARTBEAT', blocking=False)
        if hb and hb.get_srcSystem() != 0:
            mav.target_system = hb.get_srcSystem(); break
        time.sleep(0.3)
    else:
        print("ERROR: sin heartbeat"); sys.exit(1)
    print(f"  Device sysid={mav.target_system}\n")

    orig_raw = get_param(mav, 'OPTIONS')
    if orig_raw is None:
        print("ERROR: no se pudo leer OPTIONS"); sys.exit(1)
    orig = int(orig_raw)

    bench_mode = bool(orig & OPT_BENCH_MODE)
    if not bench_mode:
        if not set_param(mav, 'OPTIONS', orig | OPT_BENCH_MODE):
            print("WARN: no se pudo activar BENCH_MODE — scan_us/heap no disponibles")
        else:
            bench_mode = True
            print("  Bench mode activado (OPTIONS bit 20)\n")

    has_nvf = bench_mode
    hdr = f"{'Punto':<46} {'tile':>12}  {'scan_us':>8}  {'rtt_ms':>7}  {'free_KB':>7}  {'min_KB':>7}  resultado"
    print(hdr)
    print("─" * len(hdr))

    all_scan, all_rtt, all_free, all_min = [], [], [], []
    prev_tile = None
    rows = []

    for lat, lon, label, tile in BENCH_POINTS:
        swap = (prev_tile is not None and tile != prev_tile)
        prev_tile = tile

        scans, rtts, frees, mins = [], [], [], []
        last_reason = ""
        for _ in range(args.reps):
            arm, nvf = bench_point(mav, lat, lon)
            if arm is None:
                continue
            ok, reason, rtt = arm
            last_reason = reason
            rtts.append(rtt)
            if has_nvf and nvf:
                scans.append(nvf.get('scan_us', 0))
                frees.append(nvf.get('free_heap', 0))
                mins.append(nvf.get('min_heap', 0))

        def avg(lst): return sum(lst)/len(lst) if lst else 0

        scan_s = f"{avg(scans):>8.0f}" if scans else f"{'N/A':>8}"
        free_s = f"{avg(frees)/1024:>7.1f}" if frees else f"{'N/A':>7}"
        min_s  = f"{avg(mins)/1024:>7.1f}"  if mins  else f"{'N/A':>7}"
        rtt_s  = f"{avg(rtts):>7.0f}" if rtts else f"{'TIMEOUT':>7}"
        swap_s = " ◄SWAP" if swap else ""
        result = ("OK" if not last_reason else last_reason[:25])

        print(f"  {label:<44} {tile:>12}  {scan_s}  {rtt_s}  {free_s}  {min_s}  {result}{swap_s}")
        rows.append({'label': label, 'tile': tile, 'lat': lat, 'lon': lon,
                     'swap': swap,
                     'scan_us': round(avg(scans)) if scans else None,
                     'rtt_ms':  round(avg(rtts),  1) if rtts  else None,
                     'free_KB': round(avg(frees)/1024, 1) if frees else None,
                     'min_KB':  round(avg(mins)/1024,  1) if mins  else None,
                     'result': result})

        all_scan.extend(scans); all_rtt.extend(rtts)
        all_free.extend(frees); all_min.extend(mins)

    print("\n" + "─" * len(hdr))
    def avg(l): return sum(l)/len(l) if l else 0
    print(f"  {'Promedio':<44} {'':>12}  {avg(all_scan):>8.0f}  {avg(all_rtt):>7.0f}  "
          f"{avg(all_free)/1024:>7.1f}  {avg(all_min)/1024:>7.1f}")
    if all_min:
        print(f"\n  Heap mínimo histórico: {min(all_min)/1024:.1f} KB")

    if not (orig & OPT_BENCH_MODE):
        set_param(mav, 'OPTIONS', orig)
        print("  OPTIONS restaurado")

    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(os.path.dirname(__file__), 'test_result')
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f'bench_{ts}')

    def avg(l): return round(sum(l)/len(l), 1) if l else None
    summary = {
        'scan_us': avg(all_scan),
        'rtt_ms':  avg(all_rtt),
        'free_KB': round(avg(all_free)/1024, 1) if all_free else None,
        'min_KB':  round(avg(all_min)/1024,  1) if all_min  else None,
        'min_heap_KB': round(min(all_min)/1024, 1) if all_min else None,
    }
    with open(stem + '.json', 'w') as f:
        json.dump({'timestamp': ts, 'port': args.port, 'baud': args.baud,
                   'reps': args.reps, 'summary': summary, 'rows': rows}, f, indent=2)

    print(f"\n  Saved → {stem}.json")


main()
