#!/usr/bin/env python3
"""Fix R36S 10-FPS menu THP audio starvation without changing gameplay graphics.

Keep GameCube-facing structs and the three original audio descriptors intact.
A PC-only sidecar pool enlarges the OSMessage rings and adds decode buffers.
Read-ahead has its own THP frame cursor and scratch buffer, independently of
the video cursor, preventing duplicate audio submission from frame catch-up.

The player still mixes and presents audio through its existing DMA callback.
The VI post-retrace callback only refills a 10-frame audio lead, before the
SDL DMA pump (reordered in starfox_thp_audio_pump_fix.py). No background
threads, concurrent DVD access or changes to gameplay audio are introduced.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
b = root / "game/src/main/thp/dll_3b.c"
s = b.read_text()
if '#include <stdlib.h>' not in s:
    s = s.replace('#include "main/audio_decode_thread.h"\n',
                  '#include "main/audio_decode_thread.h"\n#include <stdlib.h>\n#include <stdio.h>\n', 1)

marker = "s32 gAttractMovieAudioThreadActive;\n"
replacement = r"""s32 gAttractMovieAudioThreadActive;

/* R36S: sidecar buffers preserve the decompilation-facing 3-buffer ABI. */
#define R36S_THP_AUDIO_POOL 16
#define R36S_THP_ORIGINAL_POOL 3
static OSMessage sR36SThpFreeMessages[R36S_THP_AUDIO_POOL];
static OSMessage sR36SThpDecodedMessages[R36S_THP_AUDIO_POOL];
static AttractMovieAudioBuffer sR36SThpExtraAudio[R36S_THP_AUDIO_POOL - R36S_THP_ORIGINAL_POOL];
static void* sR36SThpExtraBacking;
static int sR36SThpExpanded;

int r36sThpAudioExpanded(void) {
    return sR36SThpExpanded;
}
"""
assert s.count(marker) == 1, "dll_3b audio pool declaration missing"
s = s.replace(marker, replacement, 1)

start = s.index("void AttractMovieAudio_InitQueuesPC(void) {")
end = s.index("\nvoid AttractMovieAudio_DecodeFramePC(", start)
old = s[start:end]
assert "ARRAY_COUNT(gAttractMoviePlayer.audioBuffer)" in old, "unexpected audio queue init"
new = r"""void AttractMovieAudio_InitQueuesPC(void) {
    s32 i;
    u32 maxSamples = gAttractMoviePlayer.header.mAudioMaxSamples;
    size_t bytesPerBuffer = 0;
    int poolSize = R36S_THP_ORIGINAL_POOL;

    free(sR36SThpExtraBacking);
    sR36SThpExtraBacking = NULL;
    sR36SThpExpanded = 0;

    if (maxSamples > 0 && maxSamples <= 16384u) {
        bytesPerBuffer = ((size_t)maxSamples * 4u + 31u) & ~(size_t)31u;
        sR36SThpExtraBacking =
            malloc(bytesPerBuffer * (R36S_THP_AUDIO_POOL - R36S_THP_ORIGINAL_POOL));
    }
    if (sR36SThpExtraBacking != NULL) {
        poolSize = R36S_THP_AUDIO_POOL;
        sR36SThpExpanded = 1;
        for (i = 0; i < R36S_THP_AUDIO_POOL - R36S_THP_ORIGINAL_POOL; i++) {
            AttractMovieAudioBuffer* buf = &sR36SThpExtraAudio[i];
            buf->buffer = (s16*)((u8*)sR36SThpExtraBacking + (size_t)i * bytesPerBuffer);
            buf->curPtr = buf->buffer;
            buf->validSample = 0;
            buf->frameNumber = 0;
        }
    }

    OSInitMessageQueue(&gAttractMovieFreeAudioQueueAndStack.queue,
                       sR36SThpFreeMessages, poolSize);
    OSInitMessageQueue(&gAttractMovieDecodedAudioQueue,
                       sR36SThpDecodedMessages, poolSize);
    for (i = 0; i < R36S_THP_ORIGINAL_POOL; i++) {
        PushFreeAudioBuffer(&gAttractMoviePlayer.audioBuffer[i]);
    }
    if (sR36SThpExpanded) {
        for (i = 0; i < R36S_THP_AUDIO_POOL - R36S_THP_ORIGINAL_POOL; i++) {
            PushFreeAudioBuffer(&sR36SThpExtraAudio[i]);
        }
    }
    fprintf(stderr, "[r36s-thp-audio-pool] buffers=%d max_samples=%u bytes_each=%zu\n",
            poolSize, maxSamples, bytesPerBuffer);
}
"""
s=s[:start]+new+s[end:]
b.write_text(s)

p = root / "game/src/main/thp/dll_3e.c"
s = p.read_text()
if "#include <stdlib.h>" not in s:
    s = s.replace('#include "dolphin/thp/THPDecode.h"\n',
                  '#include "dolphin/thp/THPDecode.h"\n#include <stdlib.h>\n#include <stdio.h>\n', 1)

marker = "static OSTime sPcMovieFrameTicks;\n"
insert = r"""static OSTime sPcMovieFrameTicks;

