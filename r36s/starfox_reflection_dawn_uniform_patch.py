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
    raise SystemExit("reflection Dawn-uniform diagnostic: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SReflectionPassActive = false;
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: active flag anchor missing")
s = s.replace(old, new, 1)

old = """    const GLuint buffer = sMapped != nullptr ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
new = """    const GLuint buffer =
        (sMapped != nullptr && !sR36SReflectionPassActive) ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: uniform anchor missing")
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
    raise SystemExit("reflection Dawn-uniform diagnostic: plan init anchor missing")
s = s.replace(old, new, 1)

old = """  bool streamsNeeded = false; // some consumer reads the streams through Dawn's buffers
"""
new = """  bool streamsNeeded = false; // some consumer reads the streams through Dawn's buffers
  bool r36sReflectionNeedsDawnUniform = false;
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: stream flag anchor missing")
s = s.replace(old, new, 1)

old = """    if (hasGxDraw && !pass.directResourcesOnly) {
      streamsNeeded = true;
    }
"""
new = """    if (hasGxDraw && !pass.directResourcesOnly) {
      streamsNeeded = true;
    }
    if (hasGxDraw && plan.r36sReflectionResolve) {
      r36sReflectionNeedsDawnUniform = true;
    }
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: pass stream flag anchor missing")
s = s.replace(old, new, 1)

old = """  if (sMapped != nullptr && streamsNeeded) {
    const auto& res = resources();
    const auto upload = [](const wgpu::Buffer& dst, const ByteBuffer& src) {
      if (src.size() != 0) {
        webgpu::g_queue.WriteBuffer(dst, 0, src.data(), AURORA_ALIGN(src.size(), 4));
      }
    };
    upload(res.vertexBuffer, frame.verts);
    upload(res.uniformBuffer, frame.uniforms);
    upload(res.indexBuffer, frame.indices);
  }
"""
new = """  if (sMapped != nullptr && (streamsNeeded || r36sReflectionNeedsDawnUniform)) {
    const auto& res = resources();
    const auto upload = [](const wgpu::Buffer& dst, const ByteBuffer& src) {
      if (src.size() != 0) {
        webgpu::g_queue.WriteBuffer(dst, 0, src.data(), AURORA_ALIGN(src.size(), 4));
      }
    };
    if (streamsNeeded) {
      upload(res.vertexBuffer, frame.verts);
      upload(res.indexBuffer, frame.indices);
    }
    if (streamsNeeded || r36sReflectionNeedsDawnUniform) {
      upload(res.uniformBuffer, frame.uniforms);
    }
  }
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: upload block anchor missing")
s = s.replace(old, new, 1)

old = """  glBindVertexArray(sVao);
  sPassEbo = sMapped != nullptr ? sMapped->indices : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
new = """  glBindVertexArray(sVao);
  sR36SReflectionPassActive = plan.r36sReflectionResolve;
  sPassEbo = sMapped != nullptr ? sMapped->indices : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: pass active anchor missing")
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
                   "[r36s-reflection-dawn-uniform] Direct-GLES reflection pass using Dawn uniform only; mapped vertex+index %ux%u\\n",
                   plan.width, plan.height);
    }
  }
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  sR36SReflectionPassActive = false;
  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("reflection Dawn-uniform diagnostic: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source Direct-GLES pass to use Dawn uniform buffer only")
