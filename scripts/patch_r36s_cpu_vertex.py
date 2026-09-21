#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_r36s_cpu_vertex.py <strikers-dir>")

root = Path(sys.argv[1])
repo = Path(__file__).resolve().parents[1]
aur = root / "extern/aurora"
vendor = repo / "vendor/aurora-cpu-vertex"

def replace_once(path, old, new, label):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if old not in s:
        raise SystemExit(f"{label}: pattern not found in {p}")
    p.write_text(s.replace(old, new, 1))

# Exact Aurora CPU vertex loader from zalo/aurora-arm commit
# fc45532da0d39ae070005a419bfd15251ef768e5.
shutil.copy2(vendor / "vertex_loader.cpp", aur / "lib/gx/vertex_loader.cpp")
shutil.copy2(vendor / "vertex_loader.hpp", aur / "lib/gx/vertex_loader.hpp")

replace_once(
    aur / "cmake/aurora_gx.cmake",
    "        lib/gx/shader_info.cpp\n",
    "        lib/gx/shader_info.cpp\n        lib/gx/vertex_loader.cpp\n",
    "aurora_gx vertex loader source",
)

# Public toggle in AuroraConfig.
replace_once(
    aur / "include/aurora/aurora.h",
    """  uint32_t mem2Size;
} AuroraConfig;
""",
    """  uint32_t mem2Size;

  /*
   * Decode GX vertex attributes on the CPU into conventional vertex buffers.
   * Required on GLES-class Mali devices that expose zero vertex-stage storage buffers.
   */
  bool cpuVertexDecode;
} AuroraConfig;
""",
    "AuroraConfig cpuVertexDecode",
)

# Force the handheld decode path inside Aurora itself. This keeps GX state,
# shader generation and draw submission on the same path even if the outer
# application's config struct changes.
aurora_cpp = aur / "lib/aurora.cpp"
s = aurora_cpp.read_text()
old = """AuroraInfo initialize(int argc, char* argv[], const AuroraConfig& config) noexcept {
  g_config = config;
  Log.info("Aurora initializing");
"""
new = """AuroraInfo initialize(int argc, char* argv[], const AuroraConfig& config) noexcept {
  g_config = config;
#ifdef MELEE_MIYOO_FLIP
  g_config.cpuVertexDecode = true;
#endif
  Log.info("Aurora initializing");
#ifdef MELEE_MIYOO_FLIP
  Log.info("R36S CPU vertex decode: {}", g_config.cpuVertexDecode);
#endif
"""
if new not in s:
    if old not in s:
        raise SystemExit("aurora.cpp config-copy marker not found")
    s = s.replace(old, new, 1)
aurora_cpp.write_text(s)

# Directly reserve decoded vertex records in the per-frame stream.
replace_once(
    aur / "lib/gfx/recording.cpp",
    """Range push_verts(const uint8_t* data, size_t length, size_t alignment) {
  ZoneScoped;
  if (!check_recording("push_verts")) {
    return {};
  }
  return push(current_frame_packet().verts, data, length, alignment);
}

Range push_indices""",
    """Range push_verts(const uint8_t* data, size_t length, size_t alignment) {
  ZoneScoped;
  if (!check_recording("push_verts")) {
    return {};
  }
  return push(current_frame_packet().verts, data, length, alignment);
}

Range map_verts(size_t length, size_t alignment, uint8_t*& data) {
  ZoneScoped;
  data = nullptr;
  if (!check_recording("map_verts")) {
    return {};
  }
  auto& verts = current_frame_packet().verts;
  const auto range = map(verts, length, alignment);
  data = verts.data() + range.offset;
  return range;
}

Range push_indices""",
    "recording map_verts implementation",
)
replace_once(
    aur / "lib/gfx/recording.hpp",
    """Range push_verts(const uint8_t* data, size_t length, size_t alignment);
template <typename T>
Range push_verts(ArrayRef<T> data, size_t alignment) {
  return push_verts(reinterpret_cast<const uint8_t*>(data.data()), data.size() * sizeof(T), alignment);
}
Range push_indices""",
    """Range push_verts(const uint8_t* data, size_t length, size_t alignment);
template <typename T>
Range push_verts(ArrayRef<T> data, size_t alignment) {
  return push_verts(reinterpret_cast<const uint8_t*>(data.data()), data.size() * sizeof(T), alignment);
}
// Reserves bytes in the frame vertex stream for CPU-decoded records.
Range map_verts(size_t length, size_t alignment, uint8_t*& data);
Range push_indices""",
    "recording map_verts declaration",
)

