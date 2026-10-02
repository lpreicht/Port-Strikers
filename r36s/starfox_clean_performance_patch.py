#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

def replace(path, old, new, label):
    p = root / path
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"{label}: expected pattern not found in {p}")
    p.write_text(s.replace(old, new, 1))
    print(f"patched {label}: {path}")

# ---------------------------------------------------------------------------
# 1) Expose the current map to the native PC-side THP fast path.
#    starfox_clean_visual_patch.py already owns fhNoteMapLoaded and EFB scaling.
# ---------------------------------------------------------------------------
replace(
    "port/src/foxhollow_breadcrumb.c",
    """#include <stdio.h>

void fhNoteMapLoaded(int mapId) {
    const f32 scale = mapId == 63 ? 0.5f : fhConfigRenderScale();
    VISetFrameBufferScale(scale);
    fprintf(stderr, "[foxhollow] map-loaded id=%d efb-scale=%.4f\\n", mapId, scale);
    fflush(stderr);
}
""",
    """#include <stdio.h>

static int sCurrentMapId = -1;

int fhIsMenuMap(void) {
    return sCurrentMapId == 63;
}

void fhNoteMapLoaded(int mapId) {
    const f32 scale = mapId == 63 ? 0.5f : fhConfigRenderScale();
    sCurrentMapId = mapId;
    VISetFrameBufferScale(scale);
    fprintf(stderr, "[foxhollow] map-loaded id=%d efb-scale=%.4f\\n", mapId, scale);
    fflush(stderr);
}
""",
    "menu-map tracker",
)

# ---------------------------------------------------------------------------
# 2) Restore V046/V053 menu-fast THP decode in source.
#    On map 63 libjpeg-turbo writes RGBA directly to the texture backing store.
#    Gameplay keeps the compatible YUV+RGBA path untouched.
# ---------------------------------------------------------------------------
thp = root / "port/src/thp_shim.c"
s = thp.read_text()
if 'extern int fhIsMenuMap(void);' not in s:
    s = s.replace(
        '#include <string.h>\n',
        '#include <string.h>\n\nextern int fhIsMenuMap(void);\n',
        1,
    )

old = """    u32 x;
    u32 y;

    (void)work;
"""
new = """    u32 x;
    u32 y;
    BOOL menuFast = fhIsMenuMap();

    (void)work;
"""
if old not in s:
    raise SystemExit("THP fast decode: local declaration pattern not found")
s = s.replace(old, new, 1)

old = """    jpeg_mem_src(&info, sJpegFrame, sourceSize);
    jpeg_read_header(&info, TRUE);
    info.out_color_space = JCS_YCbCr;
    jpeg_start_decompress(&info);

    width = info.output_width;
    height = info.output_height;
    if (info.output_components != 3 || width != gAttractMoviePlayer.videoInfo.xSize ||
        height != gAttractMoviePlayer.videoInfo.ySize || (width & 15) != 0 || (height & 7) != 0)
    {
        jpeg_destroy_decompress(&info);
        return 19;
    }

    decodedSize = (size_t)width * height * 3;
"""
new = """    jpeg_mem_src(&info, sJpegFrame, sourceSize);
    jpeg_read_header(&info, TRUE);
#if defined(JCS_EXTENSIONS)
    info.out_color_space = menuFast ? JCS_EXT_RGBA : JCS_YCbCr;
#else
    menuFast = FALSE;
    info.out_color_space = JCS_YCbCr;
#endif
    jpeg_start_decompress(&info);

    width = info.output_width;
    height = info.output_height;
    if (info.output_components != (menuFast ? 4 : 3) || width != gAttractMoviePlayer.videoInfo.xSize ||
        height != gAttractMoviePlayer.videoInfo.ySize || (width & 15) != 0 || (height & 7) != 0)
    {
        jpeg_destroy_decompress(&info);
        return 19;
    }

    if (menuFast)
    {
        static BOOL loggedFast;
        rgbTexture = thpGetRGBTexture(tileY, (size_t)width * height * 4);
        if (rgbTexture == NULL)
        {
            jpeg_destroy_decompress(&info);
            return 6;
        }
        while (info.output_scanline < height)
        {
            JSAMPROW row = rgbTexture->rgba + (size_t)info.output_scanline * width * 4;
            jpeg_read_scanlines(&info, &row, 1);
        }
        jpeg_finish_decompress(&info);
        jpeg_destroy_decompress(&info);
        if (!loggedFast)
        {
            fprintf(stderr, "[r36s-thp] menu fast direct RGBA decode active\\n");
            fflush(stderr);
            loggedFast = TRUE;
        }
        return 0;
    }

    decodedSize = (size_t)width * height * 3;
"""
if old not in s:
    raise SystemExit("THP fast decode: decoder body pattern not found")
