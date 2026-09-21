#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: patch_r36s_display.py <strikers-dir> <melee-dir>")

root = Path(sys.argv[1])
melee = Path(sys.argv[2])

# Fast Aurora intentionally wins renderer merge conflicts. Re-add only the small
# Strikers-facing ABI surface that the game sources require on the handheld.
aurora_h = root / "extern/aurora/include/aurora/aurora.h"
hs = aurora_h.read_text()
if "bool startMaximized;" not in hs:
    marker = "  bool startFullscreen;\n"
    if marker not in hs:
        raise SystemExit("aurora.h: startFullscreen marker not found")
    hs = hs.replace(marker, marker + "  bool startMaximized; /* Strikers compatibility; ignored by external R36S window */\n", 1)

compat_decls = """void aurora_capture_frame(const char* path);
void aurora_gpu_frame_time(uint64_t* lastNs, uint64_t* meanNs, uint64_t* maxNs, uint64_t* count);
void aurora_set_frame_buffer_scale(float scale);
AuroraWindowSize aurora_window_size();
void aurora_apply_frame_buffer_resize();
"""
if "void aurora_capture_frame(const char* path);" not in hs:
    marker = "void aurora_shutdown();\n"
    if marker not in hs:
        raise SystemExit("aurora.h: shutdown declaration marker not found")
    hs = hs.replace(marker, marker + compat_decls, 1)
aurora_h.write_text(hs)

compat_cpp = root / "src/platform/r36s_aurora_compat.cpp"
compat_cpp.write_text(r'''#include <aurora/aurora.h>
#include "window.hpp"

#include <cstddef>
#include <cstdint>

extern "C" {

void aurora_capture_frame(const char*) {
  // Diagnostic-only feature on desktop. Keep the symbol for Strikers but avoid
  // a WebGPU readback path on the direct-GLES handheld renderer.
}

void aurora_gpu_frame_time(uint64_t* lastNs, uint64_t* meanNs, uint64_t* maxNs, uint64_t* count) {
  if (lastNs) *lastNs = 0;
  if (meanNs) *meanNs = 0;
  if (maxNs) *maxNs = 0;
  if (count) *count = 0;
}

void aurora_set_frame_buffer_scale(float scale) {
  aurora::window::set_frame_buffer_scale(scale);
}

AuroraWindowSize aurora_window_size() {
  return aurora::window::get_window_size();
}

void aurora_apply_frame_buffer_resize() {
  // Fixed-size R36S display: a deferred resize is sufficient and avoids reaching
  // into Aurora's private swapchain implementation.
  aurora::window::request_frame_buffer_resize();
}

void aurora_gfx_pool_stats(uint32_t* peakBytes, uint32_t* reservedBytes, size_t count) {
  for (size_t i = 0; i < count; ++i) {
    if (peakBytes) peakBytes[i] = 0;
    if (reservedBytes) reservedBytes[i] = 0;
  }
}

void aurora_gfx_texture_stats(uint64_t* srcBytes, uint64_t* uploadedBytes, uint64_t* count) {
  if (srcBytes) *srcBytes = 0;
  if (uploadedBytes) *uploadedBytes = 0;
  if (count) *count = 0;
}

} // extern "C"
''')

# 1) Link Melee's proven SDL/KMSDRM + EGL pbuffer/present bridge into Strikers.
cmake = root / "CMakeLists.txt"
s = cmake.read_text()
needle = "target_link_libraries(strikers PRIVATE port_flags)\n"
if "STRIKERS_R36S_DISPLAY_BRIDGE" not in s:
    bridge = f'''target_link_libraries(strikers PRIVATE port_flags)

# STRIKERS_R36S_DISPLAY_BRIDGE
find_path(STRIKERS_R36S_DRM_INCLUDE_DIR drm.h PATH_SUFFIXES libdrm REQUIRED)
find_library(STRIKERS_R36S_EGL EGL REQUIRED)
find_library(STRIKERS_R36S_GLES GLESv2 REQUIRED)
target_sources(strikers PRIVATE
    "{melee.as_posix()}/native/platform/flip/display.cpp"
    "{melee.as_posix()}/native/platform/flip/present_worker.cpp"
    "{(root / "src/platform/r36s_aurora_compat.cpp").as_posix()}")
set_source_files_properties(
    "{melee.as_posix()}/native/platform/flip/display.cpp"
    "{melee.as_posix()}/native/platform/flip/present_worker.cpp"
    PROPERTIES COMPILE_OPTIONS "-std=gnu++20")
target_include_directories(strikers PRIVATE
    "{melee.as_posix()}/native/platform/flip"
    "{(root / "extern/aurora/lib").as_posix()}"
    "${{STRIKERS_R36S_DRM_INCLUDE_DIR}}")
target_link_libraries(strikers PRIVATE
    "${{STRIKERS_R36S_EGL}}" "${{STRIKERS_R36S_GLES}}" dl)
'''
    if needle not in s:
        raise SystemExit("CMake: strikers target link marker not found")
    cmake.write_text(s.replace(needle, bridge, 1))

