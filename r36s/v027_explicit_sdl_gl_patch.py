#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new, count=1):
    p = root / rel
    s = p.read_text()
    if s.count(old) < count:
        raise SystemExit(f"{rel}: expected at least {count} match(es), got {s.count(old)}: {old[:180]!r}")
    p.write_text(s.replace(old, new, count))

p = root / "extern/aurora/lib/window.cpp"
s = p.read_text()

# Keep an explicit SDL-created GLES context, exactly like the working Strikers/Melee
# KMSDRM display path. SDL_Renderer owns a private context and cannot safely hand
# its EGL window surface to our shared presenter on Mali r13p0.
# Aurora's newer direct-GLES branch adds g_windowExternal between the
# window and renderer. Insert the explicit R36S context at the first R36S
# presentation-state block instead of matching the older exact state layout.
old = "SDL_Renderer* g_renderer;\n#ifdef AURORA_R36S_OFFSCREEN\n"
new = """SDL_Renderer* g_renderer;
#ifdef AURORA_R36S_OFFSCREEN
SDL_GLContext g_r36sWindowContext = nullptr;
"""
if old not in s:
    raise SystemExit("window state anchor not found")
s = s.replace(old, new, 1)

# The SDL window must be an actual OpenGL window so SDL_GL_CreateContext owns the
# visible KMSDRM EGL surface.
old = "  SDL_WindowFlags flags = SDL_WINDOW_HIGH_PIXEL_DENSITY;\n"
new = """#ifdef AURORA_R36S_OFFSCREEN
  SDL_WindowFlags flags = SDL_WINDOW_HIGH_PIXEL_DENSITY | SDL_WINDOW_OPENGL;
#else
  SDL_WindowFlags flags = SDL_WINDOW_HIGH_PIXEL_DENSITY;
#endif
"""
if old not in s:
    raise SystemExit("window flags anchor not found")
s = s.replace(old, new, 1)

# KMSDRM needs a real panel mode for an EGL window surface. This target is
# always the R36S 640x480 panel; do not request Aurora's desktop default 1280x960.
old_size = """  Sint32 posX = g_config.windowPosX;
"""
new_size = """#ifdef AURORA_R36S_OFFSCREEN
  width = 640;
  height = 480;
  Log.info("R36S V027 forcing native KMSDRM window mode {}x{}", width, height);
#endif

  Sint32 posX = g_config.windowPosX;
"""
if old_size not in s:
    raise SystemExit("window position anchor not found")
s = s.replace(old_size, new_size, 1)

# Match the GLES context attributes used by the final Strikers/Melee SDL path.
old = """  const auto props = SDL_CreateProperties();
  TRY(SDL_SetStringProperty(props, SDL_PROP_WINDOW_CREATE_TITLE_STRING, g_config.appName), "Failed to set {}: {}",
"""
new = """#ifdef AURORA_R36S_OFFSCREEN
  TRY(SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES),
      "Failed to request GLES profile: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3),
      "Failed to request GLES major version: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1),
      "Failed to request GLES minor version: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_RED_SIZE, 8), "Failed to set GL red size: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_GREEN_SIZE, 8), "Failed to set GL green size: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_BLUE_SIZE, 8), "Failed to set GL blue size: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_ALPHA_SIZE, 8), "Failed to set GL alpha size: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 0), "Failed to set GL depth size: {}", SDL_GetError());
  TRY(SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1), "Failed to enable GL double buffer: {}", SDL_GetError());
#endif
  const auto props = SDL_CreateProperties();
  TRY(SDL_SetStringProperty(props, SDL_PROP_WINDOW_CREATE_TITLE_STRING, g_config.appName), "Failed to set {}: {}",
"""
if old not in s:
    raise SystemExit("window props anchor not found")
s = s.replace(old, new, 1)

