#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_r36s_sdl_audio.py <melee-dir>")

melee = Path(sys.argv[1])
helper = melee / "native/tools/build_sdl3_shim.sh"
s = helper.read_text()

# Force one rebuild of the cached SDL3 shim for V0.4.
if "layout=3" not in s:
    if "layout=1" not in s:
        raise SystemExit("build_sdl3_shim.sh: layout marker not found")
    s = s.replace("layout=1", "layout=3", 1)

# Prefer SDL3's native ALSA backend on ArkOS. The SDL2 backend remains available
# for video and as an audio fallback, but playback no longer needs the
# SDL3 -> SDL2 QueueAudio -> ALSA chain.
if "-DSDL_ALSA=ON" not in s:
    if "-DSDL_ALSA=OFF" not in s:
        raise SystemExit("build_sdl3_shim.sh: SDL_ALSA option not found")
    s = s.replace(
        "-DSDL_ALSA=OFF",
        "-DSDL_ALSA=ON -DSDL_ALSA_SHARED=ON -DSDL_DEPS_SHARED=ON",
        1,
    )

needle = '''if [ "$(git -C "$src" rev-parse HEAD)" != "$rev" ]; then
    git -C "$src" fetch -q origin "$branch"
    git -C "$src" checkout -q "$rev"
fi
'''
patch = needle + '''# R36S fallback path: if SDL3 ever has to use the SDL2 audio backend, make both
# the SDL2 hardware period and the queue substantially less sensitive to short
# scheduler stalls.
audio_src="$src/src/audio/sdl2/SDL_sdl2audio.c"
if grep -q 'desired.samples = (Uint16)device->sample_frames;' "$audio_src"; then
    sed -i 's/desired.samples = (Uint16)device->sample_frames;/desired.samples = (Uint16)((device->sample_frames < 2048) ? 2048 : device->sample_frames);/' "$audio_src"
fi
if grep -q 'device->buffer_size \* 2' "$audio_src"; then
    sed -i 's/device->buffer_size \* 2/device->buffer_size * 8/' "$audio_src"
fi
'''
if "R36S fallback path" not in s:
    if needle not in s:
        raise SystemExit("build_sdl3_shim.sh: checkout block not found")
    s = s.replace(needle, patch, 1)

helper.write_text(s)
print("Applied R36S native-ALSA + fallback audio buffering patch")
