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
export STRIKERS_CACHE_DIR="$GAMEDIR/runtime/cache/direct-gles-v1"
mkdir -p "$STRIKERS_CACHE_DIR"

# Keep the learned Dawn/Aurora caches across launches and port updates.
# Pipeline config versions are part of the cache key, so incompatible records
# are ignored without throwing away good stadium pipelines from previous runs.
echo "[launcher] keeping Dawn + Aurora pipeline caches"


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
# SDL3 handles audio through its native ALSA driver in V0.4. Video still uses
# the SDL2 shim because ArkOS' KMSDRM stack is provided there.
export SDL_AUDIODRIVER=alsa

# R36S/ArkOS: make PortMaster's kill combo deterministic. gptokeyb defaults to
# BACK/SELECT unless HOTKEY was inherited from device detection; force it here.
export HOTKEY=back

echo "[launcher] SDL3 video=sdl2->$SDL3SHIM_SDL2_VIDEODRIVER audio=$SDL_AUDIODRIVER"

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

# This exact Mali-G31/r13p0 path has now been validated across normal play and
# goal replays. Skip Aurora's expensive diagnostic double-render probe unless
# explicitly re-enabled for debugging.
export AURORA_GLES_DRIVER_PROBE="${AURORA_GLES_DRIVER_PROBE:-0}"


chmod +x "$GAMEDIR/strikers"
# gptokeyb2 uses pkill on ArkOS; Linux comm names are limited to 15 chars, so
# "strikers.aarch64" cannot be matched reliably. The executable comm begins "strikers".
$GPTOKEYB2 "strikers" -c "$GAMEDIR/strikers.gptk.ini" &
GPTK_PID=$!

pm_platform_helper "$GAMEDIR/strikers"
./strikers
status=$?

# Promote the learned writable Aurora pipeline DB to the read-only seed format
# expected beside the game. On the next launch Strikers can compile those known
# stadium/replay pipelines before gameplay instead of discovering them again in
# the opening camera. This is especially useful after PortMaster updates.
PIPE_DB="$GAMEDIR/runtime/cache/direct-gles-v1/pipeline_cache.db"
PIPE_SEED="$GAMEDIR/initial_pipeline_cache.db"
if [ -s "$PIPE_DB" ]; then
  cp -f "$PIPE_DB" "$PIPE_SEED" 2>/dev/null || true
fi

# Do not leave the input helper around after the native process releases KMSDRM.
if [ -n "${GPTK_PID:-}" ]; then
  kill "$GPTK_PID" >/dev/null 2>&1 || true
  wait "$GPTK_PID" 2>/dev/null || true
fi

echo "[launcher] strikers exit status: $status"
pm_finish
