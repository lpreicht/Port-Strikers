#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# Keep one small overlay so hardware can verify the live reflection source itself.
p = root / "game/src/main/lightmap.c"
s = p.read_text()
inc_old = '#include "track/intersect.h"\n'
inc_new = '#include "track/intersect.h"\n#include "track/intersect_hud.h"\n'
if inc_old not in s:
    raise SystemExit("reflection targeted finish: lightmap include anchor missing")
s = s.replace(inc_old, inc_new, 1)

old = """    if (bEnableColorFilter == 1) {
        doColorFilter(colorFilterColor);
    }
    shadowVolumesSetDirty(0);
}
"""
new = """    if (bEnableColorFilter == 1) {
        doColorFilter(colorFilterColor);
    }

    /* R36S diagnostic: direct view of the normal live RGB565 reflection. */
    {
        Texture* r36sReflection = getReflectionTexture1();
        if (r36sReflection != NULL) {
            drawTexture(r36sReflection, 0.0f, 0.0f, 0xff, 0x80);
        }
    }

    shadowVolumesSetDirty(0);
}
"""
if old not in s:
    raise SystemExit("reflection targeted finish: lightmap tail anchor missing")
p.write_text(s.replace(old, new, 1))

# Direct-GLES draws the reflection-source EFB pass again, but publish its framebuffer
# writes explicitly before Dawn performs the following GXCopyTex resolve.
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
    raise SystemExit("reflection targeted finish: PassPlan anchor missing")
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
    raise SystemExit("reflection targeted finish: plan init anchor missing")
s = s.replace(old, new, 1)

old = """  const uint32_t drawIndex = replay_plan(plan, passIndex);
  if (draw_barrier_policy().pass) {
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT);
  }
"""
new = """  const uint32_t drawIndex = replay_plan(plan, passIndex);

  /*
   * R36S / Mali-G31: Dawn resolves the EFB immediately after this callback.
   * The Direct-GLES draws are correct on screen, but without an explicit
   * framebuffer publication the following Dawn GXCopyTex can observe stale
   * tile contents.  Publish only the full-size RGB565 reflection-source pass.
   */
  if (plan.r36sReflectionResolve) {
    glFinish();
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-reflection-finish] Direct-GLES EFB completed before Dawn RGB565 resolve %ux%u\\n",
                   plan.width, plan.height);
    }
  }

  if (draw_barrier_policy().pass) {
    glMemoryBarrier(GL_TEXTURE_FETCH_BARRIER_BIT);
  }
"""
if old not in s:
    raise SystemExit("reflection targeted finish: render_pass anchor missing")
s = s.replace(old, new, 1)
p.write_text(s)

print("patched targeted Direct-GLES -> Dawn reflection EFB glFinish handoff")
