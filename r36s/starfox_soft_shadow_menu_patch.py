#!/usr/bin/env python3
"""R36S: avoid R4 shadow alpha quantization shimmer; cap synchronous THP catch-up.

Soft shadow conversion keeps GX_CTF_R4 output texture layout and all copy
sizes/targets unchanged. It simply retains the GPU source's continuous
8-bit red signal instead of rounding to 16 steps before world-space
projective sampling. No additional texture fetches.

Menu catch-up previously reads/decompresses up to two stale THP audio frames
before rendering the current frame on the game thread, worsening stalls on
the RK3326. Cap that synchronous catch-up at one. This does not affect THP
decoding in gameplay/cutscenes or discard EFB passes.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
conv=root/"extern/aurora/lib/gfx/tex_copy_conv.cpp"
s=conv.read_text()
old="""// GX_CTF_R4: 4-bit red -> R8Unorm
static constexpr std::string_view FragR4 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let r = quantize4(textureSample(src, src_samp, in.uv).r);
    return vec4f(r, r, r, r);
}
)"sv;"""
new="""// GX_CTF_R4 (R36S): retain source alpha precision for stable projected shadows.
// The original 4-bit quantization exaggerates small frame-to-frame changes
// when the lower-resolution (scaled EFB) shadow mask is reprojected.
static constexpr std::string_view FragR4 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let r = textureSample(src, src_samp, in.uv).r;
    return vec4f(r, r, r, r);
}
)"sv;"""
if s.count(old)!=1:
    raise SystemExit(f"R4 conversion shader anchor mismatch: {s.count(old)}")
conv.write_text(s.replace(old,new,1))

thp=root/"game/src/main/thp/dll_3e.c"
s=thp.read_text()
old="    skip = overdueFrames > 2 ? 2 : (int)overdueFrames;"
new="    skip = overdueFrames > 1 ? 1 : (int)overdueFrames;"
if s.count(old)!=1:
    raise SystemExit(f"THP catch-up anchor mismatch: {s.count(old)}")
s=s.replace(old,new,1)
s=s.replace("[r36s-thp] menu catch-up active (max 3 movie frames/retrace)", "[r36s-thp] menu catch-up active (max 2 movie frames/retrace)")
thp.write_text(s)
print("R36S projected R4 shadows use source precision; menu catch-up limited to 1 stale frame")
