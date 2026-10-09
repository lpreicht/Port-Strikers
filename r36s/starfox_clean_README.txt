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



RC6 SAFE GX PER-DRAW PROFILING COST A/B (2026-10-09)
From the confirmed RC5 device log: map 8 median 7.43 FPS; GX FIFO drain
50.14ms / frame, Aurora frame_prepare 15.84ms / frame, submit 21.65ms / frame.
The current command_processor.cpp hashes draw keys and full pipeline
configurations and inserts them into diagnostic hash maps on each GX draw
when renderStats=true. RC6 skips ONLY this optional statistics work.
No GX pipeline, draw batching, shader, vertex decode, texture, water,
EFB copy, shadow or presentation semantics have been altered.

DEFAULT: starfoxadventures/conf/gx-heavy-stats.txt missing or containing 0
  -> R36S_GX_HEAVY_STATS=0 -> skip per-draw statistics hashing (RC6).
CONTROL: write a single 1 to conf/gx-heavy-stats.txt
  -> R36S_GX_HEAVY_STATS=1 -> original RC5 per-draw diagnostics.
Leave rc4-profile.txt=1 and compare the same water/outdoor viewpoint
on 0 vs 1, using [R36S V025 timing] and [r36s-rc5-gx] fifo_drain
medians. Stats lines [gx-batch] still report merged draw counts;
[gx-variance] is expected to show 0 entries when heavy stats=0.
If there is no measurable gain, restore 1 and investigate vertex
decoder or texture resolve timing in a subsequent independent test.

The source contract checks and GitHub CI do not prove device FPS gains.
Preserve game data, save data, shadows, decals and reflective water.



RC7 OPTIONAL KMSDRM DISPLAY PACING A/B (2026-10-09)
RC6 Map 8 median interval FPS improved from RC5 ~7.43 to ~9.19 (+24%),
and GX FIFO drain time dropped ~49.85 -> ~25.37ms. This comparison
covers differing views and does not replace controlled A/B measurement.
The remaining SDL_GL_SwapWindow call often costs ~14-16 ms/frame,
and sometimes more, despite other stages still being expensive.
RC7 requests EGL/SDL swap interval 0 to test the extra page-flip pacing.
This can cause visible tearing and may be ignored by the RK3326 driver.
It does NOT alter the producer/presenter EGL fences or render commands.
All RC5 GX phase and RC4 presenter timings remain enabled.

A/B config file under existing starfoxadventures/conf:
  swap-interval.txt missing or single line 0 = RC7 experimental uncapped
  swap-interval.txt single line 1 = RC6 original synchronized presentation
For controlled A/B compare same Map 8 scene and similar camera orientation,
20-30 seconds each. Compare [r36s-rc4-present] swap= and
[R36S V025 timing] retraces/s, rendering time, and tearing/visual glitches.
The log header R36S_SWAP_INTERVAL= shows the requested setting;
startup [INFO] confirms an SDL request, not necessarily driver acceptance.
If image tearing or new glitches occur, set 1 and restart.
Keep gx-heavy-stats.txt = 0 (RC6 fast path), rc4-profile.txt=1,
render-scale.txt=0.6667, and all existing visual safety flags unchanged.
Do not remove user gamedata or conf. Device performance is not verified
until the new build runs successfully.



RC8: SAMPLED GX CPU HOT-PATH PROFILING (2026-10-09)
Hardware-tested RC7 showed map 8 interval median ~10.16 FPS
(vs RC6 ~9.19), GX fifo_drain ~21.29ms, Dawn submit ~22.10ms
and SDL swap ~12.65ms (views not perfectly matched).
SDL request=0 was accepted by SDL, but tearing and VSync-on control
have not yet been tested. Do not interpret as a proven swap advantage.

The upstream Aurora sampled deep profiler is compiled in for RC8;
AURORA_DEEP_PROFILE=1 and AURORA_DEEP_INTERVAL=60 enable detailed
timing for only each 60th frame, avoiding RC5 heavy 10k-draw/frame
statistics overhead. New added scopes:
  vertex_upload_decode (CPU GX vertex preparation)
  index_generate (GameCube primitive index list preparation)
