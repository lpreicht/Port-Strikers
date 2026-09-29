#!/usr/bin/env python3
from pathlib import Path
import sys

dawn = Path(sys.argv[1])
hdr = dawn / "include/dawn/native/OpenGLBackend.h"
cpp = dawn / "src/dawn/native/opengl/OpenGLBackend.cpp"

h = hdr.read_text()
c = cpp.read_text()

if "GetGLInteropTexture(WGPUTexture texture)" not in h:
    anchor = "DAWN_NATIVE_EXPORT bool RunGLInterop(WGPUDevice device, GLInteropCallback callback, void* userdata);\n"
    if anchor not in h:
        raise SystemExit("full GL interop patch missing RunGLInterop declaration")
    h = h.replace(anchor, anchor + "DAWN_NATIVE_EXPORT GLuint GetGLInteropTexture(WGPUTexture texture);\n", 1)

if "GLuint GetGLInteropTexture(WGPUTexture texture)" not in c:
    if '#include "src/dawn/native/opengl/TextureGL.h"' not in c:
        inc = '#include "src/dawn/native/opengl/DeviceGL.h"\n'
        if inc not in c:
            raise SystemExit("DeviceGL include anchor missing")
        c = c.replace(inc, inc + '#include "src/dawn/native/opengl/TextureGL.h"\n', 1)

    end = "}  // namespace dawn::native::opengl\n"
    pos = c.rfind(end)
    if pos < 0:
        raise SystemExit("OpenGL namespace end missing")
    body = r'''
GLuint GetGLInteropTexture(WGPUTexture texture) {
    if (texture == nullptr) {
        return 0;
    }
    return ToBackend(FromAPI(texture))->GetTextureHandle();
}

'''
    c = c[:pos] + body + c[pos:]

hdr.write_text(h)
cpp.write_text(c)
print("V034 Dawn full-interop presenter compatibility added")
