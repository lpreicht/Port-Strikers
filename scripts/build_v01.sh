#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/build"
TOOLS="$WORK/melee/build/flip-tools"
STRIKERS="$WORK/strikers/smstrikers-port"
MELEE="$WORK/melee"
BUILD="$WORK/strikers-r36s"
DIST="$ROOT/dist"

STRIKERS_TAG="v1.2.0"

mkdir -p "$WORK" "$DIST"

if [ ! -d "$WORK/strikers/.git" ]; then
  git clone --depth 1 --branch "$STRIKERS_TAG" https://github.com/new-coke/strikers.git "$WORK/strikers"
fi
if [ ! -d "$MELEE/.git" ]; then
  # actions/cache restores flip-tools inside build/melee before the Melee repo exists.
  # Preserve that cache while replacing the placeholder directory with the real checkout.
  SAVED_FLIP_TOOLS="$WORK/.saved-flip-tools"
  rm -rf "$SAVED_FLIP_TOOLS"
  if [ -d "$MELEE/build/flip-tools" ]; then
    mv "$MELEE/build/flip-tools" "$SAVED_FLIP_TOOLS"
  fi
  rm -rf "$MELEE"
  git clone --depth 1 --branch portmaster https://github.com/zalo/melee.git "$MELEE"
  if [ -d "$SAVED_FLIP_TOOLS" ]; then
    mkdir -p "$MELEE/build"
    mv "$SAVED_FLIP_TOOLS" "$MELEE/build/flip-tools"
  fi
fi

# Strikers 1.2.0 already contains its game-specific Aurora changes in extern/aurora.
# Keep that tree intact. Replacing it with the Melee fork caused the V0.1 merge conflicts.
test -f "$STRIKERS/extern/aurora/include/aurora/aurora.h"
grep -q "aurora_capture_frame" "$STRIKERS/extern/aurora/include/aurora/aurora.h"
grep -q "AURORA_LINUX_EGL_PROC" "$STRIKERS/extern/aurora/lib/webgpu/gpu.cpp"

export RUSTUP_HOME="$TOOLS/rustup"
export CARGO_HOME="$TOOLS/cargo"
export PATH="$CARGO_HOME/bin:$PATH"

if [ ! -x "$CARGO_HOME/bin/rustup" ]; then
  curl -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path --profile minimal --default-toolchain stable
fi
"$CARGO_HOME/bin/rustup" target add aarch64-unknown-linux-gnu

PLAIN_SDK="$TOOLS/aarch64--glibc--stable-2023.08-1"
HYBRID_SDK="$TOOLS/aarch64--glibc-2.30-hybrid"
DAWN="$TOOLS/dawn-install-a35"
SDL3="$TOOLS/sdl3-shim-install"

# These must be visible to Melee's helper scripts themselves, not only to the final CMake step.
export FLIP_TOOLCHAIN="$HYBRID_SDK"
export FLIP_SDL3_ROOT="$SDL3"
export FLIP_DAWN_PREFIX="$DAWN"

# Build the same Cortex-A35 Dawn/toolchain stack used by the working native Melee port.
# The workflow restores this from cache for normal compile attempts.
if [ "${SKIP_PREP:-0}" != "1" ]; then
  python3 "$MELEE/native/tools/prepare_flip.py" --no-device --cpu a35
  sh "$MELEE/native/tools/glibc230_toolchain.sh" build "$PLAIN_SDK" "$HYBRID_SDK"
  sh "$MELEE/native/tools/build_sdl3_shim.sh" "$SDL3"
else
  test -x "$HYBRID_SDK/bin/aarch64-linux-gcc"
  test -f "$DAWN/lib/cmake/Dawn/DawnConfig.cmake"
  test -f "$SDL3/lib/libSDL3.so.0"
fi

if [ "${PREP_ONLY:-0}" = "1" ]; then
  echo "Toolchain/Dawn/SDL preparation complete."
  exit 0
fi

# Strikers upstream forces -static-libgcc. GCC 12's static unwinder references _dl_find_object
# (glibc 2.35), while the hybrid toolchain intentionally ships the old glibc-2.30-compatible
# libgcc_s.so.1. Keep libstdc++ static but let libgcc resolve dynamically.
python3 - "$STRIKERS/CMakeLists.txt" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
old = "target_link_options(strikers PRIVATE -static-libstdc++ -static-libgcc -Wl,-z,noexecstack)"
new = "target_link_options(strikers PRIVATE -static-libstdc++ -Wl,-z,noexecstack)"
if new not in s:
    if old not in s:
        raise SystemExit("could not locate static libgcc link options")
    s = s.replace(old, new, 1)
    p.write_text(s)
PY
# Dawn's exported CMake target references Threads::Threads. Aurora's system provider
# currently imports Dawn before it calls find_package(Threads), which is too late for
# CMake to validate DawnTargets.cmake. Load Threads immediately before Dawn.
python3 - "$STRIKERS/extern/aurora/cmake/AuroraDawnProvider.cmake" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text()
needle = "    set(CMAKE_FIND_PACKAGE_TARGETS_GLOBAL ON)\n    find_package(Dawn REQUIRED)\n"
repl = "    set(CMAKE_FIND_PACKAGE_TARGETS_GLOBAL ON)\n    find_package(Threads REQUIRED)\n    find_package(Dawn REQUIRED)\n"
if repl not in s:
    if needle not in s:
        raise SystemExit("could not locate system Dawn import")
    s = s.replace(needle, repl, 1)
    p.write_text(s)
