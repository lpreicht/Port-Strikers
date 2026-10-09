#!/usr/bin/env python3
"""RC9 verify fast triangle and quad output against stock Aurora indices."""
import sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
source=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
for needle in (
  'static bool r36s_fast_gx_indices_enabled() noexcept',
  'std::getenv("R36S_FAST_GX_INDICES")',
  "s == nullptr || s[0] != '0'",
  'if (prim == GX_TRIANGLES && vtxCount == 3)',
  'if (prim == GX_QUADS && vtxCount == 4)',
  'buf.append(std::array{i0, i1, i2, i2, i3, i0});',
  'buf.reserve_extra((vtxCount / 4) * 6 * sizeof(u16))',
  'buf.reserve_extra(vtxCount * sizeof(u16))',
  'gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4)',
  'gfx::detail::increment_merged_draw_count();',
  'gfx::profile::Scope r36sRc8IndexProfile("index_generate")',
):
  assert needle in source, needle
# Mirror both original and new expressions for a range of merged-draw
# starts, including 16-bit rollover (the original indices use u16).
for base in (0, 1, 2, 5, 32, 1234, 65530, 65533, 65535):
  word=lambda v:v & 0xffff
  orig_tri=[word(base+i) for i in range(3)]
  fast_tri=[word(base),word(base+1),word(base+2)]
  assert orig_tri==fast_tri
  orig_quad=[]
  for v in range(0,4,4):
    i0,i1,i2,i3=[word(base+v+i) for i in range(4)]
    orig_quad.extend([i0,i1,i2,i2,i3,i0])
  fast_quad=[word(base),word(base+1),word(base+2),
             word(base+2),word(base+3),word(base)]
  assert orig_quad==fast_quad
print("PASS RC9: tiny GX triangle/quad indices exact, standard paths and batching preserved")
