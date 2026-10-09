#!/usr/bin/env python3
"""RC4 instrumentation contract (not a hardware speed claim)."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
aurora=(root/"extern/aurora/lib/aurora.cpp").read_text()
window=(root/"extern/aurora/lib/window.cpp").read_text()
assert "r36sRc4FrameStartNs = SDL_GetTicksNS()" in aurora
assert "r36sRc4EnteredNs = SDL_GetTicksNS()" in aurora
assert "r36sRc4EncodeDoneNs = SDL_GetTicksNS()" in aurora
assert "r36sRc4SubmitDoneNs = SDL_GetTicksNS()" in aurora
assert "r36sRc4PresentDoneNs = SDL_GetTicksNS()" in aurora
assert "[r36s-rc4-endframe]" in aurora
assert "[r36s-rc4-present]" in window
assert 'std::getenv("R36S_PRESENT_PROFILE")' in aurora
assert 'std::getenv("R36S_PRESENT_PROFILE")' in window
# Golden submit and synchronization operations must be left in place.
for token in ["g_queue.Submit(1, &commandBuffer);",
              "dawn::native::opengl::RunGLInterop(g_device.Get()",
              "gfx::gles_direct::install_frame();",
              "gfx::gles_direct::uninstall_frame();"]:
    assert token in aurora, token
for token in ["glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0)",
              "glWaitSync(ready, 0, GL_TIMEOUT_IGNORED)",
              "glWaitSync(consumed, 0, GL_TIMEOUT_IGNORED)",
              "glBlitFramebuffer(0, 0, width, height",
              "SDL_GL_SwapWindow(g_window)",
              "restore();"]:
    assert token in window, token
assert "[R36S V025 timing]" in (root/"port/src/vi_shim.c").read_text()
print("PASS RC4: full-frame and KMSDRM presenter phase counters, critical GL operations intact")
