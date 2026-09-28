#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new, count=1):
    p = root / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:180]!r}")
    p.write_text(s.replace(old, new, count))

def replace_all(rel, old, new):
    p = root / rel
    s = p.read_text()
    n = s.count(old)
    if n == 0:
        raise SystemExit(f"pattern not found in {rel}: {old!r}")
    p.write_text(s.replace(old, new))
    print(f"{rel}: replaced {n} occurrences of {old!r}")

# ---------------------------------------------------------------------------
# Dawn/Aurora device limits: this R36S path removes vertex-stage SSBOs entirely.
# ---------------------------------------------------------------------------
replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """    wgpu::CompatibilityModeLimits compatibilityModeLimits{wgpu::CompatibilityModeLimits::Init{
        .maxStorageBuffersInVertexStage = 2,
        .maxStorageBuffersInFragmentStage = 2,
    }};
""",
    """    wgpu::CompatibilityModeLimits compatibilityModeLimits{wgpu::CompatibilityModeLimits::Init{
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
        .maxStorageBuffersInVertexStage = 0,
        .maxStorageBuffersInFragmentStage = 0,
#else
        .maxStorageBuffersInVertexStage = 2,
        .maxStorageBuffersInFragmentStage = 2,
#endif
    }};
""",
)

# ---------------------------------------------------------------------------
# GPU-side mirrors for GX vertex/attribute memory.
# 2048 texels * 4 bytes = 8192 bytes per row (WebGPU 256-byte aligned).
# VertexBufferSize 5 MiB -> 2048 x 640 R32Uint exactly.
# StorageBufferSize 8 MiB -> 2048 x 1024 R32Uint exactly.
# ---------------------------------------------------------------------------
replace(
    "extern/aurora/lib/gfx/common.cpp",
    """wgpu::Buffer g_storageBuffer;
enum class BufferMapState {
""",
    """wgpu::Buffer g_storageBuffer;
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
static constexpr uint32_t R36SFetchTextureWidth = 2048;
static constexpr uint32_t R36SFetchBytesPerRow = R36SFetchTextureWidth * sizeof(uint32_t);
static constexpr uint32_t R36SVertexFetchTextureHeight = VertexBufferSize / R36SFetchBytesPerRow;
static constexpr uint32_t R36SStorageFetchTextureHeight = StorageBufferSize / R36SFetchBytesPerRow;
static_assert(VertexBufferSize % R36SFetchBytesPerRow == 0);
static_assert(StorageBufferSize % R36SFetchBytesPerRow == 0);
static_assert(R36SFetchBytesPerRow % 256 == 0);
static wgpu::Texture g_r36sVertexFetchTexture;
static wgpu::TextureView g_r36sVertexFetchView;
static wgpu::Texture g_r36sStorageFetchTexture;
static wgpu::TextureView g_r36sStorageFetchView;
#endif
enum class BufferMapState {
""",
)

replace(
    "extern/aurora/lib/gfx/common.cpp",
    """  StagingHighWater copied;
  AuroraStats stats{};
""",
    """  StagingHighWater copied;
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
  StagingHighWater textureMirrored;
#endif
  AuroraStats stats{};
""",
)

replace(
    "extern/aurora/lib/gfx/common.cpp",
    """  createBuffer(g_storageBuffer, wgpu::BufferUsage::Storage | wgpu::BufferUsage::CopyDst, StorageBufferSize,
               "Shared Storage Buffer");
  for (size_t i = 0; i < g_stagingBuffers.size(); ++i) {
""",
    """  createBuffer(g_storageBuffer, wgpu::BufferUsage::Storage | wgpu::BufferUsage::CopyDst, StorageBufferSize,
               "Shared Storage Buffer");
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
  const auto createFetchTexture = [&](wgpu::Texture& texture, wgpu::TextureView& view, uint32_t height,
                                      const char* label) {
    const wgpu::TextureDescriptor descriptor{
        .label = label,
        .usage = wgpu::TextureUsage::TextureBinding | wgpu::TextureUsage::CopyDst,
        .dimension = wgpu::TextureDimension::e2D,
        .size =
            wgpu::Extent3D{
                .width = R36SFetchTextureWidth,
                .height = height,
                .depthOrArrayLayers = 1,
            },
        .format = wgpu::TextureFormat::R32Uint,
        .mipLevelCount = 1,
        .sampleCount = 1,
    };
    texture = g_device.CreateTexture(&descriptor);
    view = texture.CreateView();
  };
  createFetchTexture(g_r36sVertexFetchTexture, g_r36sVertexFetchView, R36SVertexFetchTextureHeight,
                     "R36S Vertex Fetch Texture");
  createFetchTexture(g_r36sStorageFetchTexture, g_r36sStorageFetchView, R36SStorageFetchTextureHeight,
                     "R36S Attribute Fetch Texture");
#endif
  for (size_t i = 0; i < g_stagingBuffers.size(); ++i) {
""",
)

