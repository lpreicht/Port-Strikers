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
