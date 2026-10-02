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
};
"""
new = """struct PassPlan {
  std::string label;
  std::vector<PlanCommand> commands;
  uint32_t width = 0;
  uint32_t height = 0;
  Vec4<float> clearColor{0.f, 0.f, 0.f, 0.f};
  float clearDepth = 1.f;
  uint32_t draws = 0; // GX and clear draws
  bool eligible = false;
  bool r36sReflectionResolve = false;
};
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SReflectionPassActive = false;
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: active flag anchor missing")
s = s.replace(old, new, 1)

old = """IndexDrawMode index_draw_mode() {
  static const IndexDrawMode mode = [] {
    const char* value = std::getenv("AURORA_GLES_INDEX_DRAW");
    if (value != nullptr && std::strcmp(value, "plain") == 0) {
      return IndexDrawMode::Plain;
    }
    if (value != nullptr && std::strcmp(value, "instanced") == 0) {
      return IndexDrawMode::Instanced;
    }
    return IndexDrawMode::Range;
  }();
  return mode;
}
"""
new = """IndexDrawMode index_draw_mode() {
  static const IndexDrawMode mode = [] {
    const char* value = std::getenv("AURORA_GLES_INDEX_DRAW");
    if (value != nullptr && std::strcmp(value, "plain") == 0) {
      return IndexDrawMode::Plain;
    }
    if (value != nullptr && std::strcmp(value, "instanced") == 0) {
      return IndexDrawMode::Instanced;
    }
    return IndexDrawMode::Range;
  }();
  return sR36SReflectionPassActive ? IndexDrawMode::Plain : mode;
}
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: index mode anchor missing")
s = s.replace(old, new, 1)

old = """  const auto& native = prepared->gl;
"""
new = """  const auto& native = prepared->gl;
  if (sR36SReflectionPassActive) {
    const auto blendMode = static_cast<unsigned>(prepared->config.blendMode);
    const auto blendOp = static_cast<unsigned>(prepared->config.blendOp);
    if (blendMode == static_cast<unsigned>(GX_BM_LOGIC)) {
      static bool seenLogicOps[32] = {};
      if (blendOp < 32 && !seenLogicOps[blendOp]) {
        seenLogicOps[blendOp] = true;
        std::fprintf(stderr,
                     "[r36s-reflection-logic] observed GX_BM_LOGIC op=%u depthFunc=%u depthUpdate=%u colorUpdate=%u alphaUpdate=%u dstAlpha=%u\\n",
                     blendOp, static_cast<unsigned>(prepared->config.depthFunc),
                     prepared->config.depthUpdate ? 1u : 0u,
                     prepared->config.colorUpdate ? 1u : 0u,
                     prepared->config.alphaUpdate ? 1u : 0u,
                     prepared->config.dstAlpha);
      }
    }
  }
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: render_draw pipeline anchor missing")
s = s.replace(old, new, 1)

old = """    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1,
    };
"""
new = """    const bool r36sReflectionResolve =
        pass.resolveTarget && pass.resolveFormat == GX_TF_RGB565 &&
        pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
        pass.resolveRect.width == static_cast<int32_t>(pass.colorAttachments[0].size.width) &&
        pass.resolveRect.height == static_cast<int32_t>(pass.colorAttachments[0].size.height) &&
        pass.resolveRect.width > 128 && pass.resolveRect.height > 128;
    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1,
        .r36sReflectionResolve = r36sReflectionResolve,
    };
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: plan init anchor missing")
s = s.replace(old, new, 1)

old = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
"""
new = """  gl_ok("pass-state", passIndex, 0);

  sR36SReflectionPassActive = plan.r36sReflectionResolve;
  if (sR36SReflectionPassActive) {
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-reflection-index-plain] glDrawElements active for reflection-source pass %ux%u\\n",
                   plan.width, plan.height);
    }
  }

  const uint32_t drawIndex = replay_plan(plan, passIndex);
  sR36SReflectionPassActive = false;

  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("reflection index diagnostic: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source pass to use plain glDrawElements only")
