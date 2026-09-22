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
if "uint32_t pipelineJobs;" not in hs:
    marker = "  uint32_t msaa;\n"
    if marker not in hs:
        raise SystemExit("aurora.h: msaa marker not found")
    hs = hs.replace(marker, marker + "  uint32_t pipelineJobs; /* Strikers shader compilation worker limit; 0 = automatic */\n", 1)

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
#include "../../extern/aurora/lib/window.hpp"

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

bool aurora_present_waits_for_vblank() {
  // The R36S presentation worker uses swap interval 0, but SDL/KMSDRM's page flip
  // still paces scanout to the panel. Tell Strikers not to fight that with an
  // additional exact display-rate limiter.
  return true;
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

} // extern "C"
''')

# Fast Aurora implements GXWaitDrawDone in GXManage.cpp. Strikers' older platform
# compatibility wrapper aliases it to GXDrawDone and would collide at final link.
aurora_compat_c = root / "src/platform/aurora_compat.c"
acs = aurora_compat_c.read_text()
acs = acs.replace(
    "void GXWaitDrawDone(void)\n"
    "{\n"
    "    GXDrawDone();\n"
    "}\n\n",
    ""
)
aurora_compat_c.write_text(acs)

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

# command_processor.hpp can auto-merge both the current fast-Aurora two-argument
# process() declaration and Strikers' old diagnostic streamPos overload. Because the
# latter has a default argument, every two-argument call becomes ambiguous. The fast
# FIFO/command processor no longer uses streamPos, so normalize the public declaration.
command_h = root / "extern/aurora/lib/gx/command_processor.hpp"
chs = command_h.read_text()
old_process = "ProcessResult process(const uint8_t* data, uint32_t size, uint64_t streamPos = 0) noexcept;\n"
fast_process = "ProcessResult process(const uint8_t* data, uint32_t size) noexcept;\n"
chs = chs.replace(old_process, "")
if fast_process not in chs:
    marker = "struct ProcessResult {\n  uint32_t bytesProcessed;\n  bool drawDone;\n};\n"
    if marker not in chs:
        raise SystemExit("command_processor.hpp: ProcessResult marker not found")
    chs = chs.replace(marker, marker + "\n// Process GX FIFO commands until draw-done or end of buffer.\n" + fast_process, 1)
# De-duplicate defensively if an auto-merge already supplied the fast declaration.
first = chs.find(fast_process)
second = chs.find(fast_process, first + len(fast_process)) if first >= 0 else -1
while second >= 0:
    chs = chs[:second] + chs[second + len(fast_process):]
    second = chs.find(fast_process, first + len(fast_process))
command_h.write_text(chs)

# Strikers exposes atomic shader warmup counters through aurora_get_pipeline_counts().
# The implementation merged cleanly into pipeline_cache.cpp; restore its private declaration
# after resolving pipeline_cache.hpp in favour of the fast renderer.
pipeline_h = root / "extern/aurora/lib/gfx/pipeline_cache.hpp"
phs = pipeline_h.read_text()
if "void get_pipeline_counts(uint32_t& queued, uint32_t& created);" not in phs:
    old = "bool get_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline);\n"
    new = old + "void get_pipeline_counts(uint32_t& queued, uint32_t& created);\n"
    if old not in phs:
        raise SystemExit("pipeline_cache.hpp: get_pipeline marker not found")
    phs = phs.replace(old, new, 1)
    pipeline_h.write_text(phs)

# Fast command_processor.cpp uses Aurora's shared ByteReader, while Strikers'
# older internal.hpp predated that helper. Restore the current utility without
# replacing Strikers' useful ByteBuffer diagnostics/extensions.
internal_h = root / "extern/aurora/lib/internal.hpp"
ihs = internal_h.read_text()
# ByteReader needs the same standard-library surface as current fast Aurora.
for header in ("<limits>", "<span>", "<string>"):
    include = "#include " + header + "\n"
    if include not in ihs:
        anchor = "#include <cstdint>\n"
        if anchor not in ihs:
            raise SystemExit("internal.hpp: cstdint include marker not found")
        ihs = ihs.replace(anchor, anchor + include, 1)
if "class ByteReader" not in ihs:
    insert = r'''
class ByteReader {
public:
  explicit ByteReader(std::span<const uint8_t> data) noexcept : ByteReader{data.data(), data.size()} {}
  ByteReader(const uint8_t* data, size_t size) noexcept : mData{data}, mSize{size} {}

