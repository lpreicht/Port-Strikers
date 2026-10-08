#!/usr/bin/env python3
"""Restore Aurora's safe nonblocking pass preflight, keep draw-local wait.

encode_pass_resources scans every unique pipeline in each pass, sometimes
hundreds per frame. Polling 5000x1ms for each pending pipeline here stalls
the menu/cutscenes and water scenes. Aurora's original preflight returns
false on an unready pipeline, recording the entire pass through Dawn,
without partially intercepting it. The actual Direct-GLES draw still waits
for an asynchronously compiling pipeline in prepare_pipeline().
"""
from pathlib import Path
import sys

p=Path(sys.argv[1]).resolve()/"extern/aurora/lib/gfx/gles_direct.cpp"
s=p.read_text()
old="if (!wait_pipeline(d.pipeline, p, 5000) || !gx::find_pipeline_config(d.pipeline, c) || !pipeline_eligible(c)) {"
new="if (!get_pipeline(d.pipeline, p) || !gx::find_pipeline_config(d.pipeline, c) || !pipeline_eligible(c)) {"
if s.count(old)!=1:
    raise SystemExit(f"nonblocking pipeline preflight: expected one anchor, found {s.count(old)}")
s=s.replace(old,new,1)
if "if (!wait_pipeline(ref, p.owner, 5000))" not in s:
    raise SystemExit("Direct-GLES draw-local pipeline safety was lost")
p.write_text(s)
print("R36S pass preflight nonblocking; draw-local pipeline wait unchanged")
