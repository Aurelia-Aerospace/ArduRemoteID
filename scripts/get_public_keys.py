#!/usr/bin/env python3
'''
Read public keys stored on an ArduRemoteID module via MAVLink SECURE_COMMAND (op 3).

Connect directly to the RID module UART — no FC in the loop.

Usage (unsigned — only works when module has NO public keys installed):
  python3 get_public_keys.py --port /dev/ttyUSB0

Usage (signed — required when module already has public keys):
  python3 get_public_keys.py --port /dev/ttyUSB0 --private-key rid_private_key

Key file format: PRIVATE_KEYV1:<base64-encoded 32-byte seed>
  Generate with: python3 scripts/generate_keys.py
'''

import sys, struct, base64, time
from argparse import ArgumentParser

try:
    import monocypher as _monocypher
    import ctypes as _ctypes
    _mono_lib = _ctypes.CDLL(_monocypher.__file__)
except ImportError:
    print("Install monocypher: python3 -m pip install pymonocypher")
    sys.exit(1)
_Buf32 = _ctypes.c_char * 32
_Buf64 = _ctypes.c_char * 64
try:
    _mono_lib.crypto_eddsa_key_pair
    _SIGN_API = 'eddsa'
except AttributeError:
    _SIGN_API = 'sign'

try:
    from pymavlink import mavutil
except ImportError:
    print("Install pymavlink: python3 -m pip install pymavlink")
    sys.exit(1)

SECURE_COMMAND_GET_REMOTEID_SESSION_KEY = 1
SECURE_COMMAND_GET_PUBLIC_KEYS          = 3
MAX_PUBLIC_KEYS                         = 5
PUBLIC_KEY_LEN                          = 32

parser = ArgumentParser(description='Read public keys from ArduRemoteID module via MAVLink')
parser.add_argument("--port",        required=True, help="MAVLink connection (e.g. /dev/ttyUSB0, udp:127.0.0.1:14550)")
parser.add_argument("--baudrate",    default=115200, type=int)
parser.add_argument("--private-key", help="Private key file (PRIVATE_KEYV1: format). Required if module has public keys.")
parser.add_argument("--timeout",     default=5, type=float)
args = parser.parse_args()


def load_private_key(path):
    data = open(path, 'r').read().strip()
    prefix = "PRIVATE_KEYV1:"
    if not data.startswith(prefix):
        print(f"Invalid key format, expected {prefix}...")
        sys.exit(1)
    key = base64.b64decode(data[len(prefix):])
    if len(key) != 32:
        print(f"ERROR: expected 32-byte key, got {len(key)}")
        sys.exit(1)
    return key


def sign(private_key, sequence, operation, data, session_key):
    payload = struct.pack("<II", sequence, operation) + bytes(data) + bytes(session_key)
    sig = _Buf64()
    msg_buf = (_ctypes.c_char * len(payload))(*payload)
    if _SIGN_API == 'eddsa':
        sk = _Buf64()
        _mono_lib.crypto_eddsa_key_pair(sk, _Buf32(), _Buf32(*private_key))
        _mono_lib.crypto_eddsa_sign(sig, sk, msg_buf, _ctypes.c_size_t(len(payload)))
    else:
        pk = _Buf32()
        _mono_lib.crypto_sign_public_key(pk, _Buf32(*private_key))
        _mono_lib.crypto_sign(sig, _Buf32(*private_key), pk, msg_buf, _ctypes.c_size_t(len(payload)))
    return bytes(sig)


def send_secure_command(mav, sequence, operation, data_bytes, sig_bytes):
    payload = bytearray(data_bytes) + bytearray(sig_bytes)
    payload += bytearray(220 - len(payload))
    mav.mav.secure_command_send(
        mav.target_system, mav.target_component,
        sequence, operation,
        len(data_bytes), len(sig_bytes),
        payload
    )


