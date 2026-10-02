#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
s = p.read_text()

anchor = """namespace {
aurora::Vec2<uint32_t> scale_copy_dst(u32 logicalWidth, u32 logicalHeight) {
"""
replacement = """namespace {
// Star Fox Adventures feeds its 320x240 RGB565 reflection copy back into the
// next frame. Direct-GLES/WebGPU recording can keep an earlier sample queued
// while GXCopyTex overwrites the same GPU image. Mirror Aurora's streaming
// texture strategy: rotate only this reflection target across three images.
struct R36SReflectionCopyRing {
  const void* dest = nullptr;
  u32 width = 0;
  u32 height = 0;
  std::array<aurora::gfx::TextureHandle, 3> handles{};
  u32 next = 0;
  u32 revision = 0;
};
R36SReflectionCopyRing sR36SReflectionRing;

aurora::Vec2<uint32_t> scale_copy_dst(u32 logicalWidth, u32 logicalHeight) {
"""
if anchor not in s:
    raise SystemExit("reflection ring: namespace anchor not found")
s = s.replace(anchor, replacement, 1)

anchor = """  const auto texCopyFmt = g_gxState.texCopyFmt;

  const GXState::CopyTextureKey key{
"""
replacement = """  const auto texCopyFmt = g_gxState.texCopyFmt;

  const bool r36sStarfoxReflectionRgb =
      g_gxState.texCopySrc.x == 0 && g_gxState.texCopySrc.y == 0 &&
      g_gxState.texCopySrc.width == 640 && g_gxState.texCopySrc.height == 480 &&
      g_gxState.texCopyDstWidth == 320 && g_gxState.texCopyDstHeight == 240 &&
      texCopyFmt == GX_TF_RGB565 && clear == GX_FALSE;

  if (r36sStarfoxReflectionRgb) {
    auto& ring = sR36SReflectionRing;
    if (ring.dest != dest || ring.width != dstWidth || ring.height != dstHeight || !ring.handles[0] ||
        !ring.handles[1] || !ring.handles[2]) {
      ring = {};
      ring.dest = dest;
      ring.width = dstWidth;
      ring.height = dstHeight;
      for (auto& h : ring.handles) {
        h = gfx::new_conv_texture(dstWidth, dstHeight, GX_TF_RGB565, "R36S Star Fox Reflection Ring");
      }
      std::fprintf(stderr, "[r36s-reflection-ring] reset dest=%p size=%ux%u slots=3\\n", dest, dstWidth, dstHeight);
    }

    auto& target = ring.handles[ring.next];
    const u32 slot = ring.next;
    ring.next = (ring.next + 1) % 3;
    ++ring.revision;

    const auto clearColor = clear && g_gxState.colorUpdate;
    const auto clearAlpha = clear && g_gxState.alphaUpdate;
    const auto clearDepth = clear && g_gxState.depthUpdate;
    gfx::resolve_pass_into(target, rect, clearColor, clearAlpha, clearDepth, g_gxState.clearColor,
                           clear_depth_value(), texCopyFmt);
    g_gxState.copyTextures[dest] = GXState::CopyTextureRef{.handle = target, .revision = ring.revision};
    texture::invalidate_bindings();

    if ((ring.revision % 120) == 0) {
      std::fprintf(stderr, "[r36s-reflection-ring] revision=%u slot=%u dest=%p\\n", ring.revision, slot, dest);
    }
    return;
  }

  const GXState::CopyTextureKey key{
"""
if anchor not in s:
    raise SystemExit("reflection ring: copy_tex anchor not found")
s = s.replace(anchor, replacement, 1)

p.write_text(s)
print("patched Star Fox RGB565 reflection copy with 3-slot GPU texture ring")