Existing nested Aurora scopes: fifo_process, draw_prepare,
pipeline_build, texture_resolve_bind, uniform_build.

Run game for >60 game frames in the same outdoor Map 8 water view.
For more reliable samples, test a few minutes and send complete log.
Look for [deep-profile] frame=... lane=fifo lines and compare
wall_us/self_wall_us/calls for the work zones, in addition to
[r36s-rc5-gx] and [R36S V025 timing].
Conf toggles:
  deep-profile.txt 0 -> disable sampled deep profiler
  deep-profile.txt 1/missing -> enable sampled deep profiler
  gx-heavy-stats.txt 0 -> KEEP RC6 speed optimization
  swap-interval.txt 0 -> RC7 uncapped presenter experiment
  swap-interval.txt 1 -> RC6 synchronized presenter (A/B control)
No changes to GX graphics semantics, EFB, water, shadows or controls.
Build success and on-device runtime are not established until tests.



RC9 REVERSIBLE TINY GX TRIANGLE/QUAD INDEX OPTIMIZATION (2026-10-09)
RC8 source/hardware log contains >13,000 lines from sampled deep profiling;
map 8 interval median ~9 FPS, frame=720 FIFO ~126ms with 18,386
draw-prepare calls. Of these, vertex upload/decode ~34.81ms and index
generation ~10.46ms in one expensive sample (NOT frame averages).
RC9 uses direct index array appends for 3-vertex GX triangles and
4-vertex GX quads, preserving byte-identical winding and index order.
All other primitive sizes, merged base offsets, resident display lists,
water/texture/render passes, shadow masks and EFB copies are unchanged.
No GL state or synchronization change from RC7. Intended to remove
many tiny index construction loops; real FPS benefit not yet measured.
Runtime A/B switch in existing conf folder:
  fast-gx-indices.txt absent or single line 1: RC9 exact-index fast path
  fast-gx-indices.txt single line 0: original RC8 index generation
deep-profile.txt now defaults to 0 to avoid emitting thousands of
per-draw statistics lines; set it to 1 for further sampling if needed.
Keep gx-heavy-stats.txt=0, swap-interval.txt as preferred, and
render-scale.txt=0.6667 for comparable runs.
Benchmark same view of map 8 looking at water for 30-60 seconds with
fast-gx-indices 1 and 0; compare [R36S V025 timing] retraces/s,
[r36s-rc5-gx] fifo_drain, and [r36s-rc4-endframe] submit.
Do not delete gamedata/conf or existing memory card/save data.



RC10 AUTOMATIC CPU GEOMETRY PREPARATION OPTIMIZATION (2026-10-09)
RC9 on R36S (map8, 29 timing windows): median retraces/s 9.00,
GX FIFO drain 24.25ms, OpenGL submit 22.20ms. RC7 in its own
slightly different scenes: 10.16 retraces/s, 21.29ms FIFO drain,
22.10ms submit. RC9's tiny 3/4 vertex index fast path did not
demonstrate a clear improvement, and no direct A/B is necessary.

RC8's sampled frame 720 showed 18,386 draw_prepare calls within one
rendered frame, about 34.8ms in vertex decode and 10.5ms in index
generation. RC10 extends single-allocation, sequential index writes
to GX_TRIANGLES and GX_QUADS with more than 3/4 vertices, using exact
original u16 byte order, winding and wrap semantics. For draw batches,
prepare_draw_state already resolves GX pipeline: RC10 avoids a
redundant prepare_pipeline check in the subsequent vertex decode call.
Other push_decoded_verts call sites keep original preparation.

Full deep-profile instrumentation is now compiled OUT of the optimized
release build to remove its overhead. Existing RC6 heavy stats OFF,
RC7 presenter config and render correctness patches are preserved.
All defaults are automatic. DO NOT ask user to edit numeric 0/1
settings for comparison; user only installs the GitHub ZIP, plays in
the water/outdoor scene and uploads one log.
Preserve existing user files gamedata/, conf/, memory card and saves.
No performance gain or image correctness is claimed until real R36S
hardware validation after successful GitHub build.



