#!/usr/bin/env python3
"""R36S reversible opaque-draw sorting test.

Aurora ARM already has sortOpaqueDraws: it only sorts contiguous opaque
depth-tested, depth-writing runs, preserving other draw order. It can reduce
program/texture switches, but equal-depth overlapping geometry may differ.
R36S_SORT_OPAQUE=1 enables it; 0 (or unset) preserves the original renderer.
No changes to GXCopyTex, shadows, alpha/transparency, or water materials.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
main = root / "src/main.c"
s = main.read_text()
anchor = "      .glesMappedStreams = 1,\n"
replacement = anchor + (
    '      .sortOpaqueDraws = getenv("R36S_SORT_OPAQUE") != NULL &&\n'
    '                         getenv("R36S_SORT_OPAQUE")[0] == \'1\',\n'
)
if s.count(anchor) != 1:
    raise SystemExit("opaque sort: expected one mapped-stream initializer anchor")
if "      .sortOpaqueDraws =" in s:
    raise SystemExit("opaque sort: initializer already present")
main.write_text(s.replace(anchor, replacement, 1))
print("R36S reversible opaque-sort option installed (R36S_SORT_OPAQUE=1 to enable)")
