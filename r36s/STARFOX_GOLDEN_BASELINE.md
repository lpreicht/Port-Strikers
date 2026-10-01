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
- conditional cutscene timeDelta cap 6 -> 10
- Direct-GLES pipeline correctness fallback
- blur feedback workaround
- Spirit Vision safe fallback
- audio, controls, RVZ, save/load and Start+Select exit working

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
