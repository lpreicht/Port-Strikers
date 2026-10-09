#!/usr/bin/env python3
"""RC5 timing instrumentation contract, no hardware-performance claims."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
src=(root/"extern/aurora/lib/aurora.cpp").read_text()
assert src.count("[r36s-rc5-gx]") == 1
assert "r36sRc5AfterDrainNs = SDL_GetTicksNS()" in src
assert "r36sRc5AfterFifoEndNs = SDL_GetTicksNS()" in src
assert "r36sRc5AfterTextureEndNs = SDL_GetTicksNS()" in src
assert "r36sRc5AfterRecordingFinishNs = SDL_GetTicksNS()" in src
for p in ["gx::fifo::drain();", "gx::fifo::end_frame();",
          "gx::texture::end_frame();", "gfx::finish();",
          "g_queue.Submit(1, &commandBuffer);",
          "window::present_gl_texture(p.texture, p.width, p.height);"]:
    assert p in src, p
assert "r36sRc5Remaining += (r36sRc4EnteredNs - r36sRc5AfterRecordingFinishNs) / 1e6" in src
assert 'std::getenv("R36S_PRESENT_PROFILE")' in src
assert "[r36s-rc4-endframe]" in src
print("PASS RC5: five extra GX phase counters; render and presenter untouched")
