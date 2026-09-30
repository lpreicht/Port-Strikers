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

# Foxhollow v1.0.9 declared render-scale configuration but current main does not
# provide the implementation. Add it here and expose a clean R36S env setting.
cfg = root / "port/src/foxhollow_config.c"
text = cfg.read_text()
if "fhConfigRenderScale(void)" not in text:
    text = text.replace(
        "static int sFrameLimit = FH_DEFAULT_FRAME_LIMIT;\n",
        "static int sFrameLimit = FH_DEFAULT_FRAME_LIMIT;\nstatic f32 sRenderScale = 1.0f;\n",
        1,
    )
    text = text.replace(
        "  const char* frameLimit;\n  const char* revision;\n",
        "  const char* frameLimit;\n  const char* renderScale;\n  const char* revision;\n",
        1,
    )
    text = text.replace(
        "  frameLimit = getenv(\"FOXHOLLOW_FRAME_LIMIT\");\n",
        "  renderScale = getenv(\"FOXHOLLOW_RENDER_SCALE\");\n"
        "  if (renderScale != NULL && renderScale[0] != '\\0') {\n"
        "    char* end = NULL;\n"
        "    const float value = strtof(renderScale, &end);\n"
        "    if (end != renderScale && value >= 0.25f && value <= 1.0f) {\n"
        "      sRenderScale = value;\n"
        "    }\n"
        "  }\n\n"
        "  frameLimit = getenv(\"FOXHOLLOW_FRAME_LIMIT\");\n",
        1,
    )
    marker = "int fhConfigRevision(void) {\n"
    if marker not in text:
        raise SystemExit("render-scale: revision marker not found")
    text = text.replace(
        marker,
        "f32 fhConfigRenderScale(void) {\n"
        "  load();\n"
        "  return sRenderScale;\n"
        "}\n\n"
        + marker,
        1,
    )
    cfg.write_text(text)
    print("patched Foxhollow render-scale env implementation")

# Keep the proven R36S dynamic EFB profile in source instead of libsfscale.so:
# the title/intro map (63) runs at 0.5x, while actual gameplay uses the normal
# FOXHOLLOW_RENDER_SCALE value (0.6667 in the clean launcher).
replace(
    "port/src/foxhollow_breadcrumb.c",
    """#include "foxhollow_crash.h"

#include <stdio.h>

void fhNoteMapLoaded(int mapId) {
    fprintf(stderr, "[foxhollow] map-loaded id=%d\\n", mapId);
    fflush(stderr);
}
""",
    """#include "foxhollow_crash.h"
#include "foxhollow_config.h"
#include "dolphin/vi.h"

#include <stdio.h>

void fhNoteMapLoaded(int mapId) {
    const f32 scale = mapId == 63 ? 0.5f : fhConfigRenderScale();
    VISetFrameBufferScale(scale);
    fprintf(stderr, "[foxhollow] map-loaded id=%d efb-scale=%.4f\\n", mapId, scale);
    fflush(stderr);
}
""",
    "source-level dynamic R36S EFB scale",
)

# Preserve real-time pacing on the R36S when a heavy scene drops below 10 fps.
# At normal gameplay rates this is inert; it only raises the original 6-frame cap.
replace(
    "game/src/main/pi_videoinit.c",
    "    if (timeDelta > 6.0f) {\n        timeDelta = 6.0f;\n    }",
    "    if (timeDelta > 10.0f) {\n        timeDelta = 10.0f;\n    }",
    "R36S realtime frame-delta cap 6 -> 10",
)

# Foxhollow v1.0.10: planar-reflection geometry can overflow Aurora's old 2 MiB
# index stream. Keep the ARM renderer, but carry the upstream 8 MiB fix across.
resources = root / "extern/aurora/lib/gfx/resources.hpp"
resources_text = resources.read_text()
index_variants = (
    "inline constexpr uint64_t IndexBufferSize = 2 * 1024 * 1024;",
    "inline constexpr uint64_t IndexBufferSize = 2097152;    // 2 MiB",
)
for old_index in index_variants:
    if old_index in resources_text:
        resources_text = resources_text.replace(
            old_index,
            "inline constexpr uint64_t IndexBufferSize = 8 * 1024 * 1024; // Foxhollow planar reflections",
            1,
        )
        resources.write_text(resources_text)
        print("patched planar-reflection index buffer 2 MiB -> 8 MiB")
        break
