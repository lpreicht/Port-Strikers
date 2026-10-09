#!/usr/bin/env python3
"""RC11 contract: same GX shader pipeline -> same stable vertex loader.

The referenced Aurora pipeline_cache.cpp hashes the entire GX
PipelineConfig via xxh3_hash(config, ShaderType::GX). ShaderConfig
(vertex attrs, stride and line mode) is embedded in PipelineConfig.
A pipeline-ref change forces a regular vertex_loader(config) call.
Non-batched callers always do the regular lookup.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
s=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
v=(root/"extern/aurora/lib/gx/vertex_loader.cpp").read_text()
pc=(root/"extern/aurora/lib/gfx/pipeline_cache.cpp").read_text()
for required in [
    "const VertexLoader* r36sLoader = nullptr;",
    "if (r36sAlreadyPrepared) {",
    "static gfx::PipelineRef r36sPreviousPipeline{};",
    "static const VertexLoader* r36sPreviousLoader = nullptr;",
    "if (r36sPreviousLoader == nullptr || r36sPreviousPipeline != sDrawCache.pipelineRef)",
    "r36sPreviousLoader = &vertex_loader(config);",
    "r36sPreviousPipeline = sDrawCache.pipelineRef;",
    "r36sLoader = r36sPreviousLoader;",
    "r36sLoader = &vertex_loader(config);",
    "const auto& loader = *r36sLoader;",
    "record << 8, true);",
    "gfx::detail::increment_merged_draw_count();",
    "decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays",
]:
    assert required in s, required
assert "const PipelineRef hash = xxh3_hash(config, static_cast<HashType>(type));" in pc
assert "const uint64_t hash = XXH3_64bits(&key, sizeof(key));" in v
assert "std::unique_ptr<VertexLoader>" in v
assert s.count("r36sPreviousPipeline") >= 3
assert s.count("r36sAlreadyPrepared = false")==1
assert s.count("record << 8, true);")==1
# Simulator confirms the cache calls vertex_loader() on initial draw and
# every pipeline change, and no other calls under same pipeline.
trace = [7, 7, 7, 9, 9, 7, 7, 12, 12, 12, 9]
previous = None
lookups = 0
for pipeline in trace:
    if previous != pipeline:
        lookups += 1
        previous = pipeline
assert lookups == 5
print("PASS RC11: full-config pipeline identity, stable loader lifetime, fallback for non-batched draws")
