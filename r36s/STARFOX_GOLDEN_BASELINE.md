# Star Fox Adventures R36S – Golden Baseline and Debug History

This file is the authoritative project state for the R36S Star Fox Adventures / Foxhollow port.
Do not replace the proven baseline with a broad rewrite when investigating one visual issue.

## Hardware / target

- R36S / RK3326 / Mali-G31
- ArkOS AeUX, aarch64
- 640x480 display
- Europe Rev 1 disc
- Native Foxhollow + Aurora ARM Direct-GLES path

## Golden baseline: V053 VISUAL-SAFE + PIPELINE-SAFE

V053 is the last proven baseline before the floor/reflection investigation.

Known-good architecture:
- Direct GLES renderer
- menu / intro EFB scale: 0.5 (320x240)
- gameplay EFB scale: 0.6667 (~427x320), presented at 640x480
- THP menu-fast RGBA decode
- menu-only THP catch-up, max 3 movie frames per retrace
- V039/V053 conditional cutscene real-time compensation: gameplay cap 6, scripted-sequence cap 10
- Direct-GLES pipeline correctness fallback
- blur feedback workaround
- Spirit Vision safe fallback
- 200 ms audio queue, controls, RVZ, save/load and Start+Select exit working

V053 preload chain was:
- libsfspiritfix.so
- libsfblurfix.so
- libsfthpcatchup.so
- libsfcutscenesync.so
- libsfpipelinewait.so
- libsfthpselect.so
- libsfscale.so
- system Mali

Representative V053 performance:
- title/menu EFB 5: roughly 2-4 ms during heavier title scenes
- gameplay EFB 5: roughly 0.17-1.0 ms
- no persistent 300+ ms Direct-GLES CPU stalls

Do not accept a new build as an improvement if it materially regresses these timings.

## Verified V053 package recovered on 2026-10-01

The original `starfoxadventures-r36s-v053-visual-safe.zip` is now available and was inspected directly.
It removes ambiguity about the old visual-safe behavior.

Verified runtime hashes from that package:
- `foxhollow.aarch64`: `a6e2733cbb161355dff22e917a18fac74b7f106dadf75206927b1779a5c43c6a`
- `libsfblurfix.so`: `517ff6444bc5216672b3b91bb97a8408ed5547682a335a39dd11f94ca462bab8`
- `libsfspiritfix.so`: `01cb97303fb855e95c0d4bc376c4bf9938903aa8a83911b32d30ff4e258bffb0`
- `libsfpipelinewait.so`: `c4a47617f0f723445defe88ec2da2edd6db7f6d03e1d124fea6435725c8fc53c`

Recovered visual-safe semantics:
- missing `GX_VA_CLR0/GX_VA_CLR1` defaults to white `vec4(1,1,1,1)`, not black
- `doBlurFilter` is suppressed globally
- `doSpiritVisionFilter` is bypassed only while a scripted sequence is active (`curSeqNo != 0`)
- mapped GL streams are enabled
- Direct-GLES pipeline correctness waiting is draw-local, not a generic blocking `get_pipeline()` wait

The clean GitHub build must implement these semantics in source rather than reusing the old
hard-coded V053 runtime hook addresses.

## Major progress before V053

### Early native builds
- Initial states included black screen/no audio and later image+audio with severe slowdown.
- Direct GLES around V034/V035 was the major performance breakthrough.
- RVZ/direct NOD DVD handling, CPU vertex decode, inline render worker, mapped streams,
  audio queue tuning and dynamic EFB scaling were accumulated and retained.

### THP / intro performance
- Menu-fast direct RGBA THP decode was proven useful.
- Menu-only THP catch-up was proven useful.
- Cutscene real-time compensation using timeDelta cap 10 was proven useful.
- These are baseline features, not optional experiments.

### V047-V053 visual safety
- Black sequence / feedback issues were addressed with the blur-feedback workaround.
- Spirit Vision / related cutscene fallback was added.
- Aggressive global render-state forcing during V049-V051 diagnostics caused visual regressions.
- Those aggressive state overrides were removed again.
- V053 became the visual-safe reference.


## 2026-10-01 hardware validation after source-level V053 recovery

Build `7cb0227213c94d36596b8a32966abfdcb64630b2` confirmed:
- black/temporarily missing character models are gone
- no Direct-GLES `pipeline-lookup` errors were observed in the submitted run
- water still flashes with incorrect colours
- reflective floor still flickers while moving
- gameplay and cutscenes still have performance drops; long cutscenes can accumulate audio lag

Additional clean-rebuild discrepancies found against the original V053 package:
- V039 cutscene sync had been reduced to a global cap-10 edit instead of the original cutscene-only elapsed-time compensation
- clean audio queue was 120 ms instead of V053's proven 200 ms
- Aurora ARM now performs adaptive heavy-scene driver re-probes even with `AURORA_GLES_DRIVER_PROBE=0`; use `AURORA_GLES_DRAW_BARRIER=0` to disable those diagnostics fully

These are baseline-restoration fixes, not reflection experiments. Do not change the reflection shader/path in the same validation build.


## 2026-10-01 recovery validation and GXCopyTex upstream parity

Build `5ec3dd62a2dccc0ff4109692b7037522b617a777` confirmed on R36S:
- German language is active and should remain the default
- cutscene/game audio is synchronized again with the restored 200 ms queue and V039/V053 timing
- character models remain stable; the black/missing-model regression is fixed
- some staff effects can still render partly black
- water is visually unstable and causes a severe performance drop when visible
- reflective materials/floor still flicker
- title/menu remains slow before the first memory-card load and improves somewhat afterwards

