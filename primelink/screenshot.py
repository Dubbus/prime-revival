#!/usr/bin/env python3
"""Read-only: request a screenshot (cmd 0xFC, format byte per hplp) and save the PNG if one comes back."""
import datetime
import pathlib
import sys

from hidmac import HIDDevice

VID, PID, REPORT = 0x03F0, 0x2441, 1024
OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "hardware" / "captures"


def main(fmt=8):
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    with HIDDevice(VID, PID, REPORT) as d:
        d.read_until_quiet(timeout=0.5, quiet=0.3)  # drain
        d.write(bytes([0x00, 0xFC, fmt]))
        pkts = d.read_until_quiet(timeout=10.0, quiet=1.0)
    print(f"{len(pkts)} report(s); seq bytes: {[p[0] for p in pkts[:12]]}{' ...' if len(pkts) > 12 else ''}")
    (OUT / f"screen-{stamp}.raw").write_bytes(b"".join(pkts))
    if not pkts:
        return 1
    print("first report head:", pkts[0][:16].hex(" "))
    body = b"".join(p[1:] for p in pkts)  # strip per-report sequence byte
    s = body.find(b"\x89PNG\r\n\x1a\n")
    e = body.find(b"IEND", s)
    if s < 0 or e < 0:
        print("no complete PNG found in reply (raw saved)")
        return 1
    png = body[s:e + 8]  # IEND + CRC
    path = OUT / f"screen-{stamp}.png"
    path.write_bytes(png)
    print(f"PNG: {len(png)} bytes at payload offset {s} -> {path}")
    print("bytes before PNG:", body[:s].hex(" "))
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8))
