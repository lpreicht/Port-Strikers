import pathlib
import re
import subprocess
import sys
import tempfile


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


root = pathlib.Path(sys.argv[1]) / 'extern/aurora/lib'
gx = (root / 'gx/gx.cpp').read_text()
mapping = function(gx, 'gfx::ClipRect map_logical_scissor(')
if 'gfx::ClipRect map_logical_rect(' in gx:
    mapping = function(gx, 'gfx::ClipRect map_logical_rect(') + '\n' + mapping
copy = function((root / 'dolphin/gx/GXFrameBuffer.cpp').read_text(), 'void copy_tex(')
# Only extract the two coordinate mappings. The rest of copy_tex may also
# contain shadow-destination allocation logic, which needs the real GXState
# and must not be pulled into this isolated UV coordinate fixture.
setup_lines = [line for line in copy.splitlines() if
               'const auto rect = map_logical_scissor(' in line or
               'const auto sourceRect = map_logical_rect(' in line]
assert len(setup_lines) == 2, f'expected two mapping statements, found {len(setup_lines)}'
setup = '\n'.join(setup_lines) + '\n'
recording = (root / 'gfx/recording.cpp').read_text()
uv = function(recording, 'std::array<float, 4> copy_uv_transform(')
argument = re.search(r'prevPass.resolveUniformRange = push_uniform\(copy_uv_transform\(prevPass, (\w+)\)\)', recording)[1]
fixture = r'''
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <utility>
namespace gfx {
struct ClipRect { int32_t x, y, width, height; };
std::pair<uint32_t, uint32_t> target{427,320};
auto get_render_target_size() { return target; }
}
using gfx::ClipRect;
constexpr int AURORA_VIEWPORT_NATIVE=1, SceneColorAttachmentIndex=0;
struct State { int viewportPolicy=0; ClipRect texCopySrc; } g_gxState;
auto logical_fb_size() { return std::pair<uint32_t,uint32_t>{640,480}; }
struct Size { uint32_t width,height; };
struct Attachment { Size size; };
struct RenderPass { std::array<Attachment,1> colorAttachments; };
'''
fixture += mapping + '\n' + uv
fixture += '\nstd::array<float,4> copy_transform() {\n' + setup
fixture += '(void)rect;\n'
fixture += 'RenderPass prevPass{{Attachment{{gfx::target.first,gfx::target.second}}}};\n'
fixture += f'return copy_uv_transform(prevPass, {argument});\n}}\n'
fixture += r'''
int main() {
  struct Case { ClipRect rect; float x,y,w,h; };
  const Case cases[] = {
    {{0,0,512,512},0,0,342.0f/427.0f,342.0f/320.0f},
    {{256,176,128,128},170.0f/427.0f,117.0f/320.0f,87.0f/427.0f,86.0f/320.0f},
    {{0,0,640,480},0,0,1,1},
    {{-16,-16,128,128},-11.0f/427.0f,-11.0f/320.0f,86.0f/427.0f,86.0f/320.0f},
  };
  int failed=0;
  for (const auto& c: cases) {
    g_gxState.texCopySrc=c.rect;
    auto actual=copy_transform();
    std::array<float,4> expected{c.x,c.y,c.w,c.h};
    for (int i=0;i<4;++i) if (std::abs(actual[i]-expected[i])>0.00001f) {
      std::fprintf(stderr,"copy (%d,%d %dx%d) UV[%d]=%.7f expected %.7f\n",
        c.rect.x,c.rect.y,c.rect.width,c.rect.height,i,actual[i],expected[i]);
      ++failed;
    }
  }
  auto clipped=map_logical_scissor({0,0,512,512});
  if (clipped.width!=342 || clipped.height!=320) ++failed;
  g_gxState.viewportPolicy=AURORA_VIEWPORT_NATIVE;
  auto native=map_logical_scissor({-16,0,512,512});
  if (native.x!=-16 || native.height!=512) ++failed;
  return failed ? 1 : 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    cpp = pathlib.Path(directory) / 'shadow.cpp'
    cpp.write_text(fixture)
    binary = pathlib.Path(directory) / 'shadow'
    subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('shadow-copy coordinate regression: PASS')
