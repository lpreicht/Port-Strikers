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

# Share Dawn's real device context with the SDL2/KMSDRM GLES renderer context.
# Adapter discovery temporarily makes its own context current and restores the SDL
# context afterwards, so at this point GetCurrentContext() is the firmware renderer.
replace(
    "src/dawn/native/opengl/PhysicalDeviceGL.cpp",
    """    std::unique_ptr<ContextEGL> context;
    DAWN_TRY_ASSIGN(context, ContextEGL::Create(mDisplay, GetBackendType(), useRobustness,
                                                disableEGL15Robustness, useANGLETextureSharing,
                                                forceES31AndMinExtensions, bindContextOnlyDuringUse,
                                                mAngleVirtualizationGroup));
""",
    """    std::unique_ptr<ContextEGL> context;
#ifdef AURORA_R36S_OFFSCREEN
    EGLContext r36sSharedContext = mDisplay->egl->GetCurrentContext();
#else
    EGLContext r36sSharedContext = EGL_NO_CONTEXT;
#endif
    DAWN_TRY_ASSIGN(context, ContextEGL::Create(mDisplay, GetBackendType(), useRobustness,
                                                disableEGL15Robustness, useANGLETextureSharing,
                                                forceES31AndMinExtensions, bindContextOnlyDuringUse,
                                                mAngleVirtualizationGroup, r36sSharedContext));
""",
)

print("Dawn minimal R36S direct-present interop patch applied")
