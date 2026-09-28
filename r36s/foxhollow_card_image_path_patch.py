#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])

def replace(rel, old, new):
    p = root / rel
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"{rel}: pattern not found: {old[:160]!r}")
    p.write_text(s.replace(old, new, 1))

replace(
    "extern/aurora/include/dolphin/card.h",
    """// pass -1 to set both
void CARDSetBasePath(const char*, s32 chan);
void CARDSetLoadType(CARDFileType type);
""",
    """// pass -1 to set both
void CARDSetBasePath(const char*, s32 chan);
/* Foxhollow: point a slot at an exact raw memory-card image path. */
void CARDSetCardImagePath(const char*, s32 chan);
void CARDSetLoadType(CARDFileType type);
""",
)

replace(
    "extern/aurora/lib/dolphin/card.cpp",
    """void CARDSetLoadType(CARDFileType type) { SelectedFileType = type; }
""",
    """void CARDSetCardImagePath(const char* path, const s32 chan) {
  if (Initialized) {
    Log.fatal("CARDSetCardImagePath() called after CARDInit()!");
  }

  const std::filesystem::path filePath(path);
  if (filePath.empty()) {
    return;
  }

  std::error_code ec;
  if (!filePath.parent_path().empty()) {
    std::filesystem::create_directories(filePath.parent_path(), ec);
  }
  if (ec) {
    Log.warn("Failed to create card directory '{}': {}",
             aurora::io::fs_path_to_string(filePath.parent_path()), ec.message());
  }

  cardPaths[chan == 1 ? 1 : 0] = filePath;
  Log.info("Card image path set to: {}", aurora::io::fs_path_to_string(filePath));
}

void CARDSetLoadType(CARDFileType type) { SelectedFileType = type; }
""",
)

print("Foxhollow exact memory-card image path support restored")
