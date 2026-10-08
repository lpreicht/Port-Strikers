#!/usr/bin/env python3
"""Instrument synchronous menu THP JPEG decode cost without changing playback."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "game/src/main/thp/dll_3e.c"
s = p.read_text()
old = """                decodeError = THPVideoDecode(componentData, textureSet->yTexture, textureSet->uTexture,
                                         textureSet->vTexture, player->thpWorkArea);"""
# whitespace robust matching: inject before the existing call and after its semicolon
needle="""decodeError = THPVideoDecode(componentData, textureSet->yTexture, textureSet->uTexture,
                                         textureSet->vTexture, player->thpWorkArea);"""
assert s.count(needle) == 1, f"Expected exactly one PC THP decode call, found {s.count(needle)}"
repl="""const OSTime r36sDecodeStart = OSGetTime();
                """ + needle + r"""
                // PC title THP decode happens synchronously in the VI retrace
                // callback, not in the original game's decode worker threads.
                if (fhIsMenuMap()) {
                    static OSTime totalTicks = 0;
                    static OSTime peakTicks = 0;
                    static unsigned samples = 0;
                    const OSTime elapsed = OSGetTime() - r36sDecodeStart;
                    totalTicks += elapsed;
                    if (elapsed > peakTicks) {
                        peakTicks = elapsed;
                    }
                    if (++samples >= 60) {
                        const double tickMs = 1000.0 / (double)OS_TIMER_CLOCK;
                        fprintf(stderr, "[r36s-menu-jpeg-cost] decoded=%u mean_ms=%.2f peak_ms=%.2f\n",
                                samples, ((double)totalTicks / samples) * tickMs,
                                (double)peakTicks * tickMs);
                        totalTicks = 0;
                        peakTicks = 0;
                        samples = 0;
                    }
                }"""
s = s.replace(needle, repl, 1)
p.write_text(s)
print("R36S menu-video JPEG timing measurements enabled (once per 60 decoded frames)")
