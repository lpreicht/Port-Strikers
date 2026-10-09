#!/usr/bin/env python3
"""RC4: measure actual R36S renderer/presenter wall-time stages.

No rendering, synchronization, buffering or resource code is changed.
The measurements are enabled ONLY by R36S_PRESENT_PROFILE=1.
This separates game/GX finishing, Dawn submit and SDL/EGL display costs.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()

def replace_exact(p, old, new, name):
    source=p.read_text()
    n=source.count(old)
    if n!=1:
        raise SystemExit(f"RC4 {name}: expected exactly one anchor, got {n}")
    p.write_text(source.replace(old,new,1))

aurora=root/"extern/aurora/lib/aurora.cpp"
replace_exact(aurora,
    'void end_frame() noexcept {\n  ZoneScoped;\n',
    'void end_frame() noexcept {\n  ZoneScoped;\n'
    '  // RC4: sample the full native end-frame path, including GX drain/finish.\n'
    '  const uint64_t r36sRc4FrameStartNs = SDL_GetTicksNS();\n',
    "frame entry")
replace_exact(aurora,
    'viewport, imguiDrawData = std::move(imguiDrawData)](\n',
    'viewport, imguiDrawData = std::move(imguiDrawData), r36sRc4FrameStartNs](\n',
    "render-callback capture")
replace_exact(aurora,
    """#ifdef AURORA_R36S_OFFSCREEN
    const auto& source = webgpu::present_source();
""",
    """#ifdef AURORA_R36S_OFFSCREEN
    const uint64_t r36sRc4EnteredNs = SDL_GetTicksNS();
    const auto& source = webgpu::present_source();
""", "direct-path start")
replace_exact(aurora,
    """    const auto commandBuffer = encoder.Finish(&r36sCmdDesc);
    gfx::gles_direct::install_frame();
""",
    """    const auto commandBuffer = encoder.Finish(&r36sCmdDesc);
    const uint64_t r36sRc4EncodeDoneNs = SDL_GetTicksNS();
    gfx::gles_direct::install_frame();
""", "encoder finish")
replace_exact(aurora,
    """    gfx::gles_direct::uninstall_frame();
    webgpu::gpu_prof::after_submit();
""",
    """    gfx::gles_direct::uninstall_frame();
    const uint64_t r36sRc4SubmitDoneNs = SDL_GetTicksNS();
    webgpu::gpu_prof::after_submit();
""", "submit phase")
replace_exact(aurora,
    """    if (!submitted || !present.ok) {
      Log.error("R36S V034 direct-GLES present failed");
    }
""",
    """    const uint64_t r36sRc4PresentDoneNs = SDL_GetTicksNS();
    if (!submitted || !present.ok) {
      Log.error("R36S V034 direct-GLES present failed");
    }
""", "present phase")
replace_exact(aurora,
    """    gfx::after_submit();
    return;
#endif
""",
    """    gfx::after_submit();
    if (const char* enabled = std::getenv("R36S_PRESENT_PROFILE"); enabled && enabled[0] == '1') {
      const uint64_t r36sRc4FinishedNs = SDL_GetTicksNS();
      static uint64_t r36sRc4LastReportNs = 0;
      static uint32_t r36sRc4N = 0;
      static double r36sRc4Pre = 0, r36sRc4Encode = 0, r36sRc4Submit = 0;
      static double r36sRc4Present = 0, r36sRc4After = 0;
      if (r36sRc4LastReportNs == 0) r36sRc4LastReportNs = r36sRc4FinishedNs;
      r36sRc4Pre += (r36sRc4EnteredNs - r36sRc4FrameStartNs) / 1e6;
      r36sRc4Encode += (r36sRc4EncodeDoneNs - r36sRc4EnteredNs) / 1e6;
      r36sRc4Submit += (r36sRc4SubmitDoneNs - r36sRc4EncodeDoneNs) / 1e6;
      r36sRc4Present += (r36sRc4PresentDoneNs - r36sRc4SubmitDoneNs) / 1e6;
      r36sRc4After += (r36sRc4FinishedNs - r36sRc4PresentDoneNs) / 1e6;
      ++r36sRc4N;
      if (r36sRc4FinishedNs - r36sRc4LastReportNs >= 3000000000ull) {
        std::fprintf(stderr, "[r36s-rc4-endframe] n=%u pre_gx=%.3f encode=%.3f submit=%.3f presenter=%.3f after=%.3f ms/frame\\n",
                     r36sRc4N, r36sRc4Pre/r36sRc4N, r36sRc4Encode/r36sRc4N,
                     r36sRc4Submit/r36sRc4N, r36sRc4Present/r36sRc4N, r36sRc4After/r36sRc4N);
        std::fflush(stderr);
        r36sRc4LastReportNs = r36sRc4FinishedNs;
        r36sRc4N = 0;
        r36sRc4Pre = r36sRc4Encode = r36sRc4Submit = r36sRc4Present = r36sRc4After = 0;
      }
    }
    return;
