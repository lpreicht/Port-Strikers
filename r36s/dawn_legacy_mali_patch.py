#!/usr/bin/env python3
from pathlib import Path
import sys

dawn = Path(sys.argv[1])

def replace(rel, old, new):
    p = dawn / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:180]!r}")
    p.write_text(s.replace(old, new, 1))

# The RK3326 proprietary Mali stack can create the non-robust context Dawn uses
# during adapter discovery, even if it doesn't advertise EXT_create_context_robustness.
replace(
    "src/dawn/native/opengl/BackendGL.cpp",
    """        if (!display->egl->HasExt(EGLExt::CreateContextRobustness)) {
            return DAWN_VALIDATION_ERROR("EGL_EXT_create_context_robustness is required.");
        }
        if (!display->egl->HasExt(EGLExt::FenceSync) &&
            !display->egl->HasExt(EGLExt::ReusableSync)) {
            return DAWN_INTERNAL_ERROR(
                "EGL_KHR_fence_sync or EGL_KHR_reusable_sync must be supported");
        }
""",
    """#ifndef AURORA_R36S_OFFSCREEN
        if (!display->egl->HasExt(EGLExt::CreateContextRobustness)) {
            return DAWN_VALIDATION_ERROR("EGL_EXT_create_context_robustness is required.");
        }
#endif
        if (!display->egl->HasExt(EGLExt::FenceSync) &&
            !display->egl->HasExt(EGLExt::ReusableSync)
#ifdef AURORA_R36S_OFFSCREEN
            && !display->egl->HasExt(EGLExt::NativeFenceSync)
#endif
        ) {
            return DAWN_INTERNAL_ERROR(
                "No supported EGL fence sync mechanism is available");
        }
""",
)

print("Dawn legacy Mali adapter gate patch applied")
