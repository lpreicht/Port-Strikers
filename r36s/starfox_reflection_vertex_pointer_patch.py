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
    raise SystemExit("reflection vertex diagnostic: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SReflectionPassActive = false;
"""
if old not in s:
    raise SystemExit("reflection vertex diagnostic: active flag anchor missing")
s = s.replace(old, new, 1)

old = """bool vertex_attrib_pointers() {
  static const bool pointers = [] {
    const char* value = std::getenv("AURORA_GLES_VERTEX_API");
    return value != nullptr && std::strcmp(value, "pointer") == 0;
  }();
  return pointers;
}
"""
new = """bool vertex_attrib_pointers() {
  static const bool pointers = [] {
    const char* value = std::getenv("AURORA_GLES_VERTEX_API");
    return value != nullptr && std::strcmp(value, "pointer") == 0;
  }();
  return pointers || sR36SReflectionPassActive;
}
"""
if old not in s:
    raise SystemExit("reflection vertex diagnostic: vertex API anchor missing")
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
    raise SystemExit("reflection vertex diagnostic: plan init anchor missing")
s = s.replace(old, new, 1)

old = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
"""
new = """  gl_ok("pass-state", passIndex, 0);

  sR36SReflectionPassActive = plan.r36sReflectionResolve;
  if (sR36SReflectionPassActive) {
    // Pointer API and binding API leave different VAO state. Invalidate the
    // cached binding-layout memos when entering the localized pointer path.
    sLastVertexBuffer = Unknown;
    sLastVertexOffset = Unknown;
    sLastVertexStride = Unknown;
    sLastLayout = Unknown;
    sBindingDivisor = Unknown;
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-reflection-vertex-pointer] Dawn-style glVertexAttribPointer active for reflection-source pass %ux%u\\n",
                   plan.width, plan.height);
    }
  }

  const uint32_t drawIndex = replay_plan(plan, passIndex);

  if (sR36SReflectionPassActive) {
    sR36SReflectionPassActive = false;
    // Force the next normal binding-API pass to rebuild its VAO bindings.
    sLastVertexBuffer = Unknown;
    sLastVertexOffset = Unknown;
    sLastVertexStride = Unknown;
    sLastLayout = Unknown;
    sBindingDivisor = Unknown;
    sLastRecordBuffer = Unknown;
  }

  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("reflection vertex diagnostic: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source pass to use Dawn-style vertex pointer API only")
