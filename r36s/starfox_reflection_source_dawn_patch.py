#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

# 1) Keep a simple direct overlay of the normal live RGB565 reflection.
p = root / "game/src/main/lightmap.c"
s = p.read_text()
inc_old = '#include "track/intersect.h"\n'
inc_new = '#include "track/intersect.h"\n#include "track/intersect_hud.h"\n'
if inc_old not in s:
    raise SystemExit("Dawn reflection-source test: lightmap include anchor missing")
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
    raise SystemExit("Dawn reflection-source test: lightmap tail anchor missing")
p.write_text(s.replace(old, new, 1))

# 2) The EFB pass which feeds the large full-screen RGB565 reflection copy must
# be fully encoded by Dawn and must not be intercepted by Direct-GLES.
p = root / "extern/aurora/lib/gfx/gles_direct.cpp"
s = p.read_text()

old = """bool encode_pass_resources(const wgpu::RenderPassEncoder& encoder, RenderPass& pass, std::string_view label) {
  pass.directLabel = label;
  if (!sEnabled || pass.msaaSamples != 1 || pass.colorAttachmentCount != 1) {
    return false;
  }
"""
new = """bool encode_pass_resources(const wgpu::RenderPassEncoder& encoder, RenderPass& pass, std::string_view label) {
  pass.directLabel = label;
  const bool r36sReflectionSourcePass =
      pass.resolveTarget && pass.resolveFormat == GX_TF_RGB565 &&
      pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
      pass.resolveRect.width == static_cast<int32_t>(pass.colorAttachments[0].size.width) &&
      pass.resolveRect.height == static_cast<int32_t>(pass.colorAttachments[0].size.height) &&
      pass.resolveRect.width > 128 && pass.resolveRect.height > 128;
  if (r36sReflectionSourcePass) {
    static unsigned reports = 0;
    if ((reports++ % 120) == 0) {
      std::fprintf(stderr,
                   "[r36s-reflection-source] full RGB565 EFB source pass forced through Dawn %dx%d\\n",
                   pass.resolveRect.width, pass.resolveRect.height);
    }
    return false;
  }
  if (!sEnabled || pass.msaaSamples != 1 || pass.colorAttachmentCount != 1) {
    return false;
  }
"""
if old not in s:
    raise SystemExit("Dawn reflection-source test: encode_pass_resources anchor missing")
s = s.replace(old, new, 1)

old = """    plan.eligible &= hasGxDraw;
    plan.draws = gxDraws + clearDraws;
"""
new = """    plan.eligible &= hasGxDraw;
    const bool r36sReflectionSourcePass =
        pass.resolveTarget && pass.resolveFormat == GX_TF_RGB565 &&
        pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
        pass.resolveRect.width == static_cast<int32_t>(pass.colorAttachments[0].size.width) &&
        pass.resolveRect.height == static_cast<int32_t>(pass.colorAttachments[0].size.height) &&
        pass.resolveRect.width > 128 && pass.resolveRect.height > 128;
    if (r36sReflectionSourcePass) {
      plan.eligible = false;
    }
    plan.draws = gxDraws + clearDraws;
"""
if old not in s:
    raise SystemExit("Dawn reflection-source test: prepare_frame eligibility anchor missing")
s = s.replace(old, new, 1)
p.write_text(s)

print("patched large RGB565 reflection source EFB pass to Dawn-only rendering")