  static ByteReader unbounded(const void* data) noexcept {
    return {static_cast<const uint8_t*>(data), std::numeric_limits<size_t>::max()};
  }

  [[nodiscard]] bool empty() const noexcept { return mPosition == mSize; }
  [[nodiscard]] size_t offset() const noexcept { return mPosition; }
  [[nodiscard]] size_t size() const noexcept { return mSize; }
  [[nodiscard]] size_t remaining() const noexcept { return mSize - mPosition; }
  [[nodiscard]] const uint8_t* data() const noexcept { return mData; }

  template <typename T>
    requires(std::is_arithmetic_v<T>)
  T read() noexcept {
    const auto bytes = take(sizeof(T));
    return read_bits<T>(bytes.data());
  }

  template <typename T>
    requires(std::is_arithmetic_v<T>)
  bool try_read(T& value) noexcept {
    std::span<const uint8_t> bytes;
    if (!try_take(sizeof(T), bytes)) {
      return false;
    }
    value = read_bits<T>(bytes.data());
    return true;
  }

  std::span<const uint8_t> take(size_t count) noexcept {
    AURORA_ASSERT(can_read(count), "Reader overrun: need {} bytes at offset {}, have {}", count, mPosition,
                  remaining());
    const std::span bytes{mData + mPosition, count};
    mPosition += count;
    return bytes;
  }

  bool try_take(size_t count, std::span<const uint8_t>& bytes) noexcept {
    if (!can_read(count)) {
      return false;
    }
    bytes = {mData + mPosition, count};
    mPosition += count;
    return true;
  }

  void skip(size_t count) noexcept {
    AURORA_ASSERT(can_read(count), "Reader overrun: need {} bytes at offset {}, have {}", count, mPosition,
                  remaining());
    mPosition += count;
  }

  std::string read_string() noexcept {
    const auto length = read<uint16_t>();
    const auto bytes = take(length);
    return {reinterpret_cast<const char*>(bytes.data()), bytes.size()};
  }

private:
  static constexpr aurora::Module Log{"aurora::reader"};

  [[nodiscard]] bool can_read(size_t count) const noexcept {
    return mPosition <= mSize && count <= mSize - mPosition;
  }

