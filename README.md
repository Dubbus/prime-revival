# prime-revival

Open-source tools for the HP Prime graphing calculator. Not affiliated with or endorsed by HP.

HP's Connectivity Kit for macOS is an old x86_64 build that crashes on Apple Silicon, and there is no
open-source PPL interpreter. This repo works on both.

## primelink: talk to a Prime from macOS (zero dependencies)

Pure Python + the system IOKit framework via `ctypes`. No libusb, no hidapi, nothing to install.

```
python3 primelink/primelink.py info               # firmware build / version
python3 primelink/primelink.py screenshot out.png # current screen as PNG
python3 primelink/primelink.py ls                 # list every file on the calculator
python3 primelink/primelink.py backup DIR         # save all files + manifest.json (CRC-verified)
```

Read-only for now. Sending files (`put`) is next.

**Tested on:** one HP Prime G2 (USB `03f0:2441`, firmware build 14730), macOS 26.4, Apple Silicon.
Other hardware and firmware revisions are untested.

Protocol notes for this hardware (1024-byte HID reports, length-delimited messages, backup/file format,
CRC) are in [`docs/protocol.md`](docs/protocol.md), with where each fact came from in
[`docs/provenance.md`](docs/provenance.md).

Known issue: macOS occasionally drops an HID input report during long transfers. The protocol has no
retransmit, so primelink detects the sequence gap and re-requests the whole backup.

## pplvm: a PPL interpreter for the desktop (early prototype)

Runs a subset of HP PPL (the Prime's programming language) on your computer.

```
python3 pplvm/pplvm.py run program.ppl
python3 tests/run_tests.py
```

Supported: numbers, strings, lists, `LOCAL`, `:=`, `IF`/`FOR`/`WHILE`/`REPEAT`, `EXPORT` functions,
`RETURN`, `PRINT`, a few built-ins. Not supported: matrices, CAS, graphics, apps, `INPUT`/`CHOOSE`.
Test expectations are provisional until checked against the real calculator; see
[`docs/ppl-semantics.md`](docs/ppl-semantics.md).

## Prior work

See [`docs/survey.md`](docs/survey.md). Thanks in particular to Lionel Debroux's
[hplp / libhpcalcs](https://github.com/debrouxl/hplp), whose notes on the original Prime protocol
were the starting point.

## Ground rules

No HP firmware, ROMs, emulator binaries, or Connectivity Kit files are in this repository.

## License

MIT, see [LICENSE](LICENSE).