# Shader config hashes CPU-decoded and storage-buffer pipelines separately.
replace_once(
    aur / "lib/gx/gx.hpp",
    """  u8 lineMode : 2 = 0; // 1 = GX_LINES, 2 = GX_LINESTRIP, 3 = GX_POINTS
  u8 fogRangeEnabled : 1 = false;
  u8 pad1 : 5 = 0;
""",
    """  u8 lineMode : 2 = 0; // 1 = GX_LINES, 2 = GX_LINESTRIP, 3 = GX_POINTS
  u8 fogRangeEnabled : 1 = false;
  u8 cpuVertexDecode : 1 = false;
  u8 pad1 : 4 = 0;
""",
    "ShaderConfig cpuVertexDecode",
)
replace_once(
    aur / "lib/gx/gx.cpp",
    """  config.shaderConfig.fogType = g_gxState.fog.type;
  config.shaderConfig.fogRangeEnabled = g_gxState.fog.rangeEnabled;
""",
    """  config.shaderConfig.fogType = g_gxState.fog.type;
  config.shaderConfig.fogRangeEnabled = g_gxState.fog.rangeEnabled;
#ifdef MELEE_MIYOO_FLIP
  config.shaderConfig.cpuVertexDecode = true;
#else
  config.shaderConfig.cpuVertexDecode = g_config.cpuVertexDecode;
#endif
""",
    "populate cpuVertexDecode",
)

# Pipeline: conventional vertex input when CPU decode is enabled.
pipeline = aur / "lib/gx/pipeline.cpp"
s = pipeline.read_text()
if '#include "vertex_loader.hpp"' not in s:
    s = s.replace('#include "shader_info.hpp"\n', '#include "shader_info.hpp"\n#include "vertex_loader.hpp"\n', 1)
old = """  const auto label =
      fmt::format("GX Pipeline {:x} shader {:x}", xxh3_hash(config, static_cast<HashType>(gfx::ShaderType::GX)),
                  xxh3_hash(config.shaderConfig));
  return build_pipeline(config, {}, shader, label.c_str());
"""
new = """  const auto label =
      fmt::format("GX Pipeline {:x} shader {:x}", xxh3_hash(config, static_cast<HashType>(gfx::ShaderType::GX)),
                  xxh3_hash(config.shaderConfig));
  if (config.shaderConfig.cpuVertexDecode) {
    const auto layout = decoded_vertex_layout(config.shaderConfig);
    const wgpu::VertexBufferLayout vertexBuffer{
        .stepMode = wgpu::VertexStepMode::Vertex,
        .arrayStride = layout.stride,
        .attributeCount = layout.count,
        .attributes = layout.attributes.data(),
    };
    return build_pipeline(config, {&vertexBuffer, 1}, shader, label.c_str());
  }
  return build_pipeline(config, {}, shader, label.c_str());
"""
if new not in s:
    if old not in s:
        raise SystemExit("pipeline create layout pattern not found")
    s = s.replace(old, new, 1)
old = """  const auto& resources = gfx::detail::resources();
  pass.SetImmediates(0, &data.immediateData, sizeof(data.immediateData));
"""
new = """  const auto& resources = gfx::detail::resources();
  if (g_config.cpuVertexDecode) {
    pass.SetVertexBuffer(0, resources.vertexBuffer, data.vertRange.offset, data.vertRange.size);
  }
  pass.SetImmediates(0, &data.immediateData, sizeof(data.immediateData));
"""
if new not in s:
    if old not in s:
        raise SystemExit("pipeline render vertex buffer pattern not found")
    s = s.replace(old, new, 1)
pipeline.write_text(s)

# Shader: decoded @location inputs replace vertex-stage storage-buffer reads.
shader = aur / "lib/gx/shader.cpp"
s = shader.read_text()
if '#include "vertex_loader.hpp"' not in s:
    s = s.replace('#include "shader_info.hpp"\n', '#include "shader_info.hpp"\n#include "vertex_loader.hpp"\n', 1)