# Replace the static group entries with unsigned texture bindings on R36S.
replace(
    "extern/aurora/lib/gfx/common.cpp",
    """    constexpr std::array layoutEntries{
        // Vertex data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 0,
            .visibility = wgpu::ShaderStage::Vertex,
            .buffer =
                wgpu::BufferBindingLayout{
                    .type = wgpu::BufferBindingType::ReadOnlyStorage,
                },
        },
        // Storage data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 1,
            .visibility = wgpu::ShaderStage::Vertex,
            .buffer =
                wgpu::BufferBindingLayout{
                    .type = wgpu::BufferBindingType::ReadOnlyStorage,
                },
        },
    };
""",
    """    constexpr std::array layoutEntries{
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
        wgpu::BindGroupLayoutEntry{
            .binding = 0,
            .visibility = wgpu::ShaderStage::Vertex,
            .texture =
                wgpu::TextureBindingLayout{
                    .sampleType = wgpu::TextureSampleType::Uint,
                    .viewDimension = wgpu::TextureViewDimension::e2D,
                },
        },
        wgpu::BindGroupLayoutEntry{
            .binding = 1,
            .visibility = wgpu::ShaderStage::Vertex,
            .texture =
                wgpu::TextureBindingLayout{
                    .sampleType = wgpu::TextureSampleType::Uint,
                    .viewDimension = wgpu::TextureViewDimension::e2D,
                },
        },
#else
        // Vertex data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 0,
            .visibility = wgpu::ShaderStage::Vertex,
            .buffer =
                wgpu::BufferBindingLayout{
                    .type = wgpu::BufferBindingType::ReadOnlyStorage,
                },
        },
        // Storage data buffer
        wgpu::BindGroupLayoutEntry{
            .binding = 1,
            .visibility = wgpu::ShaderStage::Vertex,
            .buffer =
                wgpu::BufferBindingLayout{
                    .type = wgpu::BufferBindingType::ReadOnlyStorage,
                },
        },
#endif
    };
""",
)

replace(
    "extern/aurora/lib/gfx/common.cpp",
    """    const std::array entries{
        wgpu::BindGroupEntry{
            .binding = 0,
            .buffer = g_vertexBuffer,
        },
        wgpu::BindGroupEntry{
            .binding = 1,
            .buffer = g_storageBuffer,
        },
    };
""",
    """    const std::array entries{
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
        wgpu::BindGroupEntry{
            .binding = 0,
            .textureView = g_r36sVertexFetchView,
        },
        wgpu::BindGroupEntry{
            .binding = 1,
            .textureView = g_r36sStorageFetchView,
        },
#else
        wgpu::BindGroupEntry{
            .binding = 0,
            .buffer = g_vertexBuffer,
        },
        wgpu::BindGroupEntry{
            .binding = 1,
            .buffer = g_storageBuffer,
        },
#endif
    };
""",
)

# Release mirrors during shutdown.
replace(
    "extern/aurora/lib/gfx/common.cpp",
    """  g_storageBuffer = {};
  g_stagingBuffers.fill({});
""",
    """  g_storageBuffer = {};
#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
  g_r36sVertexFetchView = {};
  g_r36sVertexFetchTexture = {};
  g_r36sStorageFetchView = {};
  g_r36sStorageFetchTexture = {};
#endif
  g_stagingBuffers.fill({});
""",
)

