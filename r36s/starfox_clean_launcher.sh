#!/bin/bash
# Star Fox Adventures / Foxhollow - clean R36S GitHub build
# One permanent launcher. Future clean tests replace the GitHub artifact instead
# of adding versioned launchers or LD_PRELOAD experiment shims.

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

[ -f "$controlfolder/control.txt" ] || { echo "PortMaster control.txt not found"; exit 1; }
source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

GAMEDIR="/$directory/ports/starfoxadventures"
DATADIR="$GAMEDIR/gamedata"
BINDIR="$GAMEDIR/bin"
LIBDIR="$GAMEDIR/lib"
CONFDIR="$GAMEDIR/conf"
LOGFILE="$GAMEDIR/log.txt"
NATIVE_BIN="$BINDIR/foxhollow.aarch64"

mkdir -p "$DATADIR" "$CONFDIR/config" "$CONFDIR/data" "$CONFDIR/cache" "$GAMEDIR/logs"
cd "$GAMEDIR" || exit 1
: > "$LOGFILE"
exec > >(tee "$LOGFILE") 2>&1

enabled_cpu_paths=""
cpu_governor_path=/sys/devices/system/cpu/cpufreq/policy0/scaling_governor
gpu_governor_path=/sys/class/devfreq/fde60000.gpu/governor
dmc_governor_path=/sys/class/devfreq/dmc/governor
cpu_governor_previous=""
gpu_governor_previous=""
dmc_governor_previous=""

