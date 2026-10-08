#!/usr/bin/env bash
# BlueWake GameCube recomp source-only ARM64/Linux host compile experiment.
# No Nintendo code/data. Built artifact is NOT an ArkOS-compatible game port.
set -euo pipefail
test "$(uname -m)" = "aarch64" || { echo "Requires ARM64 Linux builder"; exit 3; }
for c in git cmake ninja clang clang++ python3; do command -v "$c" || exit 3; done
mkdir -p build/windwaker-r36s
cd build/windwaker-r36s
git init -q bluewake
git -C bluewake fetch --depth 1 https://github.com/chrissotraidis/bluewake.git 33666e863b79454761682b7d84737ae58e6f1041
git -C bluewake checkout --detach FETCH_HEAD
python3 - <<'PY'
import json, subprocess
from pathlib import Path
p=Path('bluewake')
lock=json.loads((p/'config/dependencies.lock.json').read_text())
dep=next(d for d in lock['dependencies'] if d['id']=='recompcore')
folder=p/'ref/recompcore'
folder.mkdir(parents=True,exist_ok=True)
subprocess.run(['git','init','-q',str(folder)],check=True)
subprocess.run(['git','-C',str(folder),'fetch','--depth','1',dep['url'],dep['sha']],check=True)
subprocess.run(['git','-C',str(folder),'checkout','--detach','FETCH_HEAD'],check=True)
PY
cmake -S bluewake/linux -B build-host -G Ninja -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DAURORA_DAWN_PROVIDER=package -DAURORA_SDL3_PROVIDER=vendor
cmake --build build-host --target bluewake bluewake_disc_extract --parallel 2
file build-host/bluewake
mkdir -p artifacts
cp build-host/bluewake artifacts/bluewake-arm64-LINUX-unadapted
printf 'NOT a working R36S game port. Build host only; no guest game code, no glibc 2.30 / GLES/KMSDRM adaptation.\n' > artifacts/STATUS.txt
