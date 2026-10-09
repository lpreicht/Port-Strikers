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
# RK3326's Mali-G31 GPU is normally exposed as ff400000.gpu. Other
# ArkOS kernels may use another node; discover the available devfreq device.
# The previous hardcoded fde60000.gpu belongs to a different Rockchip family.
gpu_governor_path=""
gpu_devfreq_dir=""
for gpu_dir in /sys/class/devfreq/ff400000.gpu /sys/class/devfreq/*.gpu; do
  if [ -r "$gpu_dir/governor" ]; then
    gpu_governor_path="$gpu_dir/governor"
    gpu_devfreq_dir="$gpu_dir"
    break
  fi
done
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
# RC3: keep 0.6667 reference resolution; only test per-draw GL error-check costs.
# Previous 0.5000 pixel-fill A/B saved 44% of pixels but barely improved FPS.
# Leave the original shadow, water and lightmap fixes intact.
# Optional resolution A/B: write 0.5 or 0.6667 into
# starfoxadventures/conf/render-scale.txt.
R36S_EFB_SCALE=0.6667
R36S_SCALE_CONFIG="$CONFDIR/render-scale.txt"
if [ -r "$R36S_SCALE_CONFIG" ]; then
  IFS= read -r requested_scale < "$R36S_SCALE_CONFIG" || true
  case "$requested_scale" in
    0.5|0.5000|0.6667) R36S_EFB_SCALE="$requested_scale" ;;
    *) echo "R36S: invalid render-scale.txt value; using 0.6667" ;;
  esac
fi
export FOXHOLLOW_RENDER_SCALE="$R36S_EFB_SCALE"
export FOXHOLLOW_LANGUAGE=de
export FOXHOLLOW_REV=1
export FOXHOLLOW_MEMORY_CARD="$CONFDIR/memorycard.raw"
export FOXHOLLOW_AUTOSAVE="$CONFDIR/autosave.bin"
export FOXHOLLOW_USER_DIR="$CONFDIR/data"
export FOXHOLLOW_CACHE_DIR="$CONFDIR/cache"
export FOXHOLLOW_PRESENT=direct
export AURORA_GLES_DRIVER_PROBE=0
# Aurora ARM's newer adaptive probe can still re-run on heavier scenes even
# when the startup probe count is zero. Explicit 0 disables both barriers
# and probing, matching the validated V053 behavior. 'pass' is NOT off.
export AURORA_GLES_DRAW_BARRIER=0
# The Dawn-only shadow experiment did not correct flicker and increased
# render time. Restore the faster Direct-GLES baseline, and diagnose repeated
# square shadow-mask GPU texture overwrites with immutable snapshots instead.
export R36S_SHADOW_FORCE_DAWN=0
# R36S decal-depth correction: GX negative z-near is clamped by GLES.
# Use a GLES-valid foreground bias only for projected ground-shadow decals.
# Set to 0 to restore exact original depth range without changing executable.
export R36S_DECAL_DEPTH_FIX=1
# Previous water-FX lite optimization did not improve performance; restore all\n# cosmetic water rendering by default, retaining opt-in comparison mode.
# First fast-water quality preset: keep splash/ripple overlays; only simplify the
# visible water surface\x27s two costly indirect texture lookups. 0=original water.
# The previous indirect-water shader simplification did not improve performance.
# Use original water shading for this independent draw-call budget experiment.
export R36S_WATER_FAST="${R36S_WATER_FAST:-0}"
# 2 = keep two of 4/8/16 indirect overlay layers, 0 = original full amount.
# This can also affect some non-water indirect lightmaps; compare visually.
# RC2 found no meaningful frame-rate gain from opaque draw sorting.
# Restore the unsorted baseline; allow opt-in comparison if desired.
# Aurora sorts only contiguous, opaque, depth-tested
# GX draw runs by shader, texture and uniform window, reducing state churn.
# Sorting can alter visuals for overlapping equal-depth surfaces.
# To re-enable RC2 behavior without rebuilding, write 1 to
# starfoxadventures/conf/opaque-sort.txt.
R36S_SORT_REQUEST=0
if [ -r "$CONFDIR/opaque-sort.txt" ]; then
  IFS= read -r sort_setting < "$CONFDIR/opaque-sort.txt" || true
  case "$sort_setting" in
    0|1) R36S_SORT_REQUEST="$sort_setting" ;;
    *) echo "R36S: invalid opaque-sort.txt; using 0" ;;
  esac
fi
export R36S_SORT_OPAQUE="$R36S_SORT_REQUEST"
# RC3 Mali-G31 A/B: disable only optional per-draw glGetError() calls.
# End-of-pass error detection, all GL draws and all stats remain intact.
# Set starfoxadventures/conf/gl-draw-checks.txt to 1 to restore the exact
# RC2 error-check behavior without recompiling. 0 is the RC3 experiment.
R36S_GL_DRAW_CHECK_REQUEST=0
if [ -r "$CONFDIR/gl-draw-checks.txt" ]; then
  IFS= read -r check_setting < "$CONFDIR/gl-draw-checks.txt" || true
  case "$check_setting" in
    0|1) R36S_GL_DRAW_CHECK_REQUEST="$check_setting" ;;
    *) echo "R36S: invalid gl-draw-checks.txt; using 0" ;;
  esac
fi
export R36S_GL_DRAW_ERROR_CHECK="$R36S_GL_DRAW_CHECK_REQUEST"
# RC4 profiles the complete Aurora end-frame path and KMSDRM display stages.
# Only timestamps and periodic stderr diagnostics; original GL commands intact.
# conf/rc4-profile.txt = 0 suppresses extra timing overhead, 1 enables.
R36S_PRESENT_PROFILE_REQUEST=1
if [ -r "$CONFDIR/rc4-profile.txt" ]; then
  IFS= read -r profile_setting < "$CONFDIR/rc4-profile.txt" || true
  case "$profile_setting" in
    0|1) R36S_PRESENT_PROFILE_REQUEST="$profile_setting" ;;
    *) echo "R36S: invalid rc4-profile.txt; using 1" ;;
  esac
fi
export R36S_PRESENT_PROFILE="$R36S_PRESENT_PROFILE_REQUEST"
# RC6: do not build extra hash tables for every GameCube draw only to print
# per-draw GX variance stats. This skips diagnosis only; all actual rendering
# and RC5 FIFO/endframe reporting still work. Set conf/gx-heavy-stats.txt
# to 1 to re-enable the exact RC5 behavior for the A/B control test.
R36S_GX_HEAVY_STATS_REQUEST=0
if [ -r "$CONFDIR/gx-heavy-stats.txt" ]; then
  IFS= read -r gx_stats_setting < "$CONFDIR/gx-heavy-stats.txt" || true
  case "$gx_stats_setting" in
    0|1) R36S_GX_HEAVY_STATS_REQUEST="$gx_stats_setting" ;;
    *) echo "R36S: invalid gx-heavy-stats.txt; using 0" ;;
  esac
fi
export R36S_GX_HEAVY_STATS="$R36S_GX_HEAVY_STATS_REQUEST"
# RC7: R36S KMSDRM present synchronization experiment.
# 0 requests uncapped swaps (may tear), 1 restores proven RC6 vsync.
R36S_SWAP_INTERVAL_REQUEST=0
if [ -r "$CONFDIR/swap-interval.txt" ]; then
  IFS= read -r swap_setting < "$CONFDIR/swap-interval.txt" || true
  case "$swap_setting" in
    0|1) R36S_SWAP_INTERVAL_REQUEST="$swap_setting" ;;
    *) echo "R36S: invalid swap-interval.txt; using 0" ;;
  esac
fi
export R36S_SWAP_INTERVAL="$R36S_SWAP_INTERVAL_REQUEST"
# RC8: already-existing Aurora nested CPU profiler, sampled for only every
# 60th frame, to avoid reintroducing expensive per-draw diagnostics.
# Set conf/deep-profile.txt to 0 to disable without a new binary.
R36S_DEEP_PROFILE_REQUEST=0
if [ -r "$CONFDIR/deep-profile.txt" ]; then
  IFS= read -r deep_setting < "$CONFDIR/deep-profile.txt" || true
  case "$deep_setting" in
    0|1) R36S_DEEP_PROFILE_REQUEST="$deep_setting" ;;
    *) echo "R36S: invalid deep-profile.txt; using 1" ;;
  esac
fi
export AURORA_DEEP_PROFILE="$R36S_DEEP_PROFILE_REQUEST"
export AURORA_DEEP_INTERVAL=60
# RC9 safe micro-optimization, exact triangle and quad indices.
# 0 in conf/fast-gx-indices.txt reverts to the full RC8 index loops.
R36S_FAST_GX_INDICES_REQUEST=1
if [ -r "$CONFDIR/fast-gx-indices.txt" ]; then
  IFS= read -r fast_index_setting < "$CONFDIR/fast-gx-indices.txt" || true
  case "$fast_index_setting" in
    0|1) R36S_FAST_GX_INDICES_REQUEST="$fast_index_setting" ;;
    *) echo "R36S: invalid fast-gx-indices.txt; using 1" ;;
  esac
fi
export R36S_FAST_GX_INDICES="$R36S_FAST_GX_INDICES_REQUEST"
export R36S_LIGHTMAP_INDIRECT_CAP="${R36S_LIGHTMAP_INDIRECT_CAP:-2}"
export R36S_WATER_LITE="${R36S_WATER_LITE:-0}"
# R36S FULL-VIDEO-CADENCE DIAGNOSTIC: process every THP video frame reached
# by the VI callback. This removes the deliberate alternate-frame JPEG skip.
# Audio retains the proven independent 16-buffer read-ahead fix.
# 1=every video frame; 2=half-rate; 0=frozen video.
export R36S_MENU_VIDEO_STRIDE=1

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

echo "R36S_PERF_TEST=RC11_VERTEX_LOADER_PIPELINE_CACHE_20261010"
echo "R36S_PERF_TEST_REFERENCE_SCALE=0.6667"
echo "FOXHOLLOW_RENDER_SCALE=$FOXHOLLOW_RENDER_SCALE"
echo "FOXHOLLOW_LANGUAGE=$FOXHOLLOW_LANGUAGE"
echo "FOXHOLLOW_PRESENT=$FOXHOLLOW_PRESENT"
echo "AURORA_GLES_DRIVER_PROBE=$AURORA_GLES_DRIVER_PROBE"
echo "AURORA_GLES_DRAW_BARRIER=$AURORA_GLES_DRAW_BARRIER"
echo "R36S_SHADOW_FORCE_DAWN=$R36S_SHADOW_FORCE_DAWN"
echo "R36S_DECAL_DEPTH_FIX=$R36S_DECAL_DEPTH_FIX"
echo "R36S_WATER_FAST=$R36S_WATER_FAST"
echo "R36S_SORT_OPAQUE=$R36S_SORT_OPAQUE"
echo "R36S_GL_DRAW_ERROR_CHECK=$R36S_GL_DRAW_ERROR_CHECK"
echo "R36S_PRESENT_PROFILE=$R36S_PRESENT_PROFILE"
echo "R36S_GX_HEAVY_STATS=$R36S_GX_HEAVY_STATS"
echo "R36S_SWAP_INTERVAL=$R36S_SWAP_INTERVAL"
echo "AURORA_DEEP_PROFILE=$AURORA_DEEP_PROFILE"
echo "AURORA_DEEP_INTERVAL=$AURORA_DEEP_INTERVAL"
echo "R36S_FAST_GX_INDICES=$R36S_FAST_GX_INDICES"
echo "R36S_LIGHTMAP_INDIRECT_CAP=$R36S_LIGHTMAP_INDIRECT_CAP"
echo "R36S_WATER_LITE=$R36S_WATER_LITE"
echo "R36S_MENU_VIDEO_STRIDE=$R36S_MENU_VIDEO_STRIDE"
echo "CPU_GOVERNOR=$(cat "$cpu_governor_path" 2>/dev/null || echo unavailable)"
echo "GPU_DEVFREQ_PATH=${gpu_devfreq_dir:-unavailable}"
echo "GPU_GOVERNOR=$(cat "$gpu_governor_path" 2>/dev/null || echo unavailable)"
if [ -n "$gpu_devfreq_dir" ]; then
  echo "GPU_FREQ_CURRENT=$(cat "$gpu_devfreq_dir/cur_freq" 2>/dev/null || echo unavailable)"
  echo "GPU_FREQ_AVAILABLE=$(cat "$gpu_devfreq_dir/available_frequencies" 2>/dev/null || echo unavailable)"
  echo "GPU_GOVERNORS_AVAILABLE=$(cat "$gpu_devfreq_dir/available_governors" 2>/dev/null || echo unavailable)"
fi

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
