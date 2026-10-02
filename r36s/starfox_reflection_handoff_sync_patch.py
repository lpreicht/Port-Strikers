#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/gfx/gles_direct.cpp"
s = p.read_text()

old = """struct PassPlan {
  std::string label;
  std::vector<PlanCommand> commands;
  uint32_t width = 0;
  uint32_t height = 0;
  Vec4<float> clearColor{0.f, 0.f, 0.f, 0.f};
  float clearDepth = 1.f;
  uint32_t draws = 0; // GX and clear draws
  bool eligible = false;
};"""
new = """struct PassPlan {
  std::string label;
  std::vector<PlanCommand> commands;
  uint32_t width = 0;
  uint32_t height = 0;
  Vec4<float> clearColor{0.f, 0.f, 0.f, 0.f};
  float clearDepth = 1.f;
  uint32_t draws = 0; // GX and clear draws
  bool eligible = false;
  // The preceding GX_TF_Z8 resolve closes Star Fox's RGB565+Z8 screen-feedback
  // pair.  Dawn encoded that resolve, while this pass may be replayed through
  // direct GLES.  Diagnostic: wait once at exactly that API handoff.
  bool reflectionHandoffSync = false;
};"""
if old not in s:
    raise SystemExit("reflection handoff: PassPlan anchor not found")
s = s.replace(old, new, 1)

old = """  if (label == nullptr || plan.label != label) {
    return false;
  }
  const bool probe = sNextPlan == sProbePlan;
  sBarrierPlan = static_cast<uint32_t>(sNextPlan);
  ++sNextPlan;
  if (!plan.eligible) {
    return false;
  }
"""
new = """  if (label == nullptr || plan.label != label) {
    return false;
  }
  const bool probe = sNextPlan == sProbePlan;
  sBarrierPlan = static_cast<uint32_t>(sNextPlan);
  ++sNextPlan;
  if (plan.reflectionHandoffSync) {
    // R36S diagnostic: the Star Fox reflection pair is produced by Dawn's
    // EFB-copy/conversion path and consumed by the following direct-GLES pass.
    // Finish only at that boundary, not globally and not after every draw.
    glFinish();
    if (stats_enabled() && sFrameNumber % 120 == 0) {
      std::fprintf(stderr, "[r36s-reflection-handoff] frame=%llu pass=%u glFinish after Z8 reflection resolve\\n",
                   static_cast<unsigned long long>(sFrameNumber), passIndex);
    }
  }
  if (!plan.eligible) {
    return false;
  }
"""
if old not in s:
    raise SystemExit("reflection handoff: render_pass anchor not found")
s = s.replace(old, new, 1)

old = """  static unsigned sSortRuns = 0, sSortedDraws = 0, sSortFrames = 0;
  for (auto& pass : frame.renderPasses) {
    if (!pass.sealed || pass.discardable || pass.colorAttachmentCount == 0) {
      continue;
    }
    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1,
    };
"""
new = """  static unsigned sSortRuns = 0, sSortedDraws = 0, sSortFrames = 0;
  bool pendingReflectionHandoffSync = false;
  for (auto& pass : frame.renderPasses) {
    if (!pass.sealed || pass.discardable || pass.colorAttachmentCount == 0) {
      continue;
    }
    const bool reflectionHandoffSync = pendingReflectionHandoffSync;\n    pendingReflectionHandoffSync = false;
    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1,
        .reflectionHandoffSync = reflectionHandoffSync,
    };
"""
if old not in s:
    raise SystemExit("reflection handoff: prepare_frame anchor not found")
s = s.replace(old, new, 1)

old = """    if (stats_enabled() && sFrameNumber % 120 == 0) {
      std::fprintf(stderr,
                   "[gles-direct-plan] frame=%llu pass=%zu eligible=%u gx=%u clear=%u other=%u custom=%u commands=%zu\\n",
                   static_cast<unsigned long long>(sFrameNumber), sPlans.size(), plan.eligible ? 1u : 0u, gxDraws,
                   clearDraws, otherDraws, customDraws, plan.commands.size());
    }
    sPlans.push_back(std::move(plan));
"""
new = """    if (stats_enabled() && sFrameNumber % 120 == 0) {
      std::fprintf(stderr,
                   "[gles-direct-plan] frame=%llu pass=%zu eligible=%u gx=%u clear=%u other=%u custom=%u commands=%zu sync=%u\\n",
                   static_cast<unsigned long long>(sFrameNumber), sPlans.size(), plan.eligible ? 1u : 0u, gxDraws,
                   clearDraws, otherDraws, customDraws, plan.commands.size(), plan.reflectionHandoffSync ? 1u : 0u);
    }
    // Star Fox's updateReflectionTextures() emits RGB565 first and Z8 second.
    // Seeing the Z8 resolve therefore marks the end of the pair; the next game
    // render pass is the one that may sample those just-written textures.
    if (pass.resolveTarget && pass.resolveFormat == GX_TF_Z8) {
      pendingReflectionHandoffSync = true;
    }
    sPlans.push_back(std::move(plan));
"""
if old not in s:
    raise SystemExit("reflection handoff: plan push anchor not found")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched targeted Dawn->direct-GLES reflection handoff glFinish diagnostic")