/* Separate sequential audio read cursor: video catch-up never duplicates PCM. */
extern int r36sThpAudioExpanded(void);
static u8* sR36SThpAudioScratch;
static u32 sR36SThpAudioScratchBytes;
static u32 sR36SThpAudioReadOffset;
static u32 sR36SThpAudioReadSize;
static u32 sR36SThpAudioReadFrame;
static BOOL sR36SThpAudioAhead;
static unsigned sR36SThpAudioReads;

static void r36sThpAudioPrefetch(void) {
    AttractMoviePlayer* player = &gAttractMoviePlayer;
    unsigned num = 0;

    if (!sR36SThpAudioAhead || player->audioExists == 0 ||
        player->header.mNumFrames == 0 || player->dvdError != 0) {
        return;
    }

    // ~10 frames = 1/3 second at a 30-fps THP rate. Keep enough audio
    // ready for the 200-ms host queue even when VI runs at just 10 fps.
    while (gAttractMovieDecodedAudioQueue.usedCount < 10 && num++ < 12) {
        u32* sizes;
        u8* component;
        u32 i;
        if (sR36SThpAudioReadSize < 8u ||
            sR36SThpAudioReadSize > sR36SThpAudioScratchBytes) {
            fprintf(stderr, "[r36s-thp-audio-ahead] invalid compressed frame size=%u\n",
                    sR36SThpAudioReadSize);
            player->dvdError = -1;
            break;
        }
        if (DVDRead(&player->fileInfo, sR36SThpAudioScratch,
                    sR36SThpAudioReadSize, sR36SThpAudioReadOffset) !=
            (s32)sR36SThpAudioReadSize) {
            fprintf(stderr, "[r36s-thp-audio-ahead] DVD frame read error frame=%u\n",
                    sR36SThpAudioReadFrame);
            player->dvdError = -1;
            break;
        }
        sizes = (u32*)(sR36SThpAudioScratch + 8);
        component = sR36SThpAudioScratch + 8 + player->compInfo.mNumComponents * sizeof(u32);
        for (i = 0; i < player->compInfo.mNumComponents; i++) {
            u32 size = fhSwap32(sizes[i]);
            if ((uintptr_t)component < (uintptr_t)sR36SThpAudioScratch ||
                (uintptr_t)component + size >
                    (uintptr_t)sR36SThpAudioScratch + sR36SThpAudioReadSize) {
                fprintf(stderr, "[r36s-thp-audio-ahead] invalid THP component size=%u\n", size);
                player->dvdError = -1;
                return;
            }
            if (player->compInfo.mFrameComp[i] == 1) {
                AttractMovieAudio_DecodeFramePC(component, sR36SThpAudioReadFrame);
            }
            component += size;
        }

        sR36SThpAudioReadOffset += sR36SThpAudioReadSize;
        sR36SThpAudioReadSize = fhSwap32(*(u32*)sR36SThpAudioScratch);
        if (++sR36SThpAudioReadFrame >= player->header.mNumFrames) {
            sR36SThpAudioReadFrame = 0;
            sR36SThpAudioReadOffset = player->header.mMovieDataOffsets;
            sR36SThpAudioReadSize = player->header.mFirstFrameSize;
        }
        if (++sR36SThpAudioReads <= 2 || sR36SThpAudioReads % 180 == 0) {
            fprintf(stderr, "[r36s-thp-audio-ahead] read=%u queued=%d next_frame=%u\n",
                    sR36SThpAudioReads, gAttractMovieDecodedAudioQueue.usedCount,
                    sR36SThpAudioReadFrame);
        }
    }
}

