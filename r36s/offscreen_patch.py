#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:120]!r}")
    p.write_text(s.replace(old, new, 1))

# window.hpp: software presentation helper.
replace(
    "extern/aurora/lib/window.hpp",
    "bool create_renderer();\n",
    "bool create_renderer();\nbool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch);\n",
)

# window.cpp: R36S SDL renderer presentation state.
p = root / "extern/aurora/lib/window.cpp"
_window = p.read_text()
if "SDL_Window* g_window;\nbool g_windowExternal = false; // g_window belongs to the application, not to Aurora\nSDL_Renderer* g_renderer;\n" in _window:
    _window_state = "SDL_Window* g_window;\nbool g_windowExternal = false; // g_window belongs to the application, not to Aurora\nSDL_Renderer* g_renderer;\n"
    _window_state_new = """SDL_Window* g_window;
bool g_windowExternal = false; // g_window belongs to the application, not to Aurora
SDL_Renderer* g_renderer;
#ifdef AURORA_R36S_OFFSCREEN
SDL_Texture* g_r36sPresentTexture = nullptr;
uint32_t g_r36sPresentWidth = 0;
uint32_t g_r36sPresentHeight = 0;
#endif
"""
else:
    _window_state = "SDL_Window* g_window;\nSDL_Renderer* g_renderer;\n"
    _window_state_new = """SDL_Window* g_window;
SDL_Renderer* g_renderer;
#ifdef AURORA_R36S_OFFSCREEN
SDL_Texture* g_r36sPresentTexture = nullptr;
uint32_t g_r36sPresentWidth = 0;
uint32_t g_r36sPresentHeight = 0;
#endif
"""
if _window_state not in _window:
    raise SystemExit("window presentation state anchor not found")
p.write_text(_window.replace(_window_state, _window_state_new, 1))

# window.cpp: don't reserve the Wayland window for an external GPU context in R36S offscreen mode.
replace(
    "extern/aurora/lib/window.cpp",
    """  TRY(SDL_SetBooleanProperty(props, SDL_PROP_WINDOW_CREATE_EXTERNAL_GRAPHICS_CONTEXT_BOOLEAN, backend != BACKEND_NULL),
      "Failed to set {}: {}", SDL_PROP_WINDOW_CREATE_EXTERNAL_GRAPHICS_CONTEXT_BOOLEAN, SDL_GetError());
""",
    """#ifdef AURORA_R36S_OFFSCREEN
  const bool externalGraphicsContext = false;
#else
  const bool externalGraphicsContext = backend != BACKEND_NULL;
#endif
  TRY(SDL_SetBooleanProperty(props, SDL_PROP_WINDOW_CREATE_EXTERNAL_GRAPHICS_CONTEXT_BOOLEAN, externalGraphicsContext),
      "Failed to set {}: {}", SDL_PROP_WINDOW_CREATE_EXTERNAL_GRAPHICS_CONTEXT_BOOLEAN, SDL_GetError());
""",
)

replace(
    "extern/aurora/lib/window.cpp",
    """void destroy_window() {
""",
    """bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch) {
  if (g_window == nullptr || g_renderer == nullptr || pixels == nullptr || width == 0 || height == 0) {
    return false;
  }

  if (g_r36sPresentTexture == nullptr || g_r36sPresentWidth != width || g_r36sPresentHeight != height) {
    if (g_r36sPresentTexture != nullptr) {
      SDL_DestroyTexture(g_r36sPresentTexture);
      g_r36sPresentTexture = nullptr;
    }
    g_r36sPresentTexture = SDL_CreateTexture(g_renderer, SDL_PIXELFORMAT_RGBA32, SDL_TEXTUREACCESS_STREAMING,
                                             static_cast<int>(width), static_cast<int>(height));
    if (g_r36sPresentTexture == nullptr) {
      Log.error("R36S SDL_CreateTexture failed: {}", SDL_GetError());
      return false;
    }
    SDL_SetTextureScaleMode(g_r36sPresentTexture, SDL_SCALEMODE_LINEAR);
    g_r36sPresentWidth = width;
    g_r36sPresentHeight = height;
    Log.info("R36S present texture created: {}x{} renderer={}", width, height,
             SDL_GetRendererName(g_renderer) ? SDL_GetRendererName(g_renderer) : "?");
  }

  if (!SDL_UpdateTexture(g_r36sPresentTexture, nullptr, pixels, static_cast<int>(pitch))) {
    Log.error("R36S SDL_UpdateTexture failed: {}", SDL_GetError());
    return false;
  }
  if (!SDL_SetRenderDrawColor(g_renderer, 0, 0, 0, 255) || !SDL_RenderClear(g_renderer)) {
    Log.error("R36S SDL_RenderClear failed: {}", SDL_GetError());
    return false;
  }
  if (!SDL_RenderTexture(g_renderer, g_r36sPresentTexture, nullptr, nullptr)) {
    Log.error("R36S SDL_RenderTexture failed: {}", SDL_GetError());
    return false;
  }
  if (!SDL_RenderPresent(g_renderer)) {
    Log.error("R36S SDL_RenderPresent failed: {}", SDL_GetError());
    return false;
  }
  return true;
}

void destroy_window() {
#ifdef AURORA_R36S_OFFSCREEN
  if (g_r36sPresentTexture != nullptr) {
    SDL_DestroyTexture(g_r36sPresentTexture);
    g_r36sPresentTexture = nullptr;
    g_r36sPresentWidth = 0;
    g_r36sPresentHeight = 0;
  }
#endif
""",
)

