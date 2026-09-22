#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_r36s_sdl_audio.py <melee-dir>")

melee = Path(sys.argv[1])
helper = melee / "native/tools/build_sdl3_shim.sh"
s = helper.read_text()

# Bump the helper's local layout marker so an Actions cache containing the older
# SDL3 shim is rebuilt once with the R36S audio queue change.
if "layout=2" not in s:
    if "layout=1" not in s:
        raise SystemExit("build_sdl3_shim.sh: layout marker not found")
    s = s.replace("layout=1", "layout=2", 1)

needle = '''if [ "$(git -C "$src" rev-parse HEAD)" != "$rev" ]; then
    git -C "$src" fetch -q origin "$branch"
    git -C "$src" checkout -q "$rev"
fi
'''
patch = needle + '''# R36S/ArkOS: SDL2 QueueAudio is non-blocking. Two ALSA periods are too easy to
# starve when the game/render threads briefly pre-empt the SDL3 audio feeder.
# Four 1024-frame periods at 44.1 kHz give the device enough scheduling margin
# without changing the game's 32 kHz mixer or playback speed.
audio_src="$src/src/audio/sdl2/SDL_sdl2audio.c"
if grep -q 'device->buffer_size \* 2' "$audio_src"; then
    sed -i 's/device->buffer_size \* 2/device->buffer_size * 4/' "$audio_src"
fi
'''
if "Four 1024-frame periods" not in s:
    if needle not in s:
        raise SystemExit("build_sdl3_shim.sh: checkout block not found")
    s = s.replace(needle, patch, 1)

helper.write_text(s)
print("Applied R36S SDL2 audio queue high-water patch")