  const uint8_t* mData;
  size_t mSize;
  size_t mPosition = 0;
};
'''
    end = "} // namespace aurora\n"
    if end not in ihs:
        raise SystemExit("internal.hpp: aurora namespace end not found")
    ihs = ihs.replace(end, insert + end, 1)
    internal_h.write_text(ihs)
else:
    internal_h.write_text(ihs)

# One stale Strikers texture-view line survives the automatic GX merge. Fast
# Aurora's empty texture is a DynamicTexture and exposes sampleTextureView directly.
gx_cpp = root / "extern/aurora/lib/gx/gx.cpp"
gxs = gx_cpp.read_text()
gxs = gxs.replace("  sEmptyTextureView = {};\n", "")
gxs = gxs.replace("      textureEntry.textureView = sEmptyTextureView.Get();\n",
                  "      textureEntry.textureView = sEmptyTexture->sampleTextureView.Get();\n")
gxs = gxs.replace("          .textureView = sEmptyTextureView,\n",
                  "          .textureView = sEmptyTexture->sampleTextureView,\n")
gx_cpp.write_text(gxs)

# Resolve three Strikers-only symbols that survive the Aurora merge.
# 1) note_display_list() was only used by Strikers' fatal-desync diagnostics. Fast
# Aurora's resident display-list path references/caches the source list directly, so
# the old splice bookkeeping is obsolete and should not be stubbed into the hot path.
gx_disp = root / "extern/aurora/lib/dolphin/gx/GXDispList.cpp"
gds = gx_disp.read_text()
gds = gds.replace(
    "  aurora::gx::fifo::note_display_list(data, nbytes);\n"
    "  aurora::gx::fifo::write_data(data, nbytes);\n",
    "  aurora::gx::fifo::write_data(data, nbytes);\n"
)
gx_disp.write_text(gds)

# 2) Strikers' old background pre-conversion hook is superseded by Fast Aurora's
# texture cache/upload pipeline. Remove the old call from GXInitTexObjLOD rather
# than providing a no-op unresolved compatibility function.
gx_tex = root / "extern/aurora/lib/dolphin/gx/GXTexture.cpp"
gts = gx_tex.read_text()
gts = gts.replace(
    "  // smstrikers-port: the object is complete once its LOD range is set, so conversion can start here.\n"
    "  aurora::gx::texture::preconvert_texture(*obj);\n",
    ""
)
gts = gts.replace("  aurora::gx::texture::preconvert_texture(*obj);\n", "")
gx_tex.write_text(gts)

# 3) GXAdjustForOverscan genuinely needs to know whether Strikers pinned the
# framebuffer scale. Fast Aurora still owns g_frameBufferScale, it only dropped
# Strikers' getter, so restore that getter beside set_frame_buffer_scale().
window_h = root / "extern/aurora/lib/window.hpp"
whs = window_h.read_text()
if "float get_frame_buffer_scale();" not in whs:
    decl_marker = "void set_frame_buffer_scale(float scale);\n"
    if decl_marker not in whs:
        raise SystemExit("window.hpp: set_frame_buffer_scale declaration not found")
    whs = whs.replace(decl_marker, decl_marker + "float get_frame_buffer_scale();\n", 1)
    window_h.write_text(whs)

window_cpp = root / "extern/aurora/lib/window.cpp"
wcs = window_cpp.read_text()
if "float get_frame_buffer_scale()" not in wcs:
    def_marker = "void set_frame_buffer_scale(float scale) {\n"
    if def_marker not in wcs:
        raise SystemExit("window.cpp: set_frame_buffer_scale definition not found")
    wcs = wcs.replace(def_marker, "float get_frame_buffer_scale() { return g_frameBufferScale; }\n\n" + def_marker, 1)
    window_cpp.write_text(wcs)

# 6b) Do not let pkg-config inject the GitHub runner's host sqlite into an
# AArch64 cross build. Fast Aurora can build SQLite's amalgamation itself, which
# gives us matching headers and a GLIBC-independent static object.
extern_cmake = root / "extern/aurora/extern/CMakeLists.txt"
ecs = extern_cmake.read_text()
old = """  aurora_find_package_global(SQLite3)
  if (TARGET SQLite3::SQLite3)
    message(STATUS "aurora: Using existing sqlite3")
    add_library(sqlite3 ALIAS SQLite3::SQLite3)
  elseif (TARGET SQLite::SQLite3) # CMake < 4.3
    message(STATUS "aurora: Using existing sqlite3")
    add_library(sqlite3 ALIAS SQLite::SQLite3)
  else ()
    find_package(PkgConfig)
    if (PkgConfig_FOUND)
      pkg_check_modules(sqlite3 IMPORTED_TARGET GLOBAL sqlite3)
      if (TARGET PkgConfig::sqlite3)
        add_library(sqlite3 ALIAS PkgConfig::sqlite3)
      endif ()
    endif ()
  endif ()

"""
new = """  if (NOT CMAKE_CROSSCOMPILING)
    aurora_find_package_global(SQLite3)
    if (TARGET SQLite3::SQLite3)
      message(STATUS "aurora: Using existing sqlite3")
      add_library(sqlite3 ALIAS SQLite3::SQLite3)
    elseif (TARGET SQLite::SQLite3) # CMake < 4.3
      message(STATUS "aurora: Using existing sqlite3")
      add_library(sqlite3 ALIAS SQLite::SQLite3)
    else ()
      find_package(PkgConfig)
      if (PkgConfig_FOUND)
        pkg_check_modules(sqlite3 IMPORTED_TARGET GLOBAL sqlite3)
        if (TARGET PkgConfig::sqlite3)
          add_library(sqlite3 ALIAS PkgConfig::sqlite3)
        endif ()
      endif ()
    endif ()
  else ()
    message(STATUS "aurora: Cross compiling; forcing bundled sqlite3")
  endif ()

"""
if new not in ecs:
    if old not in ecs:
        raise SystemExit("Aurora sqlite discovery block not found")
    ecs = ecs.replace(old, new, 1)
    extern_cmake.write_text(ecs)

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


# 8) ArkOS' old Mali EGL accepts the SDL window surface for presentation but
# eglQuerySurface(EGL_CONFIG_ID) after SDL2 releases its context can return
# EGL_BAD_SURFACE. Capture SDL's context config while it is current and let the
# presenter use the known panel size rather than re-querying the released surface.
display_cpp = melee / "native/platform/flip/display.cpp"
ds = display_cpp.read_text()
if "EGLint sdlConfigId = 0;" not in ds:
    ds = ds.replace(
        "EGLSurface sdlSurface = EGL_NO_SURFACE; // SDL's window EGL surface; the present worker swaps it.\n",
        "EGLSurface sdlSurface = EGL_NO_SURFACE; // SDL's window EGL surface; the present worker swaps it.\n"
        "EGLint sdlConfigId = 0;\n",
        1
    )

capture_marker = '    if (sdlSurface == EGL_NO_SURFACE) failSdl("SDL did not create a window EGL surface");\n'
capture_block = capture_marker + '''    if (!eglQueryContext(display, reinterpret_cast<EGLContext>(sdlContext), EGL_CONFIG_ID, &sdlConfigId)) {
        std::fprintf(stderr, "[flip-display] cannot query SDL EGL context config (EGL=0x%x); presenter will fall back to producer config\\n", eglGetError());
        sdlConfigId = 0;
    } else {
        std::fprintf(stderr, "[flip-display] SDL EGL config id %d\\n", sdlConfigId);
    }
