#!/usr/bin/env python3
"""R36S audio-vs-VI phase fix with real THP buffer-starvation diagnostics.

Foxhollow's PC shim calls fhAIPump() before VI post-retrace callbacks. That
ordering is wrong for single-threaded THP playback: PlayControl (post callback)
generates new compressed-THP audio only AFTER the SDL audio DMA queue has
already requested its next batch of samples. At 10 VI callbacks/s this creates
an entire slow-frame latency, and the original THP decoder has only 3 buffers.

Consume the newly decoded audio in the SAME retrace by moving fhAIPump after
the VI callbacks. Keep the R36S timing profiler attribution intact.
Also log missing THP audio samples and decoder buffer exhaustion, avoiding
further blind video/shadow changes.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
vi = root / "port/src/vi_shim.c"
s = vi.read_text()
old = """  inputMs += (SDL_GetTicksNS() - phase) / 1000000.0;
  phase = SDL_GetTicksNS();
  fhAIPump();
  audioMs += (SDL_GetTicksNS() - phase) / 1000000.0;

  sRetraceCount++;"""
new = """  inputMs += (SDL_GetTicksNS() - phase) / 1000000.0;

  // R36S THP: make the VI callback produce fresh movie audio before the
  // host SDL audio pump consumes the decoder ring. The real GameCube has
  // independent audio and VI interrupts; Foxhollow currently runs both
  // from the same main thread.
  sRetraceCount++;"""
assert s.count(old) == 1, f"R36S timing VI audio anchor count={s.count(old)}"
s = s.replace(old, new, 1)
old = """  previousEnd = SDL_GetTicksNS();
  ++samples;"""
new = """  phase = SDL_GetTicksNS();
  fhAIPump();
  audioMs += (SDL_GetTicksNS() - phase) / 1000000.0;
  previousEnd = SDL_GetTicksNS();
  ++samples;"""
assert s.count(old) == 1, f"R36S VI post-callback anchor count={s.count(old)}"
vi.write_text(s.replace(old,new,1))

audio = root / "game/src/main/thp/n_options.c"
s = audio.read_text()
if "#include <stdio.h>" not in s:
    s = s.replace('#include "string.h"\n', '#include "string.h"\n#include <stdio.h>\n',1)
probe = """static unsigned sR36SThpStarvations;

static void r36sNoteThpAudioStarve(const char* branch) {
    ++sR36SThpStarvations;
    if (sR36SThpStarvations <= 10 || sR36SThpStarvations % 60 == 0) {
        fprintf(stderr, "[r36s-thp-audio-starve] count=%u path=%s frame=%d\\n",
                sR36SThpStarvations, branch, gAttractMoviePlayer.curVideoFrameNumber);
    }
}

"""
anchor = "static void AttractMovieAudio_Mix(s16* destination, s16* source, u32 sampleCount) {\n"
assert s.count(anchor) == 1, "audio mixer function not found"
s = s.replace(anchor, probe+anchor, 1)
for old,new in [
("""if (gAttractMoviePlayer.curAudioBuffer == NULL) {
                            memcpy(dst, src, cnt << 2);""",
 """if (gAttractMoviePlayer.curAudioBuffer == NULL) {
                            r36sNoteThpAudioStarve("with-game-audio");
                            memcpy(dst, src, cnt << 2);"""),
("""if (gAttractMoviePlayer.curAudioBuffer == NULL) {
                        memset(dst, 0, cnt << 2);""",
 """if (gAttractMoviePlayer.curAudioBuffer == NULL) {
                        r36sNoteThpAudioStarve("thp-only");
                        memset(dst, 0, cnt << 2);""")]:
    assert s.count(old) == 1, f"THP audio starvation anchor count={s.count(old)}"
    s=s.replace(old,new,1)
audio.write_text(s)

dec = root / "game/src/main/thp/dll_3b.c"
s = dec.read_text()
if "#include <stdio.h>" not in s:
    s = '#include <stdio.h>\n' + s
old = """    if (OSReceiveMessage(&gAttractMovieFreeAudioQueueAndStack.queue, (OSMessage*)&audioBuffer, OS_MESSAGE_NOBLOCK) ==
        0) {
        return;
    }"""
new = """    if (OSReceiveMessage(&gAttractMovieFreeAudioQueueAndStack.queue, (OSMessage*)&audioBuffer, OS_MESSAGE_NOBLOCK) ==
        0) {
        static unsigned r36sDroppedThpAudio;
        if (++r36sDroppedThpAudio <= 10 || r36sDroppedThpAudio % 60 == 0) {
            fprintf(stderr, "[r36s-thp-audio-drop] no-free-buffer count=%u frame=%d\\n",
                    r36sDroppedThpAudio, frameNumber);
        }
        return;
    }"""
assert s.count(old) == 1, f"THP decode free-buffer anchor count={s.count(old)}"
dec.write_text(s.replace(old,new,1))
print("R36S THP audio: reordered VI producer before SDL consumer; starvation and decoder-drop diagnostics active")