The submitted log contains no Direct-GLES pipeline-lookup failures, no pipeline-wait timeout and no Aurora driver-probe runs.
In water/effect-heavy maps, the dominant cost is total render/TEV workload rather than one isolated TexCopyConv pass.

A later upstream Aurora commit, `9c0bf66f1ed3276b60ad1cd746e2fb48818a6298` (2026-09-24,
"Partial GXCopyTex clears & proper GXSetDstAlpha"), landed after the ARM direct-GLES branch's last upstream merge.
The R36S fork still contains the pre-fix GXCopyTex behavior.

For the next isolated reflection test, carry only the relevant GXCopyTex correctness fixes:
- do not overwrite EFB alpha before resolving GXCopyTex
- partial `GXCopyTex(..., GX_TRUE)` clears must clear only the copied rectangle, not the whole EFB
- do not import the unrelated dual-source destination-alpha pipeline rewrite yet

This is one conceptual change surface: GXCopyTex upstream parity. Preserve all proven V053 visual/timing fixes.


### 2026-10-01 GXCopyTex parity hardware result

Build `74edeeb86ef520a97586655ad8258d224b57c235` was tested on R36S.

Result:
- German language remains correct
- audio remains synchronized
- character models remain stable
- water still flashes while walking; during scripted/cutscene presentation it is black but stable
- reflective floor/materials still flicker
- staff-end glow/smoke spheres remain black

The GXCopyTex upstream-parity fix is therefore retained as a correctness fix but excluded as the root cause.

Code correlation:
- water reflection, reflection/distortion materials and the staff reflection effect all use the dynamic
  `gNewShadowReflectionTexture` / indirect-TEV path
- scripted/cutscene frames can skip `updateReflectionTextures()` while HUD-hidden, matching the observed
  transition from dynamic flicker to static black
- `GXInvalidateTexAll()` is a no-op in Aurora and does not evict the dynamic GPU copy
- the reflection texture itself has no mip levels, so missing GXCopyTex mipmap generation is not the cause
- the three affected effects use indirect TEV / alpha-bump behavior

A second upstream Aurora correctness fix, `3840bf9ae735191026e4d4edb0ce6f24d91f7eea`
("Fix GX EFB alpha handling"), also landed after the ARM direct-GLES fork's last upstream merge.
The next isolated test ports only its independent pixel-format/alpha semantics:
- RGB EFB formats do not accept alpha updates
- DSTALPHA behaves as ONE when the EFB has no alpha
- INVDSTALPHA behaves as ZERO when the EFB has no alpha
- GX pixel-format changes invalidate the pipeline
- GXCopyTex alpha clear is gated by actual EFB alpha capability

Do not combine this test with reflection-size or render-pass-fusion changes.


### 2026-10-01 EFB-alpha hardware result and reflection-size test

Build `c1d733f70d227c6f658a8f1d3b98e3b894c6e6ad` was tested on R36S.

Hardware result:
- staff-end effect spheres remain black in the staff acquisition cutscene
- water still flashes while walking
- reflective floor/materials still flicker while moving
- German language remains correct
- character models remain correct and stable

The submitted run confirms the EFB-alpha backport is active but does not change the three unresolved visual symptoms.
On map 7 the renderer still drops to roughly 5.7-6.4 retraces/s with about 125-144 ms render time while
TexCopyConv itself remains around 1.6-1.8 ms averaged across the profiling window. This excludes EFB alpha as
the root cause and shows that the expensive state occurs after/around the reflection users rather than in one
isolated copy-conversion shader.

Source-level correlation:
- `updateReflectionTextures()` copies the full logical 640x480 EFB to two 320x240 targets every normal HUD-visible frame:
  RGB565 `gNewShadowReflectionTexture` and Z8 `gNewShadowReflectionTexture2`
- Aurora's render-scale path currently scales those destination targets again; at gameplay scale 0.6667,
  the physical GPU copy becomes about 213x160 while the GXTexObj remains logically 320x240
- water/reflection TEV code samples the RGB565 reflection target as its visible reflection source
- when HUD is hidden, the normal reflection update at lightmap.c:665-667 is skipped, but later glow rendering
  still runs; this precisely matches the observed cutscene-only static black staff-end spheres and suggests that
  the staff symptom may be a stale/unfilled reflection target rather than the same movement-flicker mechanism

Next isolated hardware test:
- preserve only the exact Star Fox 640x480 -> 320x240 RGB565/Z8 reflection pair at native logical destination size
- keep the gameplay EFB itself at 0.6667
- do not change cutscene reflection update policy, TEV math, pass fusion, audio, language, or model fixes

If water/floor behavior changes while the cutscene staff spheres remain black, treat those as two separate issues:
dynamic reflection scaling versus cutscene stale-target initialization.


### 2026-10-01 native 320x240 reflection-copy hardware result

Build `4c9bb18f45add43bea7e260a36ca09ee527adc51` was tested on R36S.

Hardware result:
- water still flashes exactly as before while walking
- reflective floor/materials still flicker while moving
- performance is effectively unchanged; at most subjectively a very small improvement
- staff-end effect spheres in the acquisition cutscene remain black
- German language and model stability remain intact

The log confirms the native-size path was active. In map 7 the port still falls from about 23 retraces/s immediately
after load to roughly 6.3-6.5 retraces/s with about 124-127 ms render time, while TexCopyConv is only around
1.8 ms. Later samples still reach about 5.5 retraces/s and 135 ms render time. Therefore the 320x240 destination
downscale mismatch is excluded as the visual root cause and provides no meaningful performance benefit.

Do not apply `starfox_reflection_native_size_patch.py` in subsequent builds unless a new reason appears.

### Next isolated test: GX indirect-TEV fixed-point parity

