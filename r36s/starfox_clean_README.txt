STAR FOX ADVENTURES - R36S CLEAN GITHUB BUILD

This package intentionally has one launcher and one port directory.
Do not layer old V0xx overlay ZIPs over it.

INSTALL / TEST
1. Extract the ZIP into your Ports folder.
2. Copy the CONTENTS of your known-good old:
      starfoxadventures/conf/
   into:
      starfoxadventures/conf/
3. Copy your Star Fox Adventures Europe Rev 1 .rvz/.iso/.gcm into:
      starfoxadventures/gamedata/
4. Start "Star Fox Adventures".

The package does not include copyrighted game data.

CURRENT CLEAN TEST GOALS
- current Foxhollow source
- 8 MiB index stream for planar reflections
- keep the ARM fast GX_CTF_B8 copy path (desktop 16x16 blur is too expensive on Mali-G31)
- no global blur-suppression preload
- source-level frame delta cap raised from 6 to 10 for slow R36S 3D intro scenes
- Direct-GLES R36S path retained
- menu/title THP uses direct RGBA decode + max-3-frame catch-up
- only actual Direct-GLES draw misses may wait for the queued pipeline (V053-style correctness fallback)
- one permanent launcher; future tests replace this GitHub artifact


RC3 R36S PERFORMANCE A/B (2026-10-09)
- Only the draw-level OpenGL glGetError overhead is being tested.
- RC3 default: R36S_GL_DRAW_ERROR_CHECK=0. Per-draw GL error checks are bypassed.
  GL error checks at the end of every render pass remain enabled.
- To restore the original draw-level error checks without reinstalling:
  create starfoxadventures/conf/gl-draw-checks.txt with ONE line: 1
- To return to RC3 test mode, change the line to: 0
- Opaque draw sorting is OFF by default (it reduced state changes but did not
  appreciably improve FPS). Override by writing 1 to conf/opaque-sort.txt.
- Internal gameplay scale is restored to 0.6667 by default. If you previously
  created conf/render-scale.txt with 0.5000, delete it or change to 0.6667
  for comparable tests.
- Keep the proven shadow, reflection, water, lightmap cap, and menu/audio
  options unchanged during this diagnostic.
- Use the same in-game viewpoint during both runs. Compare
  [R36S V025 timing] retraces/s and render= values in separate logs.
- This patch passed source checks only. A successful build, visual integrity,
  and R36S performance improvement require hardware validation.



RC4 PHASE TIMING DIAGNOSTIC (2026-10-09)
The RC3 draw-level glGetError experiment did not materially improve Map 8 FPS:
~7.4 FPS median, ~106 ms median render phase. RC4 does not alter GX/EFB,
shadows, water, texture sampling or SDL/EGL presentation commands.
It splits native end-of-frame wall time into two stderr reports:
- [r36s-rc4-endframe]: pre_gx, encode, submit, presenter, after (ms/frame)
- [r36s-rc4-present]: fence, context_wait, blit, swap, restore (ms/frame)
The sum of the RC4 endframe stages should approach the VI render timing;
the presenter report subdivides the presenter stage further.
To disable profiling for a performance control:
  starfoxadventures/conf/rc4-profile.txt : a single line containing 0
To re-enable the timing report: change the line to 1 (default if absent).
R36S_GL_DRAW_ERROR_CHECK=0 and R36S_SORT_OPAQUE=0 are unchanged from RC3.
Do not change scale, GPU governor, shadows, texture or water flags between
measurements. Collect at least 20-30 seconds of stable gameplay at the same
large outdoor/water viewpoint, and provide the complete runtime log.
RC4 has source-level contracts only until GitHub Actions and device run pass.



RC5 GX/FIFO CPU PHASE PROFILER (2026-10-09)
RC4 map 8 revealed approximately 70-100 ms/frame BEFORE GL command submission.
The presenter itself used ~12-16 ms/frame; OpenGL submission ~20-27 ms/frame.
We must separate these wall-clock costs before changing any GX drawing logic.
RC5 adds [r36s-rc5-gx] per 3 seconds, breaking the prior pre_gx stage into:
- fifo_drain: process queued GX/GameCube FIFO instructions
- fifo_end: release FIFO/end-of-frame caches
- texture_end: texture cache, invalidations, stream housekeeping
- gfx_finish: settle/queue Aurora GX render passes
- frame_prepare: all remaining Aurora frame construction and GL prep
Compare the sum with [r36s-rc4-endframe] pre_gx in the SAME 3-second period.
RC4 [r36s-rc4-present] and [r36s-rc4-endframe] reports are retained.
RC5 makes NO intentional changes to drawing, output, water, reflections,
shadow masks, render-pass count, GL synchronization, or texture formats.
The same conf/rc4-profile.txt toggle applies (1 ON, 0 OFF). Default ON.
For a useful test, open the same large outdoor/water view and collect at
least 30 seconds of gameplay. Supply the full log.txt after exiting.
Source contracts alone do not confirm successful ARM build or runtime yet.

