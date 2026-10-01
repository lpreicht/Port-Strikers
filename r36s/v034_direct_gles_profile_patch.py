#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{rel}: expected 1 match, got {n}: {old[:180]!r}")
    p.write_text(s.replace(old, new, 1))

# Direct-GLES branch has a Flip-specific 1 GiB profile; use the same bounded
# staging geometry but keep it R36S-named and conservative.
replace(
    "extern/aurora/lib/gfx/frame.hpp",
    """inline constexpr size_t FrameSlotCount = 2;
#ifdef MELEE_MIYOO_FLIP
inline constexpr size_t StagingBufferCount = FrameSlotCount + 1; // 1 GiB device: three 38 MiB staging maps
#else
inline constexpr size_t StagingBufferCount = FrameSlotCount + 3;
#endif
""",
    """// R36S V034: one frame in flight and one spare staging buffer.
inline constexpr size_t FrameSlotCount = 1;
inline constexpr size_t StagingBufferCount = 2;
""",
)

replace(
    "extern/aurora/lib/gfx/resources.hpp",
    """#ifdef MELEE_MIYOO_FLIP
// Bounded pools for the Flip's 1 GiB shared CPU/GPU memory. The vertex pool is larger than
// upstream's because CPU-decoded float records are wider than the raw GX stream.
inline constexpr uint64_t UniformBufferSize = 8 * 1024 * 1024;
inline constexpr uint64_t VertexBufferSize = 12 * 1024 * 1024;
inline constexpr uint64_t IndexBufferSize = 2 * 1024 * 1024;
inline constexpr uint64_t StorageBufferSize = 4 * 1024 * 1024;
inline constexpr uint64_t TextureUploadSize = 12 * 1024 * 1024;
#else
inline constexpr uint64_t UniformBufferSize = 25165824; // 24 MiB
#ifdef AURORA_VERTEX_BUFFER_SIZE
// Set from the AURORA_VERTEX_BUFFER_MIB CMake variable. CPU-decoded vertex records (cpuVertexDecode)
// are wider than raw GX vertices; titles that stream heavy geometry without resident display lists
// need more than the 5 MiB default.
inline constexpr uint64_t VertexBufferSize = AURORA_VERTEX_BUFFER_SIZE;
#else
inline constexpr uint64_t VertexBufferSize = 5242880;   // 5 MiB
#endif
inline constexpr uint64_t IndexBufferSize = 2097152;    // 2 MiB
inline constexpr uint64_t StorageBufferSize = 8388608;  // 8 MiB
inline constexpr uint64_t TextureUploadSize = 25165824; // 24 MiB
#endif
""",
    """// R36S V034 bounded streams for 897 MiB shared system/GPU memory.
inline constexpr uint64_t UniformBufferSize = 8 * 1024 * 1024;
#ifdef AURORA_VERTEX_BUFFER_SIZE
inline constexpr uint64_t VertexBufferSize = AURORA_VERTEX_BUFFER_SIZE;
#else
inline constexpr uint64_t VertexBufferSize = 8 * 1024 * 1024;
#endif
inline constexpr uint64_t IndexBufferSize = 2 * 1024 * 1024;
inline constexpr uint64_t StorageBufferSize = 4 * 1024 * 1024;
inline constexpr uint64_t TextureUploadSize = 12 * 1024 * 1024;
""",
)

print("R36S V034 direct-GLES low-memory profile applied")
