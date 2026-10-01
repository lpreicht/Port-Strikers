#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if s.count(old) != 1:
        raise SystemExit(f"{rel}: expected one match, got {s.count(old)}: {old[:160]!r}")
    p.write_text(s.replace(old, new, 1))

# Expose the EGLDisplay captured from SDL/KMSDRM even after we deliberately
# release SDL's window surface from its original renderer context.
replace(
    "extern/aurora/lib/window.hpp",
    "SDL_Renderer* get_sdl_renderer();\n",
    "SDL_Renderer* get_sdl_renderer();\n"
    "#ifdef AURORA_R36S_OFFSCREEN\n"
    "void* r36s_egl_display();\n"
    "#endif\n",
)

replace(
    "extern/aurora/lib/window.cpp",
    "SDL_Renderer* get_sdl_renderer() { return g_renderer; }\n",
    "SDL_Renderer* get_sdl_renderer() { return g_renderer; }\n\n"
    "#ifdef AURORA_R36S_OFFSCREEN\n"
    "void* r36s_egl_display() { return reinterpret_cast<void*>(g_r36sPresentDisplay); }\n"
    "#endif\n",
)

# V025 captured SDL's EGL surface but left it current on SDL's original GLES
# context. On the R36S Mali r13p0 driver the later presenter context therefore
# failed with EGL_BAD_ACCESS. Strikers/Melee explicitly releases this surface
# before Dawn owns its pbuffer and the presenter later owns the window surface.
replace(
    "extern/aurora/lib/window.cpp",
    """  if (g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentSurface == EGL_NO_SURFACE ||
      !eglQueryContext(g_r36sPresentDisplay, eglGetCurrentContext(), EGL_CONFIG_ID, &g_r36sPresentConfig)) {
    Log.error("R36S V025 cannot capture SDL EGL display/config");
    return false;
  }
  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",
""",
    """  if (g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentSurface == EGL_NO_SURFACE ||
      !eglQueryContext(g_r36sPresentDisplay, eglGetCurrentContext(), EGL_CONFIG_ID, &g_r36sPresentConfig)) {
    Log.error("R36S V026 cannot capture SDL EGL display/config");
    return false;
  }
  if (!SDL_GL_MakeCurrent(g_window, nullptr)) {
    Log.error("R36S V026 cannot release SDL/KMSDRM window surface: {}", SDL_GetError());
    return false;
  }
  Log.info("R36S V026 released SDL/KMSDRM EGL surface for presenter ownership");
  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",
""",
)

# Dawn must keep using the exact SDL/KMSDRM EGLDisplay even though there is no
# current SDL context after the release above.
replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  g_r36sEglDisplay = eglGetCurrentDisplay();
  if (g_r36sEglDisplay != EGL_NO_DISPLAY) {
    const char* vendor = eglQueryString(g_r36sEglDisplay, EGL_VENDOR);
""",
    """  g_r36sEglDisplay =
      reinterpret_cast<EGLDisplay>(window::r36s_egl_display());
  if (g_r36sEglDisplay == EGL_NO_DISPLAY) {
    g_r36sEglDisplay = eglGetCurrentDisplay();
  }
  if (g_r36sEglDisplay != EGL_NO_DISPLAY) {
    const char* vendor = eglQueryString(g_r36sEglDisplay, EGL_VENDOR);
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """    Log.info("R36S: reusing SDL/KMSDRM EGLDisplay vendor={} version={} APIs={}",
""",
    """    Log.info("R36S V026: reusing captured SDL/KMSDRM EGLDisplay vendor={} version={} APIs={}",
""",
)

print("R36S V026 SDL surface ownership handoff patch applied")