# window.cpp: the offscreen OpenGLES path still needs an SDL renderer for the CPU-readback image.
# Force SDL's software renderer so presentation does not depend on the old Mali EGL/Wayland stack.
replace(
    "extern/aurora/lib/window.cpp",
    """bool create_renderer() {
  if (g_window == nullptr) {
    return false;
  }
  const auto props = SDL_CreateProperties();
  TRY(SDL_SetPointerProperty(props, SDL_PROP_RENDERER_CREATE_WINDOW_POINTER, g_window), "Failed to set {}: {}",
      SDL_PROP_RENDERER_CREATE_WINDOW_POINTER, SDL_GetError());
  TRY(SDL_SetNumberProperty(props, SDL_PROP_RENDERER_CREATE_PRESENT_VSYNC_NUMBER, SDL_RENDERER_VSYNC_ADAPTIVE),
      "Failed to set {}: {}", SDL_PROP_RENDERER_CREATE_PRESENT_VSYNC_NUMBER, SDL_GetError());
  g_renderer = SDL_CreateRendererWithProperties(props);
  if (g_renderer == nullptr) {
    Log.error("Failed to create renderer: {}", SDL_GetError());
    return false;
  }
  return true;
}
""",
    """bool create_renderer() {
  if (g_window == nullptr) {
    Log.error("R36S create_renderer called without a window");
    return false;
  }
#ifdef AURORA_R36S_OFFSCREEN
  SDL_ClearError();
  // On ArkOS the shared SDL3 shim delegates to the CFW's patched SDL2 KMSDRM backend.
  // Let that backend choose its native GLES renderer instead of forcing SDL's software path.
  g_renderer = SDL_CreateRenderer(g_window, nullptr);
  if (g_renderer == nullptr) {
    Log.error("R36S SDL2/KMSDRM SDL_CreateRenderer failed: {}", SDL_GetError());
    return false;
  }
  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",
           SDL_GetRendererName(g_renderer) ? SDL_GetRendererName(g_renderer) : "?");
  return true;
#else
  const auto props = SDL_CreateProperties();
  TRY(SDL_SetPointerProperty(props, SDL_PROP_RENDERER_CREATE_WINDOW_POINTER, g_window), "Failed to set {}: {}",
      SDL_PROP_RENDERER_CREATE_WINDOW_POINTER, SDL_GetError());
  TRY(SDL_SetNumberProperty(props, SDL_PROP_RENDERER_CREATE_PRESENT_VSYNC_NUMBER, SDL_RENDERER_VSYNC_ADAPTIVE),
      "Failed to set {}: {}", SDL_PROP_RENDERER_CREATE_PRESENT_VSYNC_NUMBER, SDL_GetError());
  g_renderer = SDL_CreateRendererWithProperties(props);
  if (g_renderer == nullptr) {
    Log.error("Failed to create renderer: {}", SDL_GetError());
    return false;
  }
  return true;
#endif
}
""",
)

# gpu.cpp: no WebGPU window surface on R36S. Request a surfaceless GLES adapter.
replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  if (!create_surface()) {
    return false;
  }
""",
    """#ifndef AURORA_R36S_OFFSCREEN
  if (!create_surface()) {
    return false;
  }