'''
if "SDL EGL config id %d" not in ds:
    if capture_marker not in ds:
        raise SystemExit("display.cpp: SDL surface marker not found")
    ds = ds.replace(capture_marker, capture_block, 1)

surface_export = 'extern "C" void* MeleeFlipPresentSurface() { return sdlSurface; }\n'
config_export = surface_export + 'extern "C" int MeleeFlipPresentConfigId() { return static_cast<int>(sdlConfigId); }\n'
if "MeleeFlipPresentConfigId" not in ds:
    if surface_export not in ds:
        raise SystemExit("display.cpp: present surface export not found")
    ds = ds.replace(surface_export, config_export, 1)
display_cpp.write_text(ds)

present_cpp = melee / "native/platform/flip/present_worker.cpp"
ps = present_cpp.read_text()
decl_marker = "extern \"C\" void* MeleeFlipPresentSurface(); // SDL's window EGL surface (SDL path); the worker swaps it.\n"
decl_extra = decl_marker + '''extern "C" int MeleeFlipPresentConfigId();
extern "C" void MeleeFlipPanelSize(unsigned* width, unsigned* height);
'''
if "MeleeFlipPresentConfigId" not in ps:
    if decl_marker not in ps:
        raise SystemExit("present_worker.cpp: present surface declaration not found")
    ps = ps.replace(decl_marker, decl_extra, 1)

old_size = '''    EGLint width = 0, height = 0;
    if (!eglQuerySurface(workerDisplay, workerSurface, EGL_WIDTH, &width) ||
        !eglQuerySurface(workerDisplay, workerSurface, EGL_HEIGHT, &height))
        fail("Cannot query presentation surface");
'''
new_size = '''    EGLint width = 0, height = 0;
    if (MeleeFlipUsesSdlDisplay()) {
        unsigned panelW = 0, panelH = 0;
        MeleeFlipPanelSize(&panelW, &panelH);
        width = static_cast<EGLint>(panelW);
        height = static_cast<EGLint>(panelH);
    } else if (!eglQuerySurface(workerDisplay, workerSurface, EGL_WIDTH, &width) ||
               !eglQuerySurface(workerDisplay, workerSurface, EGL_HEIGHT, &height)) {
        fail("Cannot query presentation surface");
    }
'''
if new_size not in ps:
    if old_size not in ps:
        raise SystemExit("present_worker.cpp: surface size query block not found")
    ps = ps.replace(old_size, new_size, 1)

old_config = '''        EGLint configId = 0, count = 0;
        EGLConfig config = nullptr;
        if (!eglQuerySurface(workerDisplay, workerSurface, EGL_CONFIG_ID, &configId))
            fail("Cannot query presentation configuration");
        const EGLint choose[] = {EGL_CONFIG_ID, configId, EGL_NONE};
        if (!eglChooseConfig(workerDisplay, choose, &config, 1, &count) || count != 1)
            fail("Cannot choose presentation configuration");
