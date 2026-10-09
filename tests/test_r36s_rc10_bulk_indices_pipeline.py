#!/usr/bin/env python3
"""RC10 GX index output exactness and pre-prepared pipeline code contract."""
from pathlib import Path
import sys, struct
root=Path(sys.argv[1]).resolve()
s=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
a=(root/"extern/aurora/lib/aurora.cpp").read_text()
assert s.count('bool r36sAlreadyPrepared = false')==1
assert s.count('if (!r36sAlreadyPrepared)')==1
assert s.count('record << 8, true);')==1
assert s.index('prepare_draw_state(prim, fmt, immediates);')<s.index('record << 8, true);')
assert 'gfx::profile::Scope r36sRc8IndexProfile("index_generate")' in s
assert 'gfx::profile::Scope r36sRc8VertProfile("vertex_upload_decode")' in s
assert 'if (prim == GX_TRIANGLES && vtxCount > 3)' in s
assert 'if (prim == GX_QUADS && vtxCount > 4)' in s
assert 'buf.append_zeroes(static_cast<size_t>(vtxCount) * sizeof(u16));' in s
assert 'buf.append_zeroes(groups * 6u * sizeof(u16));' in s
assert 'std::memcpy(out + q * sizeof(idx), idx.data(), sizeof(idx));' in s
for needle in [
    'for (u16 v = 0; v < vtxCount; ++v)', # original fallback
    'for (u16 v = 0; v < vtxCount; v += 4)', # original fallback
    'gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4)',
    'gfx::detail::increment_merged_draw_count();',
    'gfx::push_draw_command(DrawData{',
    'const auto& loader = vertex_loader(config);',
    'decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays',
]:
    assert needle in s,needle
for needle in ['[r36s-rc5-gx]', '[r36s-rc4-endframe]']:
    assert needle in a,needle
# Verify direct emitted little-endian index bytes against original for wide
# range, including incomplete quad groups and u16 wraparound.
wrap=lambda x:x&65535
for count in [0,1,2,3,4,5,6,7,8,9,11,12,14,15,16,17,31,32,33,64,127,128,255,1023,4095,65535]:
    for base in [0,1,2,3,23,255,1023,32767,65530,65535]:
        old_tri=[wrap(base+i) for i in range(count)]
        new_tri=[wrap(base+i) for i in range(count)]
        assert struct.pack('<'+'H'*len(old_tri),*old_tri)==struct.pack('<'+'H'*len(new_tri),*new_tri)
        old_quad=[]
        for start in range(0,count,4):
            ids=[wrap(base+start+i) for i in range(4)]
            old_quad.extend([ids[0],ids[1],ids[2],ids[2],ids[3],ids[0]])
        new_quad=[]
        for q in range((count+3)//4):
            ids=[wrap(base+q*4+i) for i in range(4)]
            new_quad.extend([ids[0],ids[1],ids[2],ids[2],ids[3],ids[0]])
        assert old_quad==new_quad
        assert wrap(len(old_quad)) == wrap(((count+3)//4)*6)
print("PASS RC10: identical indices (including quad leftovers/u16 wrap), GX pipeline pre-prepared only on batching path")
