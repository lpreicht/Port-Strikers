#!/usr/bin/env python3
"""R36S optional reduction of expensive repeated indirect lightmap/caustic layers.

Some indirect lightmap materials replay the same display list 4, 8, or 16 times,
with a different noise texture and texture matrix each time. On RK3326 this can
multiply draw calls and pipeline/texture switches in water-facing scenes.

R36S_LIGHTMAP_INDIRECT_CAP=2 caps only this auxiliary overlay loop at two
layers, leaving the first two layers in the original order. 0 or unset restores
all original passes. This may affect some non-water indirect lightmap materials,
so hardware validation and visual comparison are required.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "game/src/main/tex_dolphin.c"
s = p.read_text()
if "#include <stdlib.h>" not in s:
    s = "#include <stdlib.h>\n" + s
if "#include <stdio.h>" not in s:
    s = "#include <stdio.h>\n" + s
anchor = """    else
    {
        return;
    }
    i = 0;
    for (; i < passCount; i = i + 1)
"""
replacement = """    else
    {
        return;
    }
    {
        const char* capSetting = getenv("R36S_LIGHTMAP_INDIRECT_CAP");
        const unsigned requestedPasses = (unsigned)passCount;
        const unsigned cap = (capSetting && capSetting[0] >= '1' &&
                              capSetting[0] <= '9' && capSetting[1] == 0)
                                 ? (unsigned)(capSetting[0] - '0') : 0u;
        static unsigned callbackCount = 0;
        static unsigned savedDraws = 0;
        ++callbackCount;
        if (cap != 0u && (unsigned)passCount > cap) {
            passCount = (u8)cap;
            savedDraws += requestedPasses - cap;
        }
        if (callbackCount <= 12 || callbackCount % 160 == 0) {
            fprintf(stderr,
                    "[r36s-lightmap-indirect] call=%u requested=%u actual=%u saved_total=%u cap=%u\n",
                    callbackCount, requestedPasses, (unsigned)passCount,
                    savedDraws, cap);
        }
    }
    i = 0;
    for (; i < passCount; i = i + 1)
"""
if s.count(anchor) != 1:
    raise SystemExit(f"R36S indirect lightmap loop anchor mismatch: {s.count(anchor)}")
s = s.replace(anchor, replacement, 1)
p.write_text(s)
print("R36S indirect lightmap material layers capped at R36S_LIGHTMAP_INDIRECT_CAP (0=stock)")
