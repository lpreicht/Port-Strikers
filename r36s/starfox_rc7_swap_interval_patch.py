#!/usr/bin/env python3
"""RC7: A/B-test KMSDRM SDL GLES swap interval without changing render commands.

On slow frames RC6's SDL_GL_SwapWindow frequently spends 10-16ms (or more).
Experiment only with display synchronization; shaders, EFB copies,
shared-context fences and all GX graphics operations stay unchanged.

R36S_SWAP_INTERVAL=0: request immediate page flips (may tear; driver-dependent).
R36S_SWAP_INTERVAL=1: proven RC6 vsync baseline (default in absence of env).
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/window.cpp"
s=p.read_text()
old='''  if (!SDL_GL_SetSwapInterval(1)) {
    Log.warn("R36S V027 SDL_GL_SetSwapInterval(1) failed: {}", SDL_GetError());
  }
'''
new='''  // RC7: reversible display-pacing A/B test. Only swap interval changes;
  // the offscreen Dawn producer, shared EGL presenter and GPU fences do not.
  const char* r36sSwapSetting = std::getenv("R36S_SWAP_INTERVAL");
  const int r36sSwapInterval = r36sSwapSetting != nullptr && r36sSwapSetting[0] == '0' ? 0 : 1;
  if (!SDL_GL_SetSwapInterval(r36sSwapInterval)) {
    Log.warn("R36S RC7 SDL_GL_SetSwapInterval({}) failed: {}", r36sSwapInterval, SDL_GetError());
  } else {
    Log.info("R36S RC7 SDL GLES swap interval request={} (0=uncapped; 1=RC6 vsync)", r36sSwapInterval);
  }
'''
if s.count(old)!=1:
    raise SystemExit(f"RC7 swap interval anchor expected once, found {s.count(old)}")
s=s.replace(old,new,1)
for needed in ("glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0)",
               "glWaitSync(ready, 0, GL_TIMEOUT_IGNORED)",
               "glWaitSync(consumed, 0, GL_TIMEOUT_IGNORED)",
               "SDL_GL_SwapWindow(g_window)",
               "[r36s-rc4-present]"):
    if needed not in s:
        raise SystemExit(f"RC7 safety assertion: {needed} absent")
p.write_text(s)
print("RC7: A/B swap interval request applied; present synchronization and renderer untouched")
