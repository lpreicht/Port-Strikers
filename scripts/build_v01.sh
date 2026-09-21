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
  git clone --depth 1 --branch portmaster https://github.com/zalo/melee.git "$MELEE"
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

# Build the same Cortex-A35 Dawn/toolchain stack used by the working native Melee port.
python3 "$MELEE/native/tools/prepare_flip.py" --no-device --cpu a35

PLAIN_SDK="$TOOLS/aarch64--glibc--stable-2023.08-1"
HYBRID_SDK="$TOOLS/aarch64--glibc-2.30-hybrid"
DAWN="$TOOLS/dawn-install-a35"
SDL3="$TOOLS/sdl3-shim-install"

sh "$MELEE/native/tools/glibc230_toolchain.sh" build "$PLAIN_SDK" "$HYBRID_SDK"
export FLIP_TOOLCHAIN="$HYBRID_SDK"

# Link SDL3 API calls to the CFW-owned SDL2 implementation, exactly as the Melee PortMaster build does.
sh "$MELEE/native/tools/build_sdl3_shim.sh" "$SDL3"
export FLIP_SDL3_ROOT="$SDL3"
export FLIP_DAWN_PREFIX="$DAWN"

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

cmake --build "$BUILD" --target strikers --parallel "${BUILD_JOBS:-4}"

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
