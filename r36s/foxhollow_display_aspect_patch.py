#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"{rel}: expected 1 match, got {count}: {old[:180]!r}")
    p.write_text(s.replace(old, new, 1))

# Restore Foxhollow's old explicit display-aspect override on the newer
# Aurora ARM branch. FIT continues to fall back to the configured VI aspect
# when no override is supplied.
replace(
    "extern/aurora/lib/window.hpp",
    """void set_frame_buffer_scale(float scale);
void set_frame_buffer_aspect_fit(bool fit);
void set_background_input(bool value);
""",
    """void set_frame_buffer_scale(float scale);
void set_frame_buffer_aspect_fit(bool fit);
void set_frame_buffer_target_aspect(float aspect);
void set_background_input(bool value);
""",
)

replace(
    "extern/aurora/lib/window.cpp",
    """float g_frameBufferScale = 0.f;
bool g_frameBufferAspectFit = false;
AuroraWindowSize g_windowSize;
""",
    """float g_frameBufferScale = 0.f;
bool g_frameBufferAspectFit = false;
float g_frameBufferTargetAspect = 0.f;
AuroraWindowSize g_windowSize;
""",
)

replace(
    "extern/aurora/lib/window.cpp",
    """  if (g_frameBufferAspectFit) {
    const auto [baseW, baseH] = vi::configured_fb_size();
    if (baseW > 0 && baseH > 0) {
      const auto [fitW, fitH] =
          fit_frame_buffer_to_aspect(fb_w, fb_h, static_cast<float>(baseW) / static_cast<float>(baseH));
      fb_w = fitW;
      fb_h = fitH;
    }
  }
""",
    """  if (g_frameBufferAspectFit) {
    const auto [baseW, baseH] = vi::configured_fb_size();
    float aspect = g_frameBufferTargetAspect;
    if (aspect <= 0.f && baseW > 0 && baseH > 0) {
      aspect = static_cast<float>(baseW) / static_cast<float>(baseH);
    }
    if (aspect > 0.f) {
      const auto [fitW, fitH] = fit_frame_buffer_to_aspect(fb_w, fb_h, aspect);
      fb_w = fitW;
      fb_h = fitH;
    }
  }
""",
)

replace(
    "extern/aurora/lib/window.cpp",
    """void set_frame_buffer_aspect_fit(bool fit) {
  if (g_frameBufferAspectFit == fit) {
    return;
  }

  g_frameBufferAspectFit = fit;
  request_frame_buffer_resize();
}

void set_background_input(bool value) { SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, value ? "1" : "0"); }
""",
    """void set_frame_buffer_aspect_fit(bool fit) {
  if (g_frameBufferAspectFit == fit) {
    return;
  }

  g_frameBufferAspectFit = fit;
  request_frame_buffer_resize();
}

void set_frame_buffer_target_aspect(float aspect) {
  if (aspect < 0.f) {
    aspect = 0.f;
  }
  if (g_frameBufferTargetAspect == aspect) {
    return;
  }
  g_frameBufferTargetAspect = aspect;
  request_frame_buffer_resize();
}

void set_background_input(bool value) { SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, value ? "1" : "0"); }
""",
)

replace(
    "extern/aurora/include/dolphin/gx/GXAurora.h",
    """void AuroraSetViewportPolicy(AuroraViewportPolicy policy);

/**
 * Retrieves the current content framebuffer size.
 */
""",
    """void AuroraSetViewportPolicy(AuroraViewportPolicy policy);

/**
 * Overrides the target content aspect used by AURORA_VIEWPORT_FIT.
 * Pass 0 to derive it from the configured VI framebuffer dimensions.
 */
void AuroraSetDisplayAspect(f32 aspect);

/**
 * Retrieves the current content framebuffer size.
 */
""",
)

replace(
    "extern/aurora/lib/dolphin/gx/GXAurora.cpp",
    """void AuroraSetViewportPolicy(AuroraViewportPolicy policy) {
  aurora::gx::set_viewport_policy(policy);
}

void AuroraGetRenderSize(u32* width, u32* height) {
""",
    """void AuroraSetViewportPolicy(AuroraViewportPolicy policy) {
  aurora::gx::set_viewport_policy(policy);
}

void AuroraSetDisplayAspect(f32 aspect) {
  aurora::window::set_frame_buffer_target_aspect(aspect);
}

void AuroraGetRenderSize(u32* width, u32* height) {
""",
)

print("Foxhollow AuroraSetDisplayAspect compatibility restored")