# Mirror only the high-water rows needed by this frame. A partial final row is
# intentionally recopied; shader accesses stay within actual high-water data.
replace(
    "extern/aurora/lib/gfx/common.cpp",
    """static bool needs_staging_copy(const FramePacket& frame, const FrameOp& op) {
""",
    """#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
static void copy_staging_texture_range(wgpu::CommandEncoder& cmd, const FramePacket& frame, uint32_t& mirrored,
                                       uint32_t highWater, uint64_t stagingOffset, const wgpu::Texture& dst,
                                       uint32_t textureHeight) {
  if (highWater <= mirrored) {
    return;
  }

  const uint32_t maxBytes = textureHeight * R36SFetchBytesPerRow;
  const uint32_t clampedHighWater = std::min(highWater, maxBytes);
  if (clampedHighWater <= mirrored) {
    return;
  }

  const uint32_t startRow = mirrored / R36SFetchBytesPerRow;
  const uint32_t endRow = (clampedHighWater + R36SFetchBytesPerRow - 1u) / R36SFetchBytesPerRow;
  if (endRow <= startRow) {
    mirrored = clampedHighWater;
    return;
  }

  const wgpu::TexelCopyBufferInfo src{
      .layout =
          wgpu::TexelCopyBufferLayout{
              .offset = stagingOffset + static_cast<uint64_t>(startRow) * R36SFetchBytesPerRow,
              .bytesPerRow = R36SFetchBytesPerRow,
              .rowsPerImage = endRow - startRow,
          },
      .buffer = g_stagingBuffers[frame.stagingBuffer],
  };
  const wgpu::TexelCopyTextureInfo dstInfo{
      .texture = dst,
      .origin =
          wgpu::Origin3D{
              .x = 0,
              .y = startRow,
              .z = 0,
          },
  };
  const wgpu::Extent3D size{
      .width = R36SFetchTextureWidth,
      .height = endRow - startRow,
      .depthOrArrayLayers = 1,
  };
  cmd.CopyBufferToTexture(&src, &dstInfo, &size);
  mirrored = clampedHighWater;
}
#endif

static bool needs_staging_copy(const FramePacket& frame, const FrameOp& op) {
""",
)

replace(
    "extern/aurora/lib/gfx/common.cpp",
    """  copy_staging_buffer_range(cmd, frame, frame.copied.storage, highWater.storage, StorageStagingOffset, g_storageBuffer);

  if constexpr (UseTextureBuffer) {
""",
    """  copy_staging_buffer_range(cmd, frame, frame.copied.storage, highWater.storage, StorageStagingOffset, g_storageBuffer);

#ifdef AURORA_R36S_VERTEX_TEXTURE_FETCH
  copy_staging_texture_range(cmd, frame, frame.textureMirrored.verts, highWater.verts, VertexStagingOffset,
                             g_r36sVertexFetchTexture, R36SVertexFetchTextureHeight);
  copy_staging_texture_range(cmd, frame, frame.textureMirrored.storage, highWater.storage, StorageStagingOffset,
                             g_r36sStorageFetchTexture, R36SStorageFetchTextureHeight);
#endif

  if constexpr (UseTextureBuffer) {
""",
)

# ---------------------------------------------------------------------------
# GX WGSL: keep all byte/word conversion helpers, but replace storage pointers
# with private selector pointers and source words through two R32Uint textures.
# ---------------------------------------------------------------------------
replace_all(
    "extern/aurora/lib/gx/shader.cpp",
    "ptr<storage, array<u32>>",
    "ptr<private, u32>",
)

replace(
    "extern/aurora/lib/gx/shader.cpp",
    """fn load_word(p: ptr<private, u32>, word_idx: u32) -> u32 {{
  // This guard is not expected to handle routine out-of-bounds accesses.
  // It appears to discourage some Adreno drivers/optimizers from storage buffer
  // optimizations that can cause visual artifacts, including vertex explosions
  // in Dusklight.
  if (word_idx < arrayLength(p)) {{
    return p[word_idx];
  }}
  return 0u;
}}
""",
    """fn load_word(p: ptr<private, u32>, word_idx: u32) -> u32 {{
  let selector = *p;
  let x = i32(word_idx & 2047u);
  let y = i32(word_idx >> 11u);
  if (selector == 0u) {{
    if (word_idx < 1310720u) {{
      return textureLoad(vtex, vec2i(x, y), 0).x;
    }}
  }} else {{
    if (word_idx < 2097152u) {{
      return textureLoad(atex, vec2i(x, y), 0).x;
    }}
  }}
  return 0u;
}}
""",
)

replace(
    "extern/aurora/lib/gx/shader.cpp",
    """@group(0) @binding(0)
var<storage, read> vbuf: array<u32>;
@group(0) @binding(1)
var<storage, read> abuf: array<u32>;
""",
    """@group(0) @binding(0)
var vtex: texture_2d<u32>;
@group(0) @binding(1)
var atex: texture_2d<u32>;
var<private> vbuf: u32 = 0u;
var<private> abuf: u32 = 1u;
""",
)

print("R36S vertex SSBO -> R32Uint texture fetch patch applied")
