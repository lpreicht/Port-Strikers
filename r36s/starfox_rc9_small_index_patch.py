#!/usr/bin/env python3
"""RC9: optional exact-index fast path for common tiny GX draw primitives.

Aurora RC8 sampled profiles on map 8 showed ~10ms of index list generation
in large (>18k-draw) frames. For the common 3-vertex triangle and 4-vertex
quad replace repeated append loops with a single std::array append.
The emitted index sequence remains bit-for-bit identical. Other counts,
line primitives, resident display lists and indexed GX_AURORA paths are
not changed. R36S_FAST_GX_INDICES=0 returns exactly to RC8 loops.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()
def exact(a,b,what):
    global s
    count=s.count(a)
    if count!=1: raise SystemExit(f"RC9 {what}: expected exactly 1 anchor, got {count}")
    s=s.replace(a,b,1)

exact(
"""u16 prepare_idx_buffer(ByteBuffer& buf, GXPrimitive prim, u16 vtxStart, u16 vtxCount) noexcept {
  gfx::profile::Scope r36sRc8IndexProfile("index_generate");
  u16 numIndices = 0;
""",
"""// RC9: one-time config read, no additional work per index.
static bool r36s_fast_gx_indices_enabled() noexcept {
  static const bool value = [] {
    const char* s = std::getenv("R36S_FAST_GX_INDICES");
    return s == nullptr || s[0] != '0';
  }();
  return value;
}

u16 prepare_idx_buffer(ByteBuffer& buf, GXPrimitive prim, u16 vtxStart, u16 vtxCount) noexcept {
  gfx::profile::Scope r36sRc8IndexProfile("index_generate");
  // Exact same winding and vertex order as the original loops. The base
  // can be nonzero for merged draws; use the same u16 arithmetic.
  if (r36s_fast_gx_indices_enabled()) {
    if (prim == GX_TRIANGLES && vtxCount == 3) {
      buf.append(std::array{vtxStart, static_cast<u16>(vtxStart + 1),
                           static_cast<u16>(vtxStart + 2)});
      return 3;
    }
    if (prim == GX_QUADS && vtxCount == 4) {
      const u16 i0 = vtxStart;
      const u16 i1 = static_cast<u16>(vtxStart + 1);
      const u16 i2 = static_cast<u16>(vtxStart + 2);
      const u16 i3 = static_cast<u16>(vtxStart + 3);
      buf.append(std::array{i0, i1, i2, i2, i3, i0});
      return 6;
    }
  }
  u16 numIndices = 0;
""", "small primitive index fast path")
# Invariant assertions: preserve original generic index algorithm and batched draws.
for needle in (
    "buf.reserve_extra((vtxCount / 4) * 6 * sizeof(u16));",
    "for (u16 v = 0; v < vtxCount; v += 4)",
    "buf.reserve_extra(vtxCount * sizeof(u16));",
    "for (u16 v = 0; v < vtxCount; ++v)",
    "gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4)",
    "gfx::detail::increment_merged_draw_count();",
):
    if needle not in s: raise SystemExit(f"RC9 invariant missing {needle}")
p.write_text(s)
print("RC9 optional tiny triangle/quad index path installed, same index order, rest untouched")