s = s.replace(old, new, 1)
thp.write_text(s)
print("patched menu-fast direct RGBA THP decoder")

# ---------------------------------------------------------------------------
# 3) Restore V040-style menu THP catch-up: if the title movie is late, skip at
#    most two stale video frames, but still decode their audio, then decode the
#    current frame normally. This keeps playback time close to real time.
# ---------------------------------------------------------------------------
dll = root / "game/src/main/thp/dll_3e.c"
s = dll.read_text()
if '#include <stdio.h>' not in s:
    anchor = '#include "dolphin/thp/THPDecode.h"\n'
    if anchor not in s:
        raise SystemExit("THP catchup: include anchor missing")
    s = s.replace(anchor, anchor + '#include <stdio.h>\n', 1)

anchor = """static OSTime sPcMovieFrameTicks;

static BOOL DecodeNextMovieFramePC(void) {
"""
insert = """static OSTime sPcMovieFrameTicks;

extern int fhIsMenuMap(void);

static BOOL SkipStaleMovieFramePC(void) {
    AttractMoviePlayer* player = &gAttractMoviePlayer;
    AttractMovieReadBuffer* readBuffer = &player->readBuffer[0];
    u32* componentSizes;
    u8* componentData;
    u32 i;

    if (DVDRead(&player->fileInfo, readBuffer->ptr, sPcMovieReadSize, sPcMovieReadOffset) != (s32)sPcMovieReadSize) {
        player->dvdError = -1;
        return FALSE;
    }

    componentSizes = (u32*)(readBuffer->ptr + 8);
    componentData = readBuffer->ptr + 8 + player->compInfo.mNumComponents * sizeof(u32);
    for (i = 0; i < player->compInfo.mNumComponents; i++) {
        u32 componentSize = fhSwap32(componentSizes[i]);
        if (player->compInfo.mFrameComp[i] == 1) {
            AttractMovieAudio_DecodeFramePC(componentData, sPcMovieFrame);
        }
        componentData += componentSize;
    }

    sPcMovieReadOffset += sPcMovieReadSize;
    sPcMovieReadSize = fhSwap32(*(u32*)readBuffer->ptr);
    sPcMovieFrame++;
    if (sPcMovieFrame >= player->header.mNumFrames) {
        sPcMovieFrame = 0;
        sPcMovieReadOffset = player->header.mMovieDataOffsets;
        sPcMovieReadSize = player->header.mFirstFrameSize;
        gAttractMovieLoopCompleted = 1;
    }
    return TRUE;
}

static void CatchUpStaleMovieFramesPC(void) {
    static BOOL loggedCatchup;
    OSTime now;
    s64 overdueFrames;
    int skip;

    if (!fhIsMenuMap() || sPcMovieFrameTicks <= 0) {
        return;
    }
    now = OSGetTime();
    if (now <= sPcMovieNextFrameTime) {
        return;
    }
    overdueFrames = (now - sPcMovieNextFrameTime) / sPcMovieFrameTicks;
    if (overdueFrames < 1) {
        return;
    }
    skip = overdueFrames > 2 ? 2 : (int)overdueFrames;
    while (skip-- > 0) {
        if (!SkipStaleMovieFramePC()) {
            break;
        }
        if (!loggedCatchup) {
            fprintf(stderr, "[r36s-thp] menu catch-up active (max 3 movie frames/retrace)\\n");
            fflush(stderr);
            loggedCatchup = TRUE;
        }
    }
}

static BOOL DecodeNextMovieFramePC(void) {
    CatchUpStaleMovieFramesPC();
"""
if anchor not in s:
    raise SystemExit("THP catchup: DecodeNextMovieFramePC anchor missing")
s = s.replace(anchor, insert, 1)
dll.write_text(s)
print("patched menu-only THP stale-frame catch-up")

# ---------------------------------------------------------------------------
# 4) Restore the V053-style Direct-GLES pipeline correctness wait narrowly.
#    IMPORTANT: never make generic get_pipeline() blocking. The direct renderer
#    probes pipelines in several preparation paths; blocking there caused the
#    300-360 ms/frame regression seen in CLEAN run 96.
#
#    Only the actual Direct-GLES draw preparation may wait for a pipeline that
#    is already queued on Aurora's async compiler. This mirrors the proven
#    helper behaviour: preserve the draw, but do not stall unrelated lookups.
# ---------------------------------------------------------------------------
hpp = root / "extern/aurora/lib/gfx/pipeline_cache.hpp"
s = hpp.read_text()
old = """bool get_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline);
// Renderer time accounting (AuroraConfig::renderStats): time and count of blocking pipeline waits.
"""
new = """bool get_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline);
bool wait_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline, uint32_t timeoutMs);
// Renderer time accounting (AuroraConfig::renderStats): time and count of blocking pipeline waits.
"""
if old not in s:
    raise SystemExit("pipeline wait: header declaration anchor not found")