Source comparison against current Dolphin GX emulation found a concrete semantics gap:
- Dolphin quantizes generated TEV texture coordinates to 1/128 texel before indirect texturing
- Dolphin samples indirect textures back into integer 0..255 values
- Dolphin applies indirect TEV coordinate arithmetic in fixed-point form and explicitly emulates signed 24-bit
  coordinate accumulator overflow
- Aurora ARM currently carries these values through the corresponding path mostly as unrestricted floats

Star Fox's water and reflection/distortion materials make heavy use of `GXSetTevIndirect` with `GX_ITF_8`,
`GX_ITB_STU`, indirect matrices and bump-alpha channels, so camera movement can repeatedly cross the exact
quantization boundaries where the implementations differ.

Next test scope:
- restore normal scaled reflection-copy behavior (remove the prior native-size experiment)
- quantize the indirect-stage input coordinate to 1/128 texel
- quantize indirect texture samples to GX-style 8-bit values
- quantize/wrap the TEV indirect coordinate accumulator to signed 24-bit fixed point after each indirect stage
- leave copy format, EFB alpha, depth, pass fusion, language, audio, V053 visual safety and model fixes unchanged

This is a renderer-semantics test for water/floor movement flicker. Do not require the cutscene staff spheres to
change; those may be a separate generic glow/particle or HUD-hidden reflection-initialization issue.

## Floor / reflection investigation after V053

The unresolved symptom at V053:
- floor/ground flickers while moving
- later comparison to original gameplay strongly suggests this surface is reflective
  rather than simply lit incorrectly
- original presentation also suggests related reflective/compositing effects on meteorites
  and possibly later water effects

### V054 – Krazoa/light test
Result: no change.
Conclusion: simple lighting hypothesis not supported.

### V055 – global depth / lightmap single-pass test
Result: no change.
The intended lightmap helper marker did not activate.
Conclusion: no evidence that the tested lightmap mechanism caused the floor issue.

### V056 – polygon/depth-bias compatibility
Result: no change.
Diagnostic summary observed zero glPolygonOffset calls.
Conclusion: polygon offset is excluded for the tested scene.

### V057 – depth-range compatibility
Result: no visual change.
The helper changed 28,712 gameplay over-range depth calls.
Conclusion: depth-range values above 1.0 / clamping are not the floor cause.

### V058 – full texture-fetch/draw barrier diagnostic
Result: no visual change despite expensive synchronization.
Conclusion: ordinary EFB/read-after-write synchronization hazard is low priority.

### V059
The intended strict-depth diagnostic did not execute:
- depthfunc calls were observed
- changed=0
- gameplay=0
Conclusion: V059 is invalid as evidence.

### V060
Abandoned when the workflow was changed to clean GitHub builds.
Do not treat it as evidence.

## Clean GitHub rebuild mistakes – do not repeat

The clean GitHub effort introduced two independent performance regressions.

### Desktop GX_CTF_B8 16x16 blur port
A literal desktop-style 16x16 blur was ported into the Mali-G31 ARM renderer.
That can require up to 256 texture samples per output pixel.
Result: catastrophic EFB pass cost.
Conclusion: do NOT use the desktop B8 shader on R36S.

Keep Aurora ARM's fast B8 copy path unless a cheaper targeted approximation is designed and measured.

### Broad get_pipeline() wait
A generic 100 ms wait was added to get_pipeline().
This function is queried from preparation/planning paths as well as real draws.
Result:
- repeated ~300-360 ms Direct-GLES CPU blocks
- EFB 5 ballooned from sub-ms / few-ms to hundreds of ms
- intro and gameplay became effectively unplayable

Conclusion:
Never make generic get_pipeline() blocking.

If pipeline correctness waiting is needed, it must be limited to the actual Direct-GLES draw
that encounters an already queued asynchronous pipeline.

## Reflection work: allowed change surface

When testing reflection fixes, preserve the V053 performance architecture first.

Current low-risk reflection change:
- 8 MiB index stream instead of 2 MiB, matching newer Foxhollow planar-reflection requirements

Do NOT combine a reflection test with:
- desktop B8 blur
- global barriers
- broad pipeline blocking
- depth-range rewrites
- polygon offset rewrites
- aggressive GX color/light state forcing

One visual variable at a time.

## Acceptance order for every future build

1. Starts on R36S.
2. Intro performance is no worse than V053.
3. Gameplay performance is no worse than V053.
4. World does not progressively appear black / lose draws.
5. Character models and cutscenes remain visually stable.
6. Only then evaluate reflective floor / meteorites / water.

If steps 1-5 regress, revert the new change before continuing the reflection investigation.


### 2026-10-01 GX indirect fixed-point hardware result

Build `ff2de9646e4ede93eeca7ca5bd3b100c2afbbb2b` was tested on R36S.

Hardware result:
- water blinking while moving: unchanged
- reflective floor/material flicker while moving: unchanged
- overall rendering/models: unchanged
- performance: unchanged
- staff-end cutscene spheres: unchanged

The runtime log confirms the intended test was active: the build identifies the exact commit and reports the
GX-style 8-bit indirect samples, 1/128-texel coordinates and signed-24 accumulator wrap.

Conclusion:
The tested indirect-TEV fixed-point differences are not the root cause of the visible movement flicker. Remove
`starfox_indirect_fixedpoint_patch.py` from active builds. Keep it only as historical diagnostic evidence.

Performance remains a separate issue: map 7 still falls into roughly 4-6 retraces/s with render time well above
130 ms while TexCopyConv itself remains only a few milliseconds. The heavy state also shows large program and
pipeline-state churn, so copy conversion is not the dominant gameplay cost.

