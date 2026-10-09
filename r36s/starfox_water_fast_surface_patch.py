#!/usr/bin/env python3
"""R36S optional cheaper water shading, without removing any water geometry.

Star Fox's water pass uses a 4-stage TEV shader with two indirect texture
offset stages, both expensive on Mali-G31. Setting R36S_WATER_FAST=1 retains
the original four TEV blend stages and live reflection texture, but
disables only the indirect offset lookups for the water block surface.
No change to projected shadows, EFB copies, audio, or other materials.

Reversible at run time: R36S_WATER_FAST=0 re-enables stock water shading.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"game/src/main/lightmap_draw.c"
s=p.read_text()
if "#include <stdlib.h>" not in s:
    s="#include <stdlib.h>\n"+s
if "#include <stdio.h>" not in s:
    s="#include <stdio.h>\n"+s
if '#include "dolphin/gx/GXBump.h"' not in s:
    s=s.replace('#include "dolphin/gx/GXLighting.h"\n',
                '#include "dolphin/gx/GXLighting.h"\n#include "dolphin/gx/GXBump.h"\n',1)
anchor="""    setupWaterCausticTev();
    countShifted = block->nRenderInstrsWater << 3;"""
replacement="""    setupWaterCausticTev();
    {
        const char* fastWater = getenv("R36S_WATER_FAST");
        if (fastWater != NULL && fastWater[0] == '1') {
            /* Preserve the reflection/alpha TEV equations and water display
             * lists, but avoid two extra caustic/noise indirect samples per
             * visible water pixel.  Non-water materials retain original TEV. */
            GXSetNumIndStages(0);
            GXSetTevDirect(GX_TEVSTAGE0);
            GXSetTevDirect(GX_TEVSTAGE1);
            GXSetTevDirect(GX_TEVSTAGE2);
            GXSetTevDirect(GX_TEVSTAGE3);
            {
                static unsigned waterBlocks = 0;
                ++waterBlocks;
                if (waterBlocks <= 3 || waterBlocks % 240 == 0) {
                    fprintf(stderr,
                            "[r36s-water-fast] enabled=1 water_block=%u "
                            "tev_stages=4 indirect_stages=0 reflection=retained\\\\n",
                            waterBlocks);
                }
            }
        }
    }
    countShifted = block->nRenderInstrsWater << 3;"""
assert s.count(anchor)==1, "mapBlockRenderWater caustic TEV anchor missing"
p.write_text(s.replace(anchor,replacement,1))
print("R36S water-fast surface: retain 4-stage blended reflection but bypass expensive indirect caustic sampling")
