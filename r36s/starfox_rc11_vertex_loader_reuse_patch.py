#!/usr/bin/env python3
"""RC11: cache Aurora's vertex decoder against the already-resolved draw pipeline.

Aurora previously hashes the whole vertex attribute configuration in
vertex_loader() for every single batch draw, even when the shader
pipeline from prepare_draw_state() is unchanged. The pipeline ref
identifies the full (immutable) shader config; it is cached centrally
in Aurora's pipeline table. Reusing the stable heap-allocated
VertexLoader pointer for the same pipeline avoids redundant per-draw
XXH3 hash/table lookup, retaining identical CPU vertex conversion.

Only batch_draw passes r36sAlreadyPrepared=true (from RC10), so all
resident/display-list/unbatched calls retain the original lookup.
No shader/vertex bytes/render state/GPU synchronization changes.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()
old="""  const auto& state = g_gxState;
  const auto& config = sDrawCache.config.shaderConfig;
  const auto& loader = vertex_loader(config);
  AURORA_ASSERT(loader.vtxStride != 0 && vertexData.size() == static_cast<size_t>(vtxCount) * loader.vtxStride,
"""
new="""  const auto& state = g_gxState;
  const auto& config = sDrawCache.config.shaderConfig;
  // RC11: prepare_draw_state() already selected sDrawCache.pipelineRef.
  // The pipeline's full shader/vertex config does not change until
  // prepare_pipeline() selects another ref. Heap-allocated loader objects
  // returned by vertex_loader() keep stable addresses across map rehashes.
  // Other call sites still use the original validation/hash lookup.
  const VertexLoader* r36sLoader = nullptr;
  if (r36sAlreadyPrepared) {
    static gfx::PipelineRef r36sPreviousPipeline{};
    static const VertexLoader* r36sPreviousLoader = nullptr;
    if (r36sPreviousLoader == nullptr || r36sPreviousPipeline != sDrawCache.pipelineRef) {
      r36sPreviousLoader = &vertex_loader(config);
      r36sPreviousPipeline = sDrawCache.pipelineRef;
    }
    r36sLoader = r36sPreviousLoader;
  } else {
    r36sLoader = &vertex_loader(config);
  }
  const auto& loader = *r36sLoader;
  AURORA_ASSERT(loader.vtxStride != 0 && vertexData.size() == static_cast<size_t>(vtxCount) * loader.vtxStride,
"""
n=s.count(old)
if n!=1:raise SystemExit(f"RC11 anchor expected once, got {n}")
s=s.replace(old,new,1)
for needle in (
    "prepare_draw_state(prim, fmt, immediates);",
    "record << 8, true);",
    "r36sAlreadyPrepared = false",
    "gfx::push_draw_command(DrawData{",
    "decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays",
    "gfx::detail::increment_merged_draw_count();",
):
    if needle not in s: raise SystemExit(f"RC11 invariant missing: {needle}")
p.write_text(s)
print("RC11: pipeline-ref keyed, stable vertex loader reuse for batch draws only")
