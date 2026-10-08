from pathlib import Path
import sys

root = Path(sys.argv[1]) / 'extern/aurora/lib'
files = {}


def replace(path, old, new, count=1):
    text = files.get(path, (root / path).read_text())
    if text.count(old) != count:
        raise SystemExit(f'{path}: expected {count} anchors, found {text.count(old)}')
    files[path] = text.replace(old, new)


replace('gx/gx.hpp',
        'gfx::ClipRect map_logical_scissor(const gfx::ClipRect& logicalScissor) noexcept;',
        'gfx::ClipRect map_logical_scissor(const gfx::ClipRect& logicalScissor) noexcept;\n'
        'gfx::ClipRect map_logical_rect(const gfx::ClipRect& logicalScissor, bool clampToTarget) noexcept;')
replace('gx/gx.cpp',
        'gfx::ClipRect map_logical_scissor(const gfx::ClipRect& logicalScissor) noexcept {',
        'gfx::ClipRect map_logical_scissor(const gfx::ClipRect& logicalScissor) noexcept {\n'
        '  return map_logical_rect(logicalScissor, true);\n}\n\n'
        'gfx::ClipRect map_logical_rect(const gfx::ClipRect& logicalScissor, bool clampToTarget) noexcept {')
replace('gx/gx.cpp',
        '  const auto mappedLeft = std::clamp(static_cast<int32_t>(std::floor(left)), 0, static_cast<int32_t>(targetWidth));',
        '''  if (!clampToTarget) {
    const auto unclampedLeft = static_cast<int32_t>(std::floor(left));
    const auto unclampedTop = static_cast<int32_t>(std::floor(top));
    return {
        .x = unclampedLeft,
        .y = unclampedTop,
        .width = static_cast<int32_t>(std::ceil(right)) - unclampedLeft,
        .height = static_cast<int32_t>(std::ceil(bottom)) - unclampedTop,
    };
  }
  const auto mappedLeft = std::clamp(static_cast<int32_t>(std::floor(left)), 0, static_cast<int32_t>(targetWidth));''')
replace('dolphin/gx/GXFrameBuffer.cpp',
        '  const auto rect = map_logical_scissor(g_gxState.texCopySrc);',
        '  const auto rect = map_logical_scissor(g_gxState.texCopySrc);\n'
        '  const auto sourceRect = map_logical_rect(g_gxState.texCopySrc, false);')
replace('dolphin/gx/GXFrameBuffer.cpp',
        'gfx::resolve_pass_into(handle.handle, rect, clearColor,',
        'gfx::resolve_pass_into(handle.handle, rect, sourceRect, clearColor,')
for path in ['gfx/recording.cpp', 'gfx/recording.hpp']:
    replace(path, 'void resolve_pass_into(TextureHandle texture, ClipRect rect, bool clearColor,',
            'void resolve_pass_into(TextureHandle texture, ClipRect rect, ClipRect sourceRect, bool clearColor,')
replace('gfx/frame_packet.hpp', '  ClipRect resolveRect;\n',
        '  ClipRect resolveRect;\n  bool resolvePartial = false;\n')
replace('gfx/recording.cpp',
        '    fusedSecond = pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);',
        '    fusedSecond = sourceRect == rect &&\n'
        '                  pass_fusion_complete(texture, rect, clearColor, clearAlpha, clearDepth, resolveFormat);')
replace('gfx/recording.cpp', '    prevPass.resolveRect = rect;\n',
        '    prevPass.resolveRect = rect;\n    prevPass.resolvePartial = sourceRect != rect;\n')
replace('gfx/recording.cpp',
        'prevPass.resolveUniformRange = push_uniform(copy_uv_transform(prevPass, rect));',
        'prevPass.resolveUniformRange = push_uniform(copy_uv_transform(prevPass, sourceRect));')
replace('gfx/recording.cpp',
        '    if (pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {',
        '    if (!prevPass.resolvePartial &&\n'
        '        pass_fusion_begin(prevPass, rect, clearColor, clearAlpha, clearDepth, clearColorValue, clearDepthValue)) {')
replace('gfx/encoding.cpp',
        '  const bool needsScaling =\n      dstSize.width != static_cast<uint32_t>(rect.width)',
        '  const bool needsScaling = passInfo.resolvePartial ||\n'
        '      dstSize.width != static_cast<uint32_t>(rect.width)')
replace('gfx/encoding.cpp',
        '  if (passInfo.extraResolves.size() != 1 || passInfo.dualResolveUniformRange.size != 32) {',
        '  if (passInfo.resolvePartial || passInfo.extraResolves.size() != 1 || passInfo.dualResolveUniformRange.size != 32) {')
replace('gfx/tex_copy_conv.cpp', 'fn intensity(rgb: vec3f) -> f32 {',
        '''fn sample_efb(uv: vec2f) -> vec4f {
    return select(textureSample(src, src_samp, uv), vec4f(0.0),
                  any(uv < vec2f(0.0)) || any(uv > vec2f(1.0)));
}

fn intensity(rgb: vec3f) -> f32 {''', count=2)
shader = files['gfx/tex_copy_conv.cpp']
shader = shader.replace('textureSample(src, src_samp, in.uv)', 'sample_efb(in.uv)')
files['gfx/tex_copy_conv.cpp'] = shader
replace('gfx/tex_copy_conv.cpp', 'fn gx_z24(uv: vec2f) -> u32 {\n',
        '''fn gx_z24(uv: vec2f) -> u32 {
    if (any(uv < vec2f(0.0)) || any(uv > vec2f(1.0))) {
        return 0x00ffffffu;
    }
''', count=2)
for path, text in files.items():
    (root / path).write_text(text)
print('shadow-copy-bounds: applied Foxhollow 1d3042e semantics with ARM pass-fusion guards')
