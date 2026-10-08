# R36S shadow copy recovery, 2026-10-08

Starting point: `e9aeef6f6c862168ac4492c61c530d1d36d7f9e9`, branch
`starfox-performance-recovery`. The original `starfox-native-build` branch stops
at V035 and is not the latest development state.

The authoritative history in `STARFOX_GOLDEN_BASELINE.md` and the final uploaded
device log establish that the global Dawn uniform buffer fix corrected water
and model materials. The last uploaded device log uses `10989ab8`, with full
Dawn shadow-source passes, and still exhibited moving shadow flicker. No device
result for the subsequent `e9aeef6` pass-barrier test was retrieved.

## Concrete defect

Foxhollow upstream commit
`1d3042e6ef6f606bb0ad48a7fa5ed3dd8c0293d5` (2026-10-03, “Fix shadows in Aurora”)
separates the clipped clear rectangle from the unclipped sampling rectangle.
The ARM fork still derives copy UVs from the clipped rectangle. For the game's
512x512 shadow source and a 427x320 EFB, this changes the sampling height from
342/320 to 320/320 and stretches the valid region over the entire destination.

The backport preserves the requested extent, returns black outside color EFB
bounds and maximum GX depth outside depth bounds. Clears remain clipped. The
ARM-specific pass fusion refuses partial copies; ordinary in-bounds fusion is
retained. No desktop B8 blur shader or renderer upgrade is imported.

## Validation and packaging

`tests/test_shadow_copy.py` compiles the actual mapper and UV-transform code
with controlled framebuffer dimensions. It failed on the starting source for
512x512 and negative-origin copies, then passed after the patch. It also covers
full-frame and interior copies and preserves scissor/native policy behavior.
`tests/test_present_contract.py` remains the presentation regression check.

RC1 retains all existing baseline settings, including the last diagnostic
Dawn shadow fallback and pass barrier, so only copy semantics change. It is a
complete PortMaster package, but not a hardware-validated final release.
The remaining device gate is a repeated moving-shadow, water, cutscene,
save/load and clean-exit check, including a performance comparison.

Source: https://github.com/JackPriceBurns/foxhollow/commit/1d3042e6ef6f606bb0ad48a7fa5ed3dd8c0293d5
