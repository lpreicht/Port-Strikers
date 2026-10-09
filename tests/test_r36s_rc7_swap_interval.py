#!/usr/bin/env python3
"""RC7 build-time contract. A working screen and actual FPS need R36S tests."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
w=(root/"extern/aurora/lib/window.cpp").read_text()
a=(root/"extern/aurora/lib/aurora.cpp").read_text()
assert 'std::getenv("R36S_SWAP_INTERVAL")' in w
assert "r36sSwapSetting[0] == '0' ? 0 : 1" in w
assert "SDL_GL_SetSwapInterval(r36sSwapInterval)" in w
assert "R36S RC7 SDL GLES swap interval request=" in w
assert "SDL_GL_SetSwapInterval(1)" not in w
assert "[r36s-rc4-present]" in w
for exact in [
    "glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0)",
    "glWaitSync(ready, 0, GL_TIMEOUT_IGNORED)",
    "glWaitSync(consumed, 0, GL_TIMEOUT_IGNORED)",
    "glBlitFramebuffer(0, 0, width, height",
    "SDL_GL_SwapWindow(g_window)",
    "restore();",
]:
    assert exact in w, exact
for exact in ["[r36s-rc4-endframe]", "[r36s-rc5-gx]",
              "g_queue.Submit(1, &commandBuffer);",
              "gfx::gles_direct::install_frame();"]:
    assert exact in a,exact
print("PASS RC7: display pacing opt-out only; EGL fences/GL blit and RC5 timing intact")
