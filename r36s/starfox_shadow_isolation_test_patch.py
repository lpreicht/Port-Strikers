#!/usr/bin/env python3
"""R36S: visually isolate projected object shadows from terrain/depth flicker.

For one hardware diagnostic only, retain *all* terrain geometry and ground
materials while alternating the newshadows.c projected object caster queue:
the first 20 seconds after the first queued caster run normally, the next
20 seconds accept no casters, then repeat. Wall-clock scheduling ensures the
comparison lasts the same time even at 5 FPS. There is no change to the GX,
EFB, Dawn, Direct-GLES, THP, audio, or material paths.

No gameplay state is persisted. Removing this patch restores normal shadows.
"""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
p = root / "game/src/main/newshadows.c"
s = p.read_text()

include_anchor = '#include "main/newshadows_internal.h"\n'
assert s.count(include_anchor) == 1, "newshadows includes layout has changed"
s = s.replace(include_anchor,
              include_anchor + '#include <time.h>\n#include <stdio.h>\n#include <stdlib.h>\n', 1)
anchor = """void queueObjectShadow(GameObject* obj)
{
    f32 dx, dy, dz, dist2;
    if (gNewShadowCasterCount < NEW_SHADOW_MAX_QUEUED_CASTERS)
"""
replacement = """/* R36S hardware diagnostic ONLY: compare projected object shadows to the
 * otherwise unchanged terrain/material/depth rendering every 20 seconds.
 * 0 (default) = normal shadows. 1 = alternate on/off from first caster.
 */
static int r36sProjectedShadowIsolationEnabled(void) {
    static int initialized = 0;
    static int enabled = 0;
    if (!initialized) {
        const char* env = getenv("R36S_SHADOW_ISOLATION");
        enabled = (env != NULL && env[0] == '1');
        initialized = 1;
    }
    return enabled;
}

static int r36sAllowProjectedShadowCaster(void) {
    static time_t firstSecond = (time_t)-1;
    static int lastPhase = -1;
    time_t now = time(NULL);
    int phase;
    if (firstSecond == (time_t)-1) {
        firstSecond = now;
    }
    phase = (((now - firstSecond) / 20) % 2) == 0 ? 1 : 0;
    if (phase != lastPhase) {
        fprintf(stderr,
                "[r36s-shadow-isolation] projected_casters=%s phase=%d "
                "period_seconds=20 ground_geometry=unchanged\\\\n",
                phase ? "ON" : "OFF", phase);
        lastPhase = phase;
    }
    return phase;
}

void queueObjectShadow(GameObject* obj)
{
    f32 dx, dy, dz, dist2;
    if (r36sProjectedShadowIsolationEnabled() &&
        !r36sAllowProjectedShadowCaster()) {
        return;
    }
    if (gNewShadowCasterCount < NEW_SHADOW_MAX_QUEUED_CASTERS)
"""
assert s.count(anchor) == 1, "queueObjectShadow insertion anchor missing"
s = s.replace(anchor, replacement, 1)
p.write_text(s)
print("R36S shadow isolation: projected caster queue toggles ON/OFF every 20s, terrain unchanged")
