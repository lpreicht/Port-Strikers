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
replace(
    "extern/aurora/lib/gfx/resources.hpp",
    "inline constexpr uint64_t IndexBufferSize = 2097152;    // 2 MiB",
    "inline constexpr uint64_t IndexBufferSize = 8388608;    // 8 MiB - Foxhollow planar reflections",
    "planar-reflection index buffer 2 MiB -> 8 MiB",
)

# Foxhollow v1.0.3 restored the GameCube B8 EFB blur used by effects/compositing.
# The ARM fork predates that fix. Use source-texel steps, which are equivalent
# under the scaled EFB and avoid changing the ARM fork's uniform ABI.
tex = root / "extern/aurora/lib/gfx/tex_copy_conv.cpp"
text = tex.read_text()
old_frag = '''static constexpr std::string_view FragB8 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let b = textureSample(src, src_samp, in.uv).b;
    return vec4f(b, b, b, b);
}
)"sv;'''
new_frag = '''static constexpr std::string_view FragB8 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    // Star Fox Adventures uses GX_CTF_B8 EFB copies as a 16x16 blur source
    // for original GameCube glow/compositing effects.
    let window: i32 = 16;
    let texSize = vec2f(textureDimensions(src));
    let step = vec2f(1.0) / texSize;
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
)"sv;'''
if old_frag not in text:
    raise SystemExit("B8 blur: shader pattern not found")
text = text.replace(old_frag, new_frag, 1)
old_vis = """.binding = 2,
          .visibility = wgpu::ShaderStage::Vertex,"""
new_vis = """.binding = 2,
          .visibility = wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment,"""
if old_vis not in text:
    raise SystemExit("B8 blur: bind-group visibility pattern not found")
text = text.replace(old_vis, new_vis, 1)
tex.write_text(text)
print("patched GX_CTF_B8 EFB blur in ARM tex-copy shader")

# The ARM fork can fuse two small render-to-texture passes. Its dual shader does
# not carry the B8 blur region independently, so never fuse B8 copies.
rec = root / "extern/aurora/lib/gfx/recording.cpp"
text = rec.read_text()
old = """  bool fusedSecond = false;
  if (g_passFusion.active) {
    fusedSecond = pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);
    if (!fusedSecond) {
      pass_fusion_split();
    }
  }"""
new = """  bool fusedSecond = false;
  if (g_passFusion.active) {
    if (resolveFormat == GX_CTF_B8) {
      pass_fusion_split();
    } else {
      fusedSecond = pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);
      if (!fusedSecond) {
        pass_fusion_split();
      }
    }
  }"""
if old not in text:
    raise SystemExit("B8 fusion: active-fusion pattern not found")
text = text.replace(old, new, 1)
old = """    if (pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {
      return;
    }"""
new = """    if (resolveFormat != GX_CTF_B8 &&
        pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {
      return;
    }"""
if old not in text:
    raise SystemExit("B8 fusion: begin-fusion pattern not found")
text = text.replace(old, new, 1)
rec.write_text(text)
print("disabled ARM pass-fusion for GX_CTF_B8 copies")

print("Star Fox clean R36S source patches applied successfully")
