#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
text = p.read_text()

old = """void copy_tex(const void* dest, GXBool clear) noexcept {
  const auto rect = map_logical_scissor(g_gxState.texCopySrc);
  const auto [dstWidth, dstHeight] = scale_copy_dst(g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight);
  const auto texCopyFmt = g_gxState.texCopyFmt;
"""

new = """void copy_tex(const void* dest, GXBool clear) noexcept {
  const auto rect = map_logical_scissor(g_gxState.texCopySrc);
  const auto texCopyFmt = g_gxState.texCopyFmt;

  // Star Fox Adventures builds its dynamic reflection pair by copying the
  // complete 640x480 EFB into logical 320x240 RGB565 + Z8 textures. The
  // game's GXTexObjs remain 320x240 and its reflection/indirect TEV math is
  // expressed in those logical texel dimensions. Keep only this exact pair
  // at native logical copy size instead of applying the global EFB render
  // scale a second time to the destination (0.6667 -> about 213x160).
  const bool r36sStarfoxReflectionCopy =
      g_gxState.texCopySrc.x == 0 && g_gxState.texCopySrc.y == 0 &&
      g_gxState.texCopySrc.width == 640 && g_gxState.texCopySrc.height == 480 &&
      g_gxState.texCopyDstWidth == 320 && g_gxState.texCopyDstHeight == 240 &&
      (texCopyFmt == GX_TF_RGB565 || texCopyFmt == GX_TF_Z8);

  auto copyDst = scale_copy_dst(g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight);
  if (r36sStarfoxReflectionCopy) {
    copyDst = {g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight};
  }
  const auto [dstWidth, dstHeight] = copyDst;
"""

if old not in text:
    raise SystemExit("Star Fox reflection native-size patch: copy_tex anchor not found")

p.write_text(text.replace(old, new, 1))
print("patched Star Fox 320x240 RGB565/Z8 reflection copies to native logical destination size")
