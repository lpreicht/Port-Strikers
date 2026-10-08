#!/usr/bin/env python3
"""R36S: throttle small water/reflection color copies, never intensity/depth shadows."""
from pathlib import Path
import sys

p = Path(sys.argv[1]) / "extern/aurora/lib/gfx/recording.cpp"
s = p.read_text()
anchor = "const bool colorFormat = resolveFormat != GX_CTF_R4 &&"
if s.count(anchor) != 1:
    raise SystemExit(f"expected one color classification anchor, found {s.count(anchor)}")
s = s.replace(anchor,"const bool colorFormat = resolveFormat != GX_CTF_B8 && resolveFormat != GX_CTF_R4 &&",1)
anchor2 = "rect.width <= 128 && rect.height <= 128 && clearColor"
if s.count(anchor2) != 1:
    raise SystemExit(f"expected one reflection copy size anchor, found {s.count(anchor2)}")
s = s.replace(anchor2,"rect.width <= 256 && rect.height <= 256 && clearColor",1)
p.write_text(s)
print("Reflection interval: <=256 color copies; GX_CTF_B8 shadow maps always every frame")
