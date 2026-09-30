# AGENTS.md — capcut-clipper

Guide for coding agents (Claude Code, Codex, Cursor, …) working in this repo.

## What this is
A toolkit that turns a long talking-head video into 9:16 short-form clips as **real CapCut desktop
projects** (Windows). CapCut has no public API, but it stores each project as plaintext
`draft_content.json`, which this repo reads and writes.

| Part | Path | Role |
|---|---|---|
| Skill | `skills/video-clipper/SKILL.md` | The editing workflow and style rules. **Read it before clipping.** |
| Subagent | `agents/clipper.md` | Claude Code subagent that runs the skill end to end |
| MCP server | `mcp/capcut-mcp/` (+ `.mcp.json`) | 35+ tools to read/edit/preview CapCut projects (vendored, MIT, see `PATCHES.md`) |
| Pipeline CLI | `clipper/` | `python -m clipper doctor / transcribe / broll / build / audit / install / sfx` |
| Assets | `assets/sfx/` | Synthesised royalty-free SFX (whoosh, pop, boom, riser, ding, click) |
| Work | `projects/<slug>/` | One folder per source video: `clips.json`, transcript, photos, `out/`. Git-ignored. |

## Setup
```powershell
.\setup.ps1              # .venv, dependencies, ffmpeg into bin\, then runs doctor
.\setup.ps1 -RegisterMcp # also: claude mcp add capcut -s user
```
Always run Python through `.venv\Scripts\python.exe`.

## Commands
```powershell
.venv\Scripts\python.exe -m clipper doctor
.venv\Scripts\python.exe -m clipper transcribe projects\<slug>\clips.json
.venv\Scripts\python.exe -m clipper broll      projects\<slug>\clips.json
.venv\Scripts\python.exe -m clipper build      projects\<slug>\clips.json [1 2 ...]
.venv\Scripts\python.exe -m clipper audit      projects\<slug>\clips.json
.venv\Scripts\python.exe -m clipper install    projects\<slug>\clips.json [1 2 ...]
```

## Styles
- `hormozi` (default): bold word-by-word captions, punch-ins, fast SFX.
- `cinematic` (spec or per clip): graded footage baked with ffmpeg at 24 fps, letterbox "moments" with serif
  titles, riser → impact, reverb tail + fade out. See SKILL.md §6b. Keep grades subtle.

## Hard rules
- **Never write to a CapCut project while CapCut has it open.** CapCut flushes its in-memory copy on close
  and silently overwrites your edits. `install` skips `.locked` folders, and the MCP `capcut_save` refuses
  while CapCut runs.
- **Back up before overwriting** an installed project (`install` does it into `out/_backup/`).
- **Ask the user before downloading anything** (photos, music, fonts, SFX).
- **Credit the source creator** (`credit` in the spec) unless the user owns the channel.
- Transitions, effects, filters and text animations can only be **reapplied** from the local catalog
  (things applied by hand in CapCut at least once). Don't invent `resource_id`s.
- Base any change to CapCut's JSON schema on a real example from a local draft. A plausible but wrong
  field can silently corrupt a project.

## Verifying work
- `clipper audit` must report `issues: OK` (freezes, -14 LUFS ±2, true peak, ≤5 s visual gap,
  20–65 s duration, credit).
- Look at frames (hook, each jump cut, each B-roll, the ending). The preview is an ffmpeg proxy: it does not
  render CapCut animations, transitions, filters or text outline, so a final check in CapCut is still needed.
- Agents can't hear. Say so when SFX or music was added, and ask the user to listen.

## Known gotchas
- An `env` block in an MCP config on Windows replaces the whole environment and the server dies with
  "Connection closed". This repo resolves ffmpeg itself (`paths.ffmpeg_exe`) so no env block is needed.
- A 24 fps source through `zoompan` needs `fps=` first, or the preview plays at 0.8x and freezes (fixed).
- Don't chase loudness with clip volume: +6 dB on quiet speech clipped to +5.8 dBTP. `build` renders a
  loudnorm'd voice track (-14 LUFS, TP ≤ -1.5) and mutes the video's own audio; sync is sample-exact.
- Caption-heavy previews exceed Windows' 32k command line, so the filter graph goes through
  `-filter_complex_script` (fixed).
