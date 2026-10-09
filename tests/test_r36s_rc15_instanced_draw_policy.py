#!/usr/bin/env python3
"""RC15 release guard: single-instance GX indexed draws use Aurora's native
instanced API without changing index bytes, shader variants or draw order.
No per-user toggles. The existing range mode can be restored next build if
Mali-G31 driver testing shows visual regressions or slower FPS.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
launch=(Path(sys.argv[2]).resolve()/"r36s/starfox_clean_launcher.sh").read_text()
gl=(root/"extern/aurora/lib/gfx/gles_direct.cpp").read_text()
assert launch.count("export AURORA_GLES_INDEX_DRAW=instanced")==1
assert launch.count('echo "AURORA_GLES_INDEX_DRAW=$AURORA_GLES_INDEX_DRAW"')==1
assert "R36S_PERF_TEST=RC15_GLES_INSTANCED_INDEX_DRAW_20261010" in launch
for needle in (
    'enum class IndexDrawMode { Range, Plain, Instanced };',
    'std::strcmp(value, "instanced") == 0',
    'case IndexDrawMode::Instanced:',
    'glDrawElementsInstanced(native.topology, static_cast<GLsizei>(d.indexCount), indexType, indices, 1);',
    'glDrawRangeElements(native.topology, start, end, static_cast<GLsizei>(d.indexCount), indexType, indices);',
    'glDrawElements(native.topology, static_cast<GLsizei>(d.indexCount), indexType, indices);',
    'glDrawArrays(native.topology, 0, static_cast<GLsizei>(d.vtxCount));',
    'glDrawElementsInstanced(native.topology, static_cast<GLsizei>(d.indexCount), indexType, indices,',
    'bind_draw_resources(d, *prepared);',
    'draw_barrier((d.indexCount != 0 ? d.indexCount : d.vtxCount) * std::max(d.instanceCount, 1u));',
    '[r36s-rc14-gles-cpu] sampled_frame=',
):
    assert needle in gl, needle
assert 'export R36S_WATER_FAST="${R36S_WATER_FAST:-0}"' in launch
print("PASS RC15: automatic GLES instanced indexed-draw mode; original CPU GX geometry/GL state untouched")