'''
new_config = '''        EGLint configId = 0, count = 0;
        EGLConfig config = nullptr;
        if (MeleeFlipUsesSdlDisplay()) {
            configId = static_cast<EGLint>(MeleeFlipPresentConfigId());
            if (configId == 0 && !eglQueryContext(workerDisplay, share, EGL_CONFIG_ID, &configId))
                fail("Cannot query presentation context configuration");
        } else if (!eglQuerySurface(workerDisplay, workerSurface, EGL_CONFIG_ID, &configId)) {
            fail("Cannot query presentation configuration");
        }
        if (configId != 0) {
            const EGLint choose[] = {EGL_CONFIG_ID, configId, EGL_NONE};
            if (!eglChooseConfig(workerDisplay, choose, &config, 1, &count) || count != 1)
                fail("Cannot choose presentation configuration");
        }
'''
if new_config not in ps:
    if old_config not in ps:
        raise SystemExit("present_worker.cpp: presentation config query block not found")
    ps = ps.replace(old_config, new_config, 1)
present_cpp.write_text(ps)


# 9) Restore Strikers' v1.2.0 64 KiB staging-copy alignment after the Fast-Aurora
# merge. The upstream fix was added specifically for corrupted goal-wipe geometry
# on older hardware; resolving renderer conflicts in favour of the handheld branch
# otherwise reverts it to 4-byte copy boundaries.
encoding = root / "extern/aurora/lib/gfx/encoding.cpp"
es = encoding.read_text()
old_align = "constexpr uint32_t align_down_copy_offset(uint32_t value) noexcept { return value & ~3u; }\n"
new_align = """// R36S: retain Strikers' upstream old-hardware goal-transition fix.
constexpr uint32_t StagingCopyAlign = 64 * 1024;
constexpr uint32_t align_down_copy_offset(uint32_t value) noexcept {
  return value & ~(StagingCopyAlign - 1);
}
"""
if "constexpr uint32_t StagingCopyAlign = 64 * 1024;" not in es:
    if old_align not in es:
        raise SystemExit("encoding.cpp: staging alignment marker not found")
    es = es.replace(old_align, new_align, 1)

old_sig = """void copy_staging_buffer_range(wgpu::CommandEncoder& cmd, const FramePacket& frame, uint32_t& copied,
                               uint32_t highWater, uint64_t stagingOffset, const wgpu::Buffer& dst) {
"""
new_sig = """void copy_staging_buffer_range(wgpu::CommandEncoder& cmd, const FramePacket& frame, uint32_t& copied,
                               uint32_t highWater, uint64_t stagingOffset, uint64_t poolSize,
                               const wgpu::Buffer& dst) {
"""
if new_sig not in es:
    if old_sig not in es:
        raise SystemExit("encoding.cpp: staging copy signature not found")
    es = es.replace(old_sig, new_sig, 1)

es = es.replace(
    "  const uint32_t copyEnd = AURORA_ALIGN(highWater, 4);\n",
    "  const uint32_t copyEnd = static_cast<uint32_t>(std::min<uint64_t>(\\n"
    "      AURORA_ALIGN(uint64_t{highWater}, StagingCopyAlign), poolSize));\\n",
    1,
)

call_repls = {
    "copy_staging_buffer_range(cmd, frame, frame.copied.verts, highWater.verts, layout.vertex, res.vertexBuffer);":
        "copy_staging_buffer_range(cmd, frame, frame.copied.verts, highWater.verts, layout.vertex, VertexBufferSize, res.vertexBuffer);",
    "copy_staging_buffer_range(cmd, frame, frame.copied.uniforms, highWater.uniforms, layout.uniform, res.uniformBuffer);":
        "copy_staging_buffer_range(cmd, frame, frame.copied.uniforms, highWater.uniforms, layout.uniform, UniformBufferSize, res.uniformBuffer);",
    "copy_staging_buffer_range(cmd, frame, frame.copied.indices, highWater.indices, layout.index, res.indexBuffer);":
        "copy_staging_buffer_range(cmd, frame, frame.copied.indices, highWater.indices, layout.index, IndexBufferSize, res.indexBuffer);",
    "copy_staging_buffer_range(cmd, frame, frame.copied.storage, highWater.storage, layout.storage, res.storageBuffer);":
        "copy_staging_buffer_range(cmd, frame, frame.copied.storage, highWater.storage, layout.storage, StorageBufferSize, res.storageBuffer);",
}
for old_call, new_call in call_repls.items():
    if new_call not in es:
        if old_call not in es:
            raise SystemExit("encoding.cpp: staging copy call not found: " + old_call)
        es = es.replace(old_call, new_call, 1)
encoding.write_text(es)

print("Applied R36S SDL/KMSDRM + Dawn EGL/pbuffer display bridge + 64KiB goal-transition alignment")