else:
    if "IndexBufferSize = 8 * 1024 * 1024" in resources_text:
        print("planar-reflection index buffer already 8 MiB")
    else:
        raise SystemExit("planar-reflection index buffer: no recognized 2 MiB source form found")

# Foxhollow v1.0.3 restored the GameCube GX_CTF_B8 EFB blur. Port that
# fix faithfully to the older ARM renderer, including logical copy size so the
# blur footprint stays correct when the R36S renders the EFB below 1.0 scale.
replace(
    "extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp",
    """  gfx::resolve_pass_into(handle.handle, rect, clearColor, clearAlpha, clearDepth, g_gxState.clearColor,
                         clear_depth_value(), texCopyFmt);""",
    """  gfx::resolve_pass_into(handle.handle, rect, clearColor, clearAlpha, clearDepth, g_gxState.clearColor,
                         clear_depth_value(), texCopyFmt,
                         {g_gxState.texCopyDstWidth, g_gxState.texCopyDstHeight});""",
    "B8 logical EFB copy size",
)

replace(
    "extern/aurora/lib/gfx/recording.hpp",
    """void resolve_pass_into(TextureHandle texture, ClipRect rect, bool clearColor, bool clearAlpha, bool clearDepth,
                       Vec4<float> clearColorValue, float clearDepthValue, GXTexFmt resolveFormat = GX_TF_RGBA8);""",
    """void resolve_pass_into(TextureHandle texture, ClipRect rect, bool clearColor, bool clearAlpha, bool clearDepth,
                       Vec4<float> clearColorValue, float clearDepthValue, GXTexFmt resolveFormat = GX_TF_RGBA8,
                       Vec2<uint32_t> logicalSize = {});""",
    "B8 resolve signature",
)

replace(
    "extern/aurora/lib/gfx/recording.cpp",
    """// UV transform uniform for tex_copy_conv (crop region in UV space)
std::array<float, 4> copy_uv_transform(const RenderPass& pass, const ClipRect& rect) {
  const auto& size = pass.colorAttachments[SceneColorAttachmentIndex].size;
  const auto srcW = static_cast<float>(size.width);
  const auto srcH = static_cast<float>(size.height);
  return {
      static_cast<float>(rect.x) / srcW,
      static_cast<float>(rect.y) / srcH,
      static_cast<float>(rect.width) / srcW,
      static_cast<float>(rect.height) / srcH,
  };
}""",
    """// UV transform uniform for tex_copy_conv (crop region in UV space).
// GX_CTF_B8 additionally carries the original logical copy size so the
// 16x16 GameCube blur remains correct under a scaled internal EFB.
std::array<float, 8> copy_uv_transform(const RenderPass& pass, const ClipRect& rect,
                                       GXTexFmt resolveFormat = GX_TF_RGBA8,
                                       Vec2<uint32_t> logicalSize = {}) {
  const auto& size = pass.colorAttachments[SceneColorAttachmentIndex].size;
  const auto srcW = static_cast<float>(size.width);
  const auto srcH = static_cast<float>(size.height);
  const float blurWindow =
      resolveFormat == GX_CTF_B8 && logicalSize.x != 0 && logicalSize.y != 0 ? 16.f : 0.f;
  return {
      static_cast<float>(rect.x) / srcW,
      static_cast<float>(rect.y) / srcH,
      static_cast<float>(rect.width) / srcW,
      static_cast<float>(rect.height) / srcH,
      blurWindow,
      0.f,
      static_cast<float>(logicalSize.x),
      static_cast<float>(logicalSize.y),
  };
}""",
    "B8 scaled UV uniform",
)

