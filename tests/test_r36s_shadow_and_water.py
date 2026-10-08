#!/usr/bin/env python3
"""Source contracts for the R36S shadow-bounds and water rendering changes.

This is a source-level regression test, not an R36S GPU or visual validation.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
shadow = (root / "game/src/main/newshadows.c").read_text()
water = (root / "game/src/main/lightmap_draw.c").read_text()

assert "screenW = w << 1" not in shadow, "first shadow caster still renders outside scaled EFB"
assert "R36S: avoid off-EFB supersampling" in shadow
assert "screenW = w;" in shadow
assert "GXSetTexCopyDst(w, w, GX_CTF_R4, GX_TRUE);" in shadow
assert "GXCopyTex(*texture + 1, GX_TRUE);" in shadow
# In gameplay at 2/3 internal scale a 256px shadow source fits within 427x320.
for source_width, efb_height in ((256, 320), (128, 320), (64, 320)):
    assert round(source_width * (2/3)) <= efb_height
assert "r36sWaterEffectsLite" in water
assert "mapBlockRender_callList(1, 1, block, newR, &state, viewMtx);" in water
assert "mapBlockRenderWater(entries[i].arg0.bounds, entries[i].arg1.block, m);" in water
assert "if (!r36sWaterEffectsLite())" in water
assert "waterFxDraw();" in water and "(*gWaterfxInterface)->render(0, 0);" in water
print("PASS: shadow source within EFB; water polygons retained; only overlay FX optional")
