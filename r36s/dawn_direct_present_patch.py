#!/usr/bin/env python3
from pathlib import Path
import sys

dawn = Path(sys.argv[1])

def replace(rel, old, new):
    p = dawn / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {rel}: {old[:180]!r}")
    p.write_text(s.replace(old, new, 1))

# Minimal native GL interop needed by the R36S zero-readback presenter.
replace(
    "include/dawn/native/OpenGLBackend.h",
    """DAWN_NATIVE_EXPORT WGPUTexture
WrapExternalGLTexture(WGPUDevice device, const ExternalImageDescriptorGLTexture* descriptor);

}  // namespace dawn::native::opengl
""",
    """DAWN_NATIVE_EXPORT WGPUTexture
WrapExternalGLTexture(WGPUDevice device, const ExternalImageDescriptorGLTexture* descriptor);

// Minimal R36S presenter interop: run after queued Dawn GL work with Dawn's
// context current, and expose the underlying GL texture name of a WebGPU texture.
using GLInteropCallback = void (*)(void* userdata);
DAWN_NATIVE_EXPORT bool RunGLInterop(WGPUDevice device, GLInteropCallback callback, void* userdata);
DAWN_NATIVE_EXPORT GLuint GetGLInteropTexture(WGPUTexture texture);

}  // namespace dawn::native::opengl
""",
)

replace(
    "src/dawn/native/opengl/OpenGLBackend.cpp",
    """#include "src/dawn/native/opengl/DeviceGL.h"
""",
    """#include "src/dawn/native/opengl/DeviceGL.h"
#include "src/dawn/native/opengl/TextureGL.h"
""",
)

replace(
    "src/dawn/native/opengl/OpenGLBackend.cpp",
    """WGPUTexture WrapExternalGLTexture(WGPUDevice device,
                                  const ExternalImageDescriptorGLTexture* descriptor) {
    Device* backendDevice = ToBackend(FromAPI(device));
    Ref<TextureBase> texture =
        backendDevice->CreateTextureWrappingGLTexture(descriptor, descriptor->texture);
    return ToAPI(ReturnToAPI(std::move(texture)));
}

}  // namespace dawn::native::opengl
""",
    """WGPUTexture WrapExternalGLTexture(WGPUDevice device,
                                  const ExternalImageDescriptorGLTexture* descriptor) {
    Device* backendDevice = ToBackend(FromAPI(device));
    Ref<TextureBase> texture =
        backendDevice->CreateTextureWrappingGLTexture(descriptor, descriptor->texture);
    return ToAPI(ReturnToAPI(std::move(texture)));
}

bool RunGLInterop(WGPUDevice device, GLInteropCallback callback, void* userdata) {
    Device* backendDevice = ToBackend(FromAPI(device));
    if (callback == nullptr) {
        return false;
    }
    return !backendDevice->ConsumedError(backendDevice->EnqueueAndFlushGL(
        [callback, userdata](const OpenGLFunctions&) -> MaybeError {
            callback(userdata);
            return {};
        }));
}

GLuint GetGLInteropTexture(WGPUTexture texture) {
    if (texture == nullptr) {
        return 0;
    }
    return ToBackend(FromAPI(texture))->GetHandle();
}

}  // namespace dawn::native::opengl
""",
)


print("Dawn R36S interop applied; producer context unchanged")