### Next isolated test: freeze the generated reflection pair

The next test changes Foxhollow rather than Aurora's reflection math:
- after a map-page change, allow exactly 8 normal calls to `updateReflectionTextures()`
- those calls build fresh RGB565 + Z8 reflection copies normally
- after the eighth update, return from `updateReflectionTextures()` and keep sampling the last valid pair
- reset this diagnostic automatically when `gCurRomListPage` changes
- leave reflection scroll/distortion animation, material TEV state, EFB alpha/copy correctness, render scale,
  depth, language, audio and V053 visual-safety behavior untouched

Interpretation:
- if water/floor movement flicker stops once the pair freezes, the live EFB-copy/update path is implicated
- if movement flicker continues unchanged with a frozen pair, the dynamic copy/update path is excluded and the
  fault is downstream in sampling/material/draw state
- the black staff-end spheres are not the primary criterion because HUD-hidden/cutscene update policy may be a
  separate issue


### 2026-10-01 reflection-freeze hardware result

Build `ec8d67fe42334875b5c4ceeaca29ca9f83fbed2d` produced the first decisive reflection result on R36S.

Observed on hardware:
- the previously flickering reflective floor became stable and looked good
- water stopped blinking, but became a permanently blue/static-looking surface and appeared no longer transparent
- staff-ball / screen-feedback effects also became blue instead of their normal glitter/smoke-like appearance
- performance still dropped heavily with water visible

Interpretation:
- stopping live `updateReflectionTextures()` updates removes the movement flicker
- the freeze itself is not a valid final fix because the RGB565 screen-feedback texture is reused by water,
  reflection, whirlpool/motion-screen effects, while the paired Z8 texture is used by distortion/depth-mask effects
- `GXInvalidateTexAll()` cannot explain the result in the pinned Aurora source because it is a no-op
- repeated `GXPixModeSync()` cannot explain it either: it rewrites PE control and unchanged BP writes are cached out
- therefore the live RGB565/Z8 EFB-copy handoff is now the primary correctness target
- water-area slowness remains separate: the hardware log shows very large draw/program/pipeline-state churn while
  TexCopyConv itself is only a small fraction of total render time

### Next isolated test: Dawn resolve -> direct-GLES handoff completion

Return `updateReflectionTextures()` to normal every-frame behavior. Do not freeze either texture.

Patch only the cross-API boundary in Aurora:
- Star Fox writes RGB565 then Z8; the Z8 resolve marks the end of the reflection pair
- tag the next game render pass after a Z8 resolve
- at the start of that pass, before either Aurora direct-GLES replay or Dawn fallback, issue one `glFinish()`
- do not enable global per-draw barriers and do not change reflection math, scale, alpha, depth or TEV
- log `[r36s-reflection-handoff]` when the diagnostic sync fires

Expected diagnostic:
- if dynamic water/effects return and movement flicker disappears, stale/incomplete Dawn->direct-GLES visibility is
  the root cause; replace glFinish later with the narrowest correct fence/barrier
- if flicker returns unchanged, the copy contents themselves are wrong rather than merely not complete/visible


### 2026-10-01 targeted reflection handoff sync hardware result

Build `c9f2f4831e75778860e837a867c9e23c5026af7c` was tested on R36S.

Hardware result:
- water returned to the original broken behavior: colorful blinking while moving
- reflective floor also returned to movement flicker
- water performance remained essentially unchanged
- user notes that water has never looked transparent in the R36S port, although original-game footage appears transparent

The runtime log confirms the targeted handoff diagnostic actually fired after the Z8 reflection resolve, including
in map 7. Therefore a simple incomplete/stale Dawn-copy -> direct-GLES visibility handoff is excluded as the
primary flicker cause.

Source-order review of `sceneDraw()` confirms Star Fox intentionally:
1. draws opaque scene/world/objects
2. calls `updateReflectionTextures()`
3. then renders particles, water and transparent scene geometry

This makes the screen reflection source timing in Foxhollow itself plausible.

Further source correlation:
- water reflection, reflection/distort materials and visible screen-feedback color all sample
  `gNewShadowReflectionTexture` (the RGB565 EFB copy)
- Z8 `gNewShadowReflectionTexture2` is used by separate depth/distortion paths and is not required to explain
  the observed water/floor color flicker
- `drawReflectionTexture()` draws the previous frame's RGB565 reflection texture back into the next frame with
  alpha 0x40 before a new reflection copy is captured, so this is a real frame-feedback loop

Aurora's `GX_TF_RGB565` conversion currently does not quantize to RGB565 at all: it copies full RGB precision
into an RGBA8 GPU texture and only forces alpha to 1.0. This differs from GameCube hardware semantics exactly in
a texture that Star Fox recursively feeds back.

### Next isolated test: true RGB565 copy quantization

Remove the failed handoff `glFinish()` diagnostic and restore normal live reflection updates.

Patch only `FragRGB565` in Aurora's EFB copy conversion:
- R -> round to 5 bits
- G -> round to 6 bits
- B -> round to 5 bits
- alpha remains 1.0
- destination GPU representation remains RGBA8; only the observable copied values change to GX RGB565 precision

Do not change Z8, reflection update cadence, render scale, TEV math, blend state, depth, audio, language or model fixes.

Interpretation:
- if movement flicker changes materially, RGB565 feedback precision is involved
- if it remains identical, restore the original shader and move to source-coordinate / blend-path investigation
- water transparency should be evaluated separately; Star Fox's water path explicitly uses SRCALPHA/INVSRCALPHA,
  so persistent opacity after reflection correctness is solved indicates an additional alpha/blend issue


### 2026-10-01 true RGB565 quantization hardware result

