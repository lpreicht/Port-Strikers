#!/usr/bin/env python3
"""RC8: use Aurora's existing sampled deep profiler to localize GX hot paths.

Requires -DAURORA_DEEP_TIMERS=ON, R36S_DEEP_PROFILE=1 in the launcher
(mapped to AURORA_DEEP_PROFILE=1), interval=60 by default.
Adds scoped vertex/index diagnostics only, without changing geometry,
render state, shader, copy or presenter behavior.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1]).resolve()
p=root/"extern/aurora/lib/gx/command_processor.cpp"
s=p.read_text()

def once(before,after,label):
    global s
    count=s.count(before)
    if count!=1:
        raise SystemExit(f"RC8 {label}: expected 1 anchor, got {count}")
    s=s.replace(before,after,1)

once(
"""u16 prepare_idx_buffer(ByteBuffer& buf, GXPrimitive prim, u16 vtxStart, u16 vtxCount) noexcept {
  u16 numIndices = 0;""",
"""u16 prepare_idx_buffer(ByteBuffer& buf, GXPrimitive prim, u16 vtxStart, u16 vtxCount) noexcept {
  gfx::profile::Scope r36sRc8IndexProfile("index_generate");
  u16 numIndices = 0;""", "index generation scope")

once(
"""static gfx::Range push_decoded_verts(GXPrimitive prim, GXVtxFmt fmt, std::span<const u8> vertexData, u16& vtxCount,
                                     size_t alignment, u32 matrixWordZ = 0) noexcept {
  ZoneScoped;
  prepare_pipeline(prim, fmt);""",
"""static gfx::Range push_decoded_verts(GXPrimitive prim, GXVtxFmt fmt, std::span<const u8> vertexData, u16& vtxCount,
                                     size_t alignment, u32 matrixWordZ = 0) noexcept {
  ZoneScoped;
  gfx::profile::Scope r36sRc8VertProfile("vertex_upload_decode");
  prepare_pipeline(prim, fmt);""", "vertex decode/upload scope")
assert "gfx::profile::Scope drawProfile(\"draw_prepare\")" in s
assert "gfx::profile::Scope profile(\"texture_resolve_bind\")" in s
assert "gfx::profile::Scope profile(\"uniform_build\")" in s
assert "gfx::profile::Scope profile(\"pipeline_build\")" in s
p.write_text(s)
print("RC8 sampled Aurora GX deep profiler scopes installed without drawing changes")
