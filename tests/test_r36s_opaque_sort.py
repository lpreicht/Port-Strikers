#!/usr/bin/env python3
"""Source-only contract checks (not hardware correctness/performance validation)."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
main=(root/"src/main.c").read_text()
gles=(root/"extern/aurora/lib/gfx/gles_direct.cpp").read_text()
assert '.sortOpaqueDraws = getenv("R36S_SORT_OPAQUE") != NULL' in main
assert 'getenv("R36S_SORT_OPAQUE")[0] == \'1\'' in main
assert "g_config.sortOpaqueDraws && plan.eligible" in gles
assert "config.depthCompare && config.depthUpdate" in gles
assert "config.blendMode == GX_BM_NONE" in gles
assert "std::stable_sort(" in gles
print("PASS: opaque sort is an opt-in, reversible existing Aurora path and gated to eligible opaque draws")