Build `5b1522e2d647af6d6be538028ab5c88415d95afa` was tested on R36S.

Hardware result:
- water still flickers
- reflective floor still flickers
- no reported visual improvement

The runtime log confirms the intended RGB565 quantization build was active. In map 7 the heavy-water state still
drops to roughly 5.7-6.6 retraces/s with about 116-126 ms render time, while TexCopyConv remains only around
1.8 ms. Therefore missing 5/6/5 color quantization is excluded as the primary flicker cause.

Remove `starfox_rgb565_quantization_patch.py` from active builds.

### Next isolated test: rotate the Star Fox RGB565 reflection copy across GPU images

Aurora's ordinary CPU-streamed textures already use a three-slot GPU texture ring specifically so a new upload
does not overwrite a texture that a queued frame still samples. EFB copy textures do not have equivalent
version isolation: `copy_tex()` reuses one cached GPU handle for a destination pointer and increments only a
revision counter.

This matters for Star Fox because:
- `drawReflectionTexture()` samples the previous RGB565 reflection early in the frame
- later in the same frame `updateReflectionTextures()` writes a new RGB565 EFB copy to the same GX destination
- water and transparent reflection materials then sample the newly written version
- the freeze test removed flicker, while completion barriers and RGB565 precision did not

Diagnostic:
- restore original Aurora RGB565 conversion
- keep normal every-frame reflection updates
- only for exact 640x480 -> 320x240, RGB565, clear=false Star Fox reflection copies, rotate through three
  independent GPU conversion textures
- publish the newly written slot as `copyTextures[dest]`
- earlier queued draws retain the older immutable GPU handle through their already-created bind groups
- leave Z8 and every other copy path unchanged

Expected:
- if flicker disappears while reflection remains dynamic, queued read/write aliasing of one GPU copy texture is
  the root cause
- if unchanged, the problem is in the actual copied source/content or later blend/material semantics
- a ring may also reduce Mali write-after-read stalls; observe water performance, but correctness is primary


### 2026-10-01 three-slot reflection ring hardware result

Build `8d2f987d275a065158447bd838254dd16c550f58` was tested on R36S.

Hardware result:
- water still blinks/flickers
- no reported improvement

The runtime log confirms the ring was active:
- branch commit matches the ring build
- menu reset created three slots
- map 7 reset created three RGB565 slots at the scaled 214x160 size
- revisions advanced through the ring (120, 240, 360...)
Despite this, the map 7 water state still falls into roughly 5.2-7.3 retraces/s with render time around 103-142 ms.

Conclusion:
Queued read/write aliasing of one RGB565 GPU texture is not the primary flicker cause. Remove
`starfox_reflection_ring_patch.py` from active builds.

Additional source review corrected an earlier assumption: in
`drawTexture(texture, 0, 0, 0xff, 0x40)`, 0xff is the alpha and 0x40 is the draw scale. The previous reflection
is therefore not intentionally faded to 25 percent by that call.

### Next isolated test: bypass previous-frame reflection feedback draw

Star Fox starts `sceneDraw()` with `drawReflectionTexture()`, which:
1. draws the previous large RGB565 reflection through the HUD-texture path
2. copies an 80x60 RGB565 region to the small reflection target with `GXCopyTex(..., GX_TRUE)`
3. continues with the fresh sky/world render
4. later captures the new 320x240 RGB565/Z8 reflection pair

The freeze test proved that holding the large reflection content constant stops the visible flicker. Ringing,
completion sync, destination size, RGB565 precision, indirect TEV fixed-point behavior and EFB alpha did not.

Diagnostic:
- bypass only the initial `drawTexture(gNewShadowReflectionTexture, ...)` call
- retain the 80x60 RGB565 copy and its GX_TRUE clear exactly as before
- retain normal live 320x240 RGB565 and Z8 reflection updates later in the frame
- restore ordinary Aurora copy texture allocation (no ring)
- do not change render scale, TEV math, alpha, depth, copy format or water material

Interpretation:
- if water/floor stop flickering while live reflection updates remain, the recursive previous-frame feedback path
  is the trigger
- if flicker remains unchanged, the newly captured reflection content itself or the later water/material sampling
  path is wrong


### 2026-10-01 previous-frame reflection feedback-bypass hardware result

Build `b8de312bcf633cbe8d679f5f83bbb5e5952bc665` was tested on R36S.

Hardware result:
- water still blinks while moving

The runtime header confirms the intended diagnostic was active: previous-frame large reflection draw bypassed, while
the small RGB565 copy/clear and the live 320x240 RGB565/Z8 updates remained enabled. In map 7 the same heavy water
state remained, around 5.6-7.6 retraces/s and roughly 96-145 ms render time.

Conclusion:
The recursive previous-frame reflection feedback draw is not the root cause. Restore it for subsequent builds.

Source review also narrows the water path:
- `setupWaterReflectionTev()` binds `gNewShadowReflectionTexture` (RGB565) through `selectReflectionTexture(0)`
- the Z8 reflection texture is not part of that water-reflection TEV setup
Therefore the live RGB565 reflection content or its water/projective sampling path is now the primary branch to split.

### Next isolated diagnostic: direct live-RGB565 overlay

Restore the normal reflection path and render `getReflectionTexture1()` directly as a 160x120 upper-left overlay
after scene rendering. The overlay uses the ordinary HUD texture draw and bypasses water/projective/indirect TEV.

Interpretation:
- overlay flickers while walking: the instability already exists in the EFB->RGB565 reflection copy/content
- overlay remains stable while water flickers: the copy itself is stable and the bug is in water/projective/indirect
  reflection sampling
