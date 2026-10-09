#!/usr/bin/env python3
"""Keep previously recorded GPU shadow reads independent of subsequent GXCopyTex writes.

Aurora reuses a cached GPU render target for every copy to the same GameCube
address. When a dynamic caster is redrawn, the previously recorded draw may
still sample that target. Keep old references immutable: on subsequent small
B8/R4/Z8 copies, make a new GPU texture and update only the current cached
reference. Earlier frame packets/bind groups retain their old TextureHandle.

Keep reflection RGB565/Z8 320x240 targets on their established path. This
patch intentionally runs after starfox_native_shadow_texture_patch.py.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/dolphin/gx/GXFrameBuffer.cpp"
s=p.read_text()
anchor="""  auto& handle = it->second;

  // R36S/upstream 9c0bf66: GXCopyTex resolves the EFB without a pre-copy dst-alpha overwrite."""
repl="""  // R36S GPU shadow snapshots: do not overwrite a texture still referenced
  // by earlier recorded draw commands or an in-flight frame. The cache owns
  // the latest generation, while the previous TextureHandles remain alive
  // until every referencing command has completed.
  // Square projected shadow masks only. Exclude rectangular 160x120 intro and
  // full-frame water/reflection copies to preserve their proven fast path.
  if (r36sNativeShadowMask && dstWidth == dstHeight && it->second.revision != 0) {
    it->second.handle = gfx::new_conv_texture(dstWidth, dstHeight, texCopyFmt, "R36S shadow snapshot");
    static unsigned r36sShadowSnapshots = 0;
    if (++r36sShadowSnapshots <= 12 || r36sShadowSnapshots % 240 == 0) {
      std::fprintf(stderr, "[r36s-shadow-snapshot] n=%u fmt=%u %ux%u fresh_target=1\\n",
                   r36sShadowSnapshots, static_cast<unsigned>(texCopyFmt), dstWidth, dstHeight);
    }
  }
  auto& handle = it->second;

  // R36S/upstream 9c0bf66: GXCopyTex resolves the EFB without a pre-copy dst-alpha overwrite."""
if s.count(anchor)!=1:
    raise SystemExit(f"snapshot placement anchor mismatch: {s.count(anchor)}")
if "r36sNativeShadowMask" not in s:
    raise SystemExit("requires native-shadow mask patch before snapshot")
s=s.replace(anchor,repl,1)
p.write_text(s)

# Diagnostic: confirm whether the GPU shadow result is actually looked up by
# the GX sampled-texture metadata, instead of accidentally reading stale CPU RAM.
tex = root/"extern/aurora/lib/gx/texture.cpp"
s = tex.read_text()
old = """    const GXState::CopyTextureRef* copyRef = copyIt != g_gxState.copyTextures.end() ? &copyIt->second : nullptr;
    if (copyRef != nullptr) {
      gfx::on_copy_texture_sampled(copyRef->handle);
    }
"""
new = """    const GXState::CopyTextureRef* copyRef = copyIt != g_gxState.copyTextures.end() ? &copyIt->second : nullptr;
    if (obj.width() == 256 && obj.height() == 256) {
      static unsigned r36sShadowSampleChecks = 0;
      const unsigned check = ++r36sShadowSampleChecks;
      if (check <= 24 || check % 240 == 0) {
        std::fprintf(stderr,
                     "[r36s-shadow-bind] n=%u tex_obj=%u gx_fmt=%u copy_ref=%u revision=%u copy_size=%ux%u\\n",
                     check, obj.texObjId, static_cast<unsigned>(obj.format()),
                     copyRef != nullptr ? 1u : 0u,
                     copyRef != nullptr ? copyRef->revision : 0u,
                     copyRef != nullptr && copyRef->handle ? copyRef->handle->size.width : 0u,
                     copyRef != nullptr && copyRef->handle ? copyRef->handle->size.height : 0u);
      }
    }
    if (copyRef != nullptr) {
      gfx::on_copy_texture_sampled(copyRef->handle);
    }
"""
assert s.count(old) == 1, f"shadow bind metadata anchor mismatch: {s.count(old)}"
tex.write_text(s.replace(old, new, 1))
print("R36S immutable GPU snapshots + sampled 256px shadow texture binding diagnostic installed")
