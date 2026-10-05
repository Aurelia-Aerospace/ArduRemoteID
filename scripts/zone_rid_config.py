#!/usr/bin/env python3
'''
Send ZONE_OK / ZONE_LOCK / ZONE_CLEAR commands to an ArduRemoteID node.

Two transport modes:

  DroneCAN (ArduPilot FC with MAVCAN tunnel):
    python3 zone_rid_config.py --target-node 121 --private-key rid_key /dev/ttyACM0 --zone-ok 0xAABBCCDD

  MAVLink (PX4 FC relay, or direct to RID UART):
    python3 zone_rid_config.py --port /dev/ttyUSB0 --baudrate 57600 --private-key rid_key --zone-ok 0xAABBCCDD
    python3 zone_rid_config.py --port udpin:0.0.0.0:14550 --private-key rid_key --zone-ok 0xAABBCCDD

Commands:
  --zone-ok    0xID ...   Permit arming inside these zone IDs
  --zone-lock  0xID ...   Re-lock previously OK-ed zones
  --zone-clear            Clear all zone overrides
'''

import time, sys, random, base64, struct
from argparse import ArgumentParser

try:
    import monocypher
except ImportError:
    print("Please install monocypher: python3 -m pip install pymonocypher")
    sys.exit(1)

MAX_PAYLOAD = 156

SECURE_COMMAND_GET_REMOTEID_SESSION_KEY = 1
SECURE_COMMAND_SET_REMOTEID_CONFIG      = 6

parser = ArgumentParser(description='Send zone-permit commands to ArduRemoteID')
parser.add_argument("--private-key", default=None,    type=str,   help="private key file (PRIVATE_KEYV1: format)")
parser.add_argument("--timeout",     default=5,       type=float, help="reply timeout in seconds")
parser.add_argument("--zone-ok",   nargs='+', metavar="ID")
parser.add_argument("--zone-lock", nargs='+', metavar="ID")
parser.add_argument("--zone-clear", action='store_true')
# DroneCAN mode
parser.add_argument("uri",          nargs='?',         type=str,   help="CAN URI for DroneCAN mode (e.g. /dev/ttyACM0)")
parser.add_argument("--target-node", default=None,    type=int,   help="RID DroneCAN node ID (DroneCAN mode)")
parser.add_argument("--bitrate",     default=1000000, type=int,   help="CAN bit rate")
parser.add_argument("--node-id",     default=100,     type=int,   help="local CAN node ID")
parser.add_argument("--bus-num",     default=1,       type=int,   help="MAVCAN bus number")
# MAVLink mode
parser.add_argument("--port",        default=None,    type=str,   help="MAVLink connection for MAVLink mode")
parser.add_argument("--baudrate",    default=115200,  type=int,   help="serial baud rate (MAVLink mode)")


def get_private_key(path):
    if path is None:
        return None
    d = open(path, 'r').read().strip()
    prefix = "PRIVATE_KEYV1:"
    if not d.startswith(prefix):
        print(f"Invalid key format, expected {prefix}..."); sys.exit(1)
    key = base64.b64decode(d[len(prefix):])
    if len(key) != 32:
        print(f"ERROR: expected 32-byte key, got {len(key)}"); sys.exit(1)
    return key


def build_payload(zone_ok, zone_lock, zone_clear):
    cmds = []
    for zid in (zone_ok or []):
        cmds.append(f"ZONE_OK=0x{int(zid, 0):08x}")
    for zid in (zone_lock or []):
        cmds.append(f"ZONE_LOCK=0x{int(zid, 0):08x}")
    if zone_clear:
        cmds.append("ZONE_CLEAR")
    if not cmds:
        print("ERROR: no commands specified"); sys.exit(1)
    payload = "\x00".join(cmds).encode('ascii')
    if len(payload) > MAX_PAYLOAD:
        print(f"ERROR: payload {len(payload)}B exceeds {MAX_PAYLOAD}B limit"); sys.exit(1)
    return payload


def sign(seq, op, data, session_key, private_key):
    msg = struct.pack("<II", seq, op) + data
    if op not in (SECURE_COMMAND_GET_REMOTEID_SESSION_KEY,):
        msg += session_key
    return monocypher.signature_sign(private_key, msg)


# ── DroneCAN mode ─────────────────────────────────────────────────────────────

