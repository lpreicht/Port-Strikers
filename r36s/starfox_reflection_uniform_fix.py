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
    raise SystemExit("reflection uniform-window fix: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SReflectionPassActive = false;
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: active flag anchor missing")
s = s.replace(old, new, 1)

old = """    const GLuint buffer = sMapped != nullptr ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
new = """    const GLuint buffer =
        (sMapped != nullptr && !sR36SReflectionPassActive) ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: uniform bind anchor missing")
s = s.replace(old, new, 1)

old = """  bool streamsNeeded = false; // some consumer reads the streams through Dawn's buffers
"""
new = """  bool streamsNeeded = false; // some consumer reads the streams through Dawn's buffers
  std::vector<uint32_t> r36sReflectionUniformWindows;
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: streamsNeeded anchor missing")
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
    raise SystemExit("reflection uniform-window fix: plan init anchor missing")
s = s.replace(old, new, 1)

old = """        if (decode_gx_draw(command.data.draw, out.draw)) {
          hasGxDraw = true;
          ++gxDraws;
"""
new = """        if (decode_gx_draw(command.data.draw, out.draw)) {
          hasGxDraw = true;
          ++gxDraws;
          if (plan.r36sReflectionResolve) {
            r36sReflectionUniformWindows.push_back(gx::uniform_window_index(out.draw.uniformRange.offset));
          }
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: draw decode anchor missing")
s = s.replace(old, new, 1)

old = """  // Frames recorded into mapped GL storage reach Dawn's buffers only when something reads them through Dawn.
  if (sMapped != nullptr && streamsNeeded) {
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
new = """  // Frames recorded into mapped GL storage reach Dawn's buffers only when something reads them through Dawn.
  // R36S/Mali-G31: the large planar-reflection source pass observes stale/corrupt data from the persistently
  // mapped uniform stream. Keep mapped vertex/index streams, but mirror only the 16 KiB uniform windows used
  // by that pass into Dawn's normal uniform buffer. Batched draws can reference several 4 KiB records inside
  // one window, so copying complete used windows is the smallest safe granularity.
  if (sMapped != nullptr && (streamsNeeded || !r36sReflectionUniformWindows.empty())) {
    const auto& res = resources();
    const auto upload = [](const wgpu::Buffer& dst, const ByteBuffer& src) {
      if (src.size() != 0) {
        webgpu::g_queue.WriteBuffer(dst, 0, src.data(), AURORA_ALIGN(src.size(), 4));
      }
    };
    if (streamsNeeded) {
      upload(res.vertexBuffer, frame.verts);
      upload(res.uniformBuffer, frame.uniforms);
      upload(res.indexBuffer, frame.indices);
    } else {
      std::sort(r36sReflectionUniformWindows.begin(), r36sReflectionUniformWindows.end());
      r36sReflectionUniformWindows.erase(
          std::unique(r36sReflectionUniformWindows.begin(), r36sReflectionUniformWindows.end()),
          r36sReflectionUniformWindows.end());

      size_t uploaded = 0;
      for (const uint32_t window : r36sReflectionUniformWindows) {
        const size_t offset = static_cast<size_t>(window) * gx::UniformWindowSize;
        if (offset >= frame.uniforms.size()) {
          continue;
        }
        const size_t bytes = std::min<size_t>(gx::UniformWindowSize, frame.uniforms.size() - offset);
        webgpu::g_queue.WriteBuffer(res.uniformBuffer, offset, frame.uniforms.data() + offset, AURORA_ALIGN(bytes, 4));
        uploaded += AURORA_ALIGN(bytes, 4);
      }
      static unsigned reports = 0;
      if (stats_enabled() && (reports++ % 120) == 0) {
        std::fprintf(stderr,
                     "[r36s-reflection-uniform-fix] windows=%zu uploaded_kib=%.1f frame_uniform_kib=%.1f\\n",
                     r36sReflectionUniformWindows.size(), uploaded / 1024.0, frame.uniforms.size() / 1024.0);
      }
    }
  }
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: upload block anchor missing")
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
    raise SystemExit("reflection uniform-window fix: pass active anchor missing")
s = s.replace(old, new, 1)

old = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
"""
new = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  sR36SReflectionPassActive = false;
  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("reflection uniform-window fix: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source Direct-GLES pass with targeted Dawn uniform-window mirror")
