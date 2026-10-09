#!/usr/bin/env python3
"""R36S: restore the GameCube's intentionally near-biased decal viewport.

The original game requests GXViewport znear=-0.05 and zfar=1 when drawing
shadows just above ground. GLES glDepthRangef clamps reversed-Z (0, 1.05)
to (0, 1), erasing the bias and producing depth fighting of coplanar decals.

Instead use GX viewport (0, .95): in reversed Z GLES obtains (.05, 1.0).
This is legal in GLES and Dawn, placing decals marginally closer to the
camera without disabling Z test, changing the projection, terrain geometry,
or the depth-write rules. The fix changes only Camera_ApplyDecalViewport.

Opt-in by R36S_DECAL_DEPTH_FIX=1 from the launcher; can be disabled without
building a new binary for hardware A/B validation.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "game/src/main/camera.c"
s = p.read_text()
marker = """void Camera_ApplyDecalViewport(void) {
    GXRenderModeObj* renderMode = gRenderModeObj;

    if (renderMode->field_rendering != 0) {
        GXSetViewportJitter(0.0f, 0.0f, renderMode->fbWidth, renderMode->xfbHeight, (-0.05f), 1.0f,
                            gViewportJitterField);
    } else {
        GXSetViewport(0.0f, 0.0f, renderMode->fbWidth, renderMode->xfbHeight, (-0.05f), 1.0f);
    }
}
"""
replacement = """void Camera_ApplyDecalViewport(void) {
    GXRenderModeObj* renderMode = gRenderModeObj;
    const char* r36sFixEnv = getenv("R36S_DECAL_DEPTH_FIX");
    const int r36sDepthFix = (r36sFixEnv != NULL && r36sFixEnv[0] == '1');
    const float nearZ = r36sDepthFix ? 0.0f : -0.05f;
    const float farZ = r36sDepthFix ? 0.95f : 1.0f;
    static int r36sDepthReported = 0;
    if (r36sFixEnv != NULL && !r36sDepthReported) {
        fprintf(stderr,
                "[r36s-decal-depth] active=%d gx_near=%.3f gx_far=%.3f "
                "reversed_gl_near=%.3f reversed_gl_far=%.3f\\\\n",
                r36sDepthFix, nearZ, farZ, 1.0f - farZ, 1.0f - nearZ);
        r36sDepthReported = 1;
    }
    if (renderMode->field_rendering != 0) {
        GXSetViewportJitter(0.0f, 0.0f, renderMode->fbWidth, renderMode->xfbHeight,
                            nearZ, farZ, gViewportJitterField);
    } else {
        GXSetViewport(0.0f, 0.0f, renderMode->fbWidth, renderMode->xfbHeight, nearZ, farZ);
    }
}
"""
assert s.count(marker)==1, f"decal viewport expected original block once, got {s.count(marker)}"
s=s.replace(marker,replacement,1)
if "#include <stdlib.h>" not in s:
    s="#include <stdlib.h>\n"+s
if "#include <stdio.h>" not in s:
    s="#include <stdio.h>\n"+s
p.write_text(s)
print("R36S decal-depth: GLES-valid viewport range (0.0,.95) instead of clipped (-.05,1), preserving depth test")
