#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
cpp = root / "extern/aurora/lib/dolphin/dvd/dvd.cpp"
hdr = root / "extern/aurora/include/aurora/dvd.h"
s = cpp.read_text()
h = hdr.read_text()

def one(text, old, new, name):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{name}: expected 1 match, got {n}")
    return text.replace(old, new, 1)

# Restore Foxhollow's main-thread callback pump on top of Aurora ARM's worker.
# The worker still performs disc I/O asynchronously, but completion callbacks are
# queued until OSYieldThread/VIWaitForRetrace calls aurora_dvd_process_callbacks().
anchor = "CommandDataNod* s_disc;\n"
insert = r'''CommandDataNod* s_disc;

struct PendingCallback {
  s32 result;
  DVDCommandBlock* block;
  DVDCBCallback callback;
};

std::mutex s_pendingCallbackMutex;
std::deque<PendingCallback> s_pendingCallbacks;
thread_local bool s_processingPendingCallbacks = false;

void enqueuePendingCallback(s32 result, DVDCommandBlock* block, DVDCBCallback callback) {
  if (callback == nullptr) {
    return;
  }
  std::lock_guard lock{s_pendingCallbackMutex};
  s_pendingCallbacks.push_back({result, block, callback});
}

void processPendingCallbacks() {
  if (s_processingPendingCallbacks) {
    return;
  }
  s_processingPendingCallbacks = true;
  while (true) {
    PendingCallback pending{};
    {
      std::lock_guard lock{s_pendingCallbackMutex};
      if (s_pendingCallbacks.empty()) {
        break;
      }
      pending = s_pendingCallbacks.front();
      s_pendingCallbacks.pop_front();
    }
    pending.callback(pending.result, pending.block);
  }
  s_processingPendingCallbacks = false;
}

void clearPendingCallbacks() {
  std::lock_guard lock{s_pendingCallbackMutex};
  s_pendingCallbacks.clear();
}
'''
s = one(s, anchor, insert, "pending callback insertion")

# Do not retain stale callbacks across disc close/reopen.
s = one(
    s,
    "void clearState() {\n  if (s_partition != nullptr) {\n",
    "void clearState() {\n  clearPendingCallbacks();\n  if (s_partition != nullptr) {\n",
    "clearState",
)

# Worker-thread completions are deferred; immediate/synchronous execution keeps
# the existing direct callback behavior.
s = one(
    s,
    "      process_command(block);\n      lk.lock();\n",
    "      process_command(block, true);\n      lk.lock();\n",
    "worker process call",
)

old_process = r'''  void process_command(DVDCommandBlock* block) {
    auto [result, transferred] = perform_command(block);
    if (consume_active_cancel(block)) {
      result = DVD_RESULT_CANCELED;
      transferred = 0;
    }
    finishCommand(block, result, transferred);
    if (block->callback != nullptr) {
      block->callback(result, block);
    }
  }
'''
new_process = r'''  void process_command(DVDCommandBlock* block, bool deferCallback) {
    auto [result, transferred] = perform_command(block);
    if (consume_active_cancel(block)) {
      result = DVD_RESULT_CANCELED;
      transferred = 0;
    }
    const DVDCBCallback callback = block->callback;
    finishCommand(block, result, transferred);
    if (deferCallback) {
      enqueuePendingCallback(result, block, callback);
    } else if (callback != nullptr) {
      callback(result, block);
    }
  }
'''
s = one(s, old_process, new_process, "process_command body")

s = one(
    s,
    "    process_command(block);\n    {\n      std::lock_guard lk{m_mutex};\n",
    "    process_command(block, false);\n    {\n      std::lock_guard lk{m_mutex};\n",
    "immediate process call",
)

# Public C API expected by Foxhollow's os_shim.c.
extern_anchor = 'extern "C" {\n\n'
extern_insert = r'''extern "C" {

void aurora_dvd_process_callbacks(void) {
  processPendingCallbacks();
}

'''
s = one(s, extern_anchor, extern_insert, "extern C pump")

header_anchor = "void aurora_dvd_close(void);\n"
header_insert = r'''void aurora_dvd_close(void);

/**
 * Run deferred asynchronous DVD completion callbacks on the calling thread.
 * Foxhollow pumps this from its emulated OS/retrace loop.
 */
void aurora_dvd_process_callbacks(void);
'''
h = one(h, header_anchor, header_insert, "dvd header declaration")

cpp.write_text(s)
hdr.write_text(h)
print("Foxhollow main-thread DVD callback pump restored on Aurora ARM")
