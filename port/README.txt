SUPER MARIO STRIKERS R36S V0.7 FINAL CANDIDATE

Native AArch64 / PortMaster adaptation for RK3326 / Mali-G31 handhelds (ArkOS).

GAME DATA IS NOT INCLUDED.

Copy your own legally dumped USA Super Mario Strikers disc image (G4QE01) to:
  ports/strikers/assets/Super Mario Strikers (USA).iso

R36S-specific fixes included:
  - native OpenGL ES / Mali-G31 renderer path
  - Cortex-A35 CPU vertex decoding
  - stable native ALSA audio with extra MusyX buffering
  - lower-cost audio resampling for high-voice matches
  - correct character rendering in goal replays / cutscenes
  - lightweight replay-end transition to avoid the final replay hitch
  - Start + Select exits cleanly back to PortMaster / ArkOS
  - persistent Dawn/Aurora pipeline caches
  - learned pipeline cache promoted to initial_pipeline_cache.db for the next launch
  - two background pipeline compiler workers

Expected behaviour:
  - Gameplay, audio and goal replays should be fully playable.
  - The first visit to a stadium can still show some progressive geometry/shader warm-up on RK3326.
    Repeated visits should improve as the cache fills.
  - Do not delete ports/strikers/runtime/cache/direct-gles-v1/ unless troubleshooting.

Known limitation:
  - THP movie decoding is not included in this build, so pre-rendered movie files are skipped.

Controls:
  - Start + Select: exit the port cleanly

If troubleshooting, attach:
  ports/strikers/log.txt
  ports/strikers/strikers-log.txt
