# Survey of existing HP Prime tooling

Status: in progress (2026-11-13). Only items marked **verified** were read from source this session.

## debrouxl/hplp (libhpcalcs)  — verified
- Last commit: 2015-11-22 ("support both the old and the new USB PID"). Effectively unmaintained.
- Licence: GPL-2.0-or-later (libhpcalcs/COPYING). Anything copied must stay GPL-compatible.
- Transport: **hidapi**, 64-byte raw HID reports (`PRIME_RAW_HID_DATA_SIZE`). Not libusb, not IOKit directly.
  This matters: a hidapi client avoids the HP Kit's crash path only if our own code handles reports safely.
- Known USB IDs: vendor 0x03F0; PIDs 0x0441 and 0x1541 (`hplibs.h`). **Our unit is 0x2441: not listed,
  so hplp will not find it without a patch** (to be confirmed by trying, once the device is connected).
- Commands (`prime_cmd.h`): check-ready 0xFF, get-infos 0xFA, recv-screen 0xFC, recv-backup 0xF9,
  req-file 0xF8, recv-file 0xF7, chat 0xF2, send-key 0xEC, set-date-time 0xE7. Send file exists.
- Tested firmware per README: SDKV0.30/0.32 (2013). Anything newer is unknown.
- Reuse plan: read it as the protocol reference; reimplement in Python on hidapi; upstreaming is moot (dead repo).

## iconmaster5326/Source — verified
- Last commit 2015-04-28; README says "no longer in development", superseded by Typhon.
  Language that compiles to PPL; not a PPL interpreter. Not useful for pplvm. (Typhon not yet checked.)

## Verified via web (2026-11-13; forum/pages read by subagent, not source)
- **HP Connectivity Kit for macOS Beta 2.4.15714**, dated 2026-08-05 (hpcalc.org/details/8724), 28.6 MB, closed source.
  Page says nothing about Apple Silicon. The user's installed Kit is the 2016 x86_64 build that crashes, so **this beta is untested and may fix it. Try it before building primelink.**
- **hplp vs. firmware** (cemetech t=9681, Sept 2015): PID changed 0x0441 -> 0x1541 after a firmware update; adding both PIDs fixed it.
  Nothing newer than 2015 on that thread. Our 0x2441 is a further change. Protocol has no retransmit.
- **Insoft-UK/Xprime**: MIT, macOS 13+ IDE for PPL / PPL+ / Python, generates .hpprgm and app packages, installs into HP Prime Virtual.
  Latest release 27.2 (2026-11-02), actively maintained. README documents no USB transfer to a physical Prime (relies on the Kit)
  and has no interpreter. **A PPL+ -> PPL compiler layer therefore already exists; do not rebuild it.**
- **PPL USB commands** (HP Museum, firmware 2021-12 onward): USBOpen(vid,pid), USBSend({list}), USBRecv(); 64-byte blocks;
  USBOpen() with no args returns {64,64}; small receive buffer reported. Forum-level evidence only.
- **Rip'Em** (Debroux): third-party firmware replacing PRIME_OS.ROM. Out of scope per hard rules.
- **hackaday.io 947**: USB-sniffer protocol work; its author's library warns it does not work on modern firmware.

## Still unverified
- PrimeComm forks (Windows only; archive says old firmware only), Typhon, Prime-C, PrimePlus transfer features.
- Whether Xprime source has any USB code.

## Implication for primelink
Protocol groundwork exists (command bytes, 64-byte framing) but is 10+ years old and was tested on old firmware.
Step 1 of primelink (enumerate 0x03F0:0x2441 and dump the HID report descriptor) is the real next unknown.
