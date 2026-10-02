#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# --- Foxhollow: allocate and update a second diagnostic reflection copy ---
p = root / "game/src/main/newshadows.c"
s = p.read_text()

old = """Texture* gNewShadowCausticTexture;
Texture* gNewShadowReflectionTexture2;
Texture* gNewShadowDiskTexture;
"""
new = """Texture* gNewShadowCausticTexture;
Texture* gNewShadowReflectionTexture2;
Texture* gR36sReflectionRgba8Diag;
Texture* gNewShadowDiskTexture;
"""
if old not in s:
    raise SystemExit("format compare: global anchor not found")
s = s.replace(old, new, 1)

old = """void getReflectionTexture2(Texture** p)
{
    *p = gNewShadowReflectionTexture2;
}
void getNewShadowCausticTexture(Texture** p)
"""
new = """void getReflectionTexture2(Texture** p)
{
    *p = gNewShadowReflectionTexture2;
}
Texture* getR36sReflectionRgba8Diag(void)
{
    return gR36sReflectionRgba8Diag;
}
void getNewShadowCausticTexture(Texture** p)
"""
if old not in s:
    raise SystemExit("format compare: getter anchor not found")
s = s.replace(old, new, 1)

old = """    GXSetTexCopyDst(0x140, 0xf0, GX_TF_RGB565, GX_TRUE);
    GXCopyTex((char*)gNewShadowReflectionTexture + sizeof(Texture), GX_FALSE);
    GXSetTexCopySrc(0, 0, 0x280, 0x1e0);
    GXSetTexCopyDst(0x140, 0xf0, GX_TF_Z8, GX_TRUE);
"""
new = """    GXSetTexCopyDst(0x140, 0xf0, GX_TF_RGB565, GX_TRUE);
    GXCopyTex((char*)gNewShadowReflectionTexture + sizeof(Texture), GX_FALSE);

    /* R36S diagnostic: capture the exact same EFB moment into an independent
       RGBA8 target, before the Z8 reflection copy. */
    if (gR36sReflectionRgba8Diag != NULL)
    {
        GXSetTexCopySrc(0, 0, 0x280, 0x1e0);
        GXSetTexCopyDst(0x140, 0xf0, GX_TF_RGBA8, GX_TRUE);
        GXCopyTex((char*)gR36sReflectionRgba8Diag + sizeof(Texture), GX_FALSE);
    }

    GXSetTexCopySrc(0, 0, 0x280, 0x1e0);
    GXSetTexCopyDst(0x140, 0xf0, GX_TF_Z8, GX_TRUE);
"""
if old not in s:
    raise SystemExit("format compare: reflection copy anchor not found")
s = s.replace(old, new, 1)

old = """    gNewShadowReflectionTexture = textureAlloc(0x140, 0xf0, 4, 0, 0, 0, 0, 1, 1);
    gNewShadowReflectionSmallTexture = textureAlloc(0x50, 0x3c, 4, 0, 0, 0, 0, 1, 1);
    gNewShadowReflectionTexture2 = textureAlloc(0x140, 0xf0, 1, 0, 0, 0, 0, 1, 1);
"""
new = """    gNewShadowReflectionTexture = textureAlloc(0x140, 0xf0, 4, 0, 0, 0, 0, 1, 1);
    gNewShadowReflectionSmallTexture = textureAlloc(0x50, 0x3c, 4, 0, 0, 0, 0, 1, 1);
    gNewShadowReflectionTexture2 = textureAlloc(0x140, 0xf0, 1, 0, 0, 0, 0, 1, 1);
    gR36sReflectionRgba8Diag = textureAlloc(0x140, 0xf0, GX_TF_RGBA8, 0, 0, 0, 0, 1, 1);
    OSReport("[r36s-reflection-format] RGB565/RGBA8 side-by-side diagnostic allocated=%p\\n",
             gR36sReflectionRgba8Diag);
"""
if old not in s:
    raise SystemExit("format compare: allocation anchor not found")
s = s.replace(old, new, 1)
p.write_text(s)