This is diagnostic only; it does not change reflection format, scale, timing, TEV math, or copy allocation.


### 2026-10-02 direct live-RGB565 overlay hardware result

Build `220e659862b7417815d28669f4a90960d20edd16` was tested on R36S.

Hardware result:
- the direct reflection overlay flickers in exactly the same colors as the water

This is the strongest localization so far. The overlay samples `gNewShadowReflectionTexture` through the ordinary
HUD texture path and bypasses water projection, water indirect TEV, the water blend state, and water geometry.
Therefore the visible color instability already exists in the live RGB565 reflection texture/content itself.

The log confirms the intended build and diagnostic were active. In map 7, the same heavy reflection/water state
still reaches roughly 5.75-7.22 retraces/s with about 101-135 ms render time. TexCopyConv remains around 1.8 ms,
so conversion cost itself is not the dominant performance problem.

### Next isolated diagnostic: same EFB moment, RGB565 vs true RGBA8

Create one additional 320x240 RGBA8 diagnostic texture and capture it immediately after the normal RGB565
reflection copy and before Z8. Show both through the same simple HUD path:
- left: normal RGB565 reflection used by the game
- right: independent true-RGBA8 copy from the exact same EFB moment

Aurora normally maps no-alpha RGB EFB resolves to an RGB565 render target even for RGBA8 copy requests. For this
single exact 640x480 -> 320x240 RGBA8 diagnostic copy, force a genuine RGBA8 GPU target so the comparison is
independent.

Interpretation:
- both windows flicker identically: the instability is already in the EFB source/pass content or capture timing;
  RGB565 conversion is innocent
- only RGB565 flickers while RGBA8 is stable: the RGB565 copy/conversion path is the remaining correctness bug
- both stable while water flickers would contradict the previous direct-overlay result and require checking draw order


### 2026-10-02 RGB565 vs true-RGBA8 side-by-side hardware result

Build `b6c73fb5cf2ee060226a65d6ed215c631b3f22f0` was tested on R36S.

Hardware result:
- left normal RGB565 reflection and right independent true-RGBA8 reflection flicker identically
- both show the same changing colors

The log confirms the exact comparison build was active. Map 7 still enters the heavy state around 5.96-7.56
retraces/s with roughly 95-130 ms render time; the extra diagnostic copy increases pass count but does not change
the nature of the flicker.

Conclusion:
- RGB565 format/quantization/conversion is not the cause
- the wrong/changing image already exists in the EFB source selected for the live reflection resolve
- water/projective TEV is not the source of the color instability because the direct HUD overlays reproduce it
- remove the extra RGBA8 copy from active builds

The second `updateReflectionTextures()` in `sceneDraw()` is guarded by `bEnableDistortionFilter`. In the
current source that filter is activated by the Andross distortion effect, so it is not a strong explanation for
the normal Map 7 water case.

### Next isolated diagnostic: render only the reflection-source EFB pass through Dawn

Direct-GLES intercepts eligible Aurora render passes in Dawn's GL interop callback. The large reflection copy then
resolves that pass into RGB565. Test whether the source corruption is introduced by Direct-GLES itself:

- restore the normal single RGB565/Z8 reflection path
- retain one small direct RGB565 overlay for observation
- identify a pass with a full-target, large RGB565 resolve (the Star Fox 640x480 reflection source)
- in `encode_pass_resources()`, return false so Dawn records all GX draws normally for that pass
- in `prepare_frame()`, mark the same pass ineligible so the GL interop callback cannot intercept it at execution
- leave every other pass on Direct-GLES

Interpretation:
- reflection overlay becomes stable: Direct-GLES rendering/interop of the source EFB pass is the root correctness bug
- unchanged flicker: the problem is above Direct-GLES, likely pass/source selection or GXCopyTex continuation semantics
This test may be slower; correctness is the only goal.


### 2026-10-02 Dawn-only reflection source pass hardware result — correctness confirmed

Build `dcdfa71a3819020167321980153051f5ae79d7a8` was tested on R36S.

Hardware result:
- water is rendered correctly
- the live reflection overlay is also correct
- the previously wrong staff-end effect is not visible
- performance is noticeably worse

This is the first fully correct live-reflection result and localizes the bug to the Direct-GLES rendering/interop of
the large EFB pass that immediately feeds the RGB565 reflection copy.

The runtime log confirms the exact diagnostic was active. The source pass is forced through Dawn at scaled sizes
such as 427x320 in map 7. The pass becomes Direct-GLES-ineligible and can contain well over 100-200 GX draws.
Render time can climb to roughly 175-215 ms in heavy map 7 windows, so the slowdown is primarily the full Dawn
fallback, not the small diagnostic overlay.

### Next isolated test: publish Direct-GLES framebuffer writes before Dawn reflection resolve

Restore the large reflection-source pass to Direct-GLES for performance. Mark only full-size large RGB565 resolves
in the Direct-GLES pass plan. At the end of that pass, before Dawn executes the resolve, issue:

`glMemoryBarrier(GL_FRAMEBUFFER_BARRIER_BIT | GL_TEXTURE_UPDATE_BARRIER_BIT | GL_TEXTURE_FETCH_BARRIER_BIT)`

Keep one small live reflection overlay for verification.

This specifically tests the newly localized direction of the interop problem:
Direct-GLES framebuffer writes -> subsequent Dawn GXCopyTex read.

This is distinct from the earlier failed handoff test, which synchronized after the reflection resolve before the
next Direct-GLES sampling pass.

Interpretation:
- correct reflection with much better performance: keep the targeted publish barrier and remove the overlay
- flicker returns: the visibility operation is stronger than a memory barrier; next test targeted glFinish at the
  same pre-resolve boundary, not a broad/global finish


