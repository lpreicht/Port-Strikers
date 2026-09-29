#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / "extern/aurora/lib/webgpu/gpu.cpp"
s = p.read_text()

old = """#ifdef MELEE_MIYOO_FLIP
        // Mali-G52 GLES drivers (g13p0..g29p1) expose zero vertex-stage storage blocks. Vertex data
        // must arrive through AuroraConfig::cpuVertexDecode on this device.
        .maxStorageBuffersInVertexStage = 0,
#else
        .maxStorageBuffersInVertexStage = 2,
#endif
"""
new = """#if defined(MELEE_MIYOO_FLIP) || defined(AURORA_R36S_OFFSCREEN)
        // Legacy Mali G31/G52 GLES drivers expose zero vertex-stage storage blocks.
        // R36S uses cpuVertexDecode/direct-GLES, so no vertex-stage storage buffer is required.
        .maxStorageBuffersInVertexStage = 0,
#else
        .maxStorageBuffersInVertexStage = 2,
#endif
"""
if s.count(old) != 1:
    raise SystemExit(f"vertex storage limit pattern count={s.count(old)}")
p.write_text(s.replace(old, new, 1))
print("R36S V035 zero vertex-stage storage-buffer limit applied")
