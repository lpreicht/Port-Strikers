#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / "extern/aurora/lib/gfx/render_worker.cpp"
s = p.read_text()

old = """void initialize() {
  if (g_running.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  g_queue.reset();
  g_pendingItems.store(0, std::memory_order_release);
  g_thread = thread::Thread{{
                                .name = "Aurora render worker",
                                .affinity = thread::Affinity::SharedCache,
                            },
                            worker_main};
}
"""

new = """void initialize() {
#ifdef AURORA_R36S_OFFSCREEN
  // R36S/KMSDRM: SDL/EGL window context ownership is main-thread bound on the
  // legacy Mali r13p0 stack. Keep Aurora's render queue in inline mode so all
  // queued BeginFrame/Encode/EndFrame callbacks execute on the caller thread.
  // enqueue() already has this exact fallback whenever g_running == false.
  g_running.store(false, std::memory_order_release);
  g_pendingItems.store(0, std::memory_order_release);
  g_queue.reset();
  Log.info("R36S V030 render worker disabled: inline main-thread rendering");
  return;
#else
  if (g_running.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  g_queue.reset();
  g_pendingItems.store(0, std::memory_order_release);
  g_thread = thread::Thread{{
                                .name = "Aurora render worker",
                                .affinity = thread::Affinity::SharedCache,
                            },
                            worker_main};
#endif
}
"""

if s.count(old) != 1:
    raise SystemExit(f"render_worker initialize pattern count={s.count(old)}")
p.write_text(s.replace(old, new, 1))
print("R36S V030 synchronous main-thread Aurora renderer patch applied")