### 2026-10-02 targeted framebuffer/texture memory-barrier hardware result — insufficient

Build `070d591a9164bd4d3cf5bea174ddecfbeff5822b` was tested on R36S.

Hardware result:
- water is again rendered incorrectly / flickers
- the runtime confirms the targeted Direct-GLES reflection publish path is active
- the publish hook fires for the large RGB565 resolve at scaled sizes including 320x240 and 427x320

Conclusion:
- `glMemoryBarrier(GL_FRAMEBUFFER_BARRIER_BIT | GL_TEXTURE_UPDATE_BARRIER_BIT | GL_TEXTURE_FETCH_BARRIER_BIT)`
  is not sufficient for this Mali-G31 Direct-GLES -> Dawn EFB handoff
- the earlier Dawn-only source-pass result remains the correctness control: when the same source pass is kept out of
  Direct-GLES, water/reflection and the staff-end effect are correct
- do not reopen RGB565 conversion, EFB alpha, water TEV, lightmap, polygon-offset or generic barrier hypotheses

### Next isolated diagnostic: targeted glFinish at the same handoff

Keep the large reflection-source pass on Direct-GLES for performance, but replace only the failed targeted memory
barrier with `glFinish()` immediately after replaying that full-size RGB565 resolve source pass and before Dawn
performs GXCopyTex.

This is deliberately localized:
- no global `glFinish()`
- no broad per-pass finish
- all unrelated Direct-GLES passes remain unchanged
- mapped streams, V053 visual-safety fixes, audio queue, timing and current GXCopyTex/EFB semantics remain unchanged

Interpretation:
- correct water/reflection: Mali needs completion, not only memory visibility, at the Direct-GLES -> Dawn boundary
- incorrect water/reflection: Direct-GLES source rendering itself differs from Dawn; the next fix must keep a selective
  Dawn fallback or split/replace the problematic Direct-GLES pass rather than add more synchronization


### 2026-10-02 targeted glFinish hardware result — no effect

Build `2853c69fe093e6e5294de6ceca9f035d440fe596` was tested on R36S.

Hardware result:
- water continues to flicker exactly as before

Conclusion:
- explicit GPU completion at the Direct-GLES -> Dawn RGB565 resolve boundary is not the missing requirement
- both the targeted memory barrier and targeted glFinish hypotheses are closed
- the Direct-GLES rendering of the source pass itself differs semantically from Dawn

### Next isolated diagnostic: restore dynamic GX state after reflection-pass clear

Source review found a concrete Direct-GLES semantic mismatch. `render_clear()` changes:
- viewport to the full render target
- depth range to `d.depth, d.depth`
- scissor to the full render target

It invalidates fixed-function pipeline memos, but it does not restore those three dynamic states before subsequent
draws. The large RGB565 reflection source pass contains both a GX clear and many subsequent GX draws.

Test:
- keep the reflection-source pass on Direct-GLES
- remove the failed targeted glFinish
- track the most recent GX viewport/depth range/scissor while replaying that pass
- immediately after a GX clear, restore those dynamic states
- leave all unrelated passes and renderer settings unchanged

Interpretation:
- water/reflection correct: Direct-GLES clear-state leakage was the root source-content bug
- water/reflection still wrong: keep the Dawn-only correctness baseline and continue comparing Direct-GLES state
  semantics against Dawn rather than synchronization/copy-format hypotheses


### 2026-10-02 reflection clear-state restoration hardware result — no effect

Build `aa78786aa10e760b8c57ab74642f12f6053d4a82` was tested on R36S.

Hardware result:
- water still flickers
- the live upper-left reflection overlay still flickers in the same way
- the runtime confirms viewport/depth-range/scissor restoration executes on the relevant 427x320 reflection pass
- no Direct-GLES runtime errors are reported

Conclusion:
- dynamic-state leakage from the GX clear is not the root cause
- because the direct overlay and water still match, the bad/changing content remains upstream in the reflection-source EFB pass
- remove the live reflection overlay from subsequent builds; it has completed its diagnostic purpose

### Next isolated diagnostic: real glClear for reflection-source GX clear

Direct-GLES normally emulates GX clears by drawing a fullscreen triangle. Aurora already contains a diagnostic
`AURORA_GLES_CLEAR=gl` path specifically for drivers that can mishandle the triangle's tile coverage.

Test only the reflection-source pass:
- keep Direct-GLES for the full pass
- keep the tested viewport/depth-range/scissor restoration
- use real `glClear()` instead of the fullscreen-triangle clear only when the large RGB565 reflection-source pass clears
- remove the upper-left live reflection overlay
- leave every unrelated pass and performance setting unchanged

Interpretation:
- water correct: the Direct-GLES triangle-clear path is corrupting/staling the reflection source on Mali-G31
- water still flickers: clear implementation is excluded and the next split should target Direct-GLES draw/resource semantics


### 2026-10-02 reflection-source real glClear hardware result — no effect

Build `b40c86f871372c8ded0d2106d338df49e2548aae` was tested on R36S.

Hardware result:
- water still flickers
- the runtime confirms real `glClear()` executes for the large RGB565 reflection-source pass
- the runtime also confirms the prior viewport/depth-range/scissor restoration executes
- on map 7 the large Direct-GLES source pass remains very busy (333 GX draws + one clear in the sampled frame)

Conclusion:
- the Direct-GLES GX clear implementation is not the root cause
- clear-state restoration is also not the root cause
- remove both diagnostics from the active reflection test path

### Next isolated diagnostic: Dawn-style GL sampler objects inside reflection source pass