starfox_write_sysfs() {
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

starfox_restore_performance() {
  [ -n "$cpu_governor_previous" ] && starfox_write_sysfs "$cpu_governor_path" "$cpu_governor_previous" || true
  [ -n "$gpu_governor_previous" ] && starfox_write_sysfs "$gpu_governor_path" "$gpu_governor_previous" || true
  [ -n "$dmc_governor_previous" ] && starfox_write_sysfs "$dmc_governor_path" "$dmc_governor_previous" || true
  for cpu_path in $enabled_cpu_paths; do
    starfox_write_sysfs "$cpu_path" 0 || true
  done
}

cleanup() {
  trap - EXIT INT TERM
  echo "=== cleanup ==="
  starfox_restore_performance
  killall gptokeyb gptokeyb2 2>/dev/null || true
  cp -f "$LOGFILE" "$GAMEDIR/logs/last.log" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

msg() { echo "$*"; type pm_message >/dev/null 2>&1 && pm_message "$*"; }

echo "============================================================"
echo "Star Fox Adventures / Foxhollow - R36S CLEAN GITHUB BUILD"
echo "============================================================"
date 2>/dev/null || true
echo "CFW_NAME=${CFW_NAME:-unknown}"
echo "DEVICE_NAME=${DEVICE_NAME:-unknown}"
echo "DEVICE_CPU=${DEVICE_CPU:-unknown}"
echo "DEVICE_ARCH=${DEVICE_ARCH:-unknown}"
echo "DISPLAY=${DISPLAY_WIDTH:-?}x${DISPLAY_HEIGHT:-?}"
uname -a 2>/dev/null || true
free -m 2>/dev/null || true
[ -f "$GAMEDIR/BUILD_INFO.txt" ] && cat "$GAMEDIR/BUILD_INFO.txt"

[ -x "$NATIVE_BIN" ] || { msg "foxhollow.aarch64 missing"; exit 2; }
DISC="$(find "$DATADIR" -maxdepth 1 -type f \( -iname '*.iso' -o -iname '*.rvz' -o -iname '*.gcm' \) -print 2>/dev/null | head -n 1)"
[ -n "$DISC" ] || { msg "No Star Fox Adventures disc image found in gamedata."; exit 2; }
echo "DISC=$DISC"

unset DISPLAY WAYLAND_DISPLAY VK_ICD_FILENAMES
export SDL_VIDEODRIVER=sdl2
export SDL3SHIM_SDL2_VIDEODRIVER=kmsdrm
export SDL_KMSDRM_ATOMIC=0
export SDL_AUDIODRIVER=alsa
export SDL3SHIM_SDL2_AUDIODRIVER=alsa
export EGL_PLATFORM=gbm
export HOTKEY=back

MALI="/usr/local/lib/aarch64-linux-gnu/libmali-bifrost-g31-rxp0-gbm.so"
SYSTEM_GL_LIB="/usr/local/lib/aarch64-linux-gnu"
[ -d "$SYSTEM_GL_LIB" ] || SYSTEM_GL_LIB="/lib/aarch64-linux-gnu"

export HOME="$CONFDIR"
export XDG_CONFIG_HOME="$CONFDIR/config"
export XDG_DATA_HOME="$CONFDIR/data"
export XDG_CACHE_HOME="$CONFDIR/cache"
export LD_LIBRARY_PATH="$LIBDIR:$SYSTEM_GL_LIB:/usr/local/lib:/usr/lib/aarch64-linux-gnu:/usr/lib:/lib/aarch64-linux-gnu:/lib:${LD_LIBRARY_PATH:-}"
if [ -f "$MALI" ]; then
  export LD_PRELOAD="$MALI"
fi
if [ ${#sdl_controllerconfig} -lt 100000 ]; then
  export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
fi
export MALLOC_ARENA_MAX=2

export FOXHOLLOW_DISC="$DISC"
export FOXHOLLOW_SCREEN_STYLE=narrow
export FOXHOLLOW_FULLSCREEN=1
export FOXHOLLOW_VSYNC=1
export FOXHOLLOW_FRAME_LIMIT=0
export FOXHOLLOW_RENDER_SCALE=0.6667
export FOXHOLLOW_LANGUAGE=de
export FOXHOLLOW_REV=1
export FOXHOLLOW_MEMORY_CARD="$CONFDIR/memorycard.raw"
export FOXHOLLOW_AUTOSAVE="$CONFDIR/autosave.bin"
export FOXHOLLOW_USER_DIR="$CONFDIR/data"
export FOXHOLLOW_CACHE_DIR="$CONFDIR/cache"
export FOXHOLLOW_PRESENT=direct
export AURORA_GLES_DRIVER_PROBE=0
# Aurora ARM's newer adaptive probe can still re-run on heavier scenes even
# when the startup probe count is zero. An explicit barrier override disables
# auto-probing completely while keeping barriers off, matching the V053 intent.
export AURORA_GLES_DRAW_BARRIER=pass
# Keep base water polygons and reflection; skip optional water particle/overlay passes.
export R36S_WATER_LITE="${R36S_WATER_LITE:-1}"

if [ "${FOXHOLLOW_PERFORMANCE:-1}" = 1 ]; then
  if [ -r "$cpu_governor_path" ]; then
    previous="$(cat "$cpu_governor_path" 2>/dev/null || true)"
    if starfox_write_sysfs "$cpu_governor_path" performance; then cpu_governor_previous="$previous"; fi
  fi
  if [ -r "$gpu_governor_path" ]; then
    previous="$(cat "$gpu_governor_path" 2>/dev/null || true)"
    if starfox_write_sysfs "$gpu_governor_path" performance; then gpu_governor_previous="$previous"; fi
  fi
  if [ -r "$dmc_governor_path" ]; then
    previous="$(cat "$dmc_governor_path" 2>/dev/null || true)"
    if starfox_write_sysfs "$dmc_governor_path" performance; then dmc_governor_previous="$previous"; fi
  fi
  for cpu_path in /sys/devices/system/cpu/cpu[0-9]*/online; do
    [ -r "$cpu_path" ] || continue
    if [ "$(cat "$cpu_path" 2>/dev/null || echo 1)" = 0 ]; then
      if starfox_write_sysfs "$cpu_path" 1; then
        enabled_cpu_paths="$enabled_cpu_paths $cpu_path"
      fi
    fi
  done
fi

echo "FOXHOLLOW_RENDER_SCALE=$FOXHOLLOW_RENDER_SCALE"
echo "FOXHOLLOW_LANGUAGE=$FOXHOLLOW_LANGUAGE"
echo "FOXHOLLOW_PRESENT=$FOXHOLLOW_PRESENT"
echo "AURORA_GLES_DRIVER_PROBE=$AURORA_GLES_DRIVER_PROBE"
echo "AURORA_GLES_DRAW_BARRIER=$AURORA_GLES_DRAW_BARRIER"
echo "R36S_WATER_LITE=$R36S_WATER_LITE"
echo "CPU_GOVERNOR=$(cat "$cpu_governor_path" 2>/dev/null || echo unavailable)"
echo "GPU_GOVERNOR=$(cat "$gpu_governor_path" 2>/dev/null || echo unavailable)"

# Native SDL handles the actual game controls. GPTOKEYB is only used for the
# PortMaster-standard device exit hotkey (Select+Start on the R36S).
$ESUDO chmod 666 /dev/uinput 2>/dev/null || true
$GPTOKEYB "$NATIVE_BIN" >/dev/null 2>&1 &

if type pm_platform_helper >/dev/null 2>&1; then
  pm_platform_helper "$NATIVE_BIN" >/dev/null 2>&1 || true
fi

echo "=== launching clean native Foxhollow ==="
echo "SDL_VIDEODRIVER=$SDL_VIDEODRIVER -> $SDL3SHIM_SDL2_VIDEODRIVER"
echo "SDL_AUDIODRIVER=$SDL_AUDIODRIVER"
echo "EGL_PLATFORM=$EGL_PLATFORM"
echo "LD_PRELOAD=${LD_PRELOAD:-}"
echo "FOXHOLLOW_DISC=$FOXHOLLOW_DISC"

set +e
"$NATIVE_BIN"
RC=$?
set -e

echo "FOXHOLLOW_EXIT_CODE=$RC"
echo "=== END ==="
exit "$RC"
