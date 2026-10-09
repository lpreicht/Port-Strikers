#!/usr/bin/env python3
"""RC13 compare reference and direct indices, including incomplete quads."""
from pathlib import Path
import sys,struct

root=Path(sys.argv[1]).resolve()
c=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
r=(root/"extern/aurora/lib/gfx/recording.cpp").read_text()
h=(root/"extern/aurora/lib/gfx/recording.hpp").read_text()

for x in [
    "Range map_indices(size_t length, size_t alignment, uint8_t*& data);",
]: assert x in h,x
for x in [
    'if (!check_recording("map_indices"))',
    'const auto range = map(indices, length, alignment);',
    'if (range.size == length && indices.data() != nullptr)',
    "data = indices.data() + range.offset;",
    "return push(current_frame_packet().indices, data, length, alignment);",
]:assert x in r,x
for x in [
    "const bool r36sDirectIndices =",
    "idxRange = gfx::map_indices(static_cast<size_t>(numIndices) * sizeof(u16), merge ? 0 : 4, out);",
    "if (out != nullptr) {",
    "std::memcpy(out + static_cast<size_t>(q) * sizeof(indicesForQuad)",
    "const std::array<u16, 6> indicesForQuad = {a, b, c, c, d, a};",
    "if (!r36sDirectIndices && numIndices != 0)",
    "previous->idxRange.size += idxRange.size;",
    "previous->indexCount += numIndices;",
    "prepare_idx_buffer(indices, prim, base, vtxCount);",
    "gfx::push_indices(indices.data(), indices.size(), merge ? 0 : 4);",
    "gfx::detail::increment_merged_draw_count();",
    "static std::array<R36SLoaderSlot, 256> r36sLoaderSlots{};",
]:assert x in c,x
assert c.count("gfx::Range idxRange;")==2, "expected one in batch and one other function"
assert c.count("const bool r36sDirectIndices =")==1
assert c.count("map_indices(")==1

def pack(v):return struct.pack('<'+'H'*len(v),*v)
wrap=lambda n:n&65535
cases=(1,2,3,4,5,6,7,8,9,11,12,13,16,17,31,32,64,127,128,255,1023,2048,4096,8192)
for base in (0,1,2,4,32,255,1023,16384,32767,65530,65535):
    for count in cases:
        orig_tri=[wrap(base+i) for i in range(count)]
        opt_tri=[wrap(base+i) for i in range(count)]
        assert pack(orig_tri)==pack(opt_tri)
        orig_quad=[]
        for start in range(0,count,4):
            a=wrap(base+start)
            ids=(a,wrap(a+1),wrap(a+2),wrap(a+2),wrap(a+3),a)
            orig_quad.extend(ids)
        opt_quad=[]
        for q in range((count+3)//4):
            a=wrap(base+q*4)
            opt_quad.extend((a,wrap(a+1),wrap(a+2),wrap(a+2),wrap(a+3),a))
        assert pack(orig_quad)==pack(opt_quad)
        assert len(orig_quad) == ((count+3)//4)*6
        assert len(orig_quad)<65536
assert 8192*6//4 < 65536
print("PASS RC13: direct index bytes exactly match reference, including incomplete quads, u16 wrap and merging")
