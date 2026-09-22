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
# already owned by Aurora and request the normal main-loop shutdown so Aurora,
# SDL/KMSDRM and PortMaster all get their cleanup paths.
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
    extern void PortRequestQuit(void);
    for (u32 i = 0; i < PADCount(); ++i)
    {
        SDL_Gamepad* pad = PADGetSDLGamepadForIndex(i);
        if (pad != nullptr &&
            SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_BACK) &&
            SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_START))
        {
            OSReport("[port] Start+Select pressed: requesting clean exit\\n");
            PortRequestQuit();
            return;
        }
    }
#endif

    update_fake_pad(frame, kHoldFrames);

    record_pad(frame);
"""
replace_once(inp, old, new, "R36S Start+Select in-process exit")


# ---------------------------------------------------------------------------
# 3) Lightweight replay-end transition.
#
# On the R36S the two goal-replay camera angles themselves are smooth. The
# hitch starts only at the end of the second angle, when Presentation begins
# preparing the random ScreenTransition while the replay is still visible.
# That stalls both rendering and the main-thread MusyX feeder. Do not preselect
# the expensive transition on this handheld and turn only the completed replay
# exit into an immediate cut. Normal gameplay/NIS wipes remain unchanged.
# ---------------------------------------------------------------------------
presentation = root / "src/Game/Render/Presentation.cpp"
replace_once(
    presentation,
    """void Presentation::WaitForAutoReplayCompletion(const char* wipe)
{
    if (nlSingleton<ScreenTransitionManager>::Instance()->m_SelectedTransition == NULL)
    {
        nlSingleton<ScreenTransitionManager>::Instance()->SelectRandomTransition(wipe);
    }
    if (!ReplayChoreo::Instance().Done())
    {
        StopWithUndo();
    }
}
""",
    """void Presentation::WaitForAutoReplayCompletion(const char* wipe)
{
#ifdef MELEE_MIYOO_FLIP
    // Preparing the random transition while the final replay angle is still
    // running causes a long RK3326/Mali-G31 frame stall. Defer all transition
    // work and use the cheap cut below once the choreography is actually done.
    (void)wipe;
#else
    if (nlSingleton<ScreenTransitionManager>::Instance()->m_SelectedTransition == NULL)
    {
        nlSingleton<ScreenTransitionManager>::Instance()->SelectRandomTransition(wipe);
    }
#endif
    if (!ReplayChoreo::Instance().Done())
    {
        StopWithUndo();
    }
}
""",
    "R36S replay completion transition deferral",
)

replace_once(
    presentation,
    """void Presentation::Wipe(const char* wipe)
{
    if (mByPassing)
    {
        return;
    }
    if (mUseInterruptWipe != NULL)
    {
        wipe = mUseInterruptWipe;
    }
""",
    """void Presentation::Wipe(const char* wipe)
{
    if (mByPassing)
    {
        return;
    }
    if (mUseInterruptWipe != NULL)
    {
        wipe = mUseInterruptWipe;
    }
#ifdef MELEE_MIYOO_FLIP
    // Only the completed auto-replay exit gets the lightweight transition.
    // Apply this after mUseInterruptWipe so a scripted transition cannot
    // override the cheap R36S replay-exit cut.
    if (nlTaskManager::m_pInstance->m_CurrState == 0x10 &&
        ReplayChoreo::Instance().Done())
    {
        wipe = "cut";
    }
#endif
""",
    "R36S replay-end lightweight cut",
)

print("Applied R36S rigid-cutscene + clean exit + replay-end fixes")
