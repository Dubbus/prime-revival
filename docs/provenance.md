# Provenance of protocol facts
| Fact | Source | Licence/notes |
|---|---|---|
| VID 0x03F0, PIDs 0x0441/0x1541, 64-byte HID reports | debrouxl/hplp `libhpcalcs/src/hplibs.h` | GPL-2.0+; read, not copied |
| Command bytes 0xFF/0xFA/0xFC/0xF9/0xF8/0xF7/0xF2/0xEC/0xE7 | hplp `prime_cmd.h` | GPL-2.0+; read, not copied |
| Our unit is PID 0x2441 | `system_profiler` on the user's Mac (per CLAUDE.md) | own device |
| Kit (2020 build, x86_64) is a Qt app using IOHIDManager/IOHIDDevice APIs with a per-device HID client class and separate G2 and firmware-updater classes | Kit analysis (static symbol table, `nm`) | RE-derived; description only, no HP code |
| Kit crash is in its HID input-report callback, which dereferences a per-device context object; leading hypothesis is a stale callback after device-object teardown (use-after-free) | Kit analysis (static disassembly + own crash reports) | RE-derived; unproven; details in private notes |
| Kit crash reproduces on macOS 26.4 with SIGBUS/KERN_PROTECTION_FAILURE in IOHIDDeviceInputReportApplier | own-machine crash reports | own device |
| G2 report descriptor: 1024-byte in/out reports, no report IDs, usage page 0x81 | own device (`ioreg`) | own device |
| Framing `[seq][payload]`, reply `[cmd][01][u32 BE len][data]`, unzeroed report tails | own-device traffic (primelink probe) | own device |
| 0xFA get-info layout (build u16 LE, version string, serial) and 0xFC screenshot -> PNG | own-device traffic; command bytes from hplp | own device + GPL source (read) |
| Backup (0xF9) = 0xF7 file messages + empty 0xF9 end marker; file header layout; CRC-16/CCITT placement; type codes; seq wrap inside messages | own-device traffic; header layout + CRC first described by hplp | own device + GPL source (read) |
