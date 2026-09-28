#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:180]!r}")
    p.write_text(s.replace(old, new, 1))

# Public direct-GL present helper.
replace(
    "extern/aurora/lib/window.hpp",
    "bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch);\n",
    "bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch);\n"
    "bool present_gl_texture(uint32_t texture, uint32_t width, uint32_t height);\n",
)

# EGL/GLES access for the direct presenter.
replace(
    "extern/aurora/lib/window.cpp",
    """#include <tracy/Tracy.hpp>

#if defined(SDL_PLATFORM_ANDROID)
""",
    """#include <tracy/Tracy.hpp>

#ifdef AURORA_R36S_OFFSCREEN
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#endif

#if defined(SDL_PLATFORM_ANDROID)
""",
)

# Keep the SDL/KMSDRM EGL objects and tiny blit resources.
replace(
    "extern/aurora/lib/window.cpp",
    """SDL_Texture* g_r36sPresentTexture = nullptr;
uint32_t g_r36sPresentWidth = 0;
uint32_t g_r36sPresentHeight = 0;
#endif
""",
    """SDL_Texture* g_r36sPresentTexture = nullptr;
uint32_t g_r36sPresentWidth = 0;
uint32_t g_r36sPresentHeight = 0;
EGLDisplay g_r36sPresentDisplay = EGL_NO_DISPLAY;
EGLContext g_r36sPresentContext = EGL_NO_CONTEXT;
EGLSurface g_r36sPresentSurface = EGL_NO_SURFACE;
GLuint g_r36sBlitProgram = 0;
GLuint g_r36sBlitVao = 0;
GLuint g_r36sBlitSampler = 0;
#endif
""",
)

# Capture the firmware-owned KMSDRM EGL surface/context after SDL creates its GLES2 renderer.
replace(
    "extern/aurora/lib/window.cpp",
    """  Log.info("R36S SDL2/KMSDRM renderer initialized: {}",
           SDL_GetRendererName(g_renderer) ? SDL_GetRendererName(g_renderer) : "?");
  return true;
""",
    """  // Touch the renderer once so its GLES context/surface is current, then remember
  // the firmware-owned EGL objects. Dawn will share objects with this context.
  SDL_SetRenderDrawColor(g_renderer, 0, 0, 0, 255);
  SDL_RenderClear(g_renderer);
  g_r36sPresentDisplay = eglGetCurrentDisplay();
  g_r36sPresentContext = eglGetCurrentContext();
  g_r36sPresentSurface = eglGetCurrentSurface(EGL_DRAW);
  Log.info("R36S SDL2/KMSDRM renderer initialized: {} EGL display={} context={} surface={}",
           SDL_GetRendererName(g_renderer) ? SDL_GetRendererName(g_renderer) : "?",
           static_cast<void*>(g_r36sPresentDisplay), static_cast<void*>(g_r36sPresentContext),
           static_cast<void*>(g_r36sPresentSurface));
  if (g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentContext == EGL_NO_CONTEXT ||
      g_r36sPresentSurface == EGL_NO_SURFACE) {
    Log.error("R36S failed to capture SDL/KMSDRM EGL objects");
    return false;
  }
  return true;
""",
)

