#!/usr/bin/env python3
"""Keep the first character shadow caster entirely inside the scaled R36S EFB.

The GameCube path supersamples the first caster (512 source texels for its
256-texel shadow texture). At EFB scale 2/3 the source projects to 342x342,
but the EFB is only 427x320. Cropping the source to 342x320 makes a partial
shadow map even with the upstream shadow-copy UV correction.

Render the first caster at its native shadow texture resolution instead.
Keep the caster's projection, texture dimensions, layout and per-frame updates.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"game/src/main/newshadows.c"
s=p.read_text()
old="""            if ((u8)texIdx == 0)
                screenW = w << 1;
            else
                screenW = w;
"""
new="""            /* R36S: avoid off-EFB supersampling of the first character shadow.
             * The 512-pixel source was clipped by the scaled 427x320 EFB.
             * The 256-pixel native source fits without changing the texture
             * allocation or the projected shadow's world-space extent. */
            screenW = w;
"""
assert s.count(old)==1, f"shadow source anchor count {s.count(old)}"
p.write_text(s.replace(old,new,1))
print("R36S first character shadow source clamped from 512 to native 256")
