#!/usr/bin/env python3
"""R36S water optimization: retain water geometry, omit costly cosmetic water overlays.

lightmap_draw.c renders base water through mapBlockRenderWater (case 5).
Cases 8/9 schedule independent waterFX overlay renderers. On the R36S those
may contribute to the huge additional draw/pipeline load when water is visible.
This does not discard or delay entire EFB passes and thus avoids the
menu/THP regression of smallCopyPassInterval=2.

Set R36S_WATER_LITE=0 to retain both effects when comparing on device.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"game/src/main/lightmap_draw.c"
s=p.read_text()
if "#include <stdlib.h>" not in s:
    s="#include <stdlib.h>\n"+s
anchor="void sceneDrawTransparentPolys(void)\n{\n"
extra="""/* Keep normal water geometry (case 5) but allow disabling optional
 * ripple/particle overlays; never suppress the reflective water surface. */
static int r36sWaterEffectsLite(void)
{
    const char* mode = getenv("R36S_WATER_LITE");
    return mode == NULL || mode[0] != '0';
}

"""
assert s.count(anchor)==1, f"water overlay function anchor count: {s.count(anchor)}"
s=s.replace(anchor, extra+anchor, 1)
old="""        case 8:
            waterFxDraw();
            break;
        case 9:
            (*gWaterfxInterface)->render(0, 0);
        }
"""
new="""        case 8:
            if (!r36sWaterEffectsLite()) {
                waterFxDraw();
            }
            break;
        case 9:
            if (!r36sWaterEffectsLite()) {
                (*gWaterfxInterface)->render(0, 0);
            }
            break;
        }
"""
assert s.count(old)==1, f"water overlay switch anchor count: {s.count(old)}"
p.write_text(s.replace(old,new,1))
print("R36S optional waterFX overlays disabled, main water geometry untouched")