Aurora Direct-GLES normally copies sampler state onto the texture object. The source explicitly provides the
alternative `AURORA_GLES_TEXTURE_SAMPLERS=0` behavior because some drivers can apply texture parameters lazily.

Test:
- return clear handling to the normal Direct-GLES path
- remove the clear-state diagnostic
- keep the reflection source pass on Direct-GLES
- only while that pass is replayed, bind Dawn's real GL sampler objects instead of carrying sampler state on textures
- all other Direct-GLES passes retain the current fast texture-object sampler path
- no live reflection overlay

Interpretation:
- water correct: stale/lazy texture-object sampler state on Mali-G31 is corrupting the reflection source render
- water still flickers: sampler binding is excluded; next isolate vertex binding API, then indexed draw API


### 2026-10-02 reflection-source Dawn sampler-object hardware result — no effect

Build `8da369debbc6d4bd45955562bf80e93552d4a336` was tested on R36S.

Hardware result:
- water still flickers
- runtime confirms Dawn GL sampler objects are active in the reflection-source diagnostic
- sampler-bind call counts rise substantially, proving the alternate resource-binding path is exercised
- map 7 remains reflection-heavy, with roughly 314 GX draws in the sampled large source pass

Conclusion:
- texture-object sampler-state laziness / sampler binding is not the root cause
- remove the sampler-object diagnostic from the active test path

### Next isolated diagnostic: Dawn-style vertex pointer API in reflection source pass

Aurora Direct-GLES normally uses the ES 3.1 vertex binding API:
- `glBindVertexBuffer`
- `glVertexAttribFormat` / `glVertexAttribIFormat`
- `glVertexAttribBinding`

Aurora already provides `AURORA_GLES_VERTEX_API=pointer` as a diagnostic because some drivers can mishandle
binding offsets. Dawn's GL backend-style path instead uses:
- `glVertexAttribPointer` / `glVertexAttribIPointer`
- `glVertexAttribDivisor`

Test only the large RGB565 reflection-source pass with the pointer API. Invalidate the cached VAO binding state
on entry/exit so surrounding normal Direct-GLES passes are rebuilt correctly. No sampler, clear, barrier or overlay
diagnostic remains active.

Interpretation:
- water correct: Mali-G31 vertex binding offsets/state in the fast ES 3.1 path are corrupting the reflection source
- water still flickers: vertex binding is excluded; next isolate indexed draw API


### 2026-10-02 reflection-source vertex-pointer hardware result — no effect

Build `a82bbf38d1df81f1a11c1f3568b50a0bca494603` was tested on R36S.

Hardware result:
- water flicker is unchanged
- runtime confirms Dawn-style `glVertexAttribPointer` is active in the relevant 427x320 reflection-source pass
- the sampled map-7 source pass still contains roughly 294 GX draws plus one clear
- performance remains in the same severe reflection-heavy range

Conclusion:
- ES 3.1 vertex binding offsets/state are not the root cause
- remove the vertex-pointer diagnostic from the active path
- `sortOpaqueDraws` is not a candidate in this build: Aurora documents it as off by default and Foxhollow's
  R36S config does not enable it

### Next isolated diagnostic: plain indexed draws in reflection source pass

Direct-GLES normally uses `glDrawRangeElements` for single-instance indexed draws. Aurora already exposes
`AURORA_GLES_INDEX_DRAW=plain|instanced` specifically to diagnose driver differences in range-index handling.

Test only the large RGB565 reflection-source pass with plain `glDrawElements`; all other passes keep the current
`glDrawRangeElements` path. No sampler, clear, vertex-pointer, barrier or overlay diagnostic remains active.

Passive diagnostic added in the same build:
- if the reflection-source pass encounters `GX_BM_LOGIC`, log the concrete GX logic op once
- this does not alter rendering and will tell us immediately whether Direct-GLES's incomplete logic-op emulation
  is relevant if the indexed-draw test fails

Interpretation:
- water correct: Mali-G31 range-index handling is corrupting the reflection-source pass
- water still flickers: indexed draw API is excluded; inspect the passive logic-op evidence next


### 2026-10-02 reflection-source plain indexed-draw hardware result — no effect

Build `c7b104d98d6423dd7023c9d9f665e8e99aab64b2` was tested on R36S.

Hardware result:
- water flicker is unchanged
- runtime confirms plain `glDrawElements` is active for the reflection-source diagnostic
- the sampled map-7 reflection source reaches roughly 355 GX draws plus one clear
- no `[r36s-reflection-logic]` marker appears anywhere in the hardware log

Conclusion:
- `glDrawRangeElements` / index-range handling is not the root cause
- GX logic-op emulation is not relevant to this scene
- remove the indexed-draw and logic-op diagnostics from the active path

### Next isolated diagnostic: Direct-GLES with Dawn-backed frame streams

The strongest remaining structural difference is how Direct-GLES consumes per-frame data:
- normal Direct-GLES binds uniform, vertex and index data from persistently mapped GL buffers
- the known-correct Dawn fallback consumes the normal Dawn/WebGPU buffers

Test:
- keep the large RGB565 reflection-source pass on Direct-GLES
- preserve the normal fast mapped-stream path for every other Direct-GLES pass
- force the frame's vertex/index/uniform streams to be uploaded to Dawn buffers
- only while replaying the reflection-source pass, bind Dawn's GL-interop vertex/index/uniform buffers
- keep pipelines, texture binding, draw calls, clears and all other Direct-GLES semantics unchanged

Interpretation:
- water correct: Mali-G31 mapped-stream coherency/visibility under the heavy reflection pass is the source corruption
- water still flickers: mapped streams are excluded; the remaining mismatch is Direct-GLES fixed-function/dynamic
  state or command semantics rather than frame-buffer transport
