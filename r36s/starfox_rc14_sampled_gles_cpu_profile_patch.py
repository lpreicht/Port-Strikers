#!/usr/bin/env python3
"""RC14: one-in-sixty-frame CPU OpenGL submission phase timing.

The previous RC13 map-8 scene still needs ~19ms GLES submission and
many GL program/layout/texture changes. Before altering any GL state,
sample ONE entire frame per 60, counting actual CPU time spent in:
  pipeline lookup+GL state, resource binding, and draw call/barrier.
The remaining 59 frames execute exactly the old path (one cheap
modulo predicate per draw). Sampled frames keep all original GL work.
This gives grounded targeting data without dangerous heuristic sorting
or suppression of GL calls.

No graphics state, shader, draw order, EFB effects, index streams,
water, shadows, timing controls or user config flags are changed.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gfx/gles_direct.cpp"
s=p.read_text()
def once(old,new,label):
 global s
 n=s.count(old)
 if n!=1:raise SystemExit(f"RC14 {label}: expected exactly 1 anchor, got {n}")
 s=s.replace(old,new,1)

once("std::unordered_map<PipelineRef, PreparedPipeline> sPrepared;",
"""std::unordered_map<PipelineRef, PreparedPipeline> sPrepared;

// RC14: one frame in 60 only. No GPU timers/queries, glFinish or GL calls.
// The total of these three parts excludes unrelated Dawn submission and
// render-pass setup, so it is NOT the complete frame render time.
struct R36SGlesCpuPhases {
  using Clock = std::chrono::steady_clock;
  uint64_t pipelineNs = 0, resourcesNs = 0, drawNs = 0;
  uint32_t draws = 0, renderPasses = 0;
  void clear() noexcept { *this = {}; }
};
R36SGlesCpuPhases sR36sGlesCpuPhases;
""","CPU phase state")

once('''  profile::Scope drawProfile("gl_draw_total");
  auto* prepared = prepare_pipeline(d.pipeline);''','''  profile::Scope drawProfile("gl_draw_total");
  // One frame / 60, including every GX draw from all passes.
  const bool r36sCpuSample = (sFrameNumber % 60u) == 0u;
  const auto r36sCpuBegin = r36sCpuSample ? R36SGlesCpuPhases::Clock::now()
                                        : R36SGlesCpuPhases::Clock::time_point{};
  auto* prepared = prepare_pipeline(d.pipeline);''',"draw entry")

once('''  if (!gl_ok("pipeline-state", passIndex, drawIndex)) {
    return true;
  }
  {
    profile::Scope resourcesProfile("gl_resources");
    bind_draw_resources(d, *prepared);
  }''','''  if (!gl_ok("pipeline-state", passIndex, drawIndex)) {
    return true;
  }
  const auto r36sCpuAfterPipeline = r36sCpuSample ? R36SGlesCpuPhases::Clock::now()
                                                  : R36SGlesCpuPhases::Clock::time_point{};
  {
    profile::Scope resourcesProfile("gl_resources");
    bind_draw_resources(d, *prepared);
  }
  const auto r36sCpuAfterResources = r36sCpuSample ? R36SGlesCpuPhases::Clock::now()
                                                   : R36SGlesCpuPhases::Clock::time_point{};''',"split pipeline and resources")

once('''  draw_barrier((d.indexCount != 0 ? d.indexCount : d.vtxCount) * std::max(d.instanceCount, 1u));
  return gl_ok("draw", passIndex, drawIndex);''','''  draw_barrier((d.indexCount != 0 ? d.indexCount : d.vtxCount) * std::max(d.instanceCount, 1u));
  const bool r36sDrawOk = gl_ok("draw", passIndex, drawIndex);
  if (r36sCpuSample) {
    const auto r36sCpuDone = R36SGlesCpuPhases::Clock::now();
    const auto ns = [](R36SGlesCpuPhases::Clock::time_point a,
                       R36SGlesCpuPhases::Clock::time_point b) -> uint64_t {
      return static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(b - a).count());
    };
    sR36sGlesCpuPhases.pipelineNs += ns(r36sCpuBegin, r36sCpuAfterPipeline);
    sR36sGlesCpuPhases.resourcesNs += ns(r36sCpuAfterPipeline, r36sCpuAfterResources);
    sR36sGlesCpuPhases.drawNs += ns(r36sCpuAfterResources, r36sCpuDone);
    ++sR36sGlesCpuPhases.draws;
  }
  return r36sDrawOk;''',"draw call measurements")

once('''  profile::Scope passProfile("gl_pass", passIndex);
  PassTimer timer;''','''  profile::Scope passProfile("gl_pass", passIndex);
  if ((sFrameNumber % 60u) == 0u) {
    ++sR36sGlesCpuPhases.renderPasses;
  }
  PassTimer timer;''',"count intercepted GL passes")

once('''  ++sFrameNumber;
  if (stats_enabled()) {
    report_gl_calls();''','''  ++sFrameNumber;
  if ((sFrameNumber % 60u) == 1u && sFrameNumber > 1u) {
    const auto& v = sR36sGlesCpuPhases;
    std::fprintf(stderr,
                 "[r36s-rc14-gles-cpu] sampled_frame=%llu passes=%u draws=%u pipeline_ms=%.3f "
                 "resources_ms=%.3f draw_ms=%.3f three_phases_ms=%.3f (CPU wall time, no GPU finish)\\n",
                 static_cast<unsigned long long>(sFrameNumber - 1u), v.renderPasses, v.draws,
                 v.pipelineNs / 1.0e6, v.resourcesNs / 1.0e6, v.drawNs / 1.0e6,
                 (v.pipelineNs + v.resourcesNs + v.drawNs) / 1.0e6);
    sR36sGlesCpuPhases.clear();
  }
  if (stats_enabled()) {
    report_gl_calls();''',"one-time periodic report")

for item in ("bool render_draw(const gx::DrawData&", "glDrawRangeElements(", "glDrawElements(", "draw_barrier(", "void bind_draw_resources(", "void prepare_frame(FramePacket&", "if (!gl_ok(\"resources\", passIndex, drawIndex))"):
 if item not in s:raise SystemExit("RC14 GL invariant missing: "+item)
p.write_text(s)
print("RC14 sampled CPU GLES pipeline/resources/draw phase measurement installed; all GL calls remain")
