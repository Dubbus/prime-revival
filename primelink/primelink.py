#!/usr/bin/env python3
"""primelink: talk to an HP Prime (G2, USB 03f0:2441) from macOS. Zero dependencies.

Read-only commands only for now:
  primelink.py info                 firmware/version info
  primelink.py screenshot [OUT.png] save the current screen as PNG
  primelink.py ls                   list everything on the calculator (pulls a full backup, ~1-2 min)
  primelink.py backup DIR           save every file + manifest.json into DIR

Wire format (own-device captures, see docs/protocol.md):
  HID report (1024 bytes, no report ID) = [seq][payload...]; device does not zero the unused tail.
  reply message = [cmd][0x01][u32 BE length][length bytes]
"""
import struct
import sys

import json
import os
import re

from backupfmt import parse_file_message, split_messages
from hidmac import HIDDevice

VID, PID, REPORT = 0x03F0, 0x2441, 1024
CMD_INFO, CMD_SCREEN, CMD_BACKUP = 0xFA, 0xFC, 0xF9
# Observed on one G2 (2026-11-13); names are our labels, not HP's.
FILE_TYPES = {0x00: "settings", 0x02: "app", 0x03: "list", 0x04: "matrix", 0x05: "note",
              0x06: "program", 0x0B: "custom-mode"}


class ProtocolError(Exception):
    pass


def request(dev, payload, timeout=10.0):
    """Send a one-report request; reassemble a length-delimited reply."""
    dev.read_until_quiet(timeout=0.3, quiet=0.2)  # drain unsolicited reports
    dev.write(bytes([0x00]) + payload)
    pkts = dev.read_until_quiet(timeout=timeout, quiet=1.0)
    if not pkts:
        raise ProtocolError("no reply")
    for i, p in enumerate(pkts):
        if p[0] != i % 0xFF:  # hplp: seq wraps after 0xFE, skipping 0xFF (unverified on G2)
            raise ProtocolError(f"report {i} out of sequence (seq={p[0]})")
    body = b"".join(p[1:] for p in pkts)
    cmd, kind, length = body[0], body[1], struct.unpack(">I", body[2:6])[0]
    if cmd != payload[0]:
        raise ProtocolError(f"reply cmd 0x{cmd:02x} != request 0x{payload[0]:02x}")
    data = body[6:6 + length]
    if len(data) != length:
        raise ProtocolError(f"short reply: {len(data)}/{length} bytes")
    return kind, data


def info(dev):
    _, data = request(dev, bytes([CMD_INFO]))
    strings = [s.decode() for s in data.split(b"\x00") if len(s) >= 4 and s.isascii() and s.decode().isprintable()]
    out = {"raw_length": len(data)}
    try:
        idx = data.index(b"V")  # build number sits just before the version string (observed, 1 device)
        out["build"] = struct.unpack("<H", data[idx - 4:idx - 2])[0]
    except (ValueError, struct.error):
        pass
    if strings:
        out["version"] = strings[0]
    out["has_serial"] = len(strings) > 1  # never printed: personal identifier
    return out


def screenshot(dev, fmt=8):
    _, data = request(dev, bytes([CMD_SCREEN, fmt]))
    s = data.find(b"\x89PNG\r\n\x1a\n")
    if s < 0:
        raise ProtocolError("no PNG in screenshot reply")
    return data[s:]


def pull_backup(dev, attempts=3):
    """The protocol has no retransmit, so a dropped HID report means re-requesting the whole backup."""
    for attempt in range(1, attempts + 1):
        dev.read_until_quiet(timeout=0.3, quiet=0.2)
        dev.write(bytes([0x00, CMD_BACKUP]))
        reports = dev.read_until_quiet(timeout=600.0, quiet=3.0)
        try:
            msgs = split_messages(reports)
            break
        except ValueError as e:
            print(f"backup attempt {attempt}/{attempts} failed: {e}", file=sys.stderr)
            dev.read_until_quiet(timeout=5.0, quiet=3.0)  # let the device finish sending
    else:
        raise ProtocolError(f"backup failed after {attempts} attempts")
    if not msgs or msgs[-1][0] != CMD_BACKUP:
        raise ProtocolError("backup did not end with the 0xF9 end marker (incomplete?)")
    files = [parse_file_message(m) for m in msgs if m[0] == 0xF7]
    bad = [f["name"] for f in files if not f["crc_ok"]]
    if bad:
        raise ProtocolError(f"CRC mismatch in: {bad}")
    return files


def _safe(name):
    return re.sub(r"[^\w.\- ]", "_", name).strip() or "_"


def save_backup(files, outdir):
    os.makedirs(outdir, exist_ok=True)
    manifest = []
    for i, f in enumerate(files):
        kind = FILE_TYPES.get(f["type"], f"type{f['type']:02x}")
        rel = os.path.join(kind, f"{i:03d}_{_safe(f['name'])}.bin")
        os.makedirs(os.path.join(outdir, kind), exist_ok=True)
        with open(os.path.join(outdir, rel), "wb") as fh:
            fh.write(f["data"])
        manifest.append({"name": f["name"], "type": f["type"], "kind": kind,
                         "size": len(f["data"]), "crc16": f["crc"], "path": rel})
    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest


def main(argv):
    if len(argv) < 2 or argv[1] not in ("info", "screenshot", "ls", "backup") or (argv[1] == "backup" and len(argv) < 3):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        with HIDDevice(VID, PID, REPORT) as dev:
            if argv[1] == "info":
                for k, v in info(dev).items():
                    print(f"{k}: {v}")
            elif argv[1] in ("ls", "backup"):
                files = pull_backup(dev)
                if argv[1] == "ls":
                    for f in files:
                        kind = FILE_TYPES.get(f["type"], f"type{f['type']:02x}")
                        print(f"{kind:12} {len(f['data']):>9}  {f['name']}")
                    print(f"{len(files)} files, all CRCs ok")
                else:
                    m = save_backup(files, argv[2])
                    print(f"saved {len(m)} files ({sum(x['size'] for x in m)} bytes) to {argv[2]}")
            else:
                out = argv[2] if len(argv) > 2 else "prime-screen.png"
                png = screenshot(dev)
                with open(out, "wb") as f:
                    f.write(png)
                print(f"saved {out} ({len(png)} bytes)")
    except ProtocolError as e:
        print(f"protocol error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
