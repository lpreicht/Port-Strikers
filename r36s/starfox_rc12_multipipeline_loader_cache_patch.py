#!/usr/bin/env python3
"""RC12: multi-entry, direct-mapped CPU GX VertexLoader reuse.

RC11 cached only the last GX pipeline. Outdoor GX frequently
alternates pipelines and loses the one-entry benefit. Use 256 slots
indexed by bits of the immutable full pipeline hash; verify full
PipelineRef on hit to prevent false matches. The slot pointer comes
only from Aurora's original vertex_loader() cache, whose heap-backed
VertexLoader objects are stable. On collision/miss fall back to
vertex_loader(config), keeping original shader/geometry semantics.

The new fast path is limited to batch_draw (the only call passing
r36sAlreadyPrepared=true). Every other call keeps RC11 behavior.
No additional environment flags or manual user tests.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()
old="""  // RC11: prepare_draw_state() already selected sDrawCache.pipelineRef.
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
"""
new="""  // RC12: The prepared pipeline hash includes the full immutable GX
  // shader/vertex config. Reuse Aurora's heap-stable VertexLoader over
  // alternating pipelines rather than keeping only RC11's last entry.
  // A direct-mapped 256-slot table costs just 4 KiB, does not allocate
  // during draws, and checks the ENTIRE PipelineRef before a hit.
  // Every miss runs the original vertex_loader(config) lookup.
  // Non-batch callers never touch the table.
  const VertexLoader* r36sLoader = nullptr;
  if (r36sAlreadyPrepared) {
    struct R36SLoaderSlot {
      gfx::PipelineRef pipeline{};
      const VertexLoader* loader = nullptr;
    };
    static std::array<R36SLoaderSlot, 256> r36sLoaderSlots{};
    const auto pipeline = sDrawCache.pipelineRef;
    // Mix the bits to distribute different pipeline hashes evenly.
    const size_t slotIndex = static_cast<size_t>(
        (static_cast<uint64_t>(pipeline) ^ (static_cast<uint64_t>(pipeline) >> 32)) & 255u);
    auto& slot = r36sLoaderSlots[slotIndex];
    if (slot.loader == nullptr || slot.pipeline != pipeline) {
      slot.loader = &vertex_loader(config);
      slot.pipeline = pipeline;
    }
    r36sLoader = slot.loader;
  } else {
    r36sLoader = &vertex_loader(config);
  }
"""
if s.count(old)!=1:raise SystemExit(f"RC12 expected exactly one RC11 cache: {s.count(old)}")
s=s.replace(old,new,1)
for required in (
    "gfx::profile::Scope r36sRc8VertProfile(\"vertex_upload_decode\")",
    "record << 8, true);",
    "prepare_draw_state(prim, fmt, immediates);",
    "decode_vertices(loader, vertexData.data(), vtxCount, out, state.arrays",
    "r36sAlreadyPrepared = false",
):
    if required not in s:raise SystemExit("RC12 invariant missing: "+required)
p.write_text(s)
print("RC12 multi-pipeline VertexLoader cache installed; original fallback on misses/non-batched draws")
