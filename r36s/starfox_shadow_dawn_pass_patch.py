#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/gfx/gles_direct.cpp"
s = p.read_text()
# Preserve current Dawn fallback by default; opt out for a controlled device A/B test.
if '#include <cstdlib>' not in s:
    s = '#include <cstdlib>\n' + s

old = """bool encode_pass_resources(const wgpu::RenderPassEncoder& encoder, RenderPass& pass, std::string_view label) {
  pass.directLabel = label;
  if (!sEnabled || pass.msaaSamples != 1 || pass.colorAttachmentCount != 1) {
    return false;
  }
"""
new = """bool encode_pass_resources(const wgpu::RenderPassEncoder& encoder, RenderPass& pass, std::string_view label) {
  pass.directLabel = label;
  if (!sEnabled || pass.msaaSamples != 1 || pass.colorAttachmentCount != 1) {
    return false;
  }
  const bool r36sShadowDawnPass =
      (std::getenv("R36S_SHADOW_FORCE_DAWN") == nullptr ||
       std::getenv("R36S_SHADOW_FORCE_DAWN")[0] != '0') &&
      pass.resolveTarget &&
      (pass.resolveFormat == GX_CTF_B8 || pass.resolveFormat == GX_CTF_R4 || pass.resolveFormat == GX_TF_Z8) &&
      pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
      pass.resolveRect.width > 0 && pass.resolveRect.height > 0 &&
      pass.resolveRect.width == pass.resolveRect.height &&
      pass.resolveRect.width <= 512;
  if (r36sShadowDawnPass) {
    // Do not record only the minimal Direct-GLES resource references. Returning false makes encoding.cpp
    // record the complete render pass through Dawn, which is required because prepare_frame will deliberately
    // make this pass ineligible for Direct-GLES replay.
    return false;
  }
"""
if old not in s:
    raise SystemExit("shadow Dawn fallback: encode_pass_resources anchor missing")
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
new = """    const bool r36sShadowDawnPass =
        (std::getenv("R36S_SHADOW_FORCE_DAWN") == nullptr ||
         std::getenv("R36S_SHADOW_FORCE_DAWN")[0] != '0') &&
        pass.resolveTarget &&
        (pass.resolveFormat == GX_CTF_B8 || pass.resolveFormat == GX_CTF_R4 || pass.resolveFormat == GX_TF_Z8) &&
        pass.resolveRect.x == 0 && pass.resolveRect.y == 0 &&
        pass.resolveRect.width > 0 && pass.resolveRect.height > 0 &&
        pass.resolveRect.width == pass.resolveRect.height &&
        pass.resolveRect.width <= 512;
    PassPlan plan{
        .label = pass.directLabel,
        .width = pass.colorAttachments[0].size.width,
        .height = pass.colorAttachments[0].size.height,
        .clearColor = pass.colorAttachments[0].clearValue,
        .clearDepth = pass.clearDepthValue,
        .eligible = pass.msaaSamples == 1 && pass.colorAttachmentCount == 1 && !r36sShadowDawnPass,
    };
"""
if old not in s:
    raise SystemExit("shadow Dawn fallback: plan init anchor missing")
s = s.replace(old, new, 1)

old = """    if (stats_enabled() && sFrameNumber % 120 == 0) {
      std::fprintf(stderr,
                   "[gles-direct-plan] frame=%llu pass=%zu eligible=%u gx=%u clear=%u other=%u custom=%u commands=%zu\\n",
"""
new = """    if (r36sShadowDawnPass) {
      static unsigned shadowReports = 0;
      if ((shadowReports++ % 120) == 0) {
        std::fprintf(stderr,
                     "[r36s-shadow-dawn-pass] resolve_fmt=%u src=%dx%d attachment=%ux%u forced_dawn=1\\n",
                     static_cast<unsigned>(pass.resolveFormat), pass.resolveRect.width, pass.resolveRect.height,
                     plan.width, plan.height);
      }
    }
    if (stats_enabled() && sFrameNumber % 120 == 0) {
      std::fprintf(stderr,
                   "[gles-direct-plan] frame=%llu pass=%zu eligible=%u gx=%u clear=%u other=%u custom=%u commands=%zu\\n",
"""
if old not in s:
    raise SystemExit("shadow Dawn fallback: plan log anchor missing")
s = s.replace(old, new, 1)

p.write_text(s)
print("forced square B8/R4/Z8 shadow-source passes up to 512x512 through fully recorded Dawn path")