def run_dronecan(args, payload, private_key):
    import dronecan

    SK_OP = dronecan.dronecan.remoteid.SecureCommand.Request().SECURE_COMMAND_GET_REMOTEID_SESSION_KEY
    CFG_OP = dronecan.dronecan.remoteid.SecureCommand.Request().SECURE_COMMAND_SET_REMOTEID_CONFIG

    session_key = [None]
    sequence    = [random.randint(0, 0xFFFFFFFF)]
    done        = [False]
    last_sk_req = [0]
    last_cfg    = [0]

    node = dronecan.make_node(args.uri, node_id=args.node_id, bitrate=args.bitrate)
    node.can_driver.set_bus(args.bus_num)
    dronecan.app.node_monitor.NodeMonitor(node)

    def on_sk(reply):
        if not reply:
            print("Session key timed out"); sys.exit(1)
        session_key[0] = bytearray(reply.response.data)
        print(f"Got session key: {bytes(session_key[0]).hex()}")

    def on_cfg(reply):
        if not reply:
            print("Config timed out"); sys.exit(1)
        results = {0:"ACCEPTED",1:"TEMPORARILY_REJECTED",2:"DENIED",3:"UNSUPPORTED",4:"FAILED"}
        print(f"Result: {results.get(reply.response.result, 'invalid')}")
        done[0] = True
        sys.exit(reply.response.result)

    def request_sk():
        last_sk_req[0] = time.time()
        sig = sign(sequence[0], SK_OP, b'', b'', private_key)
        node.request(dronecan.dronecan.remoteid.SecureCommand.Request(
            sequence=sequence[0], operation=SK_OP, sig_length=len(sig), data=sig),
            args.target_node, on_sk, timeout=args.timeout)
        sequence[0] = (sequence[0] + 1) % (1 << 32)
        print("Requesting session key...")

    def send_cfg():
        last_cfg[0] = time.time()
        if private_key:
            sig  = sign(sequence[0], CFG_OP, payload, bytes(session_key[0]), private_key)
            data = payload + sig; sig_len = len(sig)
        else:
            data = payload; sig_len = 0
        node.request(dronecan.dronecan.remoteid.SecureCommand.Request(
            sequence=sequence[0], operation=CFG_OP, sig_length=sig_len, data=data),
            args.target_node, on_cfg, timeout=args.timeout)
        sequence[0] = (sequence[0] + 1) % (1 << 32)
        print(f"Sent SET_REMOTEID_CONFIG (data={len(payload)}B sig={sig_len}B)")

    def update():
        now = time.time()
        if private_key and session_key[0] is None:
            if now - last_sk_req[0] > args.timeout + 1:
                request_sk()
        elif not done[0]:
            if now - last_cfg[0] > args.timeout + 1:
                send_cfg()

    while not done[0]:
        try:
            update()
            node.spin(timeout=0.1)
        except SystemExit:
            raise
        except Exception as ex:
            print(ex)


# ── MAVLink mode ──────────────────────────────────────────────────────────────

def run_mavlink(args, payload, private_key):
    from pymavlink import mavutil

    session_key = b'\x00' * 8
    sequence    = random.randint(0, 0xFFFFFFFF)

    mav = mavutil.mavlink_connection(args.port, baud=args.baudrate)
    mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_QUADROTOR,
                           mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, 0, 0, 0)
    if not mav.wait_heartbeat(timeout=15):
        sys.exit("No heartbeat — check port/baud")
    print(f"Heartbeat from system {mav.target_system} component {mav.target_component}")

    def recv_reply(seq, timeout):
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = mav.recv_match(type='SECURE_COMMAND_REPLY', blocking=True, timeout=0.5)
            if msg and msg.sequence == seq:
                return msg
        return None

    def send_cmd(seq, op, data_bytes, sig_bytes):
        payload_buf = bytearray(data_bytes) + bytearray(sig_bytes)
        payload_buf += bytearray(220 - len(payload_buf))
        mav.mav.secure_command_send(
            mav.target_system, mav.target_component,
            seq, op, len(data_bytes), len(sig_bytes), payload_buf)

    if private_key:
        sig = sign(sequence, SECURE_COMMAND_GET_REMOTEID_SESSION_KEY, b'', b'', private_key)
        print("Requesting session key (op 1)...")
        deadline = time.time() + args.timeout
        while True:
            send_cmd(sequence, SECURE_COMMAND_GET_REMOTEID_SESSION_KEY, b'', sig)
            remaining = deadline - time.time()
            if remaining <= 0:
                sys.exit("Timed out waiting for session key")
            reply = recv_reply(sequence, min(2.0, remaining))
            if reply is None:
                sys.exit("Timed out waiting for session key")
            if reply.result == 1:
                time.sleep(0.5); continue
            if reply.result != 0:
                results = {2:"DENIED",3:"UNSUPPORTED",4:"FAILED"}
                sys.exit(f"Session key failed: {results.get(reply.result, reply.result)}")
            session_key = bytes(reply.data[:8])
            print(f"Session key: {session_key.hex()}")
            sequence += 1
            break

    if private_key:
        sig = sign(sequence, SECURE_COMMAND_SET_REMOTEID_CONFIG, payload, session_key, private_key)
        sig_len = len(sig)
    else:
        sig = b''; sig_len = 0

    send_cmd(sequence, SECURE_COMMAND_SET_REMOTEID_CONFIG, payload, sig)
    print(f"Sent SET_REMOTEID_CONFIG (data={len(payload)}B sig={sig_len}B)")

    reply = recv_reply(sequence, args.timeout)
    if not reply:
        sys.exit("Timed out waiting for reply")
    results = {0:"ACCEPTED",1:"TEMPORARILY_REJECTED",2:"DENIED",3:"UNSUPPORTED",4:"FAILED"}
    status = results.get(reply.result, f"unknown({reply.result})")
    print(f"Result: {status}")
    sys.exit(reply.result)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    args = parser.parse_args()

    if not args.zone_ok and not args.zone_lock and not args.zone_clear:
        parser.print_help(); sys.exit(1)

    if args.port and args.uri:
        sys.exit("ERROR: specify either --port (MAVLink) or uri (DroneCAN), not both")
    if not args.port and not args.uri:
        sys.exit("ERROR: specify --port (MAVLink mode) or uri positional (DroneCAN mode)")

    payload     = build_payload(args.zone_ok, args.zone_lock, args.zone_clear)
    private_key = get_private_key(args.private_key)
    print(f"Payload ({len(payload)} bytes): {payload.decode()!r}")

    if args.port:
        run_mavlink(args, payload, private_key)
    else:
        if args.target_node is None:
            sys.exit("ERROR: --target-node required for DroneCAN mode")
        run_dronecan(args, payload, private_key)


if __name__ == '__main__':
    main()
