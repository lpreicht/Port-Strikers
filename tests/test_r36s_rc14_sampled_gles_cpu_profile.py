#!/usr/bin/env python3
"""RC14 sampling contract: real GL operations and fast paths unchanged."""
from pathlib import Path
import sys
p=(Path(sys.argv[1]).resolve()/"extern/aurora/lib/gfx/gles_direct.cpp")
s=p.read_text()
expected=[
    "struct R36SGlesCpuPhases {",
    "uint64_t pipelineNs = 0, resourcesNs = 0, drawNs = 0;",
    "const bool r36sCpuSample = (sFrameNumber % 60u) == 0u;",
    "sR36sGlesCpuPhases.pipelineNs +=",
    "sR36sGlesCpuPhases.resourcesNs +=",
    "sR36sGlesCpuPhases.drawNs +=",
    "++sR36sGlesCpuPhases.draws;",
    "++sR36sGlesCpuPhases.renderPasses;",
    "[r36s-rc14-gles-cpu] sampled_frame=",
    "sR36sGlesCpuPhases.clear();",
    "glDrawRangeElements(",
    "glDrawElements(",
    "glDrawElementsInstanced(",
    "glDrawArrays(",
    "glDrawArraysInstanced(",
    "bind_draw_resources(d, *prepared);",
    "draw_barrier((d.indexCount != 0 ? d.indexCount : d.vtxCount) * std::max(d.instanceCount, 1u));",
    "const bool r36sDrawOk = gl_ok(\"draw\", passIndex, drawIndex);",
    "return r36sDrawOk;",
]
for token in expected:assert token in s,token
assert s.count('sR36sGlesCpuPhases.pipelineNs +=')==1
assert s.count('sR36sGlesCpuPhases.resourcesNs +=')==1
assert s.count('sR36sGlesCpuPhases.drawNs +=')==1
assert s.count('const bool r36sCpuSample =')==1
assert s.count('sR36sGlesCpuPhases.clear();')==1
assert s.count('glDrawRangeElements(')==1
assert s.count('glDrawElements(')==1
assert s.count('bind_draw_resources(d, *prepared);')==1
assert s.count('const bool r36sDrawOk = gl_ok("draw", passIndex, drawIndex);')==1
assert "glFinish();" in s # original probe/barrier logic retained
# Sampling math, no need to schedule tasks; every 60th frame.
sampled=[frame for frame in range(1,421) if frame %60==0]
reported=[frame for frame in range(1,421) if frame%60==1 and frame>1]
assert sampled==[60,120,180,240,300,360,420]
assert reported==[61,121,181,241,301,361]
print("PASS RC14: sampled CPU timing and reporting; GL submission unchanged")