# Public getter for the diagnostic overlay.
p = root / "game/include/main/newshadows.h"
s = p.read_text()
old = """Texture* getReflectionTexture1(void);
void getReflectionTexture2(Texture** out);
void getNewShadowCausticTexture(Texture** out);
"""
new = """Texture* getReflectionTexture1(void);
void getReflectionTexture2(Texture** out);
Texture* getR36sReflectionRgba8Diag(void);
void getNewShadowCausticTexture(Texture** out);
"""
if old not in s:
    raise SystemExit("format compare: header anchor not found")
p.write_text(s.replace(old, new, 1))

# Side-by-side simple HUD sampling after scene rendering:
# left = normal RGB565 reflection, right = independent RGBA8 reflection.
p = root / "game/src/main/lightmap.c"
s = p.read_text()
inc_old = '#include "track/intersect.h"\n'
inc_new = '#include "track/intersect.h"\n#include "track/intersect_hud.h"\n'
if inc_old not in s:
    raise SystemExit("format compare: lightmap include anchor not found")
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
     * R36S source-vs-format diagnostic.
     * Left:  live RGB565 reflection used by water.
     * Right: live RGBA8 copy captured from the exact same EFB moment.
     * Both use the same simple HUD texture path.
     */
    {
        Texture* rgb565 = getReflectionTexture1();
        Texture* rgba8 = getR36sReflectionRgba8Diag();
        if (rgb565 != NULL) {
            drawTexture(rgb565, 0.0f, 0.0f, 0xff, 0x80);
        }
        if (rgba8 != NULL) {
            drawTexture(rgba8, 160.0f, 0.0f, 0xff, 0x80);
        }
    }

    shadowVolumesSetDirty(0);
}
"""
if old not in s:
    raise SystemExit("format compare: lightmap tail anchor not found")
p.write_text(s.replace(old, new, 1))

# --- Aurora: for the one 640x480->320x240 RGBA8 diagnostic copy, force a
# true RGBA8 render texture.  Aurora otherwise aliases any RGB EFB resolve to
# an RGB565 render target even when the requested copy format is RGBA8. ---
p = root / "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
s = p.read_text()
old = """      // Configure the texture swizzle to use alpha 1.0 if targeting RGB565 or EFB doesn't have alpha
      const auto fmt =
          texCopyFmt == GX_TF_RGB565 || g_gxState.pixelFmt == GX_PF_RGB8_Z24 || g_gxState.pixelFmt == GX_PF_RGB565_Z16
              ? GX_TF_RGB565
              : GX_TF_RGBA8;
      handle = gfx::new_render_texture(dstWidth, dstHeight, fmt, "Resolved Texture");
"""
new = """      // Configure the texture swizzle to use alpha 1.0 if targeting RGB565 or EFB doesn't have alpha.
      // R36S diagnostic exception: keep the added full-EFB 320x240 RGBA8 comparison copy
      // genuinely RGBA8 so it is independent from the normal RGB565 reflection conversion.
      const bool r36sReflectionRgba8Diag =
          texCopyFmt == GX_TF_RGBA8 &&
          g_gxState.texCopySrc.x == 0 && g_gxState.texCopySrc.y == 0 &&
          g_gxState.texCopySrc.width == 640 && g_gxState.texCopySrc.height == 480 &&
          g_gxState.texCopyDstWidth == 320 && g_gxState.texCopyDstHeight == 240;
      const auto fmt =
          r36sReflectionRgba8Diag
              ? GX_TF_RGBA8
              : (texCopyFmt == GX_TF_RGB565 || g_gxState.pixelFmt == GX_PF_RGB8_Z24 ||
                         g_gxState.pixelFmt == GX_PF_RGB565_Z16
                     ? GX_TF_RGB565
                     : GX_TF_RGBA8);
      handle = gfx::new_render_texture(dstWidth, dstHeight, fmt,
                                       r36sReflectionRgba8Diag ? "R36S Reflection RGBA8 Diagnostic"
                                                               : "Resolved Texture");
"""
if old not in s:
    raise SystemExit("format compare: Aurora RGBA8 target anchor not found")
p.write_text(s.replace(old, new, 1))

print("patched side-by-side RGB565 vs true RGBA8 reflection diagnostic")
