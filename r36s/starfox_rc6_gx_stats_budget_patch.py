#!/usr/bin/env python3
"""RC6: reversible optimization of costly per-draw GX diagnostics.

With Aurora renderStats enabled, batch_draw does heavy hash-set insertion
and XXH3 hashing of PipelineConfig for EVERY GX draw, even when 97% of
draws merge. This is reporting only, not GPU rendering or batching.
R36S_GX_HEAVY_STATS=0 (default via launcher): skip that expensive extra work.
R36S_GX_HEAVY_STATS=1: exact RC5 behavior for on-device A/B comparison.
Keep Aurora renderStats=true to retain all RC5 FIFO and frame timing logs.
"""
from pathlib import Path
import sys

p=Path(sys.argv[1]).resolve()/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()

include='#include <cstdio>\n'
if s.count(include)!=1:
    raise SystemExit(f"RC6 include anchor count {s.count(include)}")
s=s.replace(include,'#include <cstdio>\n#include <cstdlib>\n',1)

anchor="""static void batch_draw(GXPrimitive prim, GXVtxFmt fmt, u16 vtxCount, std::span<const u8> vertexData,
                       std::span<const u8> indexData) noexcept {
"""
added="""// RC6: optional per-draw diagnostic hash tables. A/B test is safe because
// no shaders, uniforms, texture bindings, render states or draws are changed.
// All basic batch counters and RC5 frame-timing reports remain enabled.
static bool r36s_gx_heavy_stats_enabled() noexcept {
  static const bool enabled = [] {
    const char* setting = std::getenv("R36S_GX_HEAVY_STATS");
    return setting == nullptr || setting[0] != '0';
  }();
  return enabled;
}

""" + anchor
if s.count(anchor)!=1:
    raise SystemExit(f"RC6 batch_draw anchor count {s.count(anchor)}")
s=s.replace(anchor,added,1)
old="""  auto& stats = sBatchStats;
  ++stats.attempts;
  if (g_config.renderStats) {
    uint64_t key = static_cast<uint64_t>(drawPipeline) * 0x9E3779B97F4A7C15ull;
"""
new="""  auto& stats = sBatchStats;
  ++stats.attempts;
  if (g_config.renderStats && r36s_gx_heavy_stats_enabled()) {
    uint64_t key = static_cast<uint64_t>(drawPipeline) * 0x9E3779B97F4A7C15ull;
"""
if s.count(old)!=1:
    raise SystemExit(f"RC6 heavy diagnostics branch count {s.count(old)}")
s=s.replace(old,new,1)
p.write_text(s)
print("RC6: GX per-draw variance hashing now opt-in; all rendering and timing unaffected")
