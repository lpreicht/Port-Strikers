#!/usr/bin/env python3
from pathlib import Path
import sys
root = Path(sys.argv[1])
def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if s.count(old) != 1:
        raise SystemExit(f'{rel}: expected one match, got {s.count(old)}: {old[:120]!r}')
    p.write_text(s.replace(old, new, 1))
replace('extern/aurora/lib/window.hpp',
        'bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch);\n',
        'bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch);\n'
        'bool present_gl_texture(uint32_t texture, uint32_t width, uint32_t height);\n')
replace('extern/aurora/lib/window.cpp', '#include <tracy/Tracy.hpp>\n',
        '#include <tracy/Tracy.hpp>\n#ifdef AURORA_R36S_OFFSCREEN\n'
        '#include <EGL/egl.h>\n#include <EGL/eglext.h>\n#include <GLES3/gl3.h>\n'
        '#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n#include <vector>\n#endif\n')
present = Path(__file__).with_name('present_gpu.cpp.in').read_text()
replace('extern/aurora/lib/window.cpp',
        'bool create_renderer() {\n',
        present + '\nbool create_renderer() {\n')
replace('extern/aurora/lib/window.cpp',
        '  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",\n',
        '''  SDL_SetRenderDrawColor(g_renderer, 0, 0, 0, 255);
  SDL_RenderClear(g_renderer);
  SDL_FlushRenderer(g_renderer);
  g_r36sPresentDisplay = eglGetCurrentDisplay();
  g_r36sPresentSurface = eglGetCurrentSurface(EGL_DRAW);
  if (g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentSurface == EGL_NO_SURFACE ||
      !eglQueryContext(g_r36sPresentDisplay, eglGetCurrentContext(), EGL_CONFIG_ID, &g_r36sPresentConfig)) {
    Log.error("R36S V025 cannot capture SDL EGL display/config");
    return false;
  }
  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",
''')
replace('extern/aurora/lib/window.cpp', 'void destroy_window() {\n', '''void destroy_window() {
#ifdef AURORA_R36S_OFFSCREEN
  if (g_r36sPresentContext != EGL_NO_CONTEXT) {
    if (eglGetCurrentContext() == g_r36sPresentContext)
      SDL_GL_MakeCurrent(g_window, nullptr);
    eglDestroyContext(g_r36sPresentDisplay, g_r36sPresentContext);
    g_r36sPresentContext = EGL_NO_CONTEXT;
    g_r36sReadFbo = 0;
  }
#endif
''')
replace('CMakeLists.txt', '        EGL\n        gbm\n', '        EGL\n        gbm\n        GLESv2\n')
replace('extern/aurora/lib/aurora.cpp', '#include <atomic>\n',
        '#include <atomic>\n#include <cstdlib>\n#include <dawn/native/OpenGLBackend.h>\n')
p = root / 'extern/aurora/lib/aurora.cpp'
_aurora = p.read_text()
_legacy_anchor = '#ifdef AURORA_R36S_OFFSCREEN\n    const auto& source = webgpu::present_source();'
if _legacy_anchor in _aurora:
    _legacy_new = '''#ifdef AURORA_R36S_OFFSCREEN
    static bool directPresent = [] {
      const char* value = std::getenv("FOXHOLLOW_PRESENT");
      return !value || std::strcmp(value, "readback") != 0;
    }();
    if (directPresent) {
      const auto& source = webgpu::present_source();
      webgpu::gpu_prof::frame_end(encoder);
      const auto commandBuffer = encoder.Finish();
      g_queue.Submit(1, &commandBuffer);
      webgpu::gpu_prof::after_submit();
      struct Present { uint32_t texture, width, height; bool ok; };
      Present present{dawn::native::opengl::GetGLInteropTexture(source.texture.Get()),
                      source.size.width, source.size.height, false};
      const bool submitted = dawn::native::opengl::RunGLInterop(g_device.Get(), [](void* userdata) {
        auto& p = *static_cast<Present*>(userdata);
        p.ok = window::present_gl_texture(p.texture, p.width, p.height);
      }, &present);
      if (!submitted || !present.ok) {
        Log.warn("R36S V025 direct present failed; switching to V022 readback");
        directPresent = false;
      }
      gfx::after_present();
      for (auto& callback : afterSubmitCallbacks) if (callback) callback();
      gfx::after_submit();
      return;
    }
    const auto& source = webgpu::present_source();'''
    p.write_text(_aurora.replace(_legacy_anchor, _legacy_new, 1))
else:
    # Aurora direct-GLES branch: hook the new end-frame callback before it tries
    # to acquire a WebGPU surface. The R36S remains offscreen in Dawn; GX render
    # passes execute through gles_direct during Submit, then our shared-context
    # KMSDRM presenter blits the completed EFB texture.
    _new_anchor = '''  finish_frame([rmlBindGroup = std::move(rmlBindGroup), rmlOverlay, viewport, imguiDrawData = std::move(imguiDrawData)](
                   wgpu::CommandEncoder& encoder, std::vector<gfx::AfterSubmitCallback> afterSubmitCallbacks) {
'''
    if _new_anchor not in _aurora:
        raise SystemExit("direct-GLES Aurora end-frame lambda anchor not found")
    _new_block = _new_anchor + '''#ifdef AURORA_R36S_OFFSCREEN
    const auto& source = webgpu::present_source();
    webgpu::gpu_prof::frame_end(encoder);
    const wgpu::CommandBufferDescriptor r36sCmdDesc{.label = "R36S direct-GLES command buffer"};
    const auto commandBuffer = encoder.Finish(&r36sCmdDesc);
    gfx::gles_direct::install_frame();
    g_queue.Submit(1, &commandBuffer);
    gfx::gles_direct::uninstall_frame();
    webgpu::gpu_prof::after_submit();

    struct Present { uint32_t texture, width, height; bool ok; };
    Present present{dawn::native::opengl::GetGLInteropTexture(source.texture.Get()),
                    source.size.width, source.size.height, false};
    const bool submitted = dawn::native::opengl::RunGLInterop(g_device.Get(), [](void* userdata) {
      auto& p = *static_cast<Present*>(userdata);
      p.ok = window::present_gl_texture(p.texture, p.width, p.height);
    }, &present);
    if (!submitted || !present.ok) {
      Log.error("R36S V034 direct-GLES present failed");
    }
    gfx::after_present();
    for (auto& callback : afterSubmitCallbacks) if (callback) callback();
    gfx::after_submit();
    return;
#endif
'''
    p.write_text(_aurora.replace(_new_anchor, _new_block, 1))
print('R36S V025 SDL scanout + producer-shared fenced presenter applied')
