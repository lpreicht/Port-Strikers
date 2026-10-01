#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/gfx/tex_copy_conv.cpp"
s = p.read_text()

old = '''// GX_TF_RGB565: Blit alpha to 1.0
static constexpr std::string_view FragRGB565 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let c = textureSample(src, src_samp, in.uv);
    return vec4f(c.rgb, 1.0);
}
)"sv;
'''

new = '''// GX_TF_RGB565: quantize to the GameCube copy format, then expose through
// Aurora's RGBA8 GPU texture representation.  Star Fox feeds this texture
// back into the next frame, so preserving RGB8 precision changes the feedback
// loop from real GX hardware.
static constexpr std::string_view FragRGB565 = R"(
@fragment fn fs_main(in: VertexOutput) -> @location(0) vec4f {
    let c = clamp(textureSample(src, src_samp, in.uv).rgb, vec3f(0.0), vec3f(1.0));
    let q = vec3f(
        round(c.r * 31.0) / 31.0,
        round(c.g * 63.0) / 63.0,
        round(c.b * 31.0) / 31.0
    );
    return vec4f(q, 1.0);
}
)"sv;
'''

if old not in s:
    raise SystemExit("RGB565 quantization patch: FragRGB565 anchor not found")
p.write_text(s.replace(old, new, 1))
print("patched GX_TF_RGB565 EFB copy to true 5/6/5 quantization")
