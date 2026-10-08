#!/usr/bin/env python3
"""R36S: keep dynamically generated shadow masks at their GameCube GX dimensions.

GXSetTexCopyDst(256,256,GX_CTF_R4,...) requests a 256x256 texture, but
Aurora's generic scale_copy_dst shrinks it to 171x171 at EFB scale 2/3.
Projective sampling still uses 256x256 GX texture metadata. Keep the native
destination allocation for small B8/R4/Z8 masks, using linear source sampling
of the already scaled EFB. Do not touch 320x240 RGB565/Z8 reflections,
normal frame copies or the EFB scaling itself.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
s=p.read_text()
old="""  const auto [dstWidth, dstHeight] = scale_copy_dst(g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight);
  const auto texCopyFmt = g_gxState.texCopyFmt;"""
new=r"""  const auto texCopyFmt = g_gxState.texCopyFmt;
  // R36S native shadow mask: these copies feed projective shadow samplers
  // whose GXTexObj dimensions are not rescaled with the display EFB.
  const bool r36sNativeShadowMask =
      g_gxState.texCopyDstWidth <= 256 && g_gxState.texCopyDstHeight <= 256 &&
      (texCopyFmt == GX_CTF_B8 || texCopyFmt == GX_CTF_R4 || texCopyFmt == GX_TF_Z8);
  auto r36sCopyDst = scale_copy_dst(g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight);
  if (r36sNativeShadowMask) {
    r36sCopyDst = {g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight};
    static unsigned r36sShadowMaskDiag = 0;
    if (r36sShadowMaskDiag++ < 6) {
      std::fprintf(stderr, "[r36s-native-shadow-mask] fmt=%u src=%dx%d dst=%ux%u\n",
                   static_cast<unsigned>(texCopyFmt), rect.width, rect.height,
                   r36sCopyDst.x, r36sCopyDst.y);
    }
  }
  const auto [dstWidth, dstHeight] = r36sCopyDst;"""
assert s.count(old)==1, f"R36S dynamic-copy size anchor count {s.count(old)}"
s=s.replace(old,new,1)
if "#include <cstdio>" not in s:
    s=s.replace("#include <algorithm>","#include <cstdio>\n#include <algorithm>",1)
p.write_text(s)
print("R36S shadow copies: native <=256 B8/R4/Z8 dimensions, large water reflections unchanged")
