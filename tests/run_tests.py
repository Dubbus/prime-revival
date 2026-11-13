#!/usr/bin/env python3 -I
"""Run tests/cases/*.ppl through pplvm and compare stdout with *.expected."""
import io, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "pplvm"))
from pplvm import Interp, PPLError

fails = 0
cases = sorted((pathlib.Path(__file__).resolve().parent / "cases").glob("*.ppl"))
for f in cases:
    out = io.StringIO()
    try:
        Interp(out).run(f.read_text(encoding="utf-8"))
        got = out.getvalue()
    except PPLError as e:
        got = f"PPL error: {e}\n"
    want = f.with_suffix(".expected").read_text(encoding="utf-8")
    ok = got == want
    fails += not ok
    print(("PASS " if ok else "FAIL ") + f.name)
    if not ok:
        print("  want:", repr(want)); print("  got: ", repr(got))
print(f"{len(cases) - fails}/{len(cases)} passed")
sys.exit(1 if fails else 0)
