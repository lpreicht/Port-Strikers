#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/gfx/gles_direct.cpp"
s = p.read_text()

old = """    const GLuint buffer = sMapped != nullptr ? sMapped->uniforms : GetGLInteropBuffer(res.uniformBuffer.Get());
"""
new = """    // R36S Mali-G31 r13p0: persistently mapped uniform storage can become stale/corrupt under
    // heavy GX workloads even though the mapped range is explicitly flushed. Always bind Dawn's
    // normal uniform buffer for Direct-GLES; mapped vertex/index streams remain enabled.
    const GLuint buffer = GetGLInteropBuffer(res.uniformBuffer.Get());
"""
if old not in s:
    raise SystemExit("uniform-safe stream fix: uniform binding anchor missing")
s = s.replace(old, new, 1)

old = """  sMapped = mapped_slot(frame);
  bool streamsNeeded = false; // some consumer reads the streams through Dawn's buffers
"""
new = """  sMapped = mapped_slot(frame);
  bool streamsNeeded = false; // some consumer reads vertex/index streams through Dawn's buffers
  bool directUniformNeeded = false;
"""
if old not in s:
    raise SystemExit("uniform-safe stream fix: stream flags anchor missing")
s = s.replace(old, new, 1)

old = """    plan.eligible &= hasGxDraw;
    plan.draws = gxDraws + clearDraws;
"""
new = """    plan.eligible &= hasGxDraw;
    plan.draws = gxDraws + clearDraws;
    if (hasGxDraw && plan.eligible) {
      directUniformNeeded = true;
    }
"""
if old not in s:
    raise SystemExit("uniform-safe stream fix: eligibility anchor missing")
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
new = """  // R36S uniform-safe mapped streams:
  // - Direct-GLES always consumes uniforms from Dawn's normal buffer.
  // - Vertex and index data stay in persistently mapped GL storage unless a true Dawn consumer needs them.
  // This avoids the Mali-G31 r13p0 mapped-uniform corruption that manifested as reflection flicker and
  // intermittent fully black Fox/Dino/backpack materials.
  if (sMapped != nullptr && (streamsNeeded || directUniformNeeded)) {
    const auto& res = resources();
    const auto upload = [](const wgpu::Buffer& dst, const ByteBuffer& src) {
      if (src.size() != 0) {
        webgpu::g_queue.WriteBuffer(dst, 0, src.data(), AURORA_ALIGN(src.size(), 4));
      }
    };
    if (directUniformNeeded || streamsNeeded) {
      upload(res.uniformBuffer, frame.uniforms);
    }
    if (streamsNeeded) {
      upload(res.vertexBuffer, frame.verts);
      upload(res.indexBuffer, frame.indices);
    }
    if (stats_enabled() && directUniformNeeded && sFrameNumber % 120 == 0) {
      std::fprintf(stderr,
                   "[r36s-uniform-safe] Dawn uniform_kib=%.1f; mapped vertex+index retained; full geometry upload=%u\\n",
                   frame.uniforms.size() / 1024.0, streamsNeeded ? 1u : 0u);
    }
  }
"""
if old not in s:
    raise SystemExit("uniform-safe stream fix: upload block anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched Direct-GLES to use Dawn uniforms globally while retaining mapped vertex/index")
