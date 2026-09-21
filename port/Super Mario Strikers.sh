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

# Keep the handheld shader/pipeline caches isolated from older desktop/storage-buffer builds.
# Aurora stores serialized GX PipelineConfig records here as well as Dawn's driver cache.
export STRIKERS_CACHE_DIR="$GAMEDIR/runtime/cache/cpu-vertex-v2"
mkdir -p "$STRIKERS_CACHE_DIR"

# One-time cleanup of the old default SDL_GetPrefPath caches. CARD saves live separately
# under userPath and are intentionally untouched.
CACHE_RESET_MARKER="$GAMEDIR/runtime/.cpu_vertex_cache_reset_v2"
if [ ! -f "$CACHE_RESET_MARKER" ]; then
  for cache_base in "$HOME/.local/share/Super Mario Strikers" "$STRIKERS_CACHE_DIR"; do
    rm -f "$cache_base/dawn_cache.db" "$cache_base/dawn_cache.db-shm" "$cache_base/dawn_cache.db-wal" \
          "$cache_base/pipeline_cache.db" "$cache_base/pipeline_cache.db-shm" "$cache_base/pipeline_cache.db-wal"
  done
  touch "$CACHE_RESET_MARKER"
  echo "[launcher] reset old Dawn + Aurora pipeline caches for CPU vertex decode"
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

# R36S/ArkOS: make PortMaster\'s kill combo deterministic. gptokeyb defaults to\n# BACK/SELECT unless HOTKEY was inherited from device detection; force it here.\nexport HOTKEY=back\n\necho "[launcher] SDL3 shim -> SDL2 video=$SDL3SHIM_SDL2_VIDEODRIVER audio=$SDL3SHIM_SDL2_AUDIODRIVER"

# Known-good ArkOS Mali-G31 driver on the user's R36S.
MALI="/usr/local/lib/aarch64-linux-gnu/libmali-bifrost-g31-rxp0-gbm.so"
if [ -f "$MALI" ]; then
  export LD_PRELOAD="$MALI${LD_PRELOAD:+:$LD_PRELOAD}"
  export LD_LIBRARY_PATH="/usr/local/lib/aarch64-linux-gnu:/usr/local/lib:/usr/lib/aarch64-linux-gnu:/usr/lib:/lib/aarch64-linux-gnu:/lib:$LD_LIBRARY_PATH"
fi

export STRIKERS_DATA="${discs[0]}"
export STRIKERS_CONFIG="$GAMEDIR/strikers.ini"

# R36S performance mode, based on the settings used by the working native Melee port.
# Enable all CPU cores and request performance governors while the game runs, then restore
# the original firmware state on exit. Failures are non-fatal on firmwares that lock sysfs.
enabled_cpu_paths=""
cpu_governor_path=/sys/devices/system/cpu/cpufreq/policy0/scaling_governor
gpu_governor_path=/sys/class/devfreq/fde60000.gpu/governor
dmc_governor_path=/sys/class/devfreq/dmc/governor
cpu_governor_previous=""
gpu_governor_previous=""
dmc_governor_previous=""

strikers_write_sysfs() {
  path="$1"
  value="$2"
  if [ -w "$path" ]; then
    printf '%s\n' "$value" > "$path" 2>/dev/null
    return $?
  fi
  if [ -n "${ESUDO:-}" ]; then
    $ESUDO sh -c "printf '%s\\n' '$value' > '$path'" >/dev/null 2>&1
    return $?
  fi
  return 1
}

strikers_restore_performance() {
  [ -n "$cpu_governor_previous" ] && strikers_write_sysfs "$cpu_governor_path" "$cpu_governor_previous" || true
  [ -n "$gpu_governor_previous" ] && strikers_write_sysfs "$gpu_governor_path" "$gpu_governor_previous" || true
  [ -n "$dmc_governor_previous" ] && strikers_write_sysfs "$dmc_governor_path" "$dmc_governor_previous" || true
  for cpu_path in $enabled_cpu_paths; do
    strikers_write_sysfs "$cpu_path" 0 || true
  done
}
trap strikers_restore_performance EXIT

if [ "${STRIKERS_PERFORMANCE:-1}" = 1 ]; then
  if [ -r "$cpu_governor_path" ]; then
    previous="$(cat "$cpu_governor_path" 2>/dev/null || true)"
    if strikers_write_sysfs "$cpu_governor_path" performance; then cpu_governor_previous="$previous"; fi
  fi
  if [ -r "$gpu_governor_path" ]; then
    previous="$(cat "$gpu_governor_path" 2>/dev/null || true)"
    if strikers_write_sysfs "$gpu_governor_path" performance; then gpu_governor_previous="$previous"; fi
  fi
  if [ -r "$dmc_governor_path" ]; then
    previous="$(cat "$dmc_governor_path" 2>/dev/null || true)"
    if strikers_write_sysfs "$dmc_governor_path" performance; then dmc_governor_previous="$previous"; fi
  fi
  for cpu_path in /sys/devices/system/cpu/cpu[0-9]*/online; do
    [ -r "$cpu_path" ] || continue
    if [ "$(cat "$cpu_path" 2>/dev/null || echo 1)" = 0 ]; then
      if strikers_write_sysfs "$cpu_path" 1; then
        enabled_cpu_paths="$enabled_cpu_paths $cpu_path"
      fi
    fi
  done
fi

# Presentation worker defaults validated by the handheld Aurora path.
export MELEE_FLIP_PRESENT_THREAD="${MELEE_FLIP_PRESENT_THREAD:-1}"
export MELEE_FLIP_ASYNC_PRESENT="${MELEE_FLIP_ASYNC_PRESENT:-1}"

chmod +x "$GAMEDIR/strikers.aarch64"
$GPTOKEYB2 "strikers.aarch64" -c "$GAMEDIR/strikers.gptk.ini" &

pm_platform_helper "$GAMEDIR/strikers.aarch64"
./strikers.aarch64
status=$?

echo "[launcher] strikers exit status: $status"
pm_finish
