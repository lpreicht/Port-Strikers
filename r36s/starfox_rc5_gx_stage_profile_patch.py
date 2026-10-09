#!/usr/bin/env python3
"""RC5 isolate pre-GPU-submit CPU time without changing render behavior.

The validated RC4 samples show 70-100 ms in the phase before encoder submission.
This patch subdivides that interval into GX FIFO drain, frame cleanup, texture
cache end, recording finish, and remainder (gfx frame preparation / callbacks).
R36S_PRESENT_PROFILE=1 gates reporting along with RC4.
"""
from pathlib import Path
import sys
p=Path(sys.argv[1]).resolve()/"extern/aurora/lib/aurora.cpp"
s=p.read_text()

def once(old,new,name):
    global s
    n=s.count(old)
    if n != 1:
        raise SystemExit(f"RC5 {name}: expected exactly one anchor, got {n}")
    s=s.replace(old,new,1)

once(
    "  const uint64_t r36sRc4FrameStartNs = SDL_GetTicksNS();\n",
    """  const uint64_t r36sRc4FrameStartNs = SDL_GetTicksNS();
  // RC5: all timestamps start at frame entry; normal synchronous GX is timed below.
  uint64_t r36sRc5AfterDrainNs = r36sRc4FrameStartNs;
  uint64_t r36sRc5AfterFifoEndNs = r36sRc4FrameStartNs;
  uint64_t r36sRc5AfterTextureEndNs = r36sRc4FrameStartNs;
  uint64_t r36sRc5AfterRecordingFinishNs = r36sRc4FrameStartNs;
""", "frame timestamps")

once(
    """  if (!asyncFrame) {
    gx::fifo::drain();
    gx::fifo::end_frame();
    gx::texture::end_frame();
    gfx::finish();
  }
""",
    """  if (!asyncFrame) {
    gx::fifo::drain();
    r36sRc5AfterDrainNs = SDL_GetTicksNS();
    gx::fifo::end_frame();
    r36sRc5AfterFifoEndNs = SDL_GetTicksNS();
    gx::texture::end_frame();
    r36sRc5AfterTextureEndNs = SDL_GetTicksNS();
    gfx::finish();
    r36sRc5AfterRecordingFinishNs = SDL_GetTicksNS();
  }
""", "GX CPU phase boundaries")

once(
    "viewport, imguiDrawData = std::move(imguiDrawData), r36sRc4FrameStartNs](",
    "viewport, imguiDrawData = std::move(imguiDrawData), r36sRc4FrameStartNs, "
    "r36sRc5AfterDrainNs, r36sRc5AfterFifoEndNs, r36sRc5AfterTextureEndNs, "
    "r36sRc5AfterRecordingFinishNs](", "capture timestamps")

once(
    """      r36sRc4After += (r36sRc4FinishedNs - r36sRc4PresentDoneNs) / 1e6;
      ++r36sRc4N;
""",
    """      r36sRc4After += (r36sRc4FinishedNs - r36sRc4PresentDoneNs) / 1e6;
      // Breakdown of RC4's broad pre_gx stage. All timestamps are wall-clock,
      // including CPU work and synchronization waits in the corresponding step.
      static double r36sRc5Drain = 0, r36sRc5FifoEnd = 0;
      static double r36sRc5TextureEnd = 0, r36sRc5GfxFinish = 0, r36sRc5Remaining = 0;
      r36sRc5Drain += (r36sRc5AfterDrainNs - r36sRc4FrameStartNs) / 1e6;
      r36sRc5FifoEnd += (r36sRc5AfterFifoEndNs - r36sRc5AfterDrainNs) / 1e6;
      r36sRc5TextureEnd += (r36sRc5AfterTextureEndNs - r36sRc5AfterFifoEndNs) / 1e6;
      r36sRc5GfxFinish += (r36sRc5AfterRecordingFinishNs - r36sRc5AfterTextureEndNs) / 1e6;
      r36sRc5Remaining += (r36sRc4EnteredNs - r36sRc5AfterRecordingFinishNs) / 1e6;
      ++r36sRc4N;
""", "stage accumulation")

once(
    """      if (r36sRc4FinishedNs - r36sRc4LastReportNs >= 3000000000ull) {
        std::fprintf(stderr, "[r36s-rc4-endframe]""",
    """      if (r36sRc4FinishedNs - r36sRc4LastReportNs >= 3000000000ull) {
        std::fprintf(stderr, "[r36s-rc5-gx] n=%u fifo_drain=%.3f fifo_end=%.3f texture_end=%.3f gfx_finish=%.3f frame_prepare=%.3f ms/frame\\n",
                     r36sRc4N, r36sRc5Drain/r36sRc4N, r36sRc5FifoEnd/r36sRc4N,
                     r36sRc5TextureEnd/r36sRc4N, r36sRc5GfxFinish/r36sRc4N,
                     r36sRc5Remaining/r36sRc4N);
        r36sRc5Drain = r36sRc5FifoEnd = r36sRc5TextureEnd =
            r36sRc5GfxFinish = r36sRc5Remaining = 0;
        std::fprintf(stderr, "[r36s-rc4-endframe]""", "report at same cadence")

p.write_text(s)
print("RC5: isolated GX FIFO/drain/texture/recording/frame-preparation wall times; rendering unchanged")