# Insert a direct GLES blitter before the existing software fallback presenter.
replace(
    "extern/aurora/lib/window.cpp",
    """bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch) {
""",
    r"""#ifdef AURORA_R36S_OFFSCREEN
static GLuint r36s_compile_shader(GLenum type, const char* source) {
  GLuint shader = glCreateShader(type);
  glShaderSource(shader, 1, &source, nullptr);
  glCompileShader(shader);
  GLint ok = GL_FALSE;
  glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
  if (ok != GL_TRUE) {
    char info[1024]{};
    GLsizei length = 0;
    glGetShaderInfoLog(shader, sizeof(info), &length, info);
    Log.error("R36S direct-present shader compile failed: {}", info);
    glDeleteShader(shader);
    return 0;
  }
  return shader;
}

static bool r36s_init_direct_blitter() {
  if (g_r36sBlitProgram != 0) {
    return true;
  }
  static const char* kVertex = R"(#version 300 es
precision highp float;
out vec2 v_uv;
void main() {
  vec2 p;
  if (gl_VertexID == 0) p = vec2(-1.0, -1.0);
  else if (gl_VertexID == 1) p = vec2(3.0, -1.0);
  else p = vec2(-1.0, 3.0);
  vec2 uv = p * 0.5 + 0.5;
  v_uv = vec2(uv.x, 1.0 - uv.y);
  gl_Position = vec4(p, 0.0, 1.0);
}
)";
  static const char* kFragment = R"(#version 300 es
precision mediump float;
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 o_color;
void main() {
  o_color = texture(u_tex, v_uv);
}
)";
  GLuint vs = r36s_compile_shader(GL_VERTEX_SHADER, kVertex);
  GLuint fs = r36s_compile_shader(GL_FRAGMENT_SHADER, kFragment);
  if (!vs || !fs) {
    if (vs) glDeleteShader(vs);
    if (fs) glDeleteShader(fs);
    return false;
  }
  g_r36sBlitProgram = glCreateProgram();
  glAttachShader(g_r36sBlitProgram, vs);
  glAttachShader(g_r36sBlitProgram, fs);
  glLinkProgram(g_r36sBlitProgram);
  glDeleteShader(vs);
  glDeleteShader(fs);
  GLint linked = GL_FALSE;
  glGetProgramiv(g_r36sBlitProgram, GL_LINK_STATUS, &linked);
  if (linked != GL_TRUE) {
    char info[1024]{};
    GLsizei length = 0;
    glGetProgramInfoLog(g_r36sBlitProgram, sizeof(info), &length, info);
    Log.error("R36S direct-present program link failed: {}", info);
    glDeleteProgram(g_r36sBlitProgram);
    g_r36sBlitProgram = 0;
    return false;
  }
  glUseProgram(g_r36sBlitProgram);
  glUniform1i(glGetUniformLocation(g_r36sBlitProgram, "u_tex"), 0);
  glGenVertexArrays(1, &g_r36sBlitVao);
  glGenSamplers(1, &g_r36sBlitSampler);
  glSamplerParameteri(g_r36sBlitSampler, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
  glSamplerParameteri(g_r36sBlitSampler, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  glSamplerParameteri(g_r36sBlitSampler, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
  glSamplerParameteri(g_r36sBlitSampler, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  Log.info("R36S direct GLES presenter initialized");
  return true;
}
#endif

bool present_gl_texture(uint32_t texture, uint32_t width, uint32_t height) {
#ifdef AURORA_R36S_OFFSCREEN
  if (texture == 0 || width == 0 || height == 0 ||
      g_r36sPresentDisplay == EGL_NO_DISPLAY || g_r36sPresentContext == EGL_NO_CONTEXT ||
      g_r36sPresentSurface == EGL_NO_SURFACE) {
    return false;
  }
  if (eglMakeCurrent(g_r36sPresentDisplay, g_r36sPresentSurface, g_r36sPresentSurface,
                     g_r36sPresentContext) != EGL_TRUE) {
    Log.error("R36S direct-present eglMakeCurrent failed: 0x{:x}",
              static_cast<unsigned>(eglGetError()));
    return false;
  }
  if (!r36s_init_direct_blitter()) {
    return false;
  }

  glViewport(0, 0, static_cast<GLsizei>(g_windowSize.native_fb_width),
             static_cast<GLsizei>(g_windowSize.native_fb_height));
  glDisable(GL_BLEND);
  glDisable(GL_DEPTH_TEST);
  glDisable(GL_STENCIL_TEST);
  glDisable(GL_CULL_FACE);
  glDisable(GL_SCISSOR_TEST);
  glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
  glUseProgram(g_r36sBlitProgram);
  glBindVertexArray(g_r36sBlitVao);
  glActiveTexture(GL_TEXTURE0);
  glBindTexture(GL_TEXTURE_2D, static_cast<GLuint>(texture));
  glBindSampler(0, g_r36sBlitSampler);
  glDrawArrays(GL_TRIANGLES, 0, 3);
  glBindSampler(0, 0);
  glBindTexture(GL_TEXTURE_2D, 0);

  if (eglSwapBuffers(g_r36sPresentDisplay, g_r36sPresentSurface) != EGL_TRUE) {
    Log.error("R36S direct-present eglSwapBuffers failed: 0x{:x}",
              static_cast<unsigned>(eglGetError()));
    return false;
  }
  return true;
#else
  (void)texture;
  (void)width;
  (void)height;
  return false;
#endif
}

bool present_software_frame(const void* pixels, uint32_t width, uint32_t height, uint32_t pitch) {
""",
)

# Remove the CPU readback path and present the final Dawn texture directly through GLES.
p = root / "extern/aurora/lib/aurora.cpp"
s = p.read_text()
start = s.find("#ifdef AURORA_R36S_OFFSCREEN\n    const auto& source = webgpu::present_source();")
end_marker = "#endif\n\n    wgpu::Texture currentTexture;"
if start < 0:
    raise SystemExit("aurora.cpp direct-present start marker not found")
end = s.find(end_marker, start)
if end < 0:
    raise SystemExit("aurora.cpp direct-present end marker not found")
replacement = r"""#ifdef AURORA_R36S_OFFSCREEN
    const auto& source = webgpu::present_source();
    const uint32_t width = source.size.width;
    const uint32_t height = source.size.height;

    webgpu::gpu_prof::frame_end(encoder);
    const wgpu::CommandBufferDescriptor r36sCmdBufDescriptor{.label = "R36S direct-present command buffer"};
    const auto commandBuffer = encoder.Finish(&r36sCmdBufDescriptor);
    g_queue.Submit(1, &commandBuffer);
    webgpu::gpu_prof::after_submit();

    const uint32_t glTexture =
        dawn::native::opengl::GetGLInteropTexture(source.texture.Get());
    const bool synchronized = dawn::native::opengl::RunGLInterop(
        g_device.Get(),
        [](void*) {
          // First zero-readback version: synchronous producer completion.
          // A later present worker can replace this with fences if needed.
          glFinish();
        },
        nullptr);
    if (!synchronized || glTexture == 0 ||
        !window::present_gl_texture(glTexture, width, height)) {
      Log.warn("R36S direct GPU present failed texture={} synchronized={}", glTexture, synchronized);
    }

    gfx::after_present();
    for (auto& callback : afterSubmitCallbacks) {
      if (callback) {
        callback();
      }
    }
    gfx::after_submit();
    return;
#endif

    wgpu::Texture currentTexture;"""
s = s[:start] + replacement + s[end + len(end_marker):]

# Add the minimal Dawn native interop header and GLES glFinish declaration.
old = """#include <magic_enum.hpp>

#ifdef AURORA_R36S_OFFSCREEN
#include <atomic>
"""
new = """#include <magic_enum.hpp>

#ifdef AURORA_R36S_OFFSCREEN
#include <dawn/native/OpenGLBackend.h>
#include <GLES3/gl3.h>
#include <atomic>
"""
if old not in s:
    raise SystemExit("aurora.cpp include marker not found")
s = s.replace(old, new, 1)
p.write_text(s)

# Direct GLES calls resolve through the same vendor GLES library as SDL/Dawn.
replace(
    "CMakeLists.txt",
    """        EGL
        gbm
""",
    """        EGL
        gbm
        GLESv2
""",
)

print("R36S direct GPU present patch applied")