hpp.write_text(s.replace(old, new, 1))

pipe = root / "extern/aurora/lib/gfx/pipeline_cache.cpp"
s = pipe.read_text()
# Undo the too-broad CLEAN implementation if this patch is being re-applied.
broad = """bool get_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline) {
  std::unique_lock lock{g_pipelineMutex};
  auto it = g_pipelines.find(ref);
  if (it == g_pipelines.end() && g_hasPipelineThread && g_pendingPipelines.contains(ref)) {
    static bool loggedRecovered = false;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(100);
    g_pipelineReadyCv.wait_until(lock, deadline, [=] {
      return g_pipelines.contains(ref) || g_pipelineThreadEnd.load(std::memory_order_relaxed);
    });
    it = g_pipelines.find(ref);
    if (it != g_pipelines.end() && !loggedRecovered) {
      Log.info("R36S pipeline wait recovered async pipeline miss; draw preserved");
      loggedRecovered = true;
    }
  }
  if (it == g_pipelines.end()) {
    return false;
  }
  pipeline = it->second.pipeline;
  return true;
}
"""
normal = """bool get_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline) {
  std::lock_guard guard{g_pipelineMutex};
  const auto it = g_pipelines.find(ref);
  if (it == g_pipelines.end()) {
    return false;
  }
  pipeline = it->second.pipeline;
  return true;
}
"""
if broad in s:
    s = s.replace(broad, normal, 1)
elif normal not in s:
    raise SystemExit("pipeline wait: get_pipeline implementation not recognized")

anchor = normal
narrow = normal + """
bool wait_pipeline(PipelineRef ref, wgpu::RenderPipeline& pipeline, uint32_t timeoutMs) {
  // Match the proven V052/V053 helper exactly in behaviour: Direct-GLES does
  // not depend on one condition-variable wakeup. It rechecks get_pipeline()
  // every millisecond for up to 5000 ms. The old helper did this for every
  // get_pipeline() call originating from the Direct-GLES code range.
  for (uint32_t i = 0; i < timeoutMs; ++i) {
    if (get_pipeline(ref, pipeline)) {
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return get_pipeline(ref, pipeline);
}
"""
if anchor not in s:
    raise SystemExit("pipeline wait: normal get_pipeline anchor not found")
s = s.replace(anchor, narrow, 1)
pipe.write_text(s)

gles = root / "extern/aurora/lib/gfx/gles_direct.cpp"
s = gles.read_text()
old = """  PreparedPipeline p;
  if (!gx::find_pipeline_config(ref, p.config) || !get_pipeline(ref, p.owner)) {
    return nullptr;
  }
"""
new = """  PreparedPipeline p;
  if (!gx::find_pipeline_config(ref, p.config)) {
    return nullptr;
  }
  if (!wait_pipeline(ref, p.owner, 5000)) {
    static bool loggedTimeout = false;
    if (!loggedTimeout) {
      Log.warn("R36S Direct-GLES pipeline correctness wait timed out; falling back to skip");
      loggedTimeout = true;
    }
    return nullptr;
  }
"""
if old not in s:
    raise SystemExit("pipeline wait: direct prepare_pipeline anchor not found")
if old not in s:
    raise SystemExit("pipeline wait: direct prepare_pipeline anchor not found")
s = s.replace(old, new, 1)

# The original V053 binary helper intercepted every get_pipeline() call whose
# return address was inside the Direct-GLES code range. Aurora currently has a
# second lookup while deciding whether a pass can use the direct path. Waiting
# only in prepare_pipeline() was therefore not V053-equivalent and allowed the
# planning path to observe transient pipeline misses.
plan_old = """      if (!get_pipeline(d.pipeline, p) || !gx::find_pipeline_config(d.pipeline, c) || !pipeline_eligible(c)) {
        return false;
      }
"""
plan_new = """      if (!wait_pipeline(d.pipeline, p, 5000) || !gx::find_pipeline_config(d.pipeline, c) || !pipeline_eligible(c)) {
        return false;
      }
"""
if plan_old not in s:
    raise SystemExit("pipeline wait: Direct-GLES planning lookup anchor not found")
s = s.replace(plan_old, plan_new, 1)

gles.write_text(s)
print("patched exact V053-style Direct-GLES pipeline polling at all current lookup sites")

print("Star Fox clean R36S performance patches applied successfully")

