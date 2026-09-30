#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

def replace(path, old, new, label):
    p = root / path
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"{label}: expected source pattern not found in {p}")
    p.write_text(text.replace(old, new, 1))
    print(f"patched {label}: {path}")

# Foxhollow v1.0.9 declared render-scale configuration but current main does not
# provide the implementation. Add it here and expose a clean R36S env setting.
cfg = root / "port/src/foxhollow_config.c"
text = cfg.read_text()
if "fhConfigRenderScale(void)" not in text:
    text = text.replace(
        "static int sFrameLimit = FH_DEFAULT_FRAME_LIMIT;\n",
        "static int sFrameLimit = FH_DEFAULT_FRAME_LIMIT;\nstatic f32 sRenderScale = 1.0f;\n",
        1,
    )
    text = text.replace(
        "  const char* frameLimit;\n  const char* revision;\n",
        "  const char* frameLimit;\n  const char* renderScale;\n  const char* revision;\n",
        1,
    )
    text = text.replace(
        "  frameLimit = getenv(\"FOXHOLLOW_FRAME_LIMIT\");\n",
        "  renderScale = getenv(\"FOXHOLLOW_RENDER_SCALE\");\n"
        "  if (renderScale != NULL && renderScale[0] != '\\0') {\n"
        "    char* end = NULL;\n"
        "    const float value = strtof(renderScale, &end);\n"
        "    if (end != renderScale && value >= 0.25f && value <= 1.0f) {\n"
        "      sRenderScale = value;\n"
        "    }\n"
        "  }\n\n"
        "  frameLimit = getenv(\"FOXHOLLOW_FRAME_LIMIT\");\n",
        1,
    )
    marker = "int fhConfigRevision(void) {\n"
    if marker not in text:
        raise SystemExit("render-scale: revision marker not found")
    text = text.replace(
        marker,
        "f32 fhConfigRenderScale(void) {\n"
        "  load();\n"
        "  return sRenderScale;\n"
        "}\n\n"
        + marker,
        1,
    )
    cfg.write_text(text)
    print("patched Foxhollow render-scale env implementation")

# Keep the proven R36S dynamic EFB profile in source instead of libsfscale.so:
# the title/intro map (63) runs at 0.5x, while actual gameplay uses the normal
# FOXHOLLOW_RENDER_SCALE value (0.6667 in the clean launcher).
replace(
    "port/src/foxhollow_breadcrumb.c",
    """#include "foxhollow_crash.h"

#include <stdio.h>

void fhNoteMapLoaded(int mapId) {
    fprintf(stderr, "[foxhollow] map-loaded id=%d\\n", mapId);
    fflush(stderr);
}
""",
    """#include "foxhollow_crash.h"
#include "foxhollow_config.h"
#include "dolphin/vi.h"

#include <stdio.h>

void fhNoteMapLoaded(int mapId) {
    const f32 scale = mapId == 63 ? 0.5f : fhConfigRenderScale();
    VISetFrameBufferScale(scale);
    fprintf(stderr, "[foxhollow] map-loaded id=%d efb-scale=%.4f\\n", mapId, scale);
    fflush(stderr);
}
""",
    "source-level dynamic R36S EFB scale",
)

# Preserve real-time pacing on the R36S when a heavy scene drops below 10 fps.
# At normal gameplay rates this is inert; it only raises the original 6-frame cap.
replace(
    "game/src/main/pi_videoinit.c",
    "    if (timeDelta > 6.0f) {\n        timeDelta = 6.0f;\n    }",
    "    if (timeDelta > 10.0f) {\n        timeDelta = 10.0f;\n    }",
    "R36S realtime frame-delta cap 6 -> 10",
)

# Foxhollow v1.0.10: planar-reflection geometry can overflow Aurora's old 2 MiB
# index stream. Keep the ARM renderer, but carry the upstream 8 MiB fix across.
resources = root / "extern/aurora/lib/gfx/resources.hpp"
resources_text = resources.read_text()
index_variants = (
    "inline constexpr uint64_t IndexBufferSize = 2 * 1024 * 1024;",
    "inline constexpr uint64_t IndexBufferSize = 2097152;    // 2 MiB",
)
for old_index in index_variants:
    if old_index in resources_text:
        resources_text = resources_text.replace(
            old_index,
            "inline constexpr uint64_t IndexBufferSize = 8 * 1024 * 1024; // Foxhollow planar reflections",
            1,
        )
        resources.write_text(resources_text)
        print("patched planar-reflection index buffer 2 MiB -> 8 MiB")
        break
else:
    if "IndexBufferSize = 8 * 1024 * 1024" in resources_text:
        print("planar-reflection index buffer already 8 MiB")
    else:
        raise SystemExit("planar-reflection index buffer: no recognized 2 MiB source form found")

# R36S performance note:
# Do NOT port Foxhollow's desktop GX_CTF_B8 16x16 blur into the ARM renderer.
# That shader can require 256 texture samples per output pixel and causes a
# severe Mali-G31 performance regression. Keep Aurora ARM's native single-sample
# B8 conversion. Planar-reflection support remains handled independently by the
# 8 MiB index stream above.

print("Star Fox clean R36S source patches applied successfully")