# 2) Bring up the application's SDL/OpenGL display before Aurora and force GLES.
main = root / "src/Game/main.cpp"
s = main.read_text()
decl = '''#if defined(MELEE_MIYOO_FLIP)
void MeleeFlipInitDisplay();
extern "C" void MeleeFlipDisplaySize(unsigned* width, unsigned* height);
#endif

'''
if decl not in s:
    marker = "int main(int argc, char* argv[])\n"
    if marker not in s:
        raise SystemExit("main.cpp: main marker not found")
    s = s.replace(marker, decl + marker, 1)

old = '''        PortAuroraConfigure(&cfg);
        AuroraInfo info = aurora_initialize(argc, argv, &cfg);
'''
new = '''        PortAuroraConfigure(&cfg);
#if defined(MELEE_MIYOO_FLIP)
        cfg.desiredBackend = BACKEND_OPENGLES;
        wantBackend = BACKEND_OPENGLES;
        cfg.vsync = false;
        cfg.allowJoystickBackgroundEvents = true;
        cfg.cpuVertexDecode = true;
        cfg.residentDisplayLists = true;
        cfg.residentGeometryBudget = 64u * 1024u * 1024u;
        cfg.asyncFrames = true;
        cfg.textureVerifyInterval = 4;
        cfg.textureAtlas = true;
        cfg.disableRenderPassFusion = false;
        cfg.uniformTable = true;
        cfg.batchDraws = true;
        cfg.glesDirectSubmission = 1;
        cfg.glesMappedStreams = 1;
        cfg.sortOpaqueDraws = false;
        cfg.renderStats = false;
        cfg.sceneOnSurface = true;
        cfg.halfResolutionSpritePoints = 4000;
        cfg.smallCopyPassInterval = 2;
        MeleeFlipInitDisplay();
        {
            unsigned displayW = 640, displayH = 480;
            MeleeFlipDisplaySize(&displayW, &displayH);
            cfg.windowWidth = (int)displayW;
            cfg.windowHeight = (int)displayH;
        }
#endif
        AuroraInfo info = aurora_initialize(argc, argv, &cfg);
'''
if new not in s:
    if old not in s:
        raise SystemExit("main.cpp: Aurora init marker not found")
    s = s.replace(old, new, 1)
main.write_text(s)

# 3) Do not force desktop X11/Wayland on the handheld SDL2-shim path.
launch = root / "src/platform/launch.cpp"
s = launch.read_text()
old = "#if defined(__linux__)\n    // Dawn's EGL swap chain cannot present to a Wayland surface, so the GL backends go through XWayland.\n"
new = "#if defined(__linux__) && !defined(MELEE_MIYOO_FLIP)\n    // Dawn's EGL swap chain cannot present to a Wayland surface, so the GL backends go through XWayland.\n"
if new not in s:
    if old not in s:
        raise SystemExit("launch.cpp: Linux video hint marker not found")
    s = s.replace(old, new, 1)
launch.write_text(s)

# 4) Aurora reuses the SDL window created by the application display bridge.
window = root / "extern/aurora/lib/window.cpp"
s = window.read_text()
# Fast Aurora already carries this platform support.
if "MeleeFlipSdlWindow" in s and "g_windowExternal" in s:
    pass
else:
    decl = '''#ifdef MELEE_MIYOO_FLIP
    extern "C" SDL_Window* MeleeFlipSdlWindow();
    #endif

    '''
    marker = '#include "rmlui.hpp"\n'
    if decl not in s:
        if marker not in s:
            raise SystemExit("window.cpp: include marker not found")
        s = s.replace(marker, decl + marker, 1)
    if "bool g_windowExternal = false;" not in s:
        s = s.replace("SDL_Window* g_window;\n", "SDL_Window* g_window;\nbool g_windowExternal = false;\n", 1)

    old = "bool create_window(AuroraBackend backend) {\n"
    new = '''bool create_window(AuroraBackend backend) {
    #ifdef MELEE_MIYOO_FLIP
      if (SDL_Window* external = MeleeFlipSdlWindow(); external != nullptr) {
        g_window = external;
        g_windowExternal = true;
        return true;
      }
    #endif
    '''
    if new not in s:
        if old not in s:
            raise SystemExit("window.cpp: create_window marker not found")
        s = s.replace(old, new, 1)

    old = '''  if (g_window != nullptr) {
        SDL_DestroyWindow(g_window);
        g_window = nullptr;
      }
    '''
    new = '''  if (g_window != nullptr) {
        if (!g_windowExternal) {
          SDL_DestroyWindow(g_window);
        }
        g_window = nullptr;
        g_windowExternal = false;
      }
    '''
    if new not in s:
        if old not in s:
            raise SystemExit("window.cpp: destroy_window marker not found")
        s = s.replace(old, new, 1)
    window.write_text(s)

