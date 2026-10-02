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
  bool r36sShadowStreamSafe = false;
};
"""
if old not in s:
    raise SystemExit("shadow stream-safe: PassPlan anchor missing")
s = s.replace(old, new, 1)

old = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
"""
new = """const MappedSlot* sMapped = nullptr; // this frame's mapped streams, or null
bool sR36SShadowPassActive = false;
"""
if old not in s:
    raise SystemExit("shadow stream-safe: mapped slot anchor missing")
s = s.replace(old, new, 1)

old = """      vertex = sMapped != nullptr ? sMapped->vertices : GetGLInteropBuffer(res.vertexBuffer.Get());
      vertexOffset = d.vertRange.offset;
"""
new = """      vertex = (sMapped != nullptr && !sR36SShadowPassActive)
                   ? sMapped->vertices
                   : GetGLInteropBuffer(res.vertexBuffer.Get());
      vertexOffset = d.vertRange.offset;
"""
if old not in s:
    raise SystemExit("shadow stream-safe: vertex source anchor missing")
s = s.replace(old, new, 1)

old = """  bool streamsNeeded = false; // some consumer reads vertex/index streams through Dawn's buffers
  bool directUniformNeeded = false;
"""
new = """  bool streamsNeeded = false; // some consumer reads vertex/index streams through Dawn's buffers
  bool directUniformNeeded = false;
  std::vector<Range> r36sShadowVertexRanges;
  std::vector<Range> r36sShadowIndexRanges;
"""
if old not in s:
    raise SystemExit("shadow stream-safe: stream flags anchor missing")
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
new = """    const bool r36sShadowStreamSafe =
        pass.resolveTarget &&
        (pass.resolveFormat == GX_CTF_B8 || pass.resolveFormat == GX_CTF_R4 || pass.resolveFormat == GX_TF_Z8) &&
        pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
        pass.resolveRect.width > 0 && pass.resolveRect.height > 0 &&
        pass.resolveRect.width == pass.resolveRect.height &&
        pass.resolveRect.width <= 256;
    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1,
        .r36sShadowStreamSafe = r36sShadowStreamSafe,
    };
"""
if old not in s:
    raise SystemExit("shadow stream-safe: plan init anchor missing")
s = s.replace(old, new, 1)

old = """        if (decode_gx_draw(command.data.draw, out.draw)) {
          hasGxDraw = true;
          ++gxDraws;
"""
new = """        if (decode_gx_draw(command.data.draw, out.draw)) {
          hasGxDraw = true;
          ++gxDraws;
          if (plan.r36sShadowStreamSafe && out.draw.residentArena == 0) {
            if (out.draw.vertRange.size != 0) {
              r36sShadowVertexRanges.push_back(out.draw.vertRange);
            }
            if (out.draw.idxRange.size != 0) {
              r36sShadowIndexRanges.push_back(out.draw.idxRange);
            }
          }
"""
if old not in s:
    raise SystemExit("shadow stream-safe: draw decode anchor missing")
s = s.replace(old, new, 1)

old = """    if (streamsNeeded) {
      upload(res.vertexBuffer, frame.verts);
      upload(res.indexBuffer, frame.indices);
    }
    if (stats_enabled() && directUniformNeeded && sFrameNumber % 120 == 0) {
"""
new = """    if (streamsNeeded) {
      upload(res.vertexBuffer, frame.verts);
      upload(res.indexBuffer, frame.indices);
    } else if (!r36sShadowVertexRanges.empty() || !r36sShadowIndexRanges.empty()) {
      const auto mergeRanges = [](std::vector<Range>& ranges, size_t sourceSize) {
        std::sort(ranges.begin(), ranges.end(),
                  [](const Range& a, const Range& b) { return a.offset < b.offset; });
        std::vector<Range> merged;
        for (const auto& range : ranges) {
          if (range.offset >= sourceSize) {
            continue;
          }
          const uint32_t end = static_cast<uint32_t>(
              std::min<size_t>(sourceSize, static_cast<size_t>(range.offset) + range.size));
          if (!merged.empty() && range.offset <= merged.back().offset + merged.back().size) {
            const uint32_t mergedEnd = std::max(merged.back().offset + merged.back().size, end);
            merged.back().size = mergedEnd - merged.back().offset;
          } else {
            merged.push_back(Range{range.offset, end - range.offset});
          }
        }
        return merged;
      };

      const auto vertexMerged = mergeRanges(r36sShadowVertexRanges, frame.verts.size());
      const auto indexMerged = mergeRanges(r36sShadowIndexRanges, frame.indices.size());
      size_t vertexUploaded = 0;
      size_t indexUploaded = 0;
      for (const auto& range : vertexMerged) {
        if (range.size == 0) {
          continue;
        }
        webgpu::g_queue.WriteBuffer(res.vertexBuffer, range.offset, frame.verts.data() + range.offset,
                                    AURORA_ALIGN(range.size, 4));
        vertexUploaded += AURORA_ALIGN(range.size, 4);
      }
      for (const auto& range : indexMerged) {
        if (range.size == 0) {
          continue;
        }
        webgpu::g_queue.WriteBuffer(res.indexBuffer, range.offset, frame.indices.data() + range.offset,
                                    AURORA_ALIGN(range.size, 4));
        indexUploaded += AURORA_ALIGN(range.size, 4);
      }
      static unsigned shadowReports = 0;
      if (stats_enabled() && (shadowReports++ % 120) == 0) {
        std::fprintf(stderr,
                     "[r36s-shadow-stream-safe] vertex_ranges=%zu vertex_kib=%.1f index_ranges=%zu index_kib=%.1f\\n",
                     vertexMerged.size(), vertexUploaded / 1024.0, indexMerged.size(), indexUploaded / 1024.0);
      }
    }
    if (stats_enabled() && directUniformNeeded && sFrameNumber % 120 == 0) {
"""
if old not in s:
    raise SystemExit("shadow stream-safe: upload block anchor missing")
s = s.replace(old, new, 1)

old = """  glBindVertexArray(sVao);
  sPassEbo = (sMapped != nullptr && !sR36SShadowPassActive)
                 ? sMapped->indices
                 : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
new = """  glBindVertexArray(sVao);
  sR36SShadowPassActive = plan.r36sShadowStreamSafe;
  sPassEbo = sMapped != nullptr ? sMapped->indices : dawn::native::opengl::GetGLInteropBuffer(resources().indexBuffer.Get());
  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, sPassEbo);
"""
if old not in s:
    raise SystemExit("shadow stream-safe: pass active anchor missing")
s = s.replace(old, new, 1)

old = """  gl_ok("pass-state", passIndex, 0);
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
"""
new = """  gl_ok("pass-state", passIndex, 0);
  if (sR36SShadowPassActive) {
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr, "[r36s-shadow-pass] safe Dawn vertex+index source %ux%u\\n", plan.width, plan.height);
    }
  }
  const uint32_t drawIndex = replay_plan(plan, passIndex);
  sR36SShadowPassActive = false;
  if (draw_barrier_policy().pass) {
"""
if old not in s:
    raise SystemExit("shadow stream-safe: replay anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched B8/R4/Z8 square shadow-source passes to use Dawn vertex+index data")
