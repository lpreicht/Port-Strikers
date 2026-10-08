#!/usr/bin/env python3
"""Decouple expensive menu JPEG video refreshes from THP audio progression.

Pinned Foxhollow's PC PlayControl decodes THP synchronously in the VI post-
retrace callback, unlike the original threaded GameCube movie player.
Keep reading EVERY compressed THP frame and decoding ALL audio components,
but reduce libjpeg video decode cadence for menu map 63.

R36S_MENU_VIDEO_STRIDE=1: original every-frame JPEG playback
R36S_MENU_VIDEO_STRIDE=2: decode every second movie frame (default)
R36S_MENU_VIDEO_STRIDE=3 or 4: lower video refresh rate
R36S_MENU_VIDEO_STRIDE=0: freeze on the first video frame, continue audio;
  diagnostic to separate JPEG/upload overhead from 3D screen fill-rate.

The last decoded texture stays bound on skipped frames. Non-menu
attract/movie paths and the normal GX draw passes remain unchanged.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"game/src/main/thp/dll_3e.c"
s=p.read_text()
if '#include <stdlib.h>' not in s:
    anchor='#include "dolphin/thp/THPDecode.h"\n'
    assert s.count(anchor)==1, "THP standard include anchor mismatch"
    s=s.replace(anchor,anchor+'#include <stdlib.h>\n',1)

anchor="static OSTime sPcMovieFrameTicks;\n"
added=r"""static OSTime sPcMovieFrameTicks;

// Lower synchronous THP JPEG work without dropping one audio component.
// This is menu-only; 0 freezes the image while keeping the THP audio stream.
static int r36sMenuVideoStride(void) {
    static int stride = -1;
    if (stride < 0) {
        const char* value = getenv("R36S_MENU_VIDEO_STRIDE");
        long requested = value != NULL ? strtol(value, NULL, 10) : 2;
        stride = (int)(requested < 0 ? 1 : requested > 4 ? 4 : requested);
        fprintf(stderr, "[r36s-menu-video] jpeg_stride=%d (0=freeze 1=original 2=half-rate)\n", stride);
    }
    return stride;
}
"""
assert s.count(anchor)==1, "THP time marker mismatch"
s=s.replace(anchor,added,1)

start="""        if (player->compInfo.mFrameComp[i] == 0) {
            s32 decodeError;
            fhTHPVideoSetCompressedSize(componentSize);"""
new_start=r"""        if (player->compInfo.mFrameComp[i] == 0) {
            const int menuStride = fhIsMenuMap() ? r36sMenuVideoStride() : 1;
            const BOOL skipMenuVideo = player->curTextureSet != NULL &&
                (menuStride == 0 || (menuStride > 1 && (sPcMovieFrame % (u32)menuStride) != 0));
            if (skipMenuVideo) {
                static unsigned videoSkipped = 0;
                if (++videoSkipped % 90 == 0) {
                    fprintf(stderr, "[r36s-menu-video] skipped_jpeg=%u audio_kept=1 stride=%d\n",
                            videoSkipped, menuStride);
                }
            } else {
                s32 decodeError;
                fhTHPVideoSetCompressedSize(componentSize);"""
assert s.count(start)==1, "THP decode anchor mismatch"
s=s.replace(start,new_start,1)
end="""            decoded = decodeError == 0;
        } else if (player->compInfo.mFrameComp[i] == 1) {"""
new_end="""                decoded = decodeError == 0;
            }
        } else if (player->compInfo.mFrameComp[i] == 1) {"""
assert s.count(end)==1, "THP decode end anchor mismatch"
s=s.replace(end,new_end,1)
p.write_text(s)
print("R36S menu JPEG stride installed: all THP audio frames retained, video optional half-rate")
