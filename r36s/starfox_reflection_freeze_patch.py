#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "game/src/main/newshadows.c"
text = p.read_text()

anchor = """void updateReflectionTextures(void)
{
    GXSetTexCopySrc(0, 0, 0x280, 0x1e0);
"""
replacement = """/*
 * R36S reflection freeze diagnostic.
 *
 * Generate a handful of valid RGB565/Z8 reflection pairs after every map-page
 * change, then keep sampling that last pair without issuing further EFB copies.
 * If movement flicker disappears, the live EFB-copy/update path is implicated.
 * If it remains, the fault is downstream in reflection sampling/material draws.
 */
static void* sR36sReflectionFreezePage = (void*)-1;
static u32 sR36sReflectionFreezeUpdates = 0;
#define R36S_REFLECTION_FREEZE_AFTER 8

void updateReflectionTextures(void)
{
    if (sR36sReflectionFreezePage != gCurRomListPage) {
        sR36sReflectionFreezePage = gCurRomListPage;
        sR36sReflectionFreezeUpdates = 0;
        OSReport("[r36s-reflection-freeze] map page changed; collecting fresh reflection copies\\n");
    }
    if (sR36sReflectionFreezeUpdates >= R36S_REFLECTION_FREEZE_AFTER) {
        return;
    }
    ++sR36sReflectionFreezeUpdates;
    if (sR36sReflectionFreezeUpdates == R36S_REFLECTION_FREEZE_AFTER) {
        OSReport("[r36s-reflection-freeze] reflection pair frozen after %u updates\\n",
                 (unsigned)R36S_REFLECTION_FREEZE_AFTER);
    }

    GXSetTexCopySrc(0, 0, 0x280, 0x1e0);
"""
if anchor not in text:
    raise SystemExit("reflection freeze patch: updateReflectionTextures anchor not found")
text = text.replace(anchor, replacement, 1)
p.write_text(text)
print("patched Star Fox reflection update freeze diagnostic (8 updates per map page)")
