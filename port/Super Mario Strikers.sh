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

if [ ${#sdl_controllerconfig} -lt 100000 ]; then
  export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
fi

export LD_LIBRARY_PATH="$GAMEDIR/libs.${DEVICE_ARCH}:${LD_LIBRARY_PATH:-}"

# SDL3-over-SDL2 shim: use ArkOS' own SDL2 display/audio/controller backends.
if [ -n "${SDL_VIDEODRIVER:-}" ] && [ -z "${SDL3SHIM_SDL2_VIDEODRIVER:-}" ]; then
  export SDL3SHIM_SDL2_VIDEODRIVER="$SDL_VIDEODRIVER"
fi
if [ -n "${SDL_AUDIODRIVER:-}" ] && [ -z "${SDL3SHIM_SDL2_AUDIODRIVER:-}" ]; then
  export SDL3SHIM_SDL2_AUDIODRIVER="$SDL_AUDIODRIVER"
fi
export SDL_VIDEODRIVER=sdl2
export SDL_AUDIODRIVER=sdl2

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
