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


# r13p0 advertises EGL_KHR_surfaceless_context but eglMakeCurrent with
# EGL_NO_SURFACE fails once SDL2/KMSDRM owns the display. Force Dawn to create
# a tiny pbuffer for its offscreen contexts and make that surface current.
replace(
    "src/dawn/native/opengl/ContextEGL.cpp",
    """    // When EGL_KHR_surfaceless_context is not supported, we need to create a pbuffer to act
    // as an offscreen surface.
    if (!egl.HasExt(EGLExt::SurfacelessContext)) {
""",
    """    // R36S/Mali r13p0 advertises surfaceless contexts but rejects
    // eglMakeCurrent(..., EGL_NO_SURFACE, ...) under SDL2/KMSDRM.
    // Always use a 1x1 pbuffer on this target.
#ifdef AURORA_R36S_OFFSCREEN
    const bool forcePbuffer = true;
#else
    const bool forcePbuffer = false;
#endif
    if (forcePbuffer || !egl.HasExt(EGLExt::SurfacelessContext)) {
""",
)

replace(
    "src/dawn/native/opengl/ContextEGL.cpp",
    """        mOffscreenSurface =
            egl.CreatePbufferSurface(mDisplay->GetDisplay(), pbufferConfig, pbufferAttribs);
        DAWN_TRY(
            CheckEGL(egl, mOffscreenSurface != EGL_NO_SURFACE, "Creating the offscreen surface."));
    }

    return {};
""",
    """        mOffscreenSurface =
            egl.CreatePbufferSurface(mDisplay->GetDisplay(), pbufferConfig, pbufferAttribs);
        DAWN_TRY(
            CheckEGL(egl, mOffscreenSurface != EGL_NO_SURFACE, "Creating the offscreen surface."));
#ifdef AURORA_R36S_OFFSCREEN
        mState.drawSurface = mOffscreenSurface;
        mState.readSurface = mOffscreenSurface;
#endif
    }

    return {};
""",
)

print("Dawn legacy Mali adapter + forced pbuffer patch applied")