replace(
    "extern/aurora/lib/gfx/recording.cpp",
    """void resolve_pass_into(TextureHandle texture, ClipRect rect, bool clearColor, bool clearAlpha, bool clearDepth,
                       Vec4<float> clearColorValue, float clearDepthValue, GXTexFmt resolveFormat) {""",
    """void resolve_pass_into(TextureHandle texture, ClipRect rect, bool clearColor, bool clearAlpha, bool clearDepth,
                       Vec4<float> clearColorValue, float clearDepthValue, GXTexFmt resolveFormat,
                       Vec2<uint32_t> logicalSize) {""",
    "B8 recording resolve signature",
)

# The ARM fork can fuse two small render-to-texture passes. Its dual conversion
# shader has a different uniform layout, so B8 copies must stay unfused.
replace(
    "extern/aurora/lib/gfx/recording.cpp",
    """  bool fusedSecond = false;
  if (g_passFusion.active) {
    fusedSecond = pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);
    if (!fusedSecond) {
      pass_fusion_split();
    }
  }""",
    """  bool fusedSecond = false;
  if (g_passFusion.active) {
    if (resolveFormat == GX_CTF_B8) {
      pass_fusion_split();
    } else {
      fusedSecond = pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);
      if (!fusedSecond) {
        pass_fusion_split();
      }
    }
  }""",
    "B8 active pass-fusion guard",
)

replace(
    "extern/aurora/lib/gfx/recording.cpp",
    """    prevPass.resolveUniformRange = push_uniform(copy_uv_transform(prevPass, rect));""",
    """    prevPass.resolveUniformRange =
        push_uniform(copy_uv_transform(prevPass, rect, resolveFormat, logicalSize));""",
    "B8 resolve uniform data",
)

replace(
    "extern/aurora/lib/gfx/recording.cpp",
    """    if (pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {
      return;
    }""",
    """    if (resolveFormat != GX_CTF_B8 &&
        pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {
      return;
    }""",
    "B8 pass-fusion begin guard",
)

replace(
    "extern/aurora/lib/gfx/tex_copy_conv.cpp",
    """struct UVTransform {
    offset: vec2f,
    scale: vec2f,
};""",
    """struct UVTransform {
    offset: vec2f,
    scale: vec2f,
    blur: vec4f,
};""",
    "B8 shader UV transform",
)

replace(
    "extern/aurora/lib/gfx/tex_copy_conv.cpp",
    """static constexpr std::string_view FragB8 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let b = textureSample(src, src_samp, in.uv).b;
    return vec4f(b, b, b, b);
}
)"sv;""",
    """static constexpr std::string_view FragB8 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let window = i32(uv_xf.blur.x);
    if (window <= 1) {
        let b = textureSample(src, src_samp, in.uv).b;
        return vec4f(b, b, b, b);
    }
    let step = uv_xf.scale / uv_xf.blur.zw;
    let lo = uv_xf.offset;
    let hi = uv_xf.offset + uv_xf.scale;
    let half = window / 2;
    var sum = 0.0;
    for (var y: i32 = -half; y < window - half; y = y + 1) {
        for (var x: i32 = -half; x < window - half; x = x + 1) {
            let uv = in.uv + vec2f(f32(x), f32(y)) * step;
            let inside = all(uv >= lo) && all(uv < hi);
            let v = textureSampleLevel(src, src_samp, clamp(uv, lo, hi), 0.0).b;
            sum = sum + select(0.0, v, inside);
        }
    }
    let b = sum / f32(window * window);
    return vec4f(b, b, b, b);
}
)"sv;""",
    "GX_CTF_B8 16x16 EFB blur",
)

replace(
    "extern/aurora/lib/gfx/tex_copy_conv.cpp",
    """.binding = 2,
          .visibility = wgpu::ShaderStage::Vertex,""",
    """.binding = 2,
          .visibility = wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment,""",
    "B8 fragment uniform visibility",
)

print("patched exact Foxhollow B8 EFB blur semantics into ARM renderer")

print("Star Fox clean R36S source patches applied successfully")
