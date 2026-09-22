#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_r36s_audio_skin.py <strikers-dir>")

root = Path(sys.argv[1])

def replace_once(path, old, new, label):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if old not in s:
        raise SystemExit(f"{label}: pattern not found in {p}")
    p.write_text(s.replace(old, new, 1))

# ---------------------------------------------------------------------------
# 1) Skin/morph correctness.
#
# v1.2.0's reconstructed ShaderSkinMesh constructor assigns morphWeights[0]
# eight times, leaving slots 1..7 undefined until the first Pose() update.
# Transitional/cutscene models can render in that window and produce a one-frame
# "exploded" mesh. Initialise the entire fixed-size array instead.
# ---------------------------------------------------------------------------
replace_once(
    root / "src/Game/GL/ShaderSkinMesh.cpp",
    """    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
    morphWeights[0] = 0.0f;
""",
    """    for (int i = 0; i < 8; ++i)
    {
        morphWeights[i] = 0.0f;
    }
""",
    "ShaderSkinMesh morphWeights init",
)

# ---------------------------------------------------------------------------
# 2) Audio queue headroom.
#
# MusyX feeds SDL at 32 kHz in 160-frame (5 ms / 640-byte) ticks, while the
# ArkOS SDL2 ALSA device opens at 44.1 kHz with a 1024-frame hardware pull.
# The v1.2.0 transport only targets six MusyX ticks (30 ms). A single device
# pull is ~23.2 ms, leaving very little scheduling margin. Current upstream
# Strikers already compensates for this on Switch; apply the same idea to the
# R36S path and keep one device pull in reserve.
# ---------------------------------------------------------------------------
audio_out = root / "src/platform/audio_out.cpp"
replace_once(
    audio_out,
    """// How far ahead to keep the device fed: 30 ms covers a dropped frame at 60 Hz.
constexpr int kTargetBuffers = 6;\n""",
    """// R36S: the renderer can occasionally hold the game thread for longer than one
// frame even when the visible animation stays smooth. Keep ~100 ms of MusyX
// source audio queued so those stalls do not turn into audible gaps.
#if defined(MELEE_MIYOO_FLIP)
constexpr int kTargetBuffers = 20;
#else
constexpr int kTargetBuffers = 6;
#endif\n""",
    "R36S audio target queue",
)
replace_once(
    audio_out,
    """SDL_AudioStream* s_stream = nullptr;
bool s_ownsSubsystem = false;
""",
    """SDL_AudioStream* s_stream = nullptr;
// Source-rate bytes consumed by one host device pull. The R36S SDL3->SDL2
// bridge uses a 1024-frame ALSA buffer at 44.1 kHz, substantially larger than
// one 5 ms MusyX tick, so keep this much extra source audio queued.
int s_pullBytes = 0;
bool s_ownsSubsystem = false;
""",
    "audio host-pull reserve state",
)

replace_once(
    audio_out,
    """    SDL_ResumeAudioStreamDevice(s_stream);
    // atexit, not PortAudioStop: salExitAi is reached only if the game shuts MusyX down, and it
""",
    """#if defined(MELEE_MIYOO_FLIP)
    {
        SDL_AudioSpec dev;
        int frames = 0;
        std::memset(&dev, 0, sizeof(dev));
        if (SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(s_stream), &dev, &frames) &&
            frames > 0 && dev.freq > 0) {
            const long long srcFrames =
                static_cast<long long>(frames) * kSampleRate / dev.freq;
            s_pullBytes = static_cast<int>(srcFrames) * kChannels *
                          static_cast<int>(sizeof(int16_t));
        }
    }
#endif

    SDL_ResumeAudioStreamDevice(s_stream);
    // atexit, not PortAudioStop: salExitAi is reached only if the game shuts MusyX down, and it
""",
    "audio host-pull reserve query",
)

replace_once(
    audio_out,
    """    const int target = static_cast<int>(bufBytes) * kTargetBuffers;
""",
    """    const int target = static_cast<int>(bufBytes) * kTargetBuffers + s_pullBytes;
""",
    "audio queue target reserve",
)

# ---------------------------------------------------------------------------
# 3) Cheaper resampling on Cortex-A35.
#
# The software mixer may render 5-6 ticks in one game-frame and the match log
# shows 30-47 simultaneous voices. The default cubic interpolation performs a
# float cubic polynomial for every output sample of every voice. On the R36S,
# use linear interpolation for the resampled path. 1:1 streams are effectively
# unchanged, while pitched SFX trade a small amount of interpolation quality for
# much lower worst-case CPU cost.
# ---------------------------------------------------------------------------
replace_once(
    root / "src/platform/audio_mix.cpp",
    """    if (srcSelect == 1)
        return (s32)((float)vm.h[1] + ((float)vm.h[2] - (float)vm.h[1]) * t);
    const float a = (float)vm.h[0];
""",
    """#if defined(MELEE_MIYOO_FLIP)
    // Cortex-A35 fast path: the cubic SRC is one of the hottest operations when
    // a match has dozens of active voices. Linear keeps pitch/resampling intact
    // without the per-sample cubic polynomial.
    return (s32)((float)vm.h[1] + ((float)vm.h[2] - (float)vm.h[1]) * t);
#else
    if (srcSelect == 1)
        return (s32)((float)vm.h[1] + ((float)vm.h[2] - (float)vm.h[1]) * t);
    const float a = (float)vm.h[0];
""",
    "R36S linear audio interpolation start",
)

replace_once(
    root / "src/platform/audio_mix.cpp",
    """    return (s32)(((c3 * t + c2) * t + c1) * t + c0);
}

// The per-voice low-pass that""",
    """    return (s32)(((c3 * t + c2) * t + c1) * t + c0);
#endif
}

// The per-voice low-pass that""",
    "R36S linear audio interpolation end",
)


# ---------------------------------------------------------------------------
# 4) Honour log_audio=0.
#
# PortConfigLoad exports every INI key as STRIKERS_<KEY>. Upstream's audio
# diagnostics historically treated any non-empty STRIKERS_LOG_AUDIO value as
# enabled, so the perfectly normal value "0" enabled hundreds of unbuffered
# writes instead of disabling them. On an SD-card handheld those writes can
# pre-empt the SDL/ALSA feeder and cause exactly the short starvation seen in
# match logs. Make all audio-side checks interpret "0" as false.
# ---------------------------------------------------------------------------
for rel in (
    "src/platform/audio_out.cpp",
    "src/platform/audio_mix.cpp",
    "src/platform/musyx_data.cpp",
    "src/platform/musyx_aram.c",
    "src/platform/dvd.c",
    "src/Game/Sys/debug.cpp",
):
    p = root / rel
    text = p.read_text()
    before = text
    text = text.replace(
        "(e != nullptr && *e != '\\0') ? 1 : 0;",
        "(e != nullptr && *e != '\\0' && *e != '0') ? 1 : 0;",
    )
    text = text.replace(
        "(e != NULL && *e != '\\0') ? 1 : 0;",
        "(e != NULL && *e != '\\0' && *e != '0') ? 1 : 0;",
    )
    if text != before:
        p.write_text(text)

print("Applied R36S audio stability + skin morph + log_audio fixes")
