#!/usr/bin/env python3
from pathlib import Path
import sys

root=Path(sys.argv[1])
p=root/"extern/aurora/lib/dolphin/dvd/dvd.cpp"
s=p.read_text()

old=r'''bool aurora_dvd_open(const char* disc_path) {
  if (disc_path == nullptr) {
    return false;
  }

  s_worker.stop();
  clearState();

  SDL_IOStream* io = SDL_IOFromFile(disc_path, "rb");
  if (io == nullptr) {
    return false;
  }

  const NodDiscStream stream{
      .user_data = io,
      .read_at = sdlStreamReadAt,
      .stream_len = sdlStreamLen,
      .close = sdlStreamClose,
  };
  const NodDiscOptions options{
      .preloader_threads = 1,
  };

  NodHandle* discHandle;
  NodResult result = nod_disc_open_stream(&stream, &options, &discHandle);
  if (result != NOD_RESULT_OK || discHandle == nullptr) {
    clearState();
    return false;
  }

  s_disc = new CommandDataNod(discHandle);
'''

new=r'''bool aurora_dvd_open(const char* disc_path) {
  if (disc_path == nullptr) {
    return false;
  }

  s_worker.stop();
  clearState();

  // R36S: open the disc directly through nod instead of routing file I/O
  // through SDL_IOStream. This avoids stream-wrapper issues on compressed RVZ
  // images and keeps the decompressor's own random-access file path intact.
  const NodDiscOptions options{
      .preloader_threads = 0,
  };

  NodHandle* discHandle = nullptr;
  NodResult result = nod_disc_open(disc_path, &options, &discHandle);
  if (result != NOD_RESULT_OK || discHandle == nullptr) {
    const char* nodError = nod_error_message();
    fprintf(stderr, "aurora_dvd_open: nod_disc_open failed result=%d path=%s error=%s\n",
            (int)result, disc_path, nodError ? nodError : "(no nod error)");
    clearState();
    return false;
  }

  NodDiscMeta discMeta{};
  if (nod_disc_meta(discHandle, &discMeta) == NOD_RESULT_OK) {
    fprintf(stdout,
            "aurora_dvd_open: opened disc format=%d compression=%d block_size=%u disc_size=%llu\n",
            (int)discMeta.format, (int)discMeta.compression.kind, discMeta.block_size,
            (unsigned long long)discMeta.disc_size);
  } else {
    const char* nodError = nod_error_message();
    fprintf(stderr, "aurora_dvd_open: nod_disc_meta failed: %s\n",
            nodError ? nodError : "(no nod error)");
  }

  s_disc = new CommandDataNod(discHandle);
'''

if old not in s:
    raise SystemExit("aurora_dvd_open pattern not found")
s=s.replace(old,new,1)

# Add diagnostics for partition/FST failures too.
s=s.replace(
r'''  result = nod_disc_open_partition_kind(s_disc->handle, NOD_PARTITION_KIND_DATA, nullptr, &s_partition);
  if (result != NOD_RESULT_OK || s_partition == nullptr) {
    clearState();
    return false;
  }
''',
r'''  result = nod_disc_open_partition_kind(s_disc->handle, NOD_PARTITION_KIND_DATA, nullptr, &s_partition);
  if (result != NOD_RESULT_OK || s_partition == nullptr) {
    const char* nodError = nod_error_message();
    fprintf(stderr, "aurora_dvd_open: open data partition failed result=%d error=%s\n",
            (int)result, nodError ? nodError : "(no nod error)");
    clearState();
    return false;
  }
''',1)

s=s.replace(
r'''  if (!rebuildFST()) {
    clearState();
    return false;
  }
''',
r'''  if (!rebuildFST()) {
    const char* nodError = nod_error_message();
    fprintf(stderr, "aurora_dvd_open: rebuildFST failed error=%s\n",
            nodError ? nodError : "(no nod error)");
    clearState();
    return false;
  }
''',1)

p.write_text(s)
print("R36S direct nod DVD loader patch applied")