#endif
""", "phase report")

window=root/"extern/aurora/lib/window.cpp"
replace_exact(window,
    '#include <SDL3/SDL_stdinc.h>\n',
    '#include <SDL3/SDL_stdinc.h>\n#include <SDL3/SDL_timer.h>\n',
    "SDL timing header")
replace_exact(window,
    """bool present_gl_texture(uint32_t texture, uint32_t width, uint32_t height) {
  if (!texture || !width || !height || !r36s_init_present_context()) return false;
""",
    """bool present_gl_texture(uint32_t texture, uint32_t width, uint32_t height) {
  if (!texture || !width || !height || !r36s_init_present_context()) return false;
  // RC4: timing probes only; preserve exact GL/EGL/SDL ordering.
  const char* r36sRc4Setting = std::getenv("R36S_PRESENT_PROFILE");
  const bool r36sRc4Profile = r36sRc4Setting != nullptr && r36sRc4Setting[0] == '1';
  const uint64_t r36sRc4StartNs = SDL_GetTicksNS();
""", "presenter entry")
replace_exact(window,
    """  glFlush();
  if (!SDL_GL_MakeCurrent(g_window, static_cast<SDL_GLContext>(g_r36sPresentContext))) {
""",
    """  glFlush();
  const uint64_t r36sRc4ProducerFenceNs = SDL_GetTicksNS();
  if (!SDL_GL_MakeCurrent(g_window, static_cast<SDL_GLContext>(g_r36sPresentContext))) {
""", "fence+flush")
replace_exact(window,
    """  glWaitSync(ready, 0, GL_TIMEOUT_IGNORED);
  glDeleteSync(ready);
""",
    """  glWaitSync(ready, 0, GL_TIMEOUT_IGNORED);
  glDeleteSync(ready);
  const uint64_t r36sRc4ConsumerReadyNs = SDL_GetTicksNS();
""", "context switch/wait")
replace_exact(window,
    """  if (!consumed) {
    Log.error("R36S V025 consumer fence unavailable");
    std::abort();
  }
  if (ok && !SDL_GL_SwapWindow(g_window)) {
""",
    """  if (!consumed) {
    Log.error("R36S V025 consumer fence unavailable");
    std::abort();
  }
  const uint64_t r36sRc4BlitNs = SDL_GetTicksNS();
  if (ok && !SDL_GL_SwapWindow(g_window)) {
""", "blit+verify+fence")
replace_exact(window,
    """    ok = false;
  }
  restore();
  glWaitSync(consumed, 0, GL_TIMEOUT_IGNORED);
""",
    """    ok = false;
  }
  const uint64_t r36sRc4SwapNs = SDL_GetTicksNS();
  restore();
  glWaitSync(consumed, 0, GL_TIMEOUT_IGNORED);
""", "SDL swap")
replace_exact(window,
    """  glDeleteSync(consumed);
  glFlush();
  return ok;
}
#endif
""",
    """  glDeleteSync(consumed);
  glFlush();
  if (r36sRc4Profile) {
    const uint64_t r36sRc4DoneNs = SDL_GetTicksNS();
    static uint32_t r36sRc4N = 0;
    static uint64_t r36sRc4ReportNs = 0;
    static double r36sRc4ProducerFence = 0, r36sRc4ConsumerSwitch = 0;
    static double r36sRc4Blit = 0, r36sRc4Swap = 0, r36sRc4Restore = 0;
    if (r36sRc4ReportNs == 0) r36sRc4ReportNs = r36sRc4DoneNs;
    r36sRc4ProducerFence += (r36sRc4ProducerFenceNs - r36sRc4StartNs) / 1e6;
    r36sRc4ConsumerSwitch += (r36sRc4ConsumerReadyNs - r36sRc4ProducerFenceNs) / 1e6;
    r36sRc4Blit += (r36sRc4BlitNs - r36sRc4ConsumerReadyNs) / 1e6;
    r36sRc4Swap += (r36sRc4SwapNs - r36sRc4BlitNs) / 1e6;
    r36sRc4Restore += (r36sRc4DoneNs - r36sRc4SwapNs) / 1e6;
    ++r36sRc4N;
    if (r36sRc4DoneNs - r36sRc4ReportNs >= 3000000000ull) {
      std::fprintf(stderr, "[r36s-rc4-present] n=%u fence=%.3f context_wait=%.3f blit=%.3f swap=%.3f restore=%.3f ms/frame\\n",
                   r36sRc4N, r36sRc4ProducerFence/r36sRc4N,
                   r36sRc4ConsumerSwitch/r36sRc4N, r36sRc4Blit/r36sRc4N,
                   r36sRc4Swap/r36sRc4N, r36sRc4Restore/r36sRc4N);
      std::fflush(stderr);
      r36sRc4ReportNs = r36sRc4DoneNs;
      r36sRc4N = 0;
      r36sRc4ProducerFence = r36sRc4ConsumerSwitch = r36sRc4Blit =
          r36sRc4Swap = r36sRc4Restore = 0;
    }
  }
  return ok;
}
#endif
""", "presenter report")

print("PASS RC4: endframe + producer/shared-KMSDRM presenter profile added without changing GL calls")
