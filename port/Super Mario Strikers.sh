#!/bin/bash
XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
  controlfolder="$XDG_DATA_HOME/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

GAMEDIR="/$directory/ports/strikers"
cd "$GAMEDIR" || exit 1

> "$GAMEDIR/log.txt"
exec > >(tee "$GAMEDIR/log.txt") 2>&1

shopt -s nullglob nocaseglob
discs=("$GAMEDIR"/assets/*.iso "$GAMEDIR"/assets/*.gcm "$GAMEDIR"/assets/*.ciso "$GAMEDIR"/assets/*.gcz)
shopt -u nocaseglob
if [ ${#discs[@]} -eq 0 ]; then
  pm_message "No Super Mario Strikers disc image found. Put your USA G4QE01 .iso in ports/strikers/assets/."
  sleep 12
  exit 1
fi

export XDG_CONFIG_HOME="$GAMEDIR/runtime/config"
export XDG_STATE_HOME="$GAMEDIR/runtime/state"
export XDG_CACHE_HOME="$GAMEDIR/runtime/cache"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME"

# CPU-vertex builds must not reuse Dawn pipeline data produced by the old
# storage-buffer vertex path. Reset only the Dawn cache once; keep CARD saves.
CACHE_RESET_MARKER="$GAMEDIR/runtime/.cpu_vertex_cache_reset_v1"
if [ ! -f "$CACHE_RESET_MARKER" ]; then
  rm -f "$HOME/.local/share/Super Mario Strikers/dawn_cache.db" \
        "$HOME/.local/share/Super Mario Strikers/dawn_cache.db-shm" \
        "$HOME/.local/share/Super Mario Strikers/dawn_cache.db-wal"
  touch "$CACHE_RESET_MARKER"
  echo "[launcher] reset old Dawn cache for CPU vertex decode"
fi

if [ ${#sdl_controllerconfig} -lt 100000 ]; then
  export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
fi

export LD_LIBRARY_PATH="$GAMEDIR/libs.${DEVICE_ARCH}:${LD_LIBRARY_PATH:-}"

# SDL3-over-SDL2 shim. SDL3 itself uses the shim's "sdl2" driver, while
# the SDL2 instance loaded inside the shim must use the CFW's real backend.
inner_video="${SDL3SHIM_SDL2_VIDEODRIVER:-${SDL_VIDEODRIVER:-}}"
inner_audio="${SDL3SHIM_SDL2_AUDIODRIVER:-${SDL_AUDIODRIVER:-}}"

# ArkOS/R36S uses SDL2 KMSDRM + ALSA. "sdl2" is only the outer SDL3 shim name
# and is not a valid SDL2 video/audio backend.
if [ "${CFW_NAME:-}" = "ArkOS" ] || [ "${inner_video:-}" = "sdl2" ] || [ -z "${inner_video:-}" ]; then
  inner_video="kmsdrm"
fi
if [ "${CFW_NAME:-}" = "ArkOS" ] || [ "${inner_audio:-}" = "sdl2" ] || [ -z "${inner_audio:-}" ]; then
  inner_audio="alsa"
fi

export SDL3SHIM_SDL2_VIDEODRIVER="$inner_video"
export SDL3SHIM_SDL2_AUDIODRIVER="$inner_audio"
export SDL_VIDEODRIVER=sdl2
export SDL_AUDIODRIVER=sdl2

echo "[launcher] SDL3 shim -> SDL2 video=$SDL3SHIM_SDL2_VIDEODRIVER audio=$SDL3SHIM_SDL2_AUDIODRIVER"

# Known-good ArkOS Mali-G31 driver on the user's R36S.
MALI="/usr/local/lib/aarch64-linux-gnu/libmali-bifrost-g31-rxp0-gbm.so"
if [ -f "$MALI" ]; then
  export LD_PRELOAD="$MALI${LD_PRELOAD:+:$LD_PRELOAD}"
  export LD_LIBRARY_PATH="/usr/local/lib/aarch64-linux-gnu:/usr/local/lib:/usr/lib/aarch64-linux-gnu:/usr/lib:/lib/aarch64-linux-gnu:/lib:$LD_LIBRARY_PATH"
fi

export STRIKERS_DATA="${discs[0]}"
export STRIKERS_CONFIG="$GAMEDIR/strikers.ini"

chmod +x "$GAMEDIR/strikers.aarch64"
$GPTOKEYB2 "strikers.aarch64" -c "$GAMEDIR/strikers.gptk.ini" &

pm_platform_helper "$GAMEDIR/strikers.aarch64"
./strikers.aarch64
status=$?

echo "[launcher] strikers exit status: $status"
pm_finish
