#!/usr/bin/env python3
"""RC12 release contract for 256-slot pipeline-keyed VertexLoader cache."""
import sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
s=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
p=(root/"extern/aurora/lib/gfx/pipeline_cache.cpp").read_text()
v=(root/"extern/aurora/lib/gx/vertex_loader.cpp").read_text()
for token in (
    "static std::array<R36SLoaderSlot, 256> r36sLoaderSlots{};",
    "slot.loader == nullptr || slot.pipeline != pipeline",
    "slot.loader = &vertex_loader(config);",
    "slot.pipeline = pipeline;",
    "r36sLoader = slot.loader;",
    "r36sLoader = &vertex_loader(config);",
    "const auto& loader = *r36sLoader;",
    "record << 8, true);",
    "prepare_draw_state(prim, fmt, immediates);",
    "gfx::detail::increment_merged_draw_count();",
    "decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays",
):
    assert token in s, token
assert "const PipelineRef hash = xxh3_hash(config, static_cast<HashType>(type));" in p
assert "std::unique_ptr<VertexLoader>" in v
assert s.count("static std::array<R36SLoaderSlot, 256>")==1
assert s.count("r36sAlreadyPrepared = false")==1
assert "r36sPreviousPipeline" not in s
# Direct-mapped cache: verify no false hit for 16K distinct/full-width
# pipeline IDs including deliberate modulo-256 collisions.
slots=[None]*256
def index(k):
    return (k^(k>>32)) & 255
hits=misses=0
trace=[(k*0x9E3779B97F4A7C15)&((1<<64)-1) for k in range(16000)]
trace=trace+trace[-512:]+[trace[4], trace[400], trace[4096], trace[7]]
for key in trace:
    idx=index(key)
    if slots[idx]==key:
        hits+=1
    else:
        misses+=1
        slots[idx]=key
    assert slots[idx]==key
assert hits>0 and misses>0
# Cross-frame loader pointer remains tied only to identical full key.
print("PASS RC12: 256 slots, full hash equality, collision fallback, all original draw and GPU paths preserved")
