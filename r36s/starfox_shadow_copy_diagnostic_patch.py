#!/usr/bin/env python3
"""Log GX shadow-copy conversions on R36S without changing rendering."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "extern/aurora/lib/gfx/encoding.cpp"
s = p.read_text()
anchor = "  const bool isDepth = gx::is_depth_format(format);\n"
assert s.count(anchor) == 1, f"expected one resolve_copy anchor, got {s.count(anchor)}"
insert = """  // R36S diagnostic only: report shadow-copy inputs without changing the output.
  if (format == GX_CTF_B8 || format == GX_CTF_R4 || format == GX_TF_Z8) {
    static unsigned r36sShadowCopies = 0;
    const unsigned copyNo = ++r36sShadowCopies;
    if (copyNo <= 16 || (copyNo % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-shadow-copy] n=%u fmt=%u src=%d,%d %dx%d dst=%ux%u conversion=%u scaled=%u partial=%u\\n",
                   copyNo, static_cast<unsigned>(format), rect.x, rect.y,
                   rect.width, rect.height, dstSize.width, dstSize.height,
                   static_cast<unsigned>(needsConversion), static_cast<unsigned>(needsScaling),
                   static_cast<unsigned>(passInfo.resolvePartial));
    }
  }
"""
s=s.replace(anchor,anchor+insert,1)
if "#include <cstdio>" not in s:
    s="#include <cstdio>\n"+s
p.write_text(s)
print("R36S shadow-copy diagnostic installed")
