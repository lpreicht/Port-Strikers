#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'port/src/vi_shim.c'
s=p.read_text().replace('#include <stdlib.h>', '#include <stdlib.h>\n#include <stdio.h>')
s=s.replace('void VIWaitForRetrace(void) {', '''void VIWaitForRetrace(void) {
  static Uint64 previousEnd, reportStart;
  static double gameMs, gxMs, renderMs, pacingMs, inputMs, audioMs;
  static unsigned samples;
  const Uint64 entry = SDL_GetTicksNS();
  if (!reportStart) reportStart = entry;
  if (previousEnd) gameMs += (entry - previousEnd) / 1000000.0;
  Uint64 phase = entry;''',1)
s=s.replace('    aurora_end_frame();', '''    gxMs += (SDL_GetTicksNS() - phase) / 1000000.0;
    phase = SDL_GetTicksNS();
    aurora_end_frame();
    renderMs += (SDL_GetTicksNS() - phase) / 1000000.0;''',1)
s=s.replace('  fhModsUpdate();', '  phase = SDL_GetTicksNS();\n  fhModsUpdate();',1)
s=s.replace('  wait_for_retrace_deadline();\n  pump_events();', '''  wait_for_retrace_deadline();
  pacingMs += (SDL_GetTicksNS() - phase) / 1000000.0;
  phase = SDL_GetTicksNS();
  pump_events();''',1)
s=s.replace('  fhAIPump();', '''  inputMs += (SDL_GetTicksNS() - phase) / 1000000.0;
  phase = SDL_GetTicksNS();
  fhAIPump();
  audioMs += (SDL_GetTicksNS() - phase) / 1000000.0;''',1)
s=s.replace('    sPostRetraceCallback(sRetraceCount);\n  }\n}', '''    sPostRetraceCallback(sRetraceCount);
  }
  previousEnd = SDL_GetTicksNS();
  ++samples;
  if (previousEnd - reportStart >= 3000000000ull) {
    fprintf(stderr, "[R36S V025 timing] retraces/s=%.2f n=%u game=%.2f gx=%.2f render=%.2f pacing=%.2f input_begin=%.2f audio=%.2f ms/retrace\\n",
            samples * 1e9 / (previousEnd - reportStart), samples,
            gameMs/samples, gxMs/samples, renderMs/samples, pacingMs/samples, inputMs/samples, audioMs/samples);
    fflush(stderr);
    reportStart = previousEnd;
    gameMs=gxMs=renderMs=pacingMs=inputMs=audioMs=0;
    samples=0;
  }
}''',1)
p.write_text(s)
p=root/'extern/aurora/lib/aurora.cpp'
s=p.read_text().replace('    if (directPresent) {\n', '    if (directPresent) {\n      const auto submitStart = SDL_GetTicksNS();\n',1)
s=s.replace('      struct Present {', '      const auto submitEnd = SDL_GetTicksNS();\n      struct Present {',1)
s=s.replace('      if (!submitted || !present.ok) {', '''      const auto presentEnd = SDL_GetTicksNS();
      static uint64_t profileStart = submitStart, frameCount = 0;
      static double submitMs = 0, presentMs = 0;
      submitMs += (submitEnd - submitStart) / 1e6;
      presentMs += (presentEnd - submitEnd) / 1e6;
      ++frameCount;
      if (presentEnd - profileStart >= 3000000000ull) {
        Log.info("R36S V025 GPU path: submit+encode={:.2f} present+flush={:.2f} ms/frame n={}",
                 submitMs/frameCount, presentMs/frameCount, frameCount);
        profileStart = presentEnd;
        frameCount = 0;
        submitMs = presentMs = 0;
      }
      if (!submitted || !present.ok) {''',1)
p.write_text(s)
print('R36S V025 frame phase measurements applied')