marker = """auto attr_load(const ShaderConfig& config, GXAttr attr, std::string_view vidx) -> std::string {
"""
decoded_func = r'''// CPU-decoded vertex input: attributes arrive through @location inputs.
auto decoded_attr_load(GXAttr attr, bool lineEnd) -> std::string {
  switch (attr) {
  case GX_VA_PNMTXIDX:
    return lineEnd ? "u32(v_line_end.w)"s : "(v_matrices.x & 255u)"s;
  case GX_VA_TEX0MTXIDX:
  case GX_VA_TEX1MTXIDX:
  case GX_VA_TEX2MTXIDX:
  case GX_VA_TEX3MTXIDX:
  case GX_VA_TEX4MTXIDX:
  case GX_VA_TEX5MTXIDX:
  case GX_VA_TEX6MTXIDX:
  case GX_VA_TEX7MTXIDX: {
    const u32 idx = attr - GX_VA_PNMTXIDX;
    return fmt::format("((v_matrices.{} >> {}u) & 255u)", "xyz"[idx / 4], (idx % 4) * 8);
  }
  case GX_VA_POS:
    return lineEnd ? "v_line_end.xyz"s : "v_pos"s;
  case GX_VA_NRM:
    return "v_nrm"s;
  case GX_VA_CLR0:
  case GX_VA_CLR1:
    return fmt::format("v_clr{}", attr - GX_VA_CLR0);
  case GX_VA_TEX0:
  case GX_VA_TEX1:
  case GX_VA_TEX2:
  case GX_VA_TEX3:
  case GX_VA_TEX4:
  case GX_VA_TEX5:
  case GX_VA_TEX6:
  case GX_VA_TEX7:
    return fmt::format("v_tex{}", attr - GX_VA_TEX0);
  default:
    Log.fatal("decoded_attr_load: Unimplemented {}", attr);
  }
}

'''
if decoded_func not in s:
    if marker not in s:
        raise SystemExit("shader attr_load marker not found")
    s = s.replace(marker, decoded_func + marker, 1)

replace = """  if (mapping.attrType == GX_NONE) {
    return vtx_attr(config, attr);
  }
  const auto [offs, buf, le] = attr_address"""
with_decode = """  if (mapping.attrType == GX_NONE) {
    return vtx_attr(config, attr);
  }
  if (config.cpuVertexDecode) {
    return decoded_attr_load(attr, vidx == "vidx_b"sv);
  }
  const auto [offs, buf, le] = attr_address"""
if with_decode not in s:
    if replace not in s:
        raise SystemExit("shader attr_load decode insertion not found")
    s = s.replace(replace, with_decode, 1)

replace = """  if (mapping.attrType == GX_NONE || mapping.cnt != 9) {
    Log.fatal("attr_load_nbt_slice: GX_TG_BINRM/TANGENT requires GX_NRM_NBT or GX_NRM_NBT3");
  }
  const auto sliceIdx"""
with_decode = """  if (mapping.attrType == GX_NONE || mapping.cnt != 9) {
    Log.fatal("attr_load_nbt_slice: GX_TG_BINRM/TANGENT requires GX_NRM_NBT or GX_NRM_NBT3");
  }
  if (config.cpuVertexDecode) {
    return slice == NbtSlice::B ? "v_binrm"s : "v_tangent"s;
  }
  const auto sliceIdx"""
if with_decode not in s:
    if replace not in s:
        raise SystemExit("shader NBT decode insertion not found")
    s = s.replace(replace, with_decode, 1)