PY
TOOLCHAIN="$MELEE/native/platform/flip/toolchain-a35.cmake"

rm -rf "$BUILD"
if ! cmake -S "$STRIKERS" -B "$BUILD" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-mcpu=cortex-a35+nocrypto" \
  -DCMAKE_CXX_FLAGS="-mcpu=cortex-a35+nocrypto -pthread" \
  -DCMAKE_EXE_LINKER_FLAGS="-pthread -Wl,--allow-shlib-undefined" \
  -DSTRIKERS_FFMPEG=OFF \
  -DSTRIKERS_AURORA=ON \
  -DAURORA_DAWN_PROVIDER=system \
  -DDawn_DIR="$DAWN/lib/cmake/Dawn" \
  -DAURORA_SDL3_PROVIDER=system \
  -DAURORA_SDL3_LINKAGE=shared \
  -DSDL3_DIR="$SDL3/lib/cmake/SDL3" \
  -DAURORA_NOD_PROVIDER=vendor \
  -DRust_CARGO_TARGET=aarch64-unknown-linux-gnu \
  -DBUILD_SHARED_LIBS=OFF \
  -DAURORA_CACHE_USE_ZSTD=OFF \
  -DTRACY_ENABLE=OFF; then
  echo "=== CMake configure diagnostics ==="
  [ -f "$BUILD/CMakeFiles/CMakeConfigureLog.yaml" ] && tail -n 300 "$BUILD/CMakeFiles/CMakeConfigureLog.yaml" || true
  exit 30
fi

# genstubs.py only scans static archives under the Strikers build tree. Our Dawn is an
# imported system archive outside that tree, so expose it there as a provider without copying it.
DAWN_ARCHIVE="$(find "$DAWN" -type f -name 'libwebgpu_dawn.a' -print -quit)"
if [ -z "$DAWN_ARCHIVE" ]; then
  echo "::error::libwebgpu_dawn.a not found under $DAWN"
  exit 41
fi
mkdir -p "$BUILD/external-providers"
ln -sf "$DAWN_ARCHIVE" "$BUILD/external-providers/libwebgpu_dawn.a"

# Safety check: these are real Dawn constructors, never acceptable as generated no-op stubs.
NM_TOOL="$(command -v llvm-nm || command -v nm)"
for sym in _ZN4dawn6native22DawnInstanceDescriptorC1Ev _ZN4dawn6native6opengl30RequestAdapterOptionsGetGLProcC1Ev; do
  if ! "$NM_TOOL" --defined-only "$DAWN_ARCHIVE" 2>/dev/null | grep -Fq "$sym"; then
    echo "::error::Expected Dawn symbol missing from $DAWN_ARCHIVE: $sym"
    exit 42
  fi
done
# Use Strikers upstream build order exactly: compile everything (including Aurora), allow the
# first executable link to fail, inspect the actually linked libraries, generate only the real
# missing host stubs, then relink. Building only strikers_scan made Aurora look absent and
# incorrectly produced ~187 GX/PAD/CARD/ImGui stubs.
(
  cd "$STRIKERS"
  sh tools/rebuild.sh "$BUILD"
)

# ArkOS compatibility gate.
sh "$MELEE/native/tools/glibc230_toolchain.sh" verify "$PLAIN_SDK" "$BUILD/strikers"

rm -rf "$DIST/stage"
mkdir -p "$DIST/stage/strikers/assets" "$DIST/stage/strikers/libs.aarch64" "$DIST/stage/strikers/runtime/config" "$DIST/stage/strikers/runtime/cache"
cp "$BUILD/strikers" "$DIST/stage/strikers/strikers.aarch64"
cp "$SDL3/lib/libSDL3.so.0" "$DIST/stage/strikers/libs.aarch64/libSDL3.so.0"
cp "$ROOT/port/strikers.ini" "$DIST/stage/strikers/strikers.ini"
cp "$ROOT/port/strikers.gptk.ini" "$DIST/stage/strikers/strikers.gptk.ini"
cp "$ROOT/port/README.txt" "$DIST/stage/strikers/README.txt"
touch "$DIST/stage/strikers/assets/PUT_YOUR_USA_G4QE01_ISO_HERE"
cp "$ROOT/port/Super Mario Strikers.sh" "$DIST/stage/Super Mario Strikers.sh"
cp "$ROOT/port/port.json" "$DIST/stage/port.json"

chmod +x "$DIST/stage/Super Mario Strikers.sh" "$DIST/stage/strikers/strikers.aarch64"
(
  cd "$DIST/stage"
  zip -r -9 "$DIST/strikers-r36s-v0.1.zip" .
)
sha256sum "$DIST/strikers-r36s-v0.1.zip"
