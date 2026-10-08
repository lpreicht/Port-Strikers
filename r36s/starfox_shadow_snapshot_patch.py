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

  if (g_gxState.alphaUpdate"""
repl="""  // R36S GPU shadow snapshots: do not overwrite a texture still referenced
  // by earlier recorded draw commands or an in-flight frame. The cache owns
  // the latest generation, while the previous TextureHandles remain alive
  // until every referencing command has completed.
  if (r36sNativeShadowMask && it->second.revision != 0) {
    it->second.handle = gfx::new_conv_texture(dstWidth, dstHeight, texCopyFmt, "R36S shadow snapshot");
    static unsigned r36sShadowSnapshots = 0;
    if (++r36sShadowSnapshots <= 6 || r36sShadowSnapshots % 300 == 0) {
      std::fprintf(stderr, "[r36s-shadow-snapshot] n=%u fmt=%u %ux%u fresh_target=1\\n",
                   r36sShadowSnapshots, static_cast<unsigned>(texCopyFmt), dstWidth, dstHeight);
    }
  }
  auto& handle = it->second;

  if (g_gxState.alphaUpdate"""
if s.count(anchor)!=1:
    raise SystemExit(f"snapshot placement anchor mismatch: {s.count(anchor)}")
if "r36sNativeShadowMask" not in s:
    raise SystemExit("requires native-shadow mask patch before snapshot")
s=s.replace(anchor,repl,1)
p.write_text(s)
print("R36S immutable GPU snapshots for repeated shadow copies installed")