#endif
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """        .compatibleSurface = g_surface,
""",
    """#ifdef AURORA_R36S_OFFSCREEN
        .compatibleSurface = nullptr,
#else
        .compatibleSurface = g_surface,
#endif
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  const wgpu::Status status = g_surface.GetCapabilities(g_adapter, &g_surfaceCapabilities);
""",
    """#ifdef AURORA_R36S_OFFSCREEN
  const auto size = window::get_window_size();
  g_vsyncEnabled.store(g_config.vsync, std::memory_order_release);
  g_graphicsConfig = GraphicsConfig{
      .surfaceConfiguration =
          wgpu::SurfaceConfiguration{
              .format = wgpu::TextureFormat::RGBA8Unorm,
              .usage = wgpu::TextureUsage::RenderAttachment,
              .width = size.native_fb_width,
              .height = size.native_fb_height,
              .presentMode = wgpu::PresentMode::Fifo,
          },
      .depthFormat = wgpu::TextureFormat::Depth32Float,
      .msaaSamples = g_config.msaa,
      .textureAnisotropy = g_config.maxTextureAnisotropy,
  };
  Log.info("R36S offscreen mode: adapter {} backend {} framebuffer {}x{}", adapterName,
           magic_enum::enum_name(g_backendType), size.fb_width, size.fb_height);
  create_copy_pipeline();
  create_resample_pipeline();
  gpu_prof::initialize();
  resize_swapchain(size.fb_width, size.fb_height, size.native_fb_width, size.native_fb_height, true);
  g_initialized = true;
  return true;
#else
  const wgpu::Status status = g_surface.GetCapabilities(g_adapter, &g_surfaceCapabilities);
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  g_initialized = true;
  return true;
}

void shutdown() {
""",
    """  g_initialized = true;
  return true;
#endif
}

void shutdown() {
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  if (!g_surface || !g_device || width == 0 || height == 0 || nativeHeight == 0 || nativeWidth == 0) {
    return;
  }
""",
    """#ifdef AURORA_R36S_OFFSCREEN
  if (!g_device || width == 0 || height == 0 || nativeHeight == 0 || nativeWidth == 0) {
    return;
  }
#else
  if (!g_surface || !g_device || width == 0 || height == 0 || nativeHeight == 0 || nativeWidth == 0) {
    return;
  }
#endif
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """  auto surfaceConfiguration = g_graphicsConfig.surfaceConfiguration;
  surfaceConfiguration.device = g_device;
  {
    window::SurfaceLock surfaceLock;
    g_surface.Configure(&surfaceConfiguration);
  }
""",
    """#ifndef AURORA_R36S_OFFSCREEN
  auto surfaceConfiguration = g_graphicsConfig.surfaceConfiguration;
  surfaceConfiguration.device = g_device;
  {
    window::SurfaceLock surfaceLock;
    g_surface.Configure(&surfaceConfiguration);
  }