static void r36sThpAudioBegin(AttractMoviePlayer* player) {
    sR36SThpAudioAhead = FALSE;
    if (sR36SThpAudioScratch != NULL) {
        free(sR36SThpAudioScratch);
        sR36SThpAudioScratch = NULL;
    }
    sR36SThpAudioScratchBytes = 0;
    sR36SThpAudioReads = 0;
    if (!player->audioExists || !r36sThpAudioExpanded() ||
        player->header.mBufferSize < 16u || player->header.mBufferSize > 4u * 1024u * 1024u) {
        fprintf(stderr, "[r36s-thp-audio-ahead] disabled (pool or THP buffer unavailable)\n");
        return;
    }
    sR36SThpAudioScratch = (u8*)malloc(player->header.mBufferSize);
    if (sR36SThpAudioScratch == NULL) {
        fprintf(stderr, "[r36s-thp-audio-ahead] disabled (scratch allocation failed)\n");
        return;
    }
    sR36SThpAudioScratchBytes = player->header.mBufferSize;
    sR36SThpAudioReadOffset = player->initOffset;
    sR36SThpAudioReadSize = player->initReadSize;
    sR36SThpAudioReadFrame = player->initReadFrame;
    sR36SThpAudioAhead = TRUE;
    fprintf(stderr, "[r36s-thp-audio-ahead] enabled max_frame_bytes=%u queue_target=10\n",
            sR36SThpAudioScratchBytes);
}
"""
assert s.count(marker) == 1, "THP movie clock insertion anchor missing"
s=s.replace(marker,insert,1)

# Both the normal movie frame and the catch-up frame reader contain an audio
# component. In ahead-mode, neither is allowed to submit duplicate PCM.
needle="AttractMovieAudio_DecodeFramePC(componentData, sPcMovieFrame);"
assert s.count(needle) == 2, f"expected two THP audio branches, saw {s.count(needle)}"
s=s.replace(needle,"if (!sR36SThpAudioAhead) {\n                AttractMovieAudio_DecodeFramePC(componentData, sPcMovieFrame);\n            }")

# Refill the audio producer independently of the menu video frame due-time.
needle = """    if (now >= sPcMovieNextFrameTime) {
        DecodeNextMovieFramePC();
        sPcMovieNextFrameTime += sPcMovieFrameTicks;
        if (now - sPcMovieNextFrameTime >= sPcMovieFrameTicks) {
            sPcMovieNextFrameTime = now + sPcMovieFrameTicks;
        }
    }
    return;"""
repl = needle.replace("    return;", "    r36sThpAudioPrefetch();\n    return;")
assert s.count(needle)==1, "PlayControl movie frame timing anchor missing"
s=s.replace(needle,repl,1)

needle = """        if (player->audioExists != 0) {
            AttractMovieAudio_InitQueuesPC();
        }
        if (!DecodeNextMovieFramePC()) {
            return FALSE;
        }"""
repl = """        if (player->audioExists != 0) {
            AttractMovieAudio_InitQueuesPC();
        }
        r36sThpAudioBegin(player);
        if (!DecodeNextMovieFramePC()) {
            return FALSE;
        }
        r36sThpAudioPrefetch();"""
assert s.count(needle) == 1, "THP prepare audio queue init anchor missing"
s=s.replace(needle,repl,1)
p.write_text(s)
print("R36S THP audio: 16-buffer ABI-safe sidecar and 10-frame independent read-ahead enabled")
