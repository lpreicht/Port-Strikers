# Super Mario Strikers native port for R36S / PortMaster

Experimental PortMaster adaptation of the native [new-coke/strikers](https://github.com/new-coke/strikers) port for AArch64 handhelds such as the R36S (RK3326 / Mali-G31).

## Current target

The first build is deliberately a bring-up build:

- Strikers 1.2.0 game code
- AArch64 / Cortex-A35 baseline
- GLIBC 2.30 ceiling for ArkOS compatibility
- OpenGL ES through the Mali driver
- Aurora/Dawn PortMaster work reused from the native Melee port
- SDL3-over-SDL2 shim so the CFW's SDL2 owns display, audio and controllers
- 640x480 / 4:3 defaults
- no copyrighted game data is included

The player supplies their own legally dumped **USA G4QE01** disc image as:

    ports/strikers/assets/Super Mario Strikers (USA).iso

This repository only contains build/packaging glue and patches. It does not contain Nintendo game data.

## Status

V0.1 is a compile-and-package probe. First goal: produce an ArkOS-loadable AArch64 executable and PortMaster zip. Device-side rendering, audio, controls and performance are validated after that.