# 5) Dawn EGL-native-window surface; null native window becomes a pbuffer in the patched Dawn.
backend = root / "extern/aurora/lib/dawn/BackendBinding.cpp"
s = backend.read_text()
if "SurfaceSourceEGLNativeWindow" in s and "MeleeFlipNativeWindow" in s:
    pass
else:
    decl = '''#ifdef MELEE_MIYOO_FLIP
    extern "C" void* MeleeFlipNativeWindow();
    #endif

    '''
    if decl not in s:
        s = s.replace('#include "BackendBinding.hpp"\n', '#include "BackendBinding.hpp"\n' + decl, 1)
    old = '''#else
      const auto props = SDL_GetWindowProperties(window);
    '''
    new = '''#else
    #ifdef MELEE_MIYOO_FLIP
      auto desc = std::make_shared<wgpu::SurfaceSourceEGLNativeWindow>();
      desc->window = MeleeFlipNativeWindow();
      return desc;
    #endif
      const auto props = SDL_GetWindowProperties(window);
    '''
    if new not in s:
        if old not in s:
            raise SystemExit("BackendBinding.cpp: platform marker not found")
        s = s.replace(old, new, 1)
    backend.write_text(s)

# 6) Dawn's GLES adapter must use the application's live EGL display and loader.
# The fast Aurora fork already carries the MELEE_MIYOO_FLIP implementation; keep
# the legacy transformation only for the older Strikers-bundled Aurora.
gpu = root / "extern/aurora/lib/webgpu/gpu.cpp"
s = gpu.read_text()
if "MeleeFlipEGLProc" not in s or "RequestAdapterOptionsGetGLProc glOptions" not in s:
    decl = '''#ifdef MELEE_MIYOO_FLIP
#include <dawn/native/OpenGLBackend.h>
extern "C" void* MeleeFlipEGLDisplay();
extern "C" dawn::native::opengl::EGLFunctionPointerType MeleeFlipEGLProc(const char*);
#endif

'''
    if decl not in s:
        s = s.replace('#include "gpu.hpp"\n\n', '#include "gpu.hpp"\n\n' + decl, 1)

    old = '''#ifdef AURORA_LINUX_EGL_PROC
    /* smstrikers-port: Dawn opens "libEGL.so", which only EGL's development package installs; hand it libEGL.so.1's eglGetProcAddress instead. */
    dawn::native::opengl::RequestAdapterOptionsGetGLProc glProc;
    if (backend == wgpu::BackendType::OpenGL || backend == wgpu::BackendType::OpenGLES) {
      static void* const libEGL = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
      if (libEGL != nullptr) {
        glProc.getProc =
            reinterpret_cast<dawn::native::opengl::EGLGetProcProc>(dlsym(libEGL, "eglGetProcAddress"));
        glProc.display = nullptr;
        if (glProc.getProc != nullptr) {
          options.nextInChain = &glProc;
        }
      }
    }
#endif
'''
    new = '''#ifdef MELEE_MIYOO_FLIP
    dawn::native::opengl::RequestAdapterOptionsGetGLProc glProc;
    if (backend == wgpu::BackendType::OpenGL || backend == wgpu::BackendType::OpenGLES) {
      glProc.getProc = MeleeFlipEGLProc;
      glProc.display = MeleeFlipEGLDisplay();
      options.nextInChain = &glProc;
    }
#elif defined(AURORA_LINUX_EGL_PROC)
    /* smstrikers-port desktop Linux fallback. */
    dawn::native::opengl::RequestAdapterOptionsGetGLProc glProc;
    if (backend == wgpu::BackendType::OpenGL || backend == wgpu::BackendType::OpenGLES) {
      static void* const libEGL = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
      if (libEGL != nullptr) {
        glProc.getProc =
            reinterpret_cast<dawn::native::opengl::EGLGetProcProc>(dlsym(libEGL, "eglGetProcAddress"));
        glProc.display = nullptr;
        if (glProc.getProc != nullptr) {
          options.nextInChain = &glProc;
        }
      }
    }
#endif
'''
    if new not in s:
        if old not in s:
            raise SystemExit("gpu.cpp: EGL proc block not found")
        s = s.replace(old, new, 1)
    gpu.write_text(s)

# 7) The Melee bridge normally inherits C++20 and several transitive standard
# headers from Melee's own target. Strikers' main target is C++11, so make the
# bridge self-contained instead of relying on include order.
display_cpp = melee / "native/platform/flip/display.cpp"
ds = display_cpp.read_text()
if "#include <type_traits>" not in ds:
    ds = ds.replace("#include <limits>\n", "#include <limits>\n#include <type_traits>\n", 1)
    display_cpp.write_text(ds)

present_cpp = melee / "native/platform/flip/present_worker.cpp"
ps = present_cpp.read_text()
if "#include <limits>" not in ps:
    ps = ps.replace("#include <dawn/native/OpenGLBackend.h>\n",
                    "#include <limits>\n#include <dawn/native/OpenGLBackend.h>\n", 1)
    present_cpp.write_text(ps)

print("Applied R36S SDL/KMSDRM + Dawn EGL/pbuffer display bridge")
