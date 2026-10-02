#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# Keep the reflection-source pass on Direct-GLES. Preserve the tested dynamic-state
# restoration and additionally use a real glClear() for GX clears in only the large
# RGB565 reflection-source pass. This isolates the Direct-GLES fullscreen-triangle
# clear implementation without changing unrelated passes.
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
    raise SystemExit("reflection glclear diagnostic: PassPlan anchor missing")
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
    raise SystemExit("reflection glclear diagnostic: plan init anchor missing")
s = s.replace(old, new, 1)


# render_clear() deliberately changes GL dynamic state to draw the GX clear, but
# the direct replay path did not restore the viewport/depth-range/scissor that
# were active before that clear. Dawn's normal command replay does preserve the
# surrounding dynamic state. Repair this only for the localized reflection pass
# first, so hardware can prove whether this is the Direct-GLES semantic mismatch.
old = """uint32_t replay_plan(const PassPlan& plan, uint32_t passIndex) {
  uint32_t drawIndex = 0;
  for (const auto& command : plan.commands) {
"""
new = """uint32_t replay_plan(const PassPlan& plan, uint32_t passIndex) {
  uint32_t drawIndex = 0;
  GLint r36sViewportX = 0, r36sViewportY = 0;
  GLsizei r36sViewportW = static_cast<GLsizei>(plan.width);
  GLsizei r36sViewportH = static_cast<GLsizei>(plan.height);
  GLfloat r36sDepthNear = 0.f, r36sDepthFar = 1.f;
  GLint r36sScissorX = 0, r36sScissorY = 0;
  GLsizei r36sScissorW = static_cast<GLsizei>(plan.width);
  GLsizei r36sScissorH = static_cast<GLsizei>(plan.height);
  for (const auto& command : plan.commands) {
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: replay_plan start anchor missing")
s = s.replace(old, new, 1)

old = """      glDepthRangef(nearDepth, farDepth);
    } break;
"""
new = """      glDepthRangef(nearDepth, farDepth);
      if (plan.r36sReflectionResolve) {
        r36sViewportX = static_cast<GLint>(v.left);
        r36sViewportY = static_cast<GLint>(v.top);
        r36sViewportW = static_cast<GLsizei>(v.width);
        r36sViewportH = static_cast<GLsizei>(v.height);
        r36sDepthNear = nearDepth;
        r36sDepthFar = farDepth;
      }
    } break;
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: viewport anchor missing")
s = s.replace(old, new, 1)

old = """    case CommandType::SetScissor: {
      if (!apply_gx_scissor()) {
        glScissor(0, 0, static_cast<GLsizei>(plan.width), static_cast<GLsizei>(plan.height));
        break;
      }
      const auto& s = command.scissor;
      const auto x = std::min(static_cast<uint32_t>(std::max(s.x, 0)), plan.width);
      const auto y = std::min(static_cast<uint32_t>(std::max(s.y, 0)), plan.height);
      glScissor(static_cast<GLint>(x), static_cast<GLint>(y),
                static_cast<GLsizei>(std::min(static_cast<uint32_t>(std::max(s.width, 0)), plan.width - x)),
                static_cast<GLsizei>(std::min(static_cast<uint32_t>(std::max(s.height, 0)), plan.height - y)));
    } break;
"""
new = """    case CommandType::SetScissor: {
      GLint x = 0, y = 0;
      GLsizei w = static_cast<GLsizei>(plan.width);
      GLsizei h = static_cast<GLsizei>(plan.height);
      if (apply_gx_scissor()) {
        const auto& sc = command.scissor;
        const auto cx = std::min(static_cast<uint32_t>(std::max(sc.x, 0)), plan.width);
        const auto cy = std::min(static_cast<uint32_t>(std::max(sc.y, 0)), plan.height);
        x = static_cast<GLint>(cx);
        y = static_cast<GLint>(cy);
        w = static_cast<GLsizei>(std::min(static_cast<uint32_t>(std::max(sc.width, 0)), plan.width - cx));
        h = static_cast<GLsizei>(std::min(static_cast<uint32_t>(std::max(sc.height, 0)), plan.height - cy));
      }
      glScissor(x, y, w, h);
      if (plan.r36sReflectionResolve) {
        r36sScissorX = x;
        r36sScissorY = y;
        r36sScissorW = w;
        r36sScissorH = h;
      }
    } break;
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: scissor anchor missing")
s = s.replace(old, new, 1)

old = """      if (command.isClear) {
        render_clear(command.clear, plan.width, plan.height, passIndex, drawIndex);
      } else {
        render_draw(command.draw, passIndex, drawIndex);
      }
