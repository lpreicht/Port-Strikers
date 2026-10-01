#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "extern/aurora/lib/gx/shader.cpp"
text = p.read_text()

old_scale = '''    const auto scaleExpr =
        fmt::format("tex{0}_uv * ubuf.texcoord_scale[{0}].xy * vec2f({1}, {2}) / ubuf.tex{3}_size_bias.xy", texCoordId,
                    ind_scale(indStage.scaleS), ind_scale(indStage.scaleT), texMapId);
'''
new_scale = '''    // R36S GX fixed-point parity: the TEV receives texture coordinates in
    // 1/128-texel units. Quantize before the indirect-stage scale just like
    // Dolphin's fixpoint_uv path instead of carrying arbitrary floats.
    const auto scaleExpr =
        fmt::format("(trunc(tex{0}_uv * ubuf.texcoord_scale[{0}].xy * 128.0) / 128.0) * "
                    "vec2f({1}, {2}) / ubuf.tex{3}_size_bias.xy", texCoordId,
                    ind_scale(indStage.scaleS), ind_scale(indStage.scaleT), texMapId);
'''
if old_scale not in text:
    raise SystemExit("indirect fixed-point patch: scaleExpr anchor not found")
text = text.replace(old_scale, new_scale, 1)

old_sample = '''        "\\n    // Indirect stage {0}"
        "\\n    var t_IndTexCoord{0} = 255.0 * textureSampleBias(tex{1}, tex{1}_samp, {2}, "
        "i32(ubuf.tex{1}_size_bias.w), ubuf.tex{1}_size_bias.z).abg;",
'''
new_sample = '''        "\\n    // Indirect stage {0}"
        "\\n    // GX indirect samples are 8-bit values before TEV bias/matrix math."
        "\\n    var t_IndTexCoord{0} = round(255.0 * clamp(textureSampleBias(tex{1}, tex{1}_samp, {2}, "
        "i32(ubuf.tex{1}_size_bias.w), ubuf.tex{1}_size_bias.z).abg, vec3f(0.0), vec3f(1.0)));",
'''
if old_sample not in text:
    raise SystemExit("indirect fixed-point patch: indirect sample anchor not found")
text = text.replace(old_sample, new_sample, 1)

old_base = '''          fragmentFnPre +=
              fmt::format("\\n    var ind{0}_texel = tex{1}_uv * ubuf.texcoord_scale[{1}].xy;", i, texCoordId);
'''
new_base = '''          fragmentFnPre +=
              fmt::format("\\n    // GX 1/128 texel fixed-point base coordinate"
                          "\\n    var ind{0}_texel = trunc(tex{1}_uv * ubuf.texcoord_scale[{1}].xy * 128.0) / 128.0;",
                          i, texCoordId);
'''
if old_base not in text:
    raise SystemExit("indirect fixed-point patch: base texel anchor not found")
text = text.replace(old_base, new_base, 1)

old_combine = '''        if (stage.indTexAddPrev) {
          fragmentFnPre += fmt::format("\\n    t_TexCoord += {};", finalCoord);
        } else {
          fragmentFnPre += fmt::format("\\n    t_TexCoord = {};", finalCoord);
        }

        if (needsTextureSample && hasBaseTexture) {
'''
new_combine = '''        if (stage.indTexAddPrev) {
          fragmentFnPre += fmt::format("\\n    t_TexCoord += {};", finalCoord);
        } else {
          fragmentFnPre += fmt::format("\\n    t_TexCoord = {};", finalCoord);
        }

        // The GX TEV coordinate accumulator is signed 24-bit fixed point with
        // 7 fractional bits (1/128 texel). Quantize each indirect stage and
        // wrap the signed 24-bit accumulator before it is sampled/forwarded.
        fragmentFnPre += fmt::format(
            "\\n    // GX signed-24 TEV coordinate wrap"
            "\\n    let ind{0}_gx_fixed = trunc(t_TexCoord * 128.0);"
            "\\n    let ind{0}_gx_s24 = ind{0}_gx_fixed - "
            "floor((ind{0}_gx_fixed + vec2f(8388608.0)) / 16777216.0) * 16777216.0;"
            "\\n    t_TexCoord = ind{0}_gx_s24 / 128.0;",
            i);

        if (needsTextureSample && hasBaseTexture) {
'''
if old_combine not in text:
    raise SystemExit("indirect fixed-point patch: TEV combine anchor not found")
text = text.replace(old_combine, new_combine, 1)

p.write_text(text)
print("patched Aurora indirect TEV path toward GX fixed-point semantics")
