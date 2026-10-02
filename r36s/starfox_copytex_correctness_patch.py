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

# Aurora upstream commit 9c0bf66f1ed3276b60ad1cd746e2fb48818a6298
# (2026-09-24) fixed two GXCopyTex correctness bugs after the ARM direct-GLES
# branch's last upstream merge. Carry only the copy/clear correctness portion
# here; do not import the unrelated dual-source destination-alpha pipeline
# rewrite into the R36S branch.

# 1) GXCopyTex must not modify EFB alpha before resolving a copy when GXSetDstAlpha
# is active. The old code explicitly did this even for GXCopyTex(..., GX_FALSE),
# which can corrupt feedback/reflection users and adds an unnecessary clear draw.
fb = root / "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
fb_text = fb.read_text()
bad_dst_alpha = """  if (g_gxState.alphaUpdate && g_gxState.dstAlpha != UINT32_MAX) {
    if (!clear) {
      // TODO: figure out the right behavior here.
      // should the copy have a specific alpha value but the EFB remains untouched?
    }
    // Overwrite alpha before resolving
    gfx::push_draw_command(gfx::clear::DrawData{
        .pipeline =
            gfx::pipeline_ref(gfx::clear::make_pipeline_config(gfx::get_render_target_layout(), false, true, false)),
        .color = wgpu::Color{0.f, 0.f, 0.f, g_gxState.dstAlpha / 255.f},
    });
  }
"""
if bad_dst_alpha not in fb_text:
    raise SystemExit("GXCopyTex dst-alpha parity: old pre-copy alpha overwrite block not found")
fb_text = fb_text.replace(
    bad_dst_alpha,
    "  // R36S/upstream 9c0bf66: GXCopyTex resolves the EFB without a pre-copy dst-alpha overwrite.\n",
    1,
)
fb.write_text(fb_text)
print("patched GXCopyTex pre-copy destination-alpha corruption")

# 2) A partial GXCopyTex(..., GX_TRUE) clear is scoped to the copy rectangle.
# The older Aurora continuation path converted it into a whole-target clear.
# Add an optional clear rectangle to the existing clear draw. Existing callers
# keep the legacy full-target behavior because a zero-sized rect means full.
clear_hpp = root / "extern/aurora/lib/gfx/clear.hpp"
clear_hpp_text = clear_hpp.read_text()
draw_data_old = """struct DrawData {
  PipelineRef pipeline;
  wgpu::Color color;
  float depth = 0.f;
};
"""
draw_data_new = """struct DrawData {
  PipelineRef pipeline;
  wgpu::Color color;
  float depth = 0.f;
  ClipRect rect{};
};
"""
if draw_data_old not in clear_hpp_text:
    raise SystemExit("GXCopyTex partial clear: DrawData layout anchor not found")
clear_hpp.write_text(clear_hpp_text.replace(draw_data_old, draw_data_new, 1))
print("patched clear DrawData with optional scissor rectangle")

clear_cpp = root / "extern/aurora/lib/gfx/clear.cpp"
clear_cpp_text = clear_cpp.read_text()
scissor_old = "  pass.SetScissorRect(0, 0, targetSize.width, targetSize.height);\n"
scissor_new = """  if (data.rect.width > 0 && data.rect.height > 0) {
    pass.SetScissorRect(data.rect.x, data.rect.y, data.rect.width, data.rect.height);
  } else {
    pass.SetScissorRect(0, 0, targetSize.width, targetSize.height);
  }
"""
if scissor_old not in clear_cpp_text:
    raise SystemExit("GXCopyTex partial clear: full-target clear scissor anchor not found")
clear_cpp.write_text(clear_cpp_text.replace(scissor_old, scissor_new, 1))
print("patched clear draw to honor partial-copy scissor")

recording = root / "extern/aurora/lib/gfx/recording.cpp"
recording_text = recording.read_text()
continuation_old = """  // Populate new render pass from previous
  const bool fullColorClear = clearColor && clearAlpha;
  current_render_passes().emplace_back(
      make_efb_continuation(prevPass, clearDepth, clearDepthValue, fullColorClear, clearColorValue));
  ++g_recorder.currentRenderPass;

  if (!fullColorClear && (clearColor || clearAlpha)) {
    // If we're only clearing color _or_ alpha, perform a clear draw
    push_leading_clear(clearColor, clearAlpha, clearColorValue);
  }
"""
continuation_new = """  // Populate new render pass from previous. GXCopyTex clear applies only to
  // the copied rectangle; attachment load-op clears are legal only when that
  // rectangle covers the complete EFB target.
  const auto& targetSize = prevPass.colorAttachments[SceneColorAttachmentIndex].size;
  const bool fullTarget = rect.x == 0 && rect.y == 0 &&
                          rect.width == targetSize.width && rect.height == targetSize.height;
  const bool fullColorClear = clearColor && clearAlpha && fullTarget;
  const bool fullDepthClear = clearDepth && fullTarget;
  current_render_passes().emplace_back(
      make_efb_continuation(prevPass, fullDepthClear, clearDepthValue, fullColorClear, clearColorValue));
  ++g_recorder.currentRenderPass;

  const bool drawClearColor = clearColor && !fullColorClear;
  const bool drawClearAlpha = clearAlpha && !fullColorClear;
  const bool drawClearDepth = clearDepth && !fullDepthClear;
  if (rect.width > 0 && rect.height > 0 && (drawClearColor || drawClearAlpha || drawClearDepth)) {
    // Partial clears must be rendered through a scissored clear draw instead
    // of clearing the complete continuation attachment.
    push_draw_command(clear::DrawData{
        .pipeline = pipeline_ref(
            clear::make_pipeline_config(get_render_target_layout(), drawClearColor, drawClearAlpha, drawClearDepth)),
        .color =
            wgpu::Color{
                .r = clearColorValue.x(),
                .g = clearColorValue.y(),
                .b = clearColorValue.z(),
                .a = clearColorValue.w(),
            },
        .depth = clearDepthValue,
        .rect = rect,
    });
  }
"""
if continuation_old not in recording_text:
    raise SystemExit("GXCopyTex partial clear: EFB continuation anchor not found")
recording.write_text(recording_text.replace(continuation_old, continuation_new, 1))
print("patched partial GXCopyTex clears to copy rectangle")

print("Star Fox R36S GXCopyTex upstream-parity fixes applied successfully")