"""
new = """      if (command.isClear) {
        render_clear(command.clear, plan.width, plan.height, passIndex, drawIndex);
        if (plan.r36sReflectionResolve) {
          glViewport(r36sViewportX, r36sViewportY, r36sViewportW, r36sViewportH);
          glDepthRangef(r36sDepthNear, r36sDepthFar);
          glScissor(r36sScissorX, r36sScissorY, r36sScissorW, r36sScissorH);
          static unsigned reports = 0;
          if ((reports++ % 120) == 0) {
            std::fprintf(stderr,
                         "[r36s-reflection-clear-restore] restored viewport/depth/scissor after GX clear %ux%u\\n",
                         plan.width, plan.height);
          }
        }
      } else {
        render_draw(command.draw, passIndex, drawIndex);
      }
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: clear replay anchor missing")
s = s.replace(old, new, 1)


# Use a real GL clear only for the localized reflection-source pass. Aurora already
# has a global AURORA_GLES_CLEAR=gl diagnostic; this makes the test pass-local.
old = "bool render_clear(const clear::DrawData& d, uint32_t width, uint32_t height, uint32_t passIndex, uint32_t drawIndex) {"
new = "bool render_clear(const clear::DrawData& d, uint32_t width, uint32_t height, uint32_t passIndex, uint32_t drawIndex,\n                  bool forceGlClear) {"
if old not in s:
    raise SystemExit("reflection glclear diagnostic: render_clear signature anchor missing")
s = s.replace(old, new, 1)

old = """  if (clear_with_gl_clear()) {
    glClearColor(static_cast<float>(d.color.r), static_cast<float>(d.color.g), static_cast<float>(d.color.b),
                 static_cast<float>(d.color.a));
    glClearDepthf(d.depth);
    glClear((config.clearColor || config.clearAlpha ? GL_COLOR_BUFFER_BIT : 0) |
            (config.clearDepth ? GL_DEPTH_BUFFER_BIT : 0));
  } else {
    glDrawArrays(GL_TRIANGLES, 0, 3);
  }
"""
new = """  if (forceGlClear || clear_with_gl_clear()) {
    glClearColor(static_cast<float>(d.color.r), static_cast<float>(d.color.g), static_cast<float>(d.color.b),
                 static_cast<float>(d.color.a));
    glClearDepthf(d.depth);
    glClear((config.clearColor || config.clearAlpha ? GL_COLOR_BUFFER_BIT : 0) |
            (config.clearDepth ? GL_DEPTH_BUFFER_BIT : 0));
    if (forceGlClear) {
      static unsigned reports = 0;
      if ((reports++ % 120) == 0) {
        std::fprintf(stderr,
                     "[r36s-reflection-glclear] real glClear used for reflection-source GX clear %ux%u\\n",
                     width, height);
      }
    }
  } else {
    glDrawArrays(GL_TRIANGLES, 0, 3);
  }
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: clear implementation anchor missing")
s = s.replace(old, new, 1)

old = """        render_clear(command.clear, plan.width, plan.height, passIndex, drawIndex);
"""
new = """        render_clear(command.clear, plan.width, plan.height, passIndex, drawIndex,
                     plan.r36sReflectionResolve);
"""
if old not in s:
    raise SystemExit("reflection glclear diagnostic: render_clear call anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("patched reflection-source real glClear diagnostic; live overlay removed")