RC11 AUTOMATIC VERTEX LOADER REUSE (2026-10-10)
On-device RC10 in the outdoor map 8 measured median 9.64 retraces/s
(32 windows), GX fifo_drain 20.71ms, GLES submit 21.40ms,
render 72.81ms. Prior RC9 same area median 9.00 retraces/s
(29 windows), GX 24.25ms, submit 22.20ms, render 79.05ms.
Different camera angles and loads; this is suggestive, not a
controlled A/B measurement.

RC8 deep profiler highlighted vertex_upload_decode (~34.8ms in
one high-load frame). Aurora vertex_loader() hashes the entire
attribute format on EVERY draw to find the VertexLoader. RC11
reuses the cached loader when the already-resolved GX pipeline ref
has not changed. The pipeline hash includes all shaderConfig vertex
layout attributes, and VertexLoader objects are heap-stable
under Aurora's unique_ptr cache. Every pipeline change triggers the
original vertex_loader(config) lookup; non-batch callers are unchanged.
No GL shader, EFB/shadow/water, vertex decoding arithmetic, texture
coordinates, control or presenter changes.

Performance improvements are hypotheses until the GitHub build passes
and a hardware log from R36S confirms them. Users do not need to edit
config flags or run A/B comparisons. Install the latest successful
GitHub PortMaster ZIP, play outdoor/water scenes, upload the log.
Keep gamedata, conf, saves and memory cards untouched.


RC12 MULTI-PIPELINE VERTEX LOADER CACHE (2026-10-10)
RC11 on the R36S in map 8 measured median 10.71 retraces/s,
GX fifo_drain 14.35ms, GLES submit 21.40ms, renderer 65.64ms
(20 timing windows). RC10 measured 9.64 retraces/s,
GX fifo_drain 20.71ms, submit 21.40ms, renderer 72.81ms
(32 timing windows). Camera views and loads vary; not a
controlled matched-frame A/B.

RC11 only cached the immediately prior GX pipeline. RC12 adds
256 direct-mapped entries (4 KiB) to reuse decoded vertex loader
pointers across alternating GX pipeline refs, including across
frames. Every cache hit checks the ENTIRE 64-bit pipeline hash.
A collision/miss invokes Aurora's original vertex_loader(config).
The vertex loader objects are stable heap allocations; no shader
or geometry bytes, uniforms, render passes, water, shadow or
EFB copying has changed. Only batch_draw uses this cache;
all other rendering paths use Aurora's original lookup.

Build and actual performance still require real hardware
verification. Everything is preconfigured automatically; users
only install the successful GitHub ZIP, run the game in the
outdoor water area and send their log. Do not request manual
0/1 config editing. Keep gamedata/conf/saves intact.


RC13 DIRECT GX INDEX STREAM (2026-10-10)
On-device RC12 map8 median retraces/s 11.30, fifo_drain
14.91ms, frame_prepare 12.91ms, submit 20.70ms and
renderer 62.82ms over 18 measurement windows.
Prior RC11 map8 median 10.71 fps, 14.35ms GX,
13.51ms preparation, 21.40ms submit, 65.64ms render
over 20 windows. Camera/scene differences prevent attributing
the observed difference conclusively to the pipeline cache.

RC13 skips one ByteBuffer scratch write plus one index-stream copy
for ordinary GX_TRIANGLES and GX_QUADS (1..8192 vertices) by
reserving their EXACT index count directly in the existing mapped
frame index stream, preserving GX winding, 16-bit wrapping, unusual
partial quad behavior, alignment and GX merged index base.
All indexed/points/lines/fan/strip/resident draws continue the
proven original ByteBuffer+push_indices code. Aurora mapped GL
frame-stream infrastructure itself is unchanged; no water, shadow,
EFB, shader, GL synchronization or control alterations.

RC13 build and R36S hardware performance/safety are pending until
confirmed. No user 0/1 settings or manual A/B tests. Install only a
successful GitHub ZIP, play at the water outdoor scene, send one log.
Preserve gamedata/conf/memorycard/saves.
