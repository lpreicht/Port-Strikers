#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 3:
    raise SystemExit("usage: patch_r36s_display.py <strikers-dir> <melee-dir>")

root = Path(sys.argv[1])
melee = Path(sys.argv[2])

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
    "{melee.as_posix()}/native/platform/flip/present_worker.cpp")
set_source_files_properties(
    "{melee.as_posix()}/native/platform/flip/display.cpp"
    "{melee.as_posix()}/native/platform/flip/present_worker.cpp"
    PROPERTIES COMPILE_OPTIONS "-std=gnu++20")
target_include_directories(strikers PRIVATE
    "{melee.as_posix()}/native/platform/flip"
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
gpu = root / "extern/aurora/lib/webgpu/gpu.cpp"
s = gpu.read_text()
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
