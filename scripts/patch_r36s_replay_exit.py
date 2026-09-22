#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_r36s_replay_exit.py <strikers-dir>")

root = Path(sys.argv[1])

def replace_once(path, old, new, label):
    p = Path(path)
    s = p.read_text()
    if new in s:
        return
    if old not in s:
        raise SystemExit(f"{label}: pattern not found in {p}")
    p.write_text(s.replace(old, new, 1))

# ---------------------------------------------------------------------------
# 1) R36S cutscene/replay compatibility.
#
# Strikers deliberately switches from the rigid character mesh to the separate
# blended mesh in auto-replays (state 0x10), presentations/NIS (0x100), debug
# replays (0x20000), and some captain-shot sequences. Normal R36S gameplay uses
# the rigid mesh and is correct; the visual corruption is isolated to those
# blended-mesh scenes. Keep the same pose/animation and render the known-good
# rigid character mesh on this low-end Mali path.
# ---------------------------------------------------------------------------
begin = root / "src/Game/BeginFrameTask.cpp"
old = """    if (g_pGame != NULL)
    {
        if (g_pGame->mbCaptainShotToScoreOn)
        {
            cCharacter::m_ModelType = CharModel_Blend;
        }
    }

    if (!init)
"""
new = """    if (g_pGame != NULL)
    {
        if (g_pGame->mbCaptainShotToScoreOn)
        {
            cCharacter::m_ModelType = CharModel_Blend;
        }
    }

#ifdef MELEE_MIYOO_FLIP
    // R36S/Mali-G31: the separate blended character model is the only mesh
    // path that corrupts in close-up NIS/goal replays. The rigid model uses
    // the same pose matrices and animations and is already proven stable in
    // normal gameplay, so use it as the handheld compatibility skin.
    cCharacter::m_ModelType = CharModel_Rigid;
#endif

    if (!init)
"""
replace_once(begin, old, new, "R36S rigid character compatibility")

# ---------------------------------------------------------------------------
# 2) Start+Select exit inside Strikers itself.
#
# gptokeyb2 sees both buttons on ArkOS, but its external pkill path does not
# terminate this native process reliably. Read the physical SDL gamepad state
# already owned by Aurora and exit from the game process itself.
# ---------------------------------------------------------------------------
inp = root / "src/platform/input.cpp"
old = """    // A controller can arrive at any time, and its mapping is Aurora's until the file's is put over
    // it.
    poll_controllers(probe_pad());
    update_fake_pad(frame, kHoldFrames);

    record_pad(frame);
"""
new = """    // A controller can arrive at any time, and its mapping is Aurora's until the file's is put over
    // it.
    poll_controllers(probe_pad());

#ifdef MELEE_MIYOO_FLIP
    // PortMaster convention on R36S: Select/Back + Start exits the port.
    // Do this in-process instead of relying on gptokeyb2/pkill: the latter
    // receives the combo on ArkOS but does not reliably kill this binary.
    for (u32 i = 0; i < PADCount(); ++i)
    {
        SDL_Gamepad* pad = PADGetSDLGamepadForIndex(i);
        if (pad != nullptr &&
            SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_BACK) &&
            SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_START))
        {
            OSReport("[port] Start+Select pressed: exiting\\n");
            std::exit(0);
        }
    }
#endif

    update_fake_pad(frame, kHoldFrames);

    record_pad(frame);
"""
replace_once(inp, old, new, "R36S Start+Select in-process exit")

print("Applied R36S rigid-cutscene + in-process Start+Select fixes")
