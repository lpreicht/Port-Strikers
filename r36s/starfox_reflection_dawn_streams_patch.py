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
    raise SystemExit("reflection Dawn-buffer diagnostic: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SReflectionPassActive = false;
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: active flag anchor missing")
s = s.replace(old, new, 1)

old = """    const GLuint buffer = sMapped != nullptr ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
new = """    const GLuint buffer =
        (sMapped != nullptr && !sR36SReflectionPassActive) ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: uniform anchor missing")
s = s.replace(old, new, 1)

old = """      vertex = sMapped != nullptr ? sMapped->vertices : GetGLInteropBuffer(res.vertexBuffer.Get());
"""
new = """      vertex = (sMapped != nullptr && !sR36SReflectionPassActive)
                   ? sMapped->vertices
                   : GetGLInteropBuffer(res.vertexBuffer.Get());
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: vertex anchor missing")
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
    raise SystemExit("reflection Dawn-buffer diagnostic: plan init anchor missing")
s = s.replace(old, new, 1)

old = """    if (hasGxDraw && !pass.directResourcesOnly) {
      streamsNeeded = true;
    }
"""
new = """    if (hasGxDraw && (!pass.directResourcesOnly || plan.r36sReflectionResolve)) {
      // Reflection diagnostic: populate Dawn's normal stream buffers even though
      // this pass is still replayed directly through GLES.
      streamsNeeded = true;
    }
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: streamsNeeded anchor missing")
s = s.replace(old, new, 1)

old = """  glBindVertexArray(sVao);
  sPassEbo = sMapped != nullptr ? sMapped->indices : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
new = """  glBindVertexArray(sVao);
  sR36SReflectionPassActive = plan.r36sReflectionResolve;
  sPassEbo = (sMapped != nullptr && !sR36SReflectionPassActive)
                 ? sMapped->indices
                 : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: EBO anchor missing")
s = s.replace(old, new, 1)

old = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
"""
new = """  gl_ok("pass-state", passIndex, 0);
  if (sR36SReflectionPassActive) {
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-reflection-dawn-streams] Direct-GLES reflection pass using Dawn vertex/index/uniform buffers %ux%u\\n",
                   plan.width, plan.height);
    }
  }

  const uint32_t drawIndex = replay_plan(plan, passIndex);
  sR36SReflectionPassActive = false;

  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("reflection Dawn-buffer diagnostic: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source Direct-GLES pass to use Dawn-backed frame streams only")
