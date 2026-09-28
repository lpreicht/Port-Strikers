#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{rel}: expected 1 match, got {n}: {old[:160]!r}")
    p.write_text(s.replace(old, new, 1))

# R36S has only ~897 MiB physical RAM. Aurora ARM's desktop-oriented defaults
# allocate five ~66 MiB staging buffers plus shared GPU streams. Keep CPU vertex
# decode, but use a single frame in flight and two staging buffers.
replace(
    "extern/aurora/lib/gfx/frame.hpp",
    """inline constexpr size_t FrameSlotCount = 2;
inline constexpr size_t StagingBufferCount = FrameSlotCount + 3;
""",
    """// R36S low-memory profile: one frame in flight and one spare staging buffer.
inline constexpr size_t FrameSlotCount = 1;
inline constexpr size_t StagingBufferCount = 2;
""",
)

# Keep enough headroom for Star Fox while cutting the largest fixed streams.
# V029 staging footprint:
# 16 MiB uniform + 8 MiB vertex + 2 MiB index + 6 MiB storage +
# 16 MiB texture upload = 48 MiB per staging buffer.
replace(
    "extern/aurora/lib/gfx/resources.hpp",
    """inline constexpr uint64_t UniformBufferSize = 25165824; // 24 MiB
""",
    """inline constexpr uint64_t UniformBufferSize = 16777216; // 16 MiB R36S low-memory profile
""",
)
replace(
    "extern/aurora/lib/gfx/resources.hpp",
    """inline constexpr uint64_t StorageBufferSize = 8388608;  // 8 MiB
inline constexpr uint64_t TextureUploadSize = 25165824; // 24 MiB
""",
    """inline constexpr uint64_t StorageBufferSize = 6291456;   // 6 MiB R36S low-memory profile
inline constexpr uint64_t TextureUploadSize = 16777216; // 16 MiB R36S low-memory profile
""",
)

# Emit the exact fixed renderer allocation at startup so the device log confirms
# which profile is running.
replace(
    "extern/aurora/lib/gfx/frame.cpp",
    """void initialize() {
  g_frameIndex = 0;
""",
    """void initialize() {
  Log.info("R36S V029 renderer memory profile: frameSlots={} stagingBuffers={} stagingMiB={} sharedStreamsMiB={}",
           FrameSlotCount, StagingBufferCount, StagingBufferSize / (1024 * 1024),
           (UniformBufferSize + VertexBufferSize + IndexBufferSize + StorageBufferSize) / (1024 * 1024));
  g_frameIndex = 0;
""",
)

print("R36S V029 low-memory Aurora ARM profile applied")
