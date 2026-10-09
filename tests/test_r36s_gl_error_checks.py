#!/usr/bin/env python3
"""RC3 source contract: retain rendering and pass-end diagnostics."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
src = (root / "extern/aurora/lib/gfx/gles_direct.cpp").read_text()
assert src.count("bool r36s_draw_error_checks_enabled() {") == 1
assert 'std::getenv("R36S_GL_DRAW_ERROR_CHECK")' in src
assert "return value == nullptr || value[0] != '0';" in src
assert "if (!always && (!stats_enabled() || !r36s_draw_error_checks_enabled()))" in src
# Always-on pass-end error reporting must not be bypassed by the toggle.
assert 'gl_ok("pass-end", passIndex, drawIndex, true);' in src
assert 'gl_ok("draw", passIndex, drawIndex)' in src
assert 'gl_ok("pipeline-state", passIndex, drawIndex)' in src
assert 'gl_ok("resources", passIndex, drawIndex)' in src
# Preserve renderer statistics used to compare RC2/RC3 results.
assert "[gles-direct-gl-calls]" in src
assert "[gles-direct-plan]" in src
assert "[gles-direct-sort]" in src
assert "glGetError()" in src
print("PASS: RC3 draw-error A/B flag, normal fallback and pass-end diagnostics")
