#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:160]!r}")
    p.write_text(s.replace(old, new, 1))

# Give Aurora direct access to the same GBM/EGL path that Weston successfully uses on ArkOS.
replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """#ifdef WEBGPU_DAWN
#include "../dawn/TracyPlatform.hpp"
#include <dawn/native/DawnNative.h>
#endif
""",
    """#ifdef WEBGPU_DAWN
#include "../dawn/TracyPlatform.hpp"
#include <dawn/native/DawnNative.h>
#ifdef AURORA_R36S_OFFSCREEN
#include <dawn/native/OpenGLBackend.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <fcntl.h>
#include <gbm.h>
#include <unistd.h>
#endif
#endif
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """static Module Log("aurora::gpu");

wgpu::Device g_device;
""",
    """static Module Log("aurora::gpu");

#ifdef AURORA_R36S_OFFSCREEN
#ifndef EGL_PLATFORM_GBM_KHR
#define EGL_PLATFORM_GBM_KHR 0x31D7
#endif

static int g_r36sDrmFd = -1;
static gbm_device* g_r36sGbmDevice = nullptr;
static EGLDisplay g_r36sEglDisplay = EGL_NO_DISPLAY;

static bool initialize_r36s_gbm_egl_display() {
  if (g_r36sEglDisplay != EGL_NO_DISPLAY) {
    return true;
  }

  g_r36sDrmFd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
  if (g_r36sDrmFd < 0) {
    Log.error("R36S GBM: failed to open /dev/dri/card0");
    return false;
  }

  g_r36sGbmDevice = gbm_create_device(g_r36sDrmFd);
  if (g_r36sGbmDevice == nullptr) {
    Log.error("R36S GBM: gbm_create_device failed");
    close(g_r36sDrmFd);
    g_r36sDrmFd = -1;
    return false;
  }

  auto getPlatformDisplay =
      reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(eglGetProcAddress("eglGetPlatformDisplayEXT"));
  if (getPlatformDisplay != nullptr) {
    g_r36sEglDisplay = getPlatformDisplay(EGL_PLATFORM_GBM_KHR, g_r36sGbmDevice, nullptr);
  }
  if (g_r36sEglDisplay == EGL_NO_DISPLAY) {
    g_r36sEglDisplay = eglGetDisplay(reinterpret_cast<EGLNativeDisplayType>(g_r36sGbmDevice));
  }
  if (g_r36sEglDisplay == EGL_NO_DISPLAY) {
    Log.error("R36S GBM: could not create EGL display");
    gbm_device_destroy(g_r36sGbmDevice);
    g_r36sGbmDevice = nullptr;
    close(g_r36sDrmFd);
    g_r36sDrmFd = -1;
    return false;
  }

  EGLint major = 0;
  EGLint minor = 0;
  if (eglInitialize(g_r36sEglDisplay, &major, &minor) != EGL_TRUE) {
    Log.error("R36S GBM: eglInitialize failed, EGL error 0x{:x}", static_cast<unsigned>(eglGetError()));
    g_r36sEglDisplay = EGL_NO_DISPLAY;
    gbm_device_destroy(g_r36sGbmDevice);
    g_r36sGbmDevice = nullptr;
    close(g_r36sDrmFd);
    g_r36sDrmFd = -1;
    return false;
  }

  const char* vendor = eglQueryString(g_r36sEglDisplay, EGL_VENDOR);
  const char* version = eglQueryString(g_r36sEglDisplay, EGL_VERSION);
  const char* apis = eglQueryString(g_r36sEglDisplay, EGL_CLIENT_APIS);
  const char* extensions = eglQueryString(g_r36sEglDisplay, EGL_EXTENSIONS);
  Log.info("R36S GBM/EGL initialized: {}.{} vendor={} version={} APIs={}", major, minor,
           vendor ? vendor : "?", version ? version : "?", apis ? apis : "?");
  Log.info("R36S EGL extensions: {}", extensions ? extensions : "(none)");
  return true;
}
#endif

wgpu::Device g_device;
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """    const wgpu::RequestAdapterOptions options{
""",
    """    wgpu::RequestAdapterOptions options{
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """    };
    Log.info("Requesting adapter\\n  Feature level: {}\\n  Power preference: {}\\n  Backend: {}\\n  Compatible surface: {}",
""",
    """    };
#ifdef AURORA_R36S_OFFSCREEN
    dawn::native::opengl::RequestAdapterOptionsGetGLProc r36sGlOptions;
    if (backend == wgpu::BackendType::OpenGLES) {
      if (!initialize_r36s_gbm_egl_display()) {
        Log.error("R36S GBM/EGL initialization failed before Dawn adapter request");
        return false;
      }
      r36sGlOptions.getProc =
          reinterpret_cast<dawn::native::opengl::EGLGetProcProc>(&eglGetProcAddress);
      r36sGlOptions.display =
          reinterpret_cast<dawn::native::opengl::EGLDisplay>(g_r36sEglDisplay);
      r36sGlOptions.nextInChain = options.nextInChain;
      options.nextInChain = &r36sGlOptions;
      Log.info("R36S: passing pre-initialized GBM EGLDisplay directly to Dawn OpenGLES");
    }
#endif
    Log.info("Requesting adapter\\n  Feature level: {}\\n  Power preference: {}\\n  Backend: {}\\n  Compatible surface: {}",
""",
)

# Resolve the new direct EGL/GBM calls against ArkOS' system graphics stack.
replace(
    "CMakeLists.txt",
    """target_link_libraries(foxhollow PRIVATE
        ZLIB::ZLIB
""",
    """target_link_libraries(foxhollow PRIVATE
        ZLIB::ZLIB
        EGL
        gbm
""",
)

print("R36S direct GBM/EGL Dawn adapter patch applied")
