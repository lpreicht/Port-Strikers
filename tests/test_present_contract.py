import pathlib
import subprocess
import sys
import tempfile

source = pathlib.Path(sys.argv[1]).read_text()
start = source.index('bool present_gl_texture(')
brace = source.index('{', start)
depth = 1
end = brace + 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
function = source[start:end]
fixture = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#define AURORA_R36S_OFFSCREEN 1
using EGLDisplay = void*; using EGLContext = void*; using EGLSurface = void*;
using GLuint = unsigned; using GLenum = unsigned; using GLsizei = int;
using GLsync = void*;
struct SDL_GLContextState; using SDL_GLContext = SDL_GLContextState*;
constexpr auto EGL_NO_DISPLAY = nullptr, EGL_NO_CONTEXT = nullptr, EGL_NO_SURFACE = nullptr;
constexpr int EGL_TRUE=1, EGL_DRAW=2, EGL_READ=3;
constexpr int GL_TRUE=1, GL_BLEND=1, GL_DEPTH_TEST=2, GL_STENCIL_TEST=3, GL_CULL_FACE=4,
 GL_SCISSOR_TEST=5, GL_TEXTURE0=6, GL_TEXTURE_2D=7, GL_TRIANGLES=8, GL_FRAMEBUFFER=9,
 GL_READ_FRAMEBUFFER=10, GL_DRAW_FRAMEBUFFER=11, GL_COLOR_ATTACHMENT0=12,
 GL_FRAMEBUFFER_COMPLETE=13, GL_COLOR_BUFFER_BIT=14, GL_LINEAR=15,
 GL_NO_ERROR=0, GL_SYNC_GPU_COMMANDS_COMPLETE=16;
constexpr uint64_t GL_TIMEOUT_IGNORED=~uint64_t(0);
void* g_window=(void*)1;
EGLDisplay g_r36sPresentDisplay=(void*)2;
EGLContext g_r36sPresentContext=(void*)3;
EGLSurface g_r36sPresentSurface=(void*)4;
GLuint g_r36sBlitProgram=1, g_r36sBlitVao=1, g_r36sBlitSampler=1, g_r36sReadFbo=1;
struct {int native_fb_width=640, native_fb_height=480;} g_windowSize;
struct Logger {template<class... T> void error(T...) {} template<class... T> void info(T...) {}} Log;
void* currentContext=(void*)20; void* currentDraw=(void*)21; void* currentRead=(void*)22;
void* sdlCachedContext=nullptr;
int flips=0; bool swapFails=false, bindFails=false, visible=true;
bool r36s_init_direct_blitter(){return true;}
bool r36s_init_present_context(){return true;}
EGLDisplay eglGetCurrentDisplay(){return g_r36sPresentDisplay;}
EGLContext eglGetCurrentContext(){return currentContext;}
EGLSurface eglGetCurrentSurface(int which){return which==EGL_DRAW?currentDraw:currentRead;}
int eglGetError(){return 0;}
int eglMakeCurrent(EGLDisplay,EGLSurface d,EGLSurface r,EGLContext c){currentContext=c;currentDraw=d;currentRead=r;return 1;}
int eglSwapBuffers(EGLDisplay,EGLSurface){return 1;}
bool SDL_GL_MakeCurrent(void*,SDL_GLContext c){if(bindFails && c)return false;if(sdlCachedContext==c)return true;sdlCachedContext=c;return eglMakeCurrent(g_r36sPresentDisplay,g_r36sPresentSurface,g_r36sPresentSurface,c);}
bool SDL_GL_SwapWindow(void*){if(swapFails || currentContext!=g_r36sPresentContext)return false;++flips;return true;}
const char* SDL_GetError(){return "test";}
// RC4 instrumentation uses SDL3 nanosecond clock; expose a compatible
// wall-clock stub to the standalone Presenter contract harness.
uint64_t SDL_GetTicksNS(){
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
GLsync glFenceSync(int,int){return (void*)30;}
bool glIsTexture(GLuint){return visible;}
int readBinding=0; GLenum glError=0;
GLenum glGetError(){auto e=glError;glError=0;return e;}
void glBindFramebuffer(int target,unsigned id){if(target==GL_READ_FRAMEBUFFER)readBinding=id;}
void glFramebufferTexture2D(int,int,int,unsigned,int){if(!readBinding)glError=0x502;}
int glCheckFramebufferStatus(int){return GL_FRAMEBUFFER_COMPLETE;}
#define NOOP(name) template<class... T> void name(T...) {}
NOOP(glViewport) NOOP(glDisable) NOOP(glColorMask) NOOP(glUseProgram)
NOOP(glBindVertexArray) NOOP(glActiveTexture) NOOP(glBindTexture) NOOP(glBindSampler)
NOOP(glDrawArrays)
NOOP(glGenFramebuffers) NOOP(glBlitFramebuffer) NOOP(glWaitSync) NOOP(glDeleteSync) NOOP(glFlush)
'''
checks = r'''
int main(int argc, char** argv) {
  if(argc>1) swapFails=true;
  bool ok=present_gl_texture(42,640,480);
  if(swapFails && ok){std::fprintf(stderr,"swap failure was hidden\n");return 1;}
  if(!swapFails && (!ok || flips!=1)){std::fprintf(stderr,"missing SDL/KMSDRM page flip: %d\n",flips);return 1;}
  if(currentContext!=(void*)20 || currentDraw!=(void*)21 || currentRead!=(void*)22){std::fprintf(stderr,"producer EGL state was not restored\n");return 1;}
  if(!swapFails && (!present_gl_texture(42,640,480) || flips!=2)){std::fprintf(stderr,"second frame lost current context\n");return 1;}
  visible=false;
  if(present_gl_texture(42,640,480) || glGetError()!=0){std::fprintf(stderr,"invalid shared texture polluted fallback GL state\n");return 1;}
  return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    cpp=pathlib.Path(tmp)/'contract.cpp'
    cpp.write_text(fixture+function+checks)
    binary=pathlib.Path(tmp)/'contract'
    subprocess.run(['g++','-std=c++20',str(cpp),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
    subprocess.run([str(binary),'swap-failure'],check=True)
print('PASS: scanout, error propagation, producer context restoration')