old = """  // Load points for line/point expansion
  std::string_view vidxAttr = "vidx"sv;
  if (config.lineMode != 0) {
    vtxInAttrs += ",\\n    @builtin(instance_index) iidx: u32";
    uniBufAttrs +=
        "\\n    line_width: f32,"
        "\\n    line_aspect_y: f32,"
        "\\n    line_tex_offset: f32,"
        "\\n    line_texcoord_mask: u32,";
    if (config.lineMode == 3) {
      // GX_POINTS: each instance = one vertex, expand to quad
      vtxXfrAttrsPre += fmt::format(
          "\\n    let in_vidx = iidx;"
          "\\n    let in_pos = {};"
          "\\n    let in_pnmtxidx = {};"
          "\\n    let mv_pos = vec4f(in_pos, 1.0) * ubuf.postex_mtx[in_pnmtxidx];",
          attr_load(config, GX_VA_POS, "in_vidx"sv), attr_load(config, GX_VA_PNMTXIDX, "in_vidx"sv));
    } else {
      // GX_LINES / GX_LINESTRIP: each instance = two vertices, expand to quad
      vtxXfrAttrsPre += fmt::format(
          "\\n    let use_b = vidx >= 2u;"
          "\\n    let vidx_a = iidx * {}u;"
          "\\n    let vidx_b = vidx_a + 1u;"
          "\\n    let in_vidx = select(vidx_a, vidx_b, use_b);"
          "\\n    let pos_a = {};"
          "\\n    let pos_b = {};"
          "\\n    let in_pos = select(pos_a, pos_b, use_b);"
          "\\n    let pnmtxidx_a = {};"
          "\\n    let pnmtxidx_b = {};"
          "\\n    let in_pnmtxidx = select(pnmtxidx_a, pnmtxidx_b, use_b);"
          "\\n    let mv_pos_a = vec4f(pos_a, 1.0) * ubuf.postex_mtx[pnmtxidx_a];"
          "\\n    let mv_pos_b = vec4f(pos_b, 1.0) * ubuf.postex_mtx[pnmtxidx_b];"
          "\\n    let mv_pos = select(mv_pos_a, mv_pos_b, use_b);",
          config.lineMode == 1 ? 2 : 1, attr_load(config, GX_VA_POS, "vidx_a"sv),
          attr_load(config, GX_VA_POS, "vidx_b"sv), attr_load(config, GX_VA_PNMTXIDX, "vidx_a"sv),
          attr_load(config, GX_VA_PNMTXIDX, "vidx_b"sv));
    }
    vidxAttr = "in_vidx"sv;
  } else if (config.attrs[GX_VA_PNMTXIDX].attrType == GX_NONE) {
"""
new = """  // Vertex inputs: storage-buffer vertex index, or CPU-decoded conventional attributes.
  if (config.cpuVertexDecode) {
    constexpr std::array<std::string_view, MaxDecodedVertexAttrs> DecodedInputs{
        "v_matrices: vec3u"sv, "v_pos: vec3f"sv,   "v_nrm: vec3f"sv,     "v_clr0: vec4f"sv,
        "v_clr1: vec4f"sv,     "v_tex0: vec2f"sv,  "v_tex1: vec2f"sv,    "v_tex2: vec2f"sv,
        "v_tex3: vec2f"sv,     "v_tex4: vec2f"sv,  "v_tex5: vec2f"sv,    "v_tex6: vec2f"sv,
        "v_tex7: vec2f"sv,     "v_binrm: vec3f"sv, "v_tangent: vec3f"sv, "v_line_end: vec4f"sv,
    };
    for (u32 i = 0; i < DecodedInputs.size(); ++i) {
      if (decoded_vertex_has_location(config, i)) {
        vtxInAttrs += fmt::format("{}\\n    @location({}) {}", vtxInAttrs.empty() ? "" : ",", i, DecodedInputs[i]);
      }
    }
  } else {
    vtxInAttrs += "\\n    @builtin(vertex_index) vidx: u32";
    if (config.lineMode != 0) {
      vtxInAttrs += ",\\n    @builtin(instance_index) iidx: u32";
    }
  }

  // Load points for line/point expansion.
  std::string_view vidxAttr = "vidx"sv;
  if (config.lineMode != 0) {
    uniBufAttrs +=
        "\\n    line_width: f32,"
        "\\n    line_aspect_y: f32,"
        "\\n    line_tex_offset: f32,"
        "\\n    line_texcoord_mask: u32,";
    if (config.cpuVertexDecode) {
      vtxXfrAttrsPre += "\\n    let vidx = v_matrices.z >> 24u;";
    }
    if (config.lineMode == 3) {
      // GX_POINTS: each instance = one vertex, expand to quad
      if (!config.cpuVertexDecode) {
        vtxXfrAttrsPre += "\\n    let in_vidx = iidx;";
      }
      vtxXfrAttrsPre += fmt::format(
          "\\n    let in_pos = {};"
          "\\n    let in_pnmtxidx = {};"
          "\\n    let mv_pos = vec4f(in_pos, 1.0) * ubuf.postex_mtx[in_pnmtxidx];",
          attr_load(config, GX_VA_POS, "in_vidx"sv), attr_load(config, GX_VA_PNMTXIDX, "in_vidx"sv));
    } else {
      // GX_LINES / GX_LINESTRIP: each instance = two vertices, expand to quad
      vtxXfrAttrsPre += "\\n    let use_b = vidx >= 2u;";
      if (!config.cpuVertexDecode) {
        vtxXfrAttrsPre += fmt::format(
            "\\n    let vidx_a = iidx * {}u;"
            "\\n    let vidx_b = vidx_a + 1u;"
            "\\n    let in_vidx = select(vidx_a, vidx_b, use_b);",
            config.lineMode == 1 ? 2 : 1);
      }
      vtxXfrAttrsPre += fmt::format(
          "\\n    let pos_a = {};"
          "\\n    let pos_b = {};"
          "\\n    let in_pos = select(pos_a, pos_b, use_b);"
          "\\n    let pnmtxidx_a = {};"
          "\\n    let pnmtxidx_b = {};"
          "\\n    let in_pnmtxidx = select(pnmtxidx_a, pnmtxidx_b, use_b);"
          "\\n    let mv_pos_a = vec4f(pos_a, 1.0) * ubuf.postex_mtx[pnmtxidx_a];"
          "\\n    let mv_pos_b = vec4f(pos_b, 1.0) * ubuf.postex_mtx[pnmtxidx_b];"
          "\\n    let mv_pos = select(mv_pos_a, mv_pos_b, use_b);",
          attr_load(config, GX_VA_POS, "vidx_a"sv), attr_load(config, GX_VA_POS, "vidx_b"sv),
          attr_load(config, GX_VA_PNMTXIDX, "vidx_a"sv), attr_load(config, GX_VA_PNMTXIDX, "vidx_b"sv));
    }
    vidxAttr = "in_vidx"sv;
  } else if (config.attrs[GX_VA_PNMTXIDX].attrType == GX_NONE) {
"""
if new not in s:
    if old not in s:
        raise SystemExit("shader vertex input block not found")
    s = s.replace(old, new, 1)

