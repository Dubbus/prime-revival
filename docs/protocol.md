# HP Prime USB protocol notes (G2, macOS)

Device tested: one HP Prime G2, USB 03f0:2441, HID VersionNumber 0x4850, firmware build 14730
(reported by the device; matches HP's 2.1.14730 release - name of the release unverified).
Host: macOS 26.4 on Apple Silicon, primelink via IOKit HID (no libusb/hidapi). Date: 2026-11-13.

## USB / HID
- Vendor 0x03F0, product 0x2441. Older units/firmware used 0x0441 and 0x1541 (hplp).
- HID report descriptor (from `ioreg`), 35 bytes:
  `05 81 09 82 a1 01 09 83 09 84 15 80 25 7f 75 08 96 00 04 81 02 09 84 15 80 25 7f 75 08 96 00 04 91 02 c0`
  = usage page 0x81, one application collection, **1024-byte input and 1024-byte output reports, no report IDs**.
  (hplp assumed 64-byte reports; G2 differs.)
- macOS needs no special entitlement or Input Monitoring permission to open it (vendor usage page).

## Framing (own-device captures)
- Each HID report = `[seq u8][payload ...]`. Host requests are one report, seq 0, zero padded.
- Reply reports carry seq 0,1,2,... (observed up to 10). Wrap behavior after 0xFE is hplp's claim, unverified on G2.
- **The device does not clear unused report bytes**: a short reply is followed by stale non-zero data.
  Always use the length field; never trim trailing zeros.
- Reply message, after stripping seq bytes: `[cmd u8][0x01][length u32 big-endian][length bytes]`.
  Meaning of the 0x01 byte unknown (constant so far).

## Commands
| Cmd | Name | Request payload | Reply | Status |
|---|---|---|---|---|
| 0xFA | get info | `FA` | 108 bytes: build number (u16 LE) immediately before an ASCII version string ("V2.060.650"), then the serial number (ASCII) | works |
| 0xFC | screenshot | `FC fmt` (fmt 8 = 320x240 PNG per hplp) | 7 unknown bytes (`35 fe 08 ff ff ff ff`; 08 likely echoes fmt) then a complete PNG | works, PNG decodes |
| 0xFF | check ready | `FF` | one report not echoing 0xFF; payload meaning unknown | unclear |
| 0xF9 | backup | `F9` | stream of 0xF7 file messages (below), then an empty 0xF9 message as end marker. 69 files / ~8 MB / 7841 reports in ~18 s | works, all CRCs verify |
| 0xF8, 0xF7 (send), 0xF2, 0xEC, 0xE7 | req file, send file, chat, key, set time | per hplp | - | untested (0xE7/0xEC/0xF7-send change device state) |

## File message (0xF7), as received in a backup
`[F7][01][size u32 BE][type u8][name_len u8][crc16 LE][name UTF-16LE, name_len bytes][data]`
- size = 4 + name_len + len(data).
- CRC-16/CCITT (poly 0x1021, init 0, MSB-first) over the first `size` bytes of the message with the CRC field
  zeroed (so the last 6 bytes are not covered - hplp's observation; holds on G2: 69/69 files verify).
- Sequence numbers restart at 0 for each message and wrap 0xFE -> 0 inside long messages, so seq 0 does
  **not** mark a message start; split messages using the size field.
- Types seen (our labels): 0x00 settings (`calc.hpsettings`, `cas.hpsettings`, `settings`, `calc.hpvars`),
  0x02 app (built-in apps are named with a leading `&`), 0x03 list (L0-L9), 0x04 matrix (M0-M9),
  0x05 note, 0x06 program, 0x0B custom mode.

## Reliability
- **Input reports get dropped on macOS**: 2 of the last 2 CLI backups lost one report on the first attempt
  (seq gap), while 2 diagnostic runs lost none. No retransmit exists, so primelink detects gaps via seq and
  re-requests the whole backup. Cause not yet known (host-side HID queue depth is the main suspect).


## Not yet known
- File listing: hplp has no list command; the Kit has one. Needs a capture or more black-box work.
- Integrity: the 2 bytes after the screenshot header may be a CRC; not checked.
