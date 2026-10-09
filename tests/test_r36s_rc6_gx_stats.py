#!/usr/bin/env python3
"""RC6 source-only safety checks, actual FPS must be tested on R36S."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
gx=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
aurora=(root/"extern/aurora/lib/aurora.cpp").read_text()
assert gx.count("static bool r36s_gx_heavy_stats_enabled() noexcept") == 1
assert 'std::getenv("R36S_GX_HEAVY_STATS")' in gx
assert "return setting == nullptr || setting[0] != '0';" in gx
assert "if (g_config.renderStats && r36s_gx_heavy_stats_enabled())" in gx
# Hash diagnostics opt-out only. Retain actual command, vertex decode and draw batching.
for s in ["prepare_draw_state(prim, fmt, immediates);",
          "push_decoded_verts(prim, fmt, vertexData, vtxCount",
          "gfx::push_draw_command(DrawData{",
          "previous->vertRange.size += vertRange.size;",
          "gfx::detail::increment_merged_draw_count();",
          "prepare_idx_buffer(indices, prim, base, vtxCount);",
          "const uint64_t cfgHash = aurora::xxh3_hash(cache.config);"]:
    assert s in gx, s
assert "[gx-batch]" in gx and "[gx-variance]" in gx
assert "[r36s-rc5-gx]" in aurora
assert "[r36s-rc4-endframe]" in aurora
print("PASS RC6: only per-draw diagnostic hashing gated, drawing/batching/timing intact")
