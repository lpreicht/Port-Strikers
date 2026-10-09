#!/usr/bin/env python3
"""RC10: reduce repeated CPU work without changing GX output.

RC8 sampled outdoor frames have thousands of very small batch_draw calls.
(1) batch_draw's prepare_draw_state() already calls prepare_pipeline().
    Avoid repeating that identical check in push_decoded_verts() ONLY for
    batch_draw, keeping normal preparation for every other call site.
(2) For triangles and quads not covered by RC9's 3/4-vertex fast path,
    grow the index byte buffer once and write the same little-endian u16
    indices directly into it. The old paths remain for non-batch variants.

No shader, EFB, shadow, water, rendering state, DMA, scheduler or
presentation changes. Keeps user-facing defaults: no manual A/B work.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()

def replace_exact(old, new, label):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit(f"RC10 {label}: anchor count {n}, expected 1")
    s=s.replace(old,new,1)

replace_exact(
"""static gfx::Range push_decoded_verts(GXPrimitive prim, GXVtxFmt fmt, std::span<const u8> vertexData, u16& vtxCount,
                                     size_t alignment, u32 matrixWordZ = 0) noexcept {
  ZoneScoped;
  gfx::profile::Scope r36sRc8VertProfile("vertex_upload_decode");
  prepare_pipeline(prim, fmt);
""",
"""static gfx::Range push_decoded_verts(GXPrimitive prim, GXVtxFmt fmt, std::span<const u8> vertexData, u16& vtxCount,
                                     size_t alignment, u32 matrixWordZ = 0, bool r36sAlreadyPrepared = false) noexcept {
  ZoneScoped;
  gfx::profile::Scope r36sRc8VertProfile("vertex_upload_decode");
  // batch_draw already resolved the exact GX pipeline in prepare_draw_state().
  // All non-batch callers still invoke prepare_pipeline() as before.
  if (!r36sAlreadyPrepared) {
    prepare_pipeline(prim, fmt);
  }
""", "skip duplicate pipeline check only after prepare_draw_state")

replace_exact(
"""  const gfx::Range vertRange = push_decoded_verts(prim, fmt, vertexData, vtxCount, merge ? 0 : 4, record << 8);
""",
"""  // prepare_draw_state() above already called prepare_pipeline() for prim/fmt.
  const gfx::Range vertRange = push_decoded_verts(prim, fmt, vertexData, vtxCount, merge ? 0 : 4, record << 8, true);
""", "batch_draw pre-prepared vertex decode")

anchor="""    if (prim == GX_QUADS && vtxCount == 4) {
      const u16 i0 = vtxStart;
      const u16 i1 = static_cast<u16>(vtxStart + 1);
      const u16 i2 = static_cast<u16>(vtxStart + 2);
      const u16 i3 = static_cast<u16>(vtxStart + 3);
      buf.append(std::array{i0, i1, i2, i2, i3, i0});
      return 6;
    }
"""
replacement=anchor+"""    // Fast path for non-tiny triangle lists. ByteBuffer::append() calls
    // resize per vertex even after reserve_extra(); append_zeroes() once
    // instead. memcpy preserves host-endian u16 bytes exactly.
    if (prim == GX_TRIANGLES && vtxCount > 3) {
      const size_t oldLen = buf.size();
      buf.append_zeroes(static_cast<size_t>(vtxCount) * sizeof(u16));
      u8* out = buf.data() + oldLen;
      for (u32 v = 0; v < vtxCount; ++v) {
        const u16 idx = static_cast<u16>(vtxStart + v);
        std::memcpy(out + static_cast<size_t>(v) * sizeof(idx), &idx, sizeof(idx));
      }
      return vtxCount;
    }
    // Original quad loop processes groups of four even if vtxCount is
    // not divisible by four. Preserve that behavior, including u16 wrap.
    if (prim == GX_QUADS && vtxCount > 4) {
      const size_t groups = (static_cast<size_t>(vtxCount) + 3u) / 4u;
      const size_t oldLen = buf.size();
      buf.append_zeroes(groups * 6u * sizeof(u16));
      u8* out = buf.data() + oldLen;
      for (size_t q = 0; q < groups; ++q) {
        const u16 start = static_cast<u16>(vtxStart + q * 4u);
        const u16 i1 = static_cast<u16>(start + 1);
        const u16 i2 = static_cast<u16>(start + 2);
        const u16 i3 = static_cast<u16>(start + 3);
        const std::array<u16, 6> idx = {start, i1, i2, i2, i3, start};
        std::memcpy(out + q * sizeof(idx), idx.data(), sizeof(idx));
      }
      return static_cast<u16>(groups * 6u);
    }
"""
replace_exact(anchor, replacement, "bulk index buffer fast paths")
for required in (
  "prepare_draw_state(prim, fmt, immediates);",
  "gfx::push_draw_command(DrawData{",
  "gfx::detail::increment_merged_draw_count();",
  "if (!r36sAlreadyPrepared)",
  "gfx::profile::Scope r36sRc8IndexProfile(\"index_generate\")",
  "gfx::profile::Scope r36sRc8VertProfile(\"vertex_upload_decode\")",
):
    if required not in s:raise SystemExit(f"RC10 invariant missing: {required}")
p.write_text(s)
print("RC10: pre-resolved batch pipeline and bulk triangle/quad index writes; original geometry bytes preserved")
