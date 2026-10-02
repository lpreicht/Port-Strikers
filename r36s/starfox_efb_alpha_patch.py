#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

def replace(path, old, new, label):
    p = root / path
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source pattern not found in {p}")
    p.write_text(text.replace(old, new, 1))
    print(f"patched {label}: {path}")

# Aurora upstream 3840bf9ae735191026e4d4edb0ce6f24d91f7eea
# "Fix GX EFB alpha handling" landed after the ARM direct-GLES fork's last
# upstream merge. Port only the independent GX pixel-format/alpha semantics.
# Do NOT import the later dual-source blending / CompiledPipeline rewrite here.

gx_hpp = root / "extern/aurora/lib/gx/gx.hpp"
text = gx_hpp.read_text()
anchor = """u8 comp_type_size(GXAttr attr, GXCompType type) noexcept;
u8 comp_cnt_count(GXAttr attr, GXCompCnt cnt) noexcept;
} // namespace aurora::gx
"""
replacement = """u8 comp_type_size(GXAttr attr, GXCompType type) noexcept;
u8 comp_cnt_count(GXAttr attr, GXCompCnt cnt) noexcept;

constexpr bool efb_has_alpha(GXPixelFmt format) noexcept { return format == GX_PF_RGBA6_Z24; }
} // namespace aurora::gx
"""
if anchor not in text:
    raise SystemExit("EFB alpha helper: gx.hpp anchor not found")
gx_hpp.write_text(text.replace(anchor, replacement, 1))
print("patched EFB alpha format helper")

gx_cpp = root / "extern/aurora/lib/gx/gx.cpp"
text = gx_cpp.read_text()
old = """  const auto cullMode = config.shaderConfig.lineMode == 0 ? g_gxState.cullMode : GX_CULL_NONE;
  const auto [polygonOffset, polygonOffsetScale] = polygon_offset_for_cull_mode(cullMode);
  config = {
      .msaaSamples = gfx::get_sample_count(),
      .shaderConfig = config.shaderConfig,
      .depthFunc = g_gxState.depthFunc,
      .cullMode = cullMode,
      .blendMode = g_gxState.blendMode,
      .blendFacSrc = g_gxState.blendFacSrc,
      .blendFacDst = g_gxState.blendFacDst,
      .blendOp = g_gxState.blendOp,
      .dstAlpha = g_gxState.dstAlpha,
      .polygonOffsetBits = std::bit_cast<uint32_t>(polygonOffset),
      .polygonOffsetScaleBits = std::bit_cast<uint32_t>(polygonOffsetScale),
      .polygonOffsetClampBits = std::bit_cast<uint32_t>(g_gxState.clamp),
      .depthCompare = g_gxState.depthCompare,
      .depthUpdate = g_gxState.depthUpdate,
      .alphaUpdate = g_gxState.alphaUpdate,
      .colorUpdate = g_gxState.colorUpdate,
  };
"""
new = """  const auto cullMode = config.shaderConfig.lineMode == 0 ? g_gxState.cullMode : GX_CULL_NONE;
  const auto [polygonOffset, polygonOffsetScale] = polygon_offset_for_cull_mode(cullMode);

  // Upstream Aurora 3840bf9: RGB8_Z24 / RGB565_Z16 EFB formats have no
  // destination alpha. GameCube treats DSTALPHA as 1 and INVDSTALPHA as 0
  // there, and alpha updates / destination-alpha replacement have no effect.
  const bool hasAlpha = efb_has_alpha(g_gxState.pixelFmt);
  const bool alphaUpdate = hasAlpha && g_gxState.alphaUpdate;
  const auto blendFactor = [hasAlpha](GXBlendFactor factor) {
    if (!hasAlpha) {
      if (factor == GX_BL_DSTALPHA) {
        return GX_BL_ONE;
      }
      if (factor == GX_BL_INVDSTALPHA) {
        return GX_BL_ZERO;
      }
    }
    return factor;
  };

  config = {
      .msaaSamples = gfx::get_sample_count(),
      .shaderConfig = config.shaderConfig,
      .depthFunc = g_gxState.depthFunc,
      .cullMode = cullMode,
      .blendMode = g_gxState.blendMode,
      .blendFacSrc = blendFactor(g_gxState.blendFacSrc),
      .blendFacDst = blendFactor(g_gxState.blendFacDst),
      .blendOp = g_gxState.blendOp,
      .dstAlpha = alphaUpdate ? g_gxState.dstAlpha : UINT32_MAX,
      .polygonOffsetBits = std::bit_cast<uint32_t>(polygonOffset),
      .polygonOffsetScaleBits = std::bit_cast<uint32_t>(polygonOffsetScale),
      .polygonOffsetClampBits = std::bit_cast<uint32_t>(g_gxState.clamp),
      .depthCompare = g_gxState.depthCompare,
      .depthUpdate = g_gxState.depthUpdate,
      .alphaUpdate = alphaUpdate,
      .colorUpdate = g_gxState.colorUpdate,
  };
"""
if old not in text:
    raise SystemExit("EFB alpha pipeline semantics: gx.cpp anchor not found")
gx_cpp.write_text(text.replace(old, new, 1))
print("patched no-alpha EFB blend and alpha-update semantics")

regs = root / "extern/aurora/lib/gx/regs.cpp"
text = regs.read_text()
old = "  regs[0x43] = {bp_pe_ctrl};\n"
new = "  regs[0x43] = {bp_pe_ctrl, DirtyPipeline};\n"
if old not in text:
    raise SystemExit("EFB pixel-format invalidation: regs.cpp anchor not found")
regs.write_text(text.replace(old, new, 1))
print("patched pixel-format writes to invalidate pipeline")

fb = root / "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
text = fb.read_text()
old = "  const auto clearAlpha = clear && g_gxState.alphaUpdate;\n"
new = "  const auto clearAlpha = clear && g_gxState.alphaUpdate && efb_has_alpha(g_gxState.pixelFmt);\n"
if old not in text:
    raise SystemExit("EFB alpha copy-clear: GXFrameBuffer.cpp anchor not found")
fb.write_text(text.replace(old, new, 1))
print("patched GXCopyTex alpha clear for actual EFB alpha capability")

print("Star Fox R36S upstream EFB-alpha semantics applied successfully")