old = """@vertex
fn vs_main(
    @builtin(vertex_index) vidx: u32{3}
) -> VertexOutput {{
"""
new = """@vertex
fn vs_main({3}
) -> VertexOutput {{
"""
if new not in s:
    if old not in s:
        raise SystemExit("shader vs_main signature not found")
    s = s.replace(old, new, 1)
shader.write_text(s)

# Command processor: decode GX vertex bytes on CPU and upload conventional records.
cp = aur / "lib/gx/command_processor.cpp"
s = cp.read_text()
if '#include "vertex_loader.hpp"' not in s:
    s = s.replace('#include "texture.hpp"\n', '#include "texture.hpp"\n#include "vertex_loader.hpp"\n', 1)

old = """  } else if (prim == GX_LINES || prim == GX_LINESTRIP || prim == GX_POINTS) {
    buf.reserve_extra(6 * sizeof(u16));
    buf.append<u16>(0);
    buf.append<u16>(1);
    buf.append<u16>(3);
    buf.append<u16>(3);
    buf.append<u16>(2);
    buf.append<u16>(0);
    numIndices = 6;
"""
new = """  } else if (prim == GX_LINES || prim == GX_LINESTRIP || prim == GX_POINTS) {
    if (g_config.cpuVertexDecode) {
      buf.reserve_extra((vtxCount / 4) * 6 * sizeof(u16));
      for (u16 v = 0; v < vtxCount; v += 4) {
        const u16 idx0 = static_cast<u16>(vtxStart + v);
        buf.append(std::array{idx0, static_cast<u16>(idx0 + 1), static_cast<u16>(idx0 + 3)});
        buf.append(std::array{static_cast<u16>(idx0 + 3), static_cast<u16>(idx0 + 2), idx0});
        numIndices += 6;
      }
    } else {
      buf.reserve_extra(6 * sizeof(u16));
      buf.append<u16>(0);
      buf.append<u16>(1);
      buf.append<u16>(3);
      buf.append<u16>(3);
      buf.append<u16>(2);
      buf.append<u16>(0);
      numIndices = 6;
    }
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor line index block not found")
    s = s.replace(old, new, 1)

push_marker = """static void push_gx_draw(GXPrimitive prim, GXVtxFmt fmt, u16 vtxCount, gfx::Range vertRange, gfx::Range idxRange,
                         u32 numIndices) noexcept {
"""
helper = r'''// Resolve the GX pipeline before CPU vertex decoding; the decoded record layout is part of ShaderConfig.
static void prepare_pipeline(GXPrimitive prim, GXVtxFmt fmt) noexcept {
  auto& state = g_gxState;
  auto& cache = sDrawCache;
  const u8 lineMode = line_mode_for_prim(prim);
  const bool pipelineValid = cache.hasPipeline && (state.dirty & DirtyPipeline) == 0 && cache.fmt == fmt &&
                             cache.lineMode == lineMode && cache.config.msaaSamples == gfx::get_sample_count();
  if (!pipelineValid) {
    const bool hadPipeline = cache.hasPipeline;
    const auto prevSampledTextures = cache.shaderInfo.sampledTextures;
    const auto prevSampledIndTextures = cache.shaderInfo.sampledIndTextures;
    populate_pipeline_config(cache.config, prim, fmt);
    cache.shaderInfo = build_shader_info(cache.config.shaderConfig);
    cache.pipelineRef = gfx::pipeline_ref(cache.config);
    cache.fmt = fmt;
    cache.lineMode = lineMode;
    cache.hasPipeline = true;
    state.dirty = (state.dirty & ~DirtyPipeline) | DirtyUniform;
    if (!hadPipeline || prevSampledTextures != cache.shaderInfo.sampledTextures ||
        prevSampledIndTextures != cache.shaderInfo.sampledIndTextures) {
      cache.bindGeneration = 0;
    }
  }
}

// Convert a GX draw's raw vertex bytes into the conventional vertex layout expected by the Mali path.
static gfx::Range push_decoded_verts(GXPrimitive prim, GXVtxFmt fmt, std::span<const u8> vertexData, u16& vtxCount,
                                     size_t alignment) noexcept {
  ZoneScoped;
  prepare_pipeline(prim, fmt);
  const auto& state = g_gxState;
  const auto& config = sDrawCache.config.shaderConfig;
  const auto& loader = vertex_loader(config);
  AURORA_ASSERT(loader.vtxStride != 0 && vertexData.size() == static_cast<size_t>(vtxCount) * loader.vtxStride,
                "vertex data of {} bytes does not hold {} vertices of {} bytes", vertexData.size(), vtxCount,
                loader.vtxStride);
  const size_t stride = loader.layout.stride;
  u8* out = nullptr;
  if (config.lineMode == 0) {
    const gfx::Range range = gfx::map_verts(static_cast<size_t>(vtxCount) * stride, alignment, out);
    if (out != nullptr) {
      decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays, state.currentPnMtx);
    }
    return range;
  }
  const u32 instances = line_instance_count(config.lineMode, vtxCount);
  AURORA_ASSERT(instances * 4 <= 0xFFFF, "too many line/point primitives in one draw ({})", instances);
  static std::vector<u8> decoded;
  decoded.resize(static_cast<size_t>(vtxCount) * stride);
  decode_vertices(loader, vertexData.data(), vtxCount, decoded.data(), state.arrays, state.currentPnMtx);
  vtxCount = static_cast<u16>(instances * 4);
  const gfx::Range range = gfx::map_verts(static_cast<size_t>(vtxCount) * stride, alignment, out);
  if (out != nullptr) {
    expand_line_vertices(loader, decoded.data(), instances, out);
  }
  return range;
}

'''
if helper not in s:
    if push_marker not in s:
        raise SystemExit("command_processor push_gx_draw marker not found")
    s = s.replace(push_marker, helper + push_marker, 1)

old = """  DrawImmediateData immediates{.vtxStart = vertRange.offset, .currentPnMtx = state.currentPnMtx};
  for (int i = GX_VA_POS; i <= GX_VA_TEX7; ++i) {
    if (state.vtxDesc[i] != GX_INDEX8 && state.vtxDesc[i] != GX_INDEX16) {
      continue;
    }
    auto& array = state.arrays[i];
    if (array.cachedRange.size == 0) {
      array.cachedRange = gfx::push_storage(static_cast<const uint8_t*>(array.data), array.size);
    }
    immediates.arrayStart[i - GX_VA_POS] = array.cachedRange.offset;
  }

  const u8 lineMode = line_mode_for_prim(prim);
  const bool pipelineValid = cache.hasPipeline && (state.dirty & DirtyPipeline) == 0 && cache.fmt == fmt &&
                             cache.lineMode == lineMode && cache.config.msaaSamples == gfx::get_sample_count();
  if (!pipelineValid) {
    const bool hadPipeline = cache.hasPipeline;
    const auto prevSampledTextures = cache.shaderInfo.sampledTextures;
    const auto prevSampledIndTextures = cache.shaderInfo.sampledIndTextures;
    populate_pipeline_config(cache.config, prim, fmt);
    cache.shaderInfo = build_shader_info(cache.config.shaderConfig);
    cache.pipelineRef = gfx::pipeline_ref(cache.config);
    cache.fmt = fmt;
    cache.lineMode = lineMode;
    cache.hasPipeline = true;
    state.dirty = (state.dirty & ~DirtyPipeline) | DirtyUniform;
    if (!hadPipeline || prevSampledTextures != cache.shaderInfo.sampledTextures ||
        prevSampledIndTextures != cache.shaderInfo.sampledIndTextures) {
      cache.bindGeneration = 0;
    }
  }
"""
new = """  DrawImmediateData immediates{.vtxStart = vertRange.offset, .currentPnMtx = state.currentPnMtx};
  if (!g_config.cpuVertexDecode) {
    for (int i = GX_VA_POS; i <= GX_VA_TEX7; ++i) {
      if (state.vtxDesc[i] != GX_INDEX8 && state.vtxDesc[i] != GX_INDEX16) {
        continue;
      }
      auto& array = state.arrays[i];
      if (array.cachedRange.size == 0) {
        array.cachedRange = gfx::push_storage(static_cast<const uint8_t*>(array.data), array.size);
      }
      immediates.arrayStart[i - GX_VA_POS] = array.cachedRange.offset;
    }
  }

  prepare_pipeline(prim, fmt);
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor pipeline extraction block not found")
    s = s.replace(old, new, 1)

old = """  uint32_t instanceCount = 1;
  if (prim == GX_LINES) {
    instanceCount = vtxCount / 2;
  } else if (prim == GX_LINESTRIP) {
    instanceCount = vtxCount - 1;
  } else if (prim == GX_POINTS) {
    instanceCount = vtxCount;
  }
"""
new = """  uint32_t instanceCount = 1;
  if (!g_config.cpuVertexDecode) {
    if (prim == GX_LINES) {
      instanceCount = vtxCount / 2;
    } else if (prim == GX_LINESTRIP) {
      instanceCount = vtxCount - 1;
    } else if (prim == GX_POINTS) {
      instanceCount = vtxCount;
    }
  }
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor instance count block not found")
    s = s.replace(old, new, 1)

old = """  // Push raw vertex data to buffer. Merged draws must remain contiguous with the previous range.
  const auto vertexData = reader.take(totalVtxBytes);
  diag_check_indices(vertexData.data(), vtxCount, fmt, vtxSize);   // smstrikers-port
  gfx::Range vertRange = gfx::push_verts(vertexData.data(), vertexData.size(), canMerge ? 0 : 4);
"""
new = """  // Push raw or CPU-decoded vertex data. Merged draws remain contiguous.
  const auto vertexData = reader.take(totalVtxBytes);
  diag_check_indices(vertexData.data(), vtxCount, fmt, vtxSize);   // smstrikers-port
  const gfx::Range vertRange = g_config.cpuVertexDecode
                                   ? push_decoded_verts(prim, fmt, vertexData, vtxCount, canMerge ? 0 : 4)
                                   : gfx::push_verts(vertexData.data(), vertexData.size(), canMerge ? 0 : 4);
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor draw_prim vertex upload not found")
    s = s.replace(old, new, 1)

old = """    const u16 vtxCount = reader.read<u16>();
    const u32 indexCount = reader.read<u32>();
"""
new = """    u16 vtxCount = reader.read<u16>();
    const u32 indexCount = reader.read<u32>();
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor indexed vtxCount not found")
    s = s.replace(old, new, 1)

old = """    diag_check_indices(vertexData.data(), vtxCount, fmt, vtxSize);   // smstrikers-port
    const gfx::Range vertRange = gfx::push_verts(vertexData.data(), vertexData.size(), 4);
"""
new = """    diag_check_indices(vertexData.data(), vtxCount, fmt, vtxSize);   // smstrikers-port
    const gfx::Range vertRange = g_config.cpuVertexDecode ? push_decoded_verts(prim, fmt, vertexData, vtxCount, 4)
                                                          : gfx::push_verts(vertexData.data(), vertexData.size(), 4);
"""
if new not in s:
    if old not in s:
        raise SystemExit("command_processor indexed vertex upload not found")
    s = s.replace(old, new, 1)
cp.write_text(s)

# Mali compatibility: no vertex-stage storage blocks when CPU decode is active.
frame = aur / "lib/gfx/frame.cpp"
s = frame.read_text()
if '#include "../internal.hpp"' not in s:
    s = s.replace('#include "../gx/gx.hpp"\n', '#include "../gx/gx.hpp"\n#include "../internal.hpp"\n', 1)
old = """  {
    constexpr std::array layoutEntries{
        // Vertex data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 0,
            .visibility = wgpu::ShaderStage::Vertex,
"""
new = """  {
    const wgpu::ShaderStage vertexStorageStage =
        g_config.cpuVertexDecode ? wgpu::ShaderStage::None : wgpu::ShaderStage::Vertex;
    const std::array layoutEntries{
        // Vertex data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 0,
            .visibility = g_config.cpuVertexDecode ? wgpu::ShaderStage::Fragment : wgpu::ShaderStage::Vertex,
"""
if new not in s:
    if old not in s:
        raise SystemExit("frame static layout start not found")
    s = s.replace(old, new, 1)
old = """        wgpu::BindGroupLayoutEntry{
            .binding = 1,
            .visibility = wgpu::ShaderStage::Vertex | wgpu::ShaderStage::Fragment,
"""
new = """        wgpu::BindGroupLayoutEntry{
            .binding = 1,
            .visibility = vertexStorageStage | wgpu::ShaderStage::Fragment,
"""
if new not in s:
    if old not in s:
        raise SystemExit("frame storage visibility not found")
    s = s.replace(old, new, 1)
frame.write_text(s)

# Handheld memory budget. Keep Strikers' measured storage/texture pools: its own
# comments document peaks of 8.10 MiB storage and 19.45 MiB texture upload.
# CPU-decoded float records need the larger 12 MiB vertex pool from the Melee path.
resources = aur / "lib/gfx/resources.hpp"
s = resources.read_text()
old = "inline constexpr uint64_t VertexBufferSize = 5242880;    // 5 MiB"
new = "inline constexpr uint64_t VertexBufferSize = 12 * 1024 * 1024; // 12 MiB, CPU-decoded vertices"
if new not in s:
    if old not in s:
        raise SystemExit("resources VertexBufferSize line not found")
    s = s.replace(old, new, 1)
resources.write_text(s)

# Three staging maps instead of five, matching the low-memory handheld path.
frame_h = aur / "lib/gfx/frame.hpp"
s = frame_h.read_text()
old = """inline constexpr size_t FrameSlotCount = 2;
inline constexpr size_t StagingBufferCount = FrameSlotCount + 3;
"""
new = """inline constexpr size_t FrameSlotCount = 2;
#ifdef MELEE_MIYOO_FLIP
inline constexpr size_t StagingBufferCount = FrameSlotCount + 1;
#else
inline constexpr size_t StagingBufferCount = FrameSlotCount + 3;
#endif
"""
if new not in s:
    if old not in s:
        raise SystemExit("frame staging buffer count not found")
    s = s.replace(old, new, 1)
frame_h.write_text(s)


# Dawn compatibility-mode limits for Mali GLES. CPU vertex decode removes all
# vertex-stage storage-buffer reads, so this device request must explicitly ask
# for zero vertex-stage storage buffers while keeping two for the fragment stage.
gpu = aur / "lib/webgpu/gpu.cpp"
s = gpu.read_text()

old = """    wgpu::CompatibilityModeLimits compatibilityModeLimits{wgpu::CompatibilityModeLimits::Init{
        .maxStorageBuffersInVertexStage = 2,
        .maxStorageBuffersInFragmentStage = 2,
    }};
"""
new = """    wgpu::CompatibilityModeLimits compatibilityModeLimits{wgpu::CompatibilityModeLimits::Init{
#ifdef MELEE_MIYOO_FLIP
        // Mali-G31 GLES exposes zero vertex-stage storage blocks. Vertex data is
        // supplied through AuroraConfig::cpuVertexDecode on the R36S.
        .maxStorageBuffersInVertexStage = 0,
#else
        .maxStorageBuffersInVertexStage = 2,
#endif
        .maxStorageBuffersInFragmentStage = 2,
    }};
"""
if new not in s:
    if old not in s:
        raise SystemExit("gpu compatibility storage-limit block not found")
    s = s.replace(old, new, 1)

old = """        .maxStorageBuffersPerShaderStage = 2,
        .minUniformBufferOffsetAlignment =
"""
new = """        .maxStorageBuffersPerShaderStage = 2,
#ifdef MELEE_MIYOO_FLIP
        .maxUniformBufferBindingSize = supportedLimits.maxUniformBufferBindingSize,
#endif
        .minUniformBufferOffsetAlignment =
"""
if new not in s:
    if old not in s:
        raise SystemExit("gpu maxUniformBufferBindingSize insertion point not found")
    s = s.replace(old, new, 1)

# Emit the compatibility-stage limits in the runtime log so device reports tell
# us immediately whether the handheld branch made it into the binary.
old = """        "\\n  maxStorageBuffersPerShaderStage: {}"
        "\\n  minUniformBufferOffsetAlignment: {}"
"""
new = """        "\\n  maxStorageBuffersPerShaderStage: {}"
        "\\n  maxStorageBuffersInVertexStage: {}"
        "\\n  maxStorageBuffersInFragmentStage: {}"
        "\\n  minUniformBufferOffsetAlignment: {}"
"""
if new not in s:
    if old not in s:
        raise SystemExit("gpu runtime limit-log format insertion point not found")
    s = s.replace(old, new, 1)

old = """        requiredLimits.maxStorageBuffersPerShaderStage, requiredLimits.minUniformBufferOffsetAlignment,
        requiredLimits.minStorageBufferOffsetAlignment, requiredLimits.maxImmediateSize);
"""
new = """        requiredLimits.maxStorageBuffersPerShaderStage, compatibilityModeLimits.maxStorageBuffersInVertexStage,
        compatibilityModeLimits.maxStorageBuffersInFragmentStage, requiredLimits.minUniformBufferOffsetAlignment,
        requiredLimits.minStorageBufferOffsetAlignment, requiredLimits.maxImmediateSize);
"""
if new not in s:
    if old not in s:
        raise SystemExit("gpu runtime limit-log args insertion point not found")
    s = s.replace(old, new, 1)

gpu.write_text(s)

# Build-time guard: never produce another nominally successful R36S build that
# still requests two vertex-stage storage buffers.
verify = gpu.read_text()
if ".maxStorageBuffersInVertexStage = 0" not in verify or "#ifdef MELEE_MIYOO_FLIP" not in verify:
    raise SystemExit("R36S Mali Dawn limit verification failed")

print("Applied Aurora CPU vertex decode for R36S Mali GLES")