def recv_reply(mav, sequence, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = mav.recv_match(type='SECURE_COMMAND_REPLY', blocking=True, timeout=0.5)
        if msg and msg.sequence == sequence:
            return msg
    return None


def main():
    private_key = None
    if args.private_key:
        private_key = load_private_key(args.private_key)

    print(f"Connecting to {args.port}...")
    mav = mavutil.mavlink_connection(args.port, baud=args.baudrate)
    # RID module waits for a GCS heartbeat before sending its own
    mav.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_QUADROTOR,
                           mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, 0, 0, 0)
    if not mav.wait_heartbeat(timeout=10):
        sys.exit("No heartbeat — check port/baud")
    print(f"Heartbeat from system {mav.target_system} component {mav.target_component}")

    sequence = 1
    session_key = b'\x00' * 8

    if private_key:
        # Get RID session key first (op 1 — no session key needed for bootstrap)
        sig_op1 = sign(private_key, sequence, SECURE_COMMAND_GET_REMOTEID_SESSION_KEY, b'', b'')
        print("Requesting session key (op 1)...")
        deadline = time.time() + args.timeout
        while True:
            send_secure_command(mav, sequence, SECURE_COMMAND_GET_REMOTEID_SESSION_KEY, b'', sig_op1)
            remaining = deadline - time.time()
            if remaining <= 0:
                print("Timed out waiting for session key"); sys.exit(1)
            reply = recv_reply(mav, sequence, min(2.0, remaining))
            if reply is None:
                print("Timed out waiting for session key"); sys.exit(1)
            if reply.result == 1:
                time.sleep(0.5); continue
            if reply.result != 0:
                results = {2: "DENIED", 3: "UNSUPPORTED", 4: "FAILED"}
                print(f"Session key request failed: {results.get(reply.result, f'unknown({reply.result})')}"); sys.exit(1)
            session_key = bytes(reply.data[:8])
            print(f"Session key: {session_key.hex()}")
            sequence += 1
            break

    # GET_PUBLIC_KEYS: data = [key_idx=0, num_keys=5]
    data_op3 = bytes([0, MAX_PUBLIC_KEYS])
    if private_key:
        sig_op3 = sign(private_key, sequence, SECURE_COMMAND_GET_PUBLIC_KEYS, data_op3, session_key)
    else:
        sig_op3 = b''

    print(f"Requesting public keys (op 3, {'signed' if private_key else 'unsigned'})...")
    send_secure_command(mav, sequence, SECURE_COMMAND_GET_PUBLIC_KEYS, data_op3, sig_op3)
    reply = recv_reply(mav, sequence, args.timeout)

    if reply is None:
        print("Timed out waiting for reply"); sys.exit(1)

    results = {0: "ACCEPTED", 1: "TEMPORARILY_REJECTED", 2: "DENIED", 3: "UNSUPPORTED", 4: "FAILED"}
    status = results.get(reply.result, f"unknown({reply.result})")
    if reply.result != 0:
        print(f"GET_PUBLIC_KEYS failed: {status}"); sys.exit(1)

    # Response: data[0]=key_idx, data[1..1+n*32]=keys
    resp = bytes(reply.data[:reply.data_length])
    if len(resp) < 1:
        print("Empty response"); sys.exit(1)

    key_idx_start = resp[0]
    key_bytes = resp[1:]
    num_returned = len(key_bytes) // PUBLIC_KEY_LEN

    print(f"\nPublic keys on module (slot : hex):")
    found = 0
    for i in range(num_returned):
        key = key_bytes[i * PUBLIC_KEY_LEN:(i + 1) * PUBLIC_KEY_LEN]
        slot = key_idx_start + i
        if key == bytes(PUBLIC_KEY_LEN):
            print(f"  slot {slot}: (empty)")
        else:
            print(f"  slot {slot}: {key.hex()}")
            found += 1

    print(f"\n{found} key(s) installed.")


if __name__ == '__main__':
    main()
