#!/usr/bin/env python3
"""RC13: emit GX triangle/quad indices directly into the frame index stream.

The existing batch_draw path builds a temporary ByteBuffer for each of
thousands of tiny draw calls and then copies it into the frame's index
buffer (mapped GL stream). RC13 adds the exact analogue of map_verts()
for indices and emits GX_TRIANGLES / GX_QUADS straight into the frame
stream. Preserve 16-bit wrapping, quad winding, draw merging,
alignment and all original fallback paths.

Limits: only ordinary unindexed triangle/quad calls, 1..8192
vertices (so the u16 result cannot wrap), on the existing CPU vertex
decode path, after the same push_decoded_verts. All special primitives,
points, externally indexed/resident paths remain unchanged.

No GL operations, shaders, EFB/shadow/water, synchronization or user
configuration changed. ARM build and real R36S validation required.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
hdr=root/"extern/aurora/lib/gfx/recording.hpp"
src=root/"extern/aurora/lib/gfx/recording.cpp"
gx=root/"extern/aurora/lib/gx/command_processor.cpp"

def replace_exact(s,old,new,label):
    n=s.count(old)
    if n!=1:raise SystemExit(f"RC13 {label}: anchor count {n} != 1")
    return s.replace(old,new,1)

h=hdr.read_text()
h=replace_exact(
    h,
    "Range push_indices(const uint8_t* data, size_t length, size_t alignment);\n",
    "// Reserve an index stream slice directly, mirroring map_verts; null on\n"
    "// inactive recording or stream overflow. No intermediate CPU copy.\n"
    "Range map_indices(size_t length, size_t alignment, uint8_t*& data);\n"
    "Range push_indices(const uint8_t* data, size_t length, size_t alignment);\n",
    "recording.hpp declaration")
hdr.write_text(h)

s=src.read_text()
anchor="""Range push_indices(const uint8_t* data, size_t length, size_t alignment) {
  ZoneScoped;
  if (!check_recording("push_indices")) {
    return {};
  }
  return push(current_frame_packet().indices, data, length, alignment);
}
"""
new="""Range map_indices(size_t length, size_t alignment, uint8_t*& data) {
  ZoneScoped;
  data = nullptr;
  if (!check_recording("map_indices")) {
    return {};
  }
  auto& indices = current_frame_packet().indices;
  const auto range = map(indices, length, alignment);
  if (range.size == length && indices.data() != nullptr) {
    data = indices.data() + range.offset;
  }
  return range;
}

"""+anchor
s=replace_exact(s,anchor,new,"recording.cpp implementation")
src.write_text(s)

s=gx.read_text()
start="""  static ByteBuffer indices;
  indices.clear();
  u32 numIndices = 0;
  if (points) {
"""
repl="""  static ByteBuffer indices;
  indices.clear();
  u32 numIndices = 0;
  gfx::Range idxRange;
  // RC13: direct index emission for the most common GX primitives,
  // avoiding a temporary ByteBuffer and a second memcpy into the
  // frame's persistent mapped stream. 8192 also avoids u16 count wrap.
  // Unusual and pre-indexed primitives keep Aurora's exact old path.
  const bool r36sDirectIndices =
      !points && indexData.empty() && vtxCount > 0 && vtxCount <= 8192 &&
      (prim == GX_TRIANGLES || prim == GX_QUADS);
  if (r36sDirectIndices) {
    numIndices = prim == GX_TRIANGLES ? static_cast<u32>(vtxCount)
                                      : ((static_cast<u32>(vtxCount) + 3u) / 4u) * 6u;
    u8* out = nullptr;
    idxRange = gfx::map_indices(static_cast<size_t>(numIndices) * sizeof(u16), merge ? 0 : 4, out);
    if (out != nullptr) {
      if (prim == GX_TRIANGLES) {
        for (u32 v = 0; v < vtxCount; ++v) {
          const u16 index = static_cast<u16>(base + v);
          std::memcpy(out + static_cast<size_t>(v) * sizeof(index), &index, sizeof(index));
        }
      } else {
        const u32 quads = (static_cast<u32>(vtxCount) + 3u) / 4u;
        for (u32 q = 0; q < quads; ++q) {
          const u16 a = static_cast<u16>(base + q * 4u);
          const u16 b = static_cast<u16>(a + 1);
          const u16 c = static_cast<u16>(a + 2);
          const u16 d = static_cast<u16>(a + 3);
          const std::array<u16, 6> indicesForQuad = {a, b, c, c, d, a};
          std::memcpy(out + static_cast<size_t>(q) * sizeof(indicesForQuad),
                      indicesForQuad.data(), sizeof(indicesForQuad));
        }
      }
    }
  } else if (points) {
"""
s=replace_exact(s,start,repl,"batch_draw temporary index buffer")
old="""  gfx::Range idxRange;
  if (numIndices != 0) {
    idxRange = gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4);
  }
"""
new="""  if (!r36sDirectIndices && numIndices != 0) {
    idxRange = gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4);
  }
"""
s=replace_exact(s,old,new,"no second push for mapped indices")
for required in [
    "gfx::profile::Scope r36sRc8IndexProfile(\"index_generate\")",
    "static std::array<R36SLoaderSlot, 256> r36sLoaderSlots{};",
    "gfx::detail::increment_merged_draw_count();",
    "previous->idxRange.size += idxRange.size;",
    "previous->indexCount += numIndices;",
    "prepare_idx_buffer(indices, prim, base, vtxCount);",
    "gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4);",
]:
    if required not in s: raise SystemExit("RC13 invariant missing: "+required)
gx.write_text(s)
print("RC13: direct mapped GX triangle/quad index emission installed; fallback/synchronization preserved")