# Replace the complete R36S branch of create_renderer() after V025/V026 patches.
start = s.index("bool create_renderer() {")
r36s = s.index("#ifdef AURORA_R36S_OFFSCREEN", start)
else_pos = s.index("#else", r36s)
new_branch = r'''#ifdef AURORA_R36S_OFFSCREEN
  SDL_ClearError();
  g_r36sWindowContext = SDL_GL_CreateContext(g_window);
  if (g_r36sWindowContext == nullptr) {
    Log.error("R36S V027 SDL_GL_CreateContext failed: {}", SDL_GetError());
    return false;
  }
  if (!SDL_GL_MakeCurrent(g_window, g_r36sWindowContext)) {
    Log.error("R36S V027 SDL_GL_MakeCurrent initial context failed: {}", SDL_GetError());
    return false;
  }
  if (!SDL_GL_SetSwapInterval(1)) {
    Log.warn("R36S V027 SDL_GL_SetSwapInterval(1) failed: {}", SDL_GetError());
  }

  g_r36sPresentDisplay = eglGetCurrentDisplay();
  if (g_r36sPresentDisplay == EGL_NO_DISPLAY)
    g_r36sPresentDisplay = static_cast<EGLDisplay>(SDL_EGL_GetCurrentDisplay());
  g_r36sPresentSurface = eglGetCurrentSurface(EGL_DRAW);
  if (g_r36sPresentSurface == EGL_NO_SURFACE)
    g_r36sPresentSurface = static_cast<EGLSurface>(SDL_EGL_GetWindowSurface(g_window));

  if (g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentSurface == EGL_NO_SURFACE ||
      !eglQueryContext(g_r36sPresentDisplay, eglGetCurrentContext(), EGL_CONFIG_ID, &g_r36sPresentConfig)) {
    Log.error("R36S V027 cannot capture SDL GL EGL display/surface/config");
    return false;
  }

  Log.info("R36S V027 explicit SDL GLES context initialized display={} surface={} config={}",
           static_cast<void*>(g_r36sPresentDisplay), static_cast<void*>(g_r36sPresentSurface),
           g_r36sPresentConfig);

  // Exact Strikers/Melee ownership handoff: SDL creates the real KMSDRM surface,
  // then releases it. Dawn renders to a pbuffer on the same EGLDisplay and the
  // shared presenter later binds this window surface through SDL.
  if (!SDL_GL_MakeCurrent(g_window, nullptr)) {
    Log.error("R36S V027 cannot release explicit SDL/KMSDRM GL context: {}", SDL_GetError());
    return false;
  }
  Log.info("R36S V027 released explicit SDL/KMSDRM EGL surface for presenter ownership");
  return true;
'''
s = s[:r36s] + new_branch + s[else_pos:]

# If the direct path really fails, preserve the proven V022 fallback by lazily
# switching this OpenGL window back to SDL_Renderer. Do not keep that private
# renderer context alive during the fast path.
old = """bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch) {
  if (g_window == nullptr || g_renderer == nullptr || pixels == nullptr || width == 0 || height == 0) {
    return false;
  }
"""
new = """bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch) {
  if (g_window == nullptr || pixels == nullptr || width == 0 || height == 0) {
    return false;
  }
#ifdef AURORA_R36S_OFFSCREEN
  if (g_renderer == nullptr) {
    if (g_r36sWindowContext != nullptr) {
      SDL_GL_MakeCurrent(g_window, nullptr);
      SDL_GL_DestroyContext(g_r36sWindowContext);
      g_r36sWindowContext = nullptr;
    }
    g_renderer = SDL_CreateRenderer(g_window, nullptr);
    if (g_renderer == nullptr) {
      Log.error("R36S V027 fallback SDL_CreateRenderer failed: {}", SDL_GetError());
      return false;
    }
    Log.warn("R36S V027 activated V022 SDL readback fallback renderer={}",
             SDL_GetRendererName(g_renderer) ? SDL_GetRendererName(g_renderer) : "?");
  }
#else
  if (g_renderer == nullptr) {
    return false;
  }
#endif
"""
if old not in s:
    raise SystemExit("software presenter anchor not found")
s = s.replace(old, new, 1)

# Destroy the explicit SDL context on shutdown if direct presentation remained active.
needle = """  if (g_window != nullptr) {
    SDL_DestroyWindow(g_window);
    g_window = nullptr;
  }
"""
replacement = """#ifdef AURORA_R36S_OFFSCREEN
  if (g_r36sWindowContext != nullptr) {
    SDL_GL_MakeCurrent(g_window, nullptr);
    SDL_GL_DestroyContext(g_r36sWindowContext);
    g_r36sWindowContext = nullptr;
  }
#endif
  if (g_window != nullptr) {
    SDL_DestroyWindow(g_window);
    g_window = nullptr;
  }
"""
if needle not in s:
    raise SystemExit("destroy window anchor not found")
s = s.replace(needle, replacement, 1)

p.write_text(s)
print("R36S V027 explicit SDL GL/KMSDRM display patch applied")
