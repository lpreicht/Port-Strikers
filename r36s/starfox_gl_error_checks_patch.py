#!/usr/bin/env python3
"""RC3 R36S draw-level glGetError() cost A/B switch.

When R36S_GL_DRAW_ERROR_CHECK=0, only the optional per-draw/per-state
glGetError() calls are skipped. Always-on end-of-pass checking remains.
When unset or set to 1, restore the exact RC2 error-check behavior.
No rasterization, GX commands, uniforms, shadows or water code changes.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
source = root / "extern/aurora/lib/gfx/gles_direct.cpp"
text = source.read_text()

original = """bool gl_ok(const char* section, uint32_t passIndex, uint32_t drawIndex, bool always = false) {
  if (!always && !stats_enabled()) {
    return true;
  }
"""

patched = """// RC3 timed Mali-G31 A/B test. glGetError may force driver synchronization
// for each draw; preserve error reporting at the end of EVERY render pass.
bool r36s_draw_error_checks_enabled() {
  static const bool enabled = [] {
    const char* value = std::getenv("R36S_GL_DRAW_ERROR_CHECK");
    return value == nullptr || value[0] != '0';
  }();
  return enabled;
}

bool gl_ok(const char* section, uint32_t passIndex, uint32_t drawIndex, bool always = false) {
  if (!always && (!stats_enabled() || !r36s_draw_error_checks_enabled())) {
    return true;
  }
"""
if text.count(original) != 1:
    raise SystemExit("RC3: expected exactly one original gl_ok; fail closed")
if "r36s_draw_error_checks_enabled()" in text:
    raise SystemExit("RC3: double patch rejected")

source.write_text(text.replace(original, patched, 1))
print("RC3: opt-out per-draw glGetError installed, end-of-pass checks retained")
