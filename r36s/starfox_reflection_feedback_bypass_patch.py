#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
p = root / "game/src/main/newshadows.c"
s = p.read_text()

old = """void drawReflectionTexture(void)
{
    char* texture = (char*)gNewShadowReflectionTexture;
    drawTexture(texture, 0.0f, 0.0f, 0xff, 0x40);
    GXSetTexCopySrc(0, 0, 0x50, 0x3c);
"""
new = """void drawReflectionTexture(void)
{
    /*
     * R36S diagnostic: keep the small-copy + GX_TRUE clear sequence, but do
     * not feed the previous frame's large RGB565 reflection back into the EFB
     * before the new scene is rendered.  The later 320x240 reflection updates
     * remain fully live.
     */
    static int sR36sFeedbackBypassLogged;
    if (!sR36sFeedbackBypassLogged) {
        OSReport("[r36s-reflection-feedback] previous-frame reflection draw bypassed; copy/clear retained\\n");
        sR36sFeedbackBypassLogged = 1;
    }
    GXSetTexCopySrc(0, 0, 0x50, 0x3c);
"""
if old not in s:
    raise SystemExit("reflection feedback bypass: drawReflectionTexture anchor not found")
p.write_text(s.replace(old, new, 1))
print("patched Star Fox previous-frame reflection feedback draw bypass")