#endif
""",
)

replace(
    "extern/aurora/lib/webgpu/gpu.cpp",
    """bool refresh_surface(bool recreate) {
  gfx::gpu_synchronize();
  if (!g_instance || !g_device) {
    return false;
  }
""",
    """bool refresh_surface(bool recreate) {
  gfx::gpu_synchronize();
  if (!g_instance || !g_device) {
    return false;
  }
#ifdef AURORA_R36S_OFFSCREEN
  const auto size = window::get_window_size();
  resize_swapchain_internal(size.fb_width, size.fb_height, size.native_fb_width, size.native_fb_height, true);
  return true;
#endif
""",
)

# aurora.cpp: on R36S create the SDL2/KMSDRM renderer before Dawn so the working
# firmware EGLDisplay is current and can be reused by Dawn instead of opening card0 twice.
replace(
    "extern/aurora/lib/aurora.cpp",
    """  if (selectedBackend != BACKEND_AUTO && window::create_window(selectedBackend)) {
    if (webgpu::initialize(selectedBackend, config.allowCpuAdapter)) {
      windowCreated = true;
    } else {
      window::destroy_window();
    }
  }
""",
    """  if (selectedBackend != BACKEND_AUTO && window::create_window(selectedBackend)) {
#ifdef AURORA_R36S_OFFSCREEN
    if (!window::create_renderer()) {
      window::destroy_window();
    } else
#endif
    if (webgpu::initialize(selectedBackend, config.allowCpuAdapter)) {
      windowCreated = true;
    } else {
      window::destroy_window();
    }
  }
""",
)

replace(
    "extern/aurora/lib/aurora.cpp",
    """      if (!window::create_window(selectedBackend)) {
        continue;
      }
      if (webgpu::initialize(selectedBackend, config.allowCpuAdapter)) {
        windowCreated = true;
        break;
      } else {
        window::destroy_window();
      }
""",
    """      if (!window::create_window(selectedBackend)) {
        continue;
      }
#ifdef AURORA_R36S_OFFSCREEN
      if (!window::create_renderer()) {
        window::destroy_window();
        continue;
      }
#endif
      if (webgpu::initialize(selectedBackend, config.allowCpuAdapter)) {
        windowCreated = true;
        break;
      } else {
        window::destroy_window();
      }
""",
)

# aurora.cpp: initialize the SDL renderer even though the selected GPU backend is OpenGLES.
replace(
    "extern/aurora/lib/aurora.cpp",
    """  AURORA_ASSERT(windowCreated, "Error creating window: {}", SDL_GetError());

  // Initialize SDL_Renderer for ImGui when we can't use a Dawn backend
  if (webgpu::g_backendType == wgpu::BackendType::Null) {
    AURORA_ASSERT(window::create_renderer(), "Failed to initialize SDL renderer: {}", SDL_GetError());
  }
""",
    """  AURORA_ASSERT(windowCreated, "Error creating window: {}", SDL_GetError());

#ifndef AURORA_R36S_OFFSCREEN
  // Initialize SDL_Renderer for ImGui when we can't use a Dawn backend.
  // R36S creates its KMSDRM renderer before Dawn so Dawn can reuse SDL's EGLDisplay.
  if (webgpu::g_backendType == wgpu::BackendType::Null) {
    AURORA_ASSERT(window::create_renderer(), "Failed to initialize SDL renderer: {}", SDL_GetError());
  }
#endif
""",
)

# aurora.cpp: asynchronous GPU readback and software Wayland blit.
replace(
    "extern/aurora/lib/aurora.cpp",
    """#include <magic_enum.hpp>

#include "system_info.hpp"
""",
    """#include <magic_enum.hpp>

#ifdef AURORA_R36S_OFFSCREEN
#include <atomic>
#include <cstring>
#include <mutex>
#include <vector>
#endif

#include "system_info.hpp"
""",
)

# Aurora logger syntax changed in the ARM performance fork.
p = root / "extern/aurora/lib/aurora.cpp"
_aurora = p.read_text()
if 'Module Log("aurora");\n\n#ifdef AURORA_ENABLE_GX' in _aurora:
    _logger_anchor = 'Module Log("aurora");'
    _logger_replacement = 'Module Log("aurora");'
elif 'constexpr Module Log{"aurora"};\n\n#ifdef AURORA_ENABLE_GX' in _aurora:
    _logger_anchor = 'constexpr Module Log{"aurora"};'
    _logger_replacement = 'constexpr Module Log{"aurora"};'
else:
    raise SystemExit("aurora.cpp logger anchor not found")

replace(
    "extern/aurora/lib/aurora.cpp",
    _logger_anchor + """\n\n#ifdef AURORA_ENABLE_GX
""",
    _logger_replacement + """\n\n#ifdef AURORA_R36S_OFFSCREEN
std::mutex g_r36sFrameMutex;
std::vector<uint8_t> g_r36sFrame;
uint32_t g_r36sFrameWidth = 0;
uint32_t g_r36sFrameHeight = 0;
std::atomic_bool g_r36sFrameReady = false;
std::atomic_bool g_r36sReadbackPending = false;

void present_r36s_frame() {
  if (!g_r36sFrameReady.exchange(false, std::memory_order_acq_rel)) {
    return;
  }
  std::vector<uint8_t> frame;
  uint32_t width = 0;
  uint32_t height = 0;
  {
    std::lock_guard lock{g_r36sFrameMutex};
    frame.swap(g_r36sFrame);
    width = g_r36sFrameWidth;
    height = g_r36sFrameHeight;
  }
  if (!frame.empty() && !window::present_software_frame(frame.data(), width, height, width * 4)) {
    Log.warn("R36S software present failed: {}", SDL_GetError());
  }
}
#endif

#ifdef AURORA_ENABLE_GX
""",
)

replace(
    "extern/aurora/lib/aurora.cpp",
    """bool begin_frame() noexcept {
  ZoneScoped;
#ifdef AURORA_ENABLE_GX
  {
    if (!window::is_presentable()) {
      webgpu::release_surface();
      return false;
    }
    if (window::is_paused()) {
      return false;
    }
    if (!g_surface) {
      webgpu::refresh_surface(true);
      if (!g_surface) {
        return false;
      }
    }
  }
""",
    """bool begin_frame() noexcept {
  ZoneScoped;
#ifdef AURORA_R36S_OFFSCREEN
  present_r36s_frame();
#endif
#ifdef AURORA_ENABLE_GX
#ifdef AURORA_R36S_OFFSCREEN
  if (window::is_paused()) {
    return false;
  }
#else
  {
    if (!window::is_presentable()) {
      webgpu::release_surface();
      return false;
    }
    if (window::is_paused()) {
      return false;
    }
    if (!g_surface) {
      webgpu::refresh_surface(true);
      if (!g_surface) {
        return false;
      }
    }
  }
#endif
""",
)

replace(
    "extern/aurora/lib/aurora.cpp",
    """                     wgpu::CommandEncoder& encoder, std::vector<gfx::AfterSubmitCallback> afterSubmitCallbacks) {
    wgpu::Texture currentTexture;
""",
    """                     wgpu::CommandEncoder& encoder, std::vector<gfx::AfterSubmitCallback> afterSubmitCallbacks) {
#ifdef AURORA_R36S_OFFSCREEN
    const auto& source = webgpu::present_source();
    const uint32_t width = source.size.width;
    const uint32_t height = source.size.height;
    const uint32_t bytesPerRow = ((width * 4u) + 255u) & ~255u;
    const uint64_t byteSize = static_cast<uint64_t>(bytesPerRow) * height;
    const bool doReadback = !g_r36sReadbackPending.exchange(true, std::memory_order_acq_rel);
    wgpu::Buffer readbackBuffer;

    if (doReadback) {
      const wgpu::BufferDescriptor readbackDesc{
          .label = "R36S offscreen readback",
          .usage = wgpu::BufferUsage::CopyDst | wgpu::BufferUsage::MapRead,
          .size = byteSize,
          .mappedAtCreation = false,
      };
      readbackBuffer = g_device.CreateBuffer(&readbackDesc);
      if (readbackBuffer) {
        const wgpu::TexelCopyTextureInfo src{
            .texture = source.texture,
        };
        const wgpu::TexelCopyBufferInfo dst{
            .layout =
                wgpu::TexelCopyBufferLayout{
                    .offset = 0,
                    .bytesPerRow = bytesPerRow,
                    .rowsPerImage = height,
                },
            .buffer = readbackBuffer,
        };
        const wgpu::Extent3D extent{
            .width = width,
            .height = height,
            .depthOrArrayLayers = 1,
        };
        encoder.CopyTextureToBuffer(&src, &dst, &extent);
      } else {
        g_r36sReadbackPending.store(false, std::memory_order_release);
      }
    }

    webgpu::gpu_prof::frame_end(encoder);
    const wgpu::CommandBufferDescriptor r36sCmdBufDescriptor{.label = "R36S offscreen redraw command buffer"};
    const auto commandBuffer = encoder.Finish(&r36sCmdBufDescriptor);
    g_queue.Submit(1, &commandBuffer);
    webgpu::gpu_prof::after_submit();

    if (doReadback && readbackBuffer) {
      readbackBuffer.MapAsync(
          wgpu::MapMode::Read, 0, byteSize, wgpu::CallbackMode::AllowSpontaneous,
          [readbackBuffer, width, height, bytesPerRow, byteSize](wgpu::MapAsyncStatus status,
                                                                 wgpu::StringView message) {
            if (status == wgpu::MapAsyncStatus::Success) {
              const auto* srcPixels =
                  static_cast<const uint8_t*>(readbackBuffer.GetConstMappedRange(0, byteSize));
              if (srcPixels != nullptr) {
                std::vector<uint8_t> tight(static_cast<size_t>(width) * height * 4u);
                for (uint32_t y = 0; y < height; ++y) {
                  std::memcpy(tight.data() + static_cast<size_t>(y) * width * 4u,
                              srcPixels + static_cast<size_t>(y) * bytesPerRow,
                              static_cast<size_t>(width) * 4u);
                }
                {
                  std::lock_guard lock{g_r36sFrameMutex};
                  g_r36sFrame = std::move(tight);
                  g_r36sFrameWidth = width;
                  g_r36sFrameHeight = height;
                }
                g_r36sFrameReady.store(true, std::memory_order_release);
              }
              readbackBuffer.Unmap();
            } else {
              Log.warn("R36S readback map failed: {} {}", magic_enum::enum_name(status), message);
            }
            g_r36sReadbackPending.store(false, std::memory_order_release);
          });
    }

    gfx::after_present();
    for (auto& callback : afterSubmitCallbacks) {
      if (callback) {
        callback();
      }
    }
    gfx::after_submit();
    return;
#endif

    wgpu::Texture currentTexture;
""",
)

print("R36S offscreen Aurora patch applied")
