#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / "game/src/main/pi_dolphin.c"
s = p.read_text()

def replace(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{label}: expected one match, got {n}")
    s = s.replace(old, new, 1)

# stderr breadcrumbs for the exact initial-map load stage.
if '#include <stdio.h>\n' not in s:
    replace('#include "string.h"\n', '#include "string.h"\n#include <stdio.h>\n', 'stdio include')

old_mapload = '''void mapLoadDataFiles(int mapIdx) {
    if (sMapFileNameAdjacencyTable[mapIdx] != -1) {
        SaveGameCharacterPosition* r = (SaveGameCharacterPosition*)(*gMapEventInterface)->getCurCharPos();
        r->mapDataFileId = mapIdx;
    }
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX1_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX1_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX0_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX0_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIM_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIM_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_MODELS_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_MODELS_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_BLOCKS_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_BLOCKS_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_VOXMAP_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_VOXMAP_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIMCURV_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIMCURV_BIN_A);
}
'''

new_mapload = r'''void mapLoadDataFiles(int mapIdx) {
    if (sMapFileNameAdjacencyTable[mapIdx] != -1) {
        SaveGameCharacterPosition* r = (SaveGameCharacterPosition*)(*gMapEventInterface)->getCurCharPos();
        r->mapDataFileId = mapIdx;
    }

#ifdef AURORA_R36S_OFFSCREEN
    // V031 diagnostic/fix: Aurora ARM changed the async DVD implementation. The
    // initial Star Fox map load happens before the normal VI/audio pump is
    // established, so force these first resource loads synchronous. This keeps
    // Foxhollow's original main-thread ownership and tells us exactly which
    // resource call (if any) stalls.
    const int savedForceLoadImmediately = gForceLoadImmediately;
    gForceLoadImmediately = 1;
#define R36S_LOAD_SLOT(slotId) do { \
        fprintf(stderr, "[R36S V031 mapload] before map=%d file=0x%02x pendingDvd=%d inFlight=0x%08x\n", \
                mapIdx, (unsigned)(slotId), gPendingDvdReadCount, (unsigned)gAssetLoadInFlightFlags); \
        fflush(stderr); \
        void* r36s_loaded = mapLoadDataFile(mapIdx, (slotId)); \
        fprintf(stderr, "[R36S V031 mapload] after  map=%d file=0x%02x ptr=%p pendingDvd=%d inFlight=0x%08x\n", \
                mapIdx, (unsigned)(slotId), r36s_loaded, gPendingDvdReadCount, (unsigned)gAssetLoadInFlightFlags); \
        fflush(stderr); \
    } while (0)
    fprintf(stderr, "[R36S V031 mapload] BEGIN map=%d forcedSync=1\n", mapIdx);
    fflush(stderr);
    R36S_LOAD_SLOT(MLDF_FILEID_TEX1_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_TEX1_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_TEX0_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_TEX0_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_ANIM_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_ANIM_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_MODELS_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_MODELS_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_BLOCKS_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_BLOCKS_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_VOXMAP_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_VOXMAP_BIN_A);
    R36S_LOAD_SLOT(MLDF_FILEID_ANIMCURV_TAB_A);
    R36S_LOAD_SLOT(MLDF_FILEID_ANIMCURV_BIN_A);
#undef R36S_LOAD_SLOT
    gForceLoadImmediately = savedForceLoadImmediately;
    fprintf(stderr, "[R36S V031 mapload] END map=%d pendingDvd=%d inFlight=0x%08x\n",
            mapIdx, gPendingDvdReadCount, (unsigned)gAssetLoadInFlightFlags);
    fflush(stderr);
#else
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX1_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX1_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX0_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_TEX0_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIM_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIM_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_MODELS_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_MODELS_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_BLOCKS_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_BLOCKS_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_VOXMAP_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_VOXMAP_BIN_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIMCURV_TAB_A);
    mapLoadDataFile(mapIdx, MLDF_FILEID_ANIMCURV_BIN_A);
#endif
}
'''
replace(old_mapload, new_mapload, 'mapLoadDataFiles')

old_rom = '''        if (ok != 0) {
            gMapRomListBuffers[mapIndex] = (uintptr_t)mmAlloc(DVD_FI_LENGTH(fi), 0x7d7d7d7d, 0);
            gRomListLoadInFlight = 1;
            DVDReadAsyncPrio(fi, (void*)gMapRomListBuffers[mapIndex], DVD_FI_LENGTH(fi), 0, romListReadCb, 2);
        }
'''
new_rom = r'''        if (ok != 0) {
            gMapRomListBuffers[mapIndex] = (uintptr_t)mmAlloc(DVD_FI_LENGTH(fi), 0x7d7d7d7d, 0);
            gRomListLoadInFlight = 1;
#ifdef AURORA_R36S_OFFSCREEN
            fprintf(stderr, "[R36S V031 romlist] sync read begin mapIndex=%d bytes=%u\n",
                    mapIndex, (unsigned)DVD_FI_LENGTH(fi));
            fflush(stderr);
            const s32 r36s_rom_result =
                DVDRead(fi, (void*)gMapRomListBuffers[mapIndex], DVD_FI_LENGTH(fi), 0);
            romListReadCb(r36s_rom_result, fi);
            fprintf(stderr, "[R36S V031 romlist] sync read end mapIndex=%d result=%d inFlight=%d\n",
                    mapIndex, (int)r36s_rom_result, gRomListLoadInFlight);
            fflush(stderr);
#else
            DVDReadAsyncPrio(fi, (void*)gMapRomListBuffers[mapIndex], DVD_FI_LENGTH(fi), 0, romListReadCb, 2);
#endif
        }
'''
replace(old_rom, new_rom, 'piRomLoadSection async branch')

p.write_text(s)
print("R36S V031 synchronous initial map-load diagnostics applied")
