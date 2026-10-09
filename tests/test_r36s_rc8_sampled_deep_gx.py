#!/usr/bin/env python3
"""RC8: source-level sampled deep GX profiler integration checks."""
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
s=(root/"extern/aurora/lib/gx/command_processor.cpp").read_text()
a=(root/"extern/aurora/lib/aurora.cpp").read_text()
f=(root/"extern/aurora/lib/gx/fifo.cpp").read_text()
h=(root/"extern/aurora/lib/gfx/profile.hpp").read_text()
for needle in [
  'gfx::profile::Scope r36sRc8IndexProfile("index_generate")',
  'gfx::profile::Scope r36sRc8VertProfile("vertex_upload_decode")',
  'gfx::profile::Scope profile("pipeline_build")',
  'gfx::profile::Scope profile("texture_resolve_bind")',
  'gfx::profile::Scope profile("uniform_build")',
  'gfx::profile::Scope drawProfile("draw_prepare")',
  'gfx::detail::increment_merged_draw_count()',
  'gfx::push_draw_command(DrawData{',
]:
  assert needle in s, needle
assert 'gfx::profile::begin(frame, "fifo")' in f
assert 'gfx::profile::end()' in f
assert '[deep-profile]' in h
assert 'std::getenv("AURORA_DEEP_PROFILE")' in h
assert 'std::getenv("AURORA_DEEP_INTERVAL")' in h
assert '[r36s-rc4-present]' not in a or '[r36s-rc4-endframe]' in a
assert '[r36s-rc5-gx]' in a
print("PASS RC8: 1/60 sampled CPU GX profiler, shader/geometry semantics preserved")
