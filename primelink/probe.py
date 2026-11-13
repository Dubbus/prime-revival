#!/usr/bin/env python3
"""Read-only probe: open the Prime, send check-ready (0xFF) and get-info (0xFA), dump replies.

Framing hypothesis (from hplp, 2013 firmware, 64-byte reports): report = [seq][payload...], zero padded.
Our unit uses 1024-byte reports, so the same framing is tried with the larger size.
"""
import datetime
import pathlib
import sys

from hidmac import HIDDevice

VID, PID, REPORT = 0x03F0, 0x2441, 1024
CAPDIR = pathlib.Path(__file__).resolve().parent.parent / "tests" / "hardware" / "captures"


def hexdump(b, limit=96):
    b = b.rstrip(b"\x00") or b[:1]
    s = " ".join(f"{x:02x}" for x in b[:limit])
    return s + (f" ... (+{len(b) - limit} bytes, trailing zeros stripped)" if len(b) > limit else "")


def main():
    CAPDIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log = []
    with HIDDevice(VID, PID, REPORT) as d:
        for k in ("Product", "Manufacturer", "VersionNumber", "MaxInputReportSize", "MaxOutputReportSize"):
            print(f"{k}: {d.prop(k)}")
        stale = d.read_until_quiet(timeout=0.5, quiet=0.3)
        if stale:
            print(f"(drained {len(stale)} unsolicited report(s); first: {hexdump(stale[0], 32)})")
        for name, cmd in (("check-ready", 0xFF), ("get-info", 0xFA)):
            d.write(bytes([0x00, cmd]))
            pkts = d.read_until_quiet(timeout=3.0, quiet=0.5)
            print(f"\n{name} (0x{cmd:02X}): {len(pkts)} report(s)")
            for i, p in enumerate(pkts[:4]):
                print(f"  [{i}] len={len(p)}: {hexdump(p)}")
            log.append((name, cmd, pkts))
    out = CAPDIR / f"probe-{stamp}.txt"
    with open(out, "w") as f:
        for name, cmd, pkts in log:
            f.write(f"# {name} 0x{cmd:02X}: {len(pkts)} reports\n")
            for p in pkts:
                f.write(p.hex() + "\n")
    print(f"\nraw capture: {out}")


if __name__ == "__main__":
    sys.exit(main())
