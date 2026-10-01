#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "game/src/main/lightmap.c"
s = p.read_text()

inc_old = '#include "track/intersect.h"\n'
inc_new = '#include "track/intersect.h"\n#include "track/intersect_hud.h"\n'
if inc_old not in s:
    raise SystemExit("reflection overlay: include anchor not found")
s = s.replace(inc_old, inc_new, 1)

old = """    if (bEnableColorFilter == 1) {
        doColorFilter(colorFilterColor);
    }
    shadowVolumesSetDirty(0);
}
"""
new = """    if (bEnableColorFilter == 1) {
        doColorFilter(colorFilterColor);
    }

    /*
     * R36S reflection-source diagnostic:
     * Show the live 320x240 RGB565 EFB-copy texture directly in the upper-left
     * at 160x120.  This bypasses the water/projective/indirect TEV path while
     * sampling the exact same dynamic reflection texture.
     */
    {
        Texture* r36sReflection = getReflectionTexture1();
        if (r36sReflection != NULL) {
            drawTexture(r36sReflection, 0.0f, 0.0f, 0xff, 0x80);
        }
    }

    shadowVolumesSetDirty(0);
}
"""
if old not in s:
    raise SystemExit("reflection overlay: sceneDraw tail anchor not found")
p.write_text(s.replace(old, new, 1))
print("patched live RGB565 reflection diagnostic overlay (160x120 upper-left)")
