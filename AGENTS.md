# Blockcut: working instructions for coding agents (Codex, Claude Code)

Read this before changing anything. Current progress and next steps live in [HANDOFF.md](HANDOFF.md).

## What this is

**Blockcut** is our ManilaHack 2026 entry (Content bucket; demo on the evening of **Nov 12, 6-10 PM Makati**).
You type a topic; the app researches it, writes a segmented short video (script, voiceover, captions, images, music,
transitions, effects), and lets you edit it like a video editor:
- **Left panel:** effects/transitions/assets library and a prompt box. The prompt edits the whole video, or only the selected segment.
- **Centre:** live preview (Remotion Player) plus a pannable canvas of segment cards on one straight timeline (drag to reorder).
- **Right panel:** an inspector for the overview (style, colours, fonts, music, voice) or the selected segment (script, timing, image, voiceover, captions, 3D prop).

Pitch line: *"Melius makes the shots. We make the edit."* Finished, human-paced videos at ₱0 per render.

## Architecture (one data object flows through everything)

```
prompt ──► server.py (Python stdlib HTTP, :8787)
             ├─ AI backend: Claude API (ANTHROPIC_API_KEY in .env) ─or─ headless Claude Code CLI (user's sign-in) ─or─ demo samples
             ├─ ScrapeGraphAI web search ─► topic images ─► web/public/assets/
             ├─ Edge TTS voiceover ─► faster-whisper word timings ─► web/public/media/
             └─ music.py original loops ─► web/public/music/
          ◄── Plan JSON ──►  web/ (Vite + React + Remotion, :5173)
                              Video.tsx renders the Plan; App/Canvas/Inspector edit it
```

**The Plan is the contract.** TypeScript types live in `web/src/video/Video.tsx` (`Plan`, `SceneData`, `Track`, `Word`).
`server.py` mirrors them as pydantic models (`Scene`, `Direction`, `Script`). **Change both sides together.**
The palette ids in `server.py` (`PaletteId`) must match `PALETTES` in `web/src/video/theme.ts`.

### File map

| File | What it owns |
|---|---|
| `server.py` | All API routes, prompts (`EDITING_GUIDE`, `DIRECTION_GUIDE`, `PROP_GUIDE`), AI backends, image search, voice and captions, asset bucket, static `/assets` `/media` `/music` |
| `music.py` | Synthesises 8 original royalty-free loops into `web/public/music/`; `LIBRARY` is what the AI picks from |
| `samples/*.json` | Handmade demo videos, loaded by keyword when no AI backend is available (`*.prop.json` = 3D props) |
| `web/src/App.tsx` | App state (plan, undo history, busy states), API calls, left panel, header |
| `web/src/Canvas.tsx` | Pannable/zoomable segment timeline, drag-to-reorder, tag ovals, timing meter |
| `web/src/Inspector.tsx` | Right panel: Overview (look, music, voice) and SegmentPanel (script, timing, image, voice, captions, prop) |
| `web/src/video/Video.tsx` | The renderer: types, timing maths, transitions, effects, captions, music ducking |
| `web/src/video/theme.ts` | Styles (editorial, pixel, 2d, 3d), palettes, fonts |
| `web/src/video/Stage3D.tsx` | 3D style: builds prop recipes live (Manifold WASM) on a three.js stage |
| `web/src/video/bench3d/recipe.ts` | Recipe → geometry builder (validates untrusted AI JSON); self-check in `recipe.check.mts` |
| `bench3d/` | 3D bake-off (Remotion vs raea vs Blender) and `modelgen/VOCAB.md`, the prop language used in prompts |

## Running it (Windows, PowerShell or Git Bash)

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
cd web && npm install && cd ..
.venv/Scripts/python server.py          # API on :8787 (restart after every server.py edit: no auto-reload)
npm --prefix web run dev -- --port 5173 # UI on :5173 (Vite proxies /api to :8787)
```

- **AI backend, in priority order:** `ANTHROPIC_API_KEY` in `.env` (git-ignored, re-read per request), then a signed-in Claude Code
  CLI (bundled with the Claude desktop app, auto-discovered; sign in with `claude auth login`), then demo mode
  (samples for "ube", "jeepney", "tower defense", placeholders otherwise).
- **Whisper model:** expected at `models/faster-whisper-base/` (git-ignored, ~145 MB). Without it, captions fall back to Edge TTS word timings.
- **Second UI:** the `ui-redesign` branch lives in the worktree `.claude/worktrees/ui-redesign/`, served on **:5175**. Its
  `web/vite.config.ts` proxies `/api`, `/assets`, `/media` and `/music` to :8787 (that edit is uncommitted there).

## How to work here

1. **Small, focused diffs.** It's a hackathon codebase: prefer the simplest working change, reuse what exists, no new
   frameworks. Add a dependency only when a few lines can't do it, and add it to `requirements.txt` or `web/package.json`.
2. **Keep the Plan contract in sync** (see above). Old plans must still load: new fields are optional with sensible defaults.
3. **Comments explain *why*,** not what. Mark deliberate shortcuts with `ponytail:` plus the limit and the upgrade path.
4. **Treat AI output and scraped content as untrusted.** Recipes go through `recipe.ts` validation; file paths use `Path(...).name`; no SVG uploads.
5. **Never put secrets in code, commits, logs or chat.** Keys only go in `.env`.
6. **Copyright:** found images keep their source page (credit them). Prompts tell the AI to make *original* props, not copies of
   game characters (Supercell's fan-content policy limits commercial use of fan art like `hog_rider_fanart.json`).

### Verify before you say it works

```bash
cd web && npx tsc -b                                   # must print nothing
node src/video/bench3d/recipe.check.mts                # must end with "recipe.ts OK"
.venv/Scripts/python -c "import ast;ast.parse(open('server.py',encoding='utf-8').read())"
npx remotion still src/video/index.tsx Main out/x.png --frame=40 --props=out/plan.json --gl=angle   # visual check (from web/)
```

Then click through the change in the browser. Typechecking isn't testing.

### Git and parallel work (Codex + Claude sessions share this repo)

- `main` is the integration branch. **Work on your own branch** (`codex/<topic>`, `claude/<topic>`), commit small, and merge into
  `main` with a short summary. Never rewrite pushed history, and never `git stash` bare (the stash is shared across worktrees).
- **Avoid editing the same file at the same time.** Before starting, say which files you'll touch (see HANDOFF.md, "Who owns what").
  The hotspots are `App.tsx`, `Inspector.tsx` and `server.py`.
- After merging to `main`, bring the test UI up to date: `git -C .claude/worktrees/ui-redesign merge --ff-only main`
  (if `ui-redesign` has its own commits, do a normal merge and resolve).
- Commit messages: imperative subject plus a short body saying why.

## Gotchas (each one cost us time)

- **The page loses everything on refresh or HMR reload.** There's no project persistence yet (top of the backlog).
- **The network here is slow and flaky** (~50 KB/s at times). Big downloads (models) need resumable `curl -C -`. Hugging Face's own downloader stalled.
- **The API doesn't auto-reload.** Restart it after editing `server.py` or `music.py`.
- **Command-line renders can miss Google Fonts** (an `@import` race). The live preview is fine.
- **Manifold reads clockwise outlines as invalid,** which used to empty whole props. `recipe.ts` now reverses them, and an empty build is an error ("Fix with AI").
- **Edge TTS (free, unofficial) occasionally drops a connection,** so `speak()` retries once.
- **Whisper `base` mishears Tagalog.** Captions keep the script's spelling when word counts line up; Filipino otherwise uses TTS timings.
- **Claude Code CLI generation takes 40-60 s (about 2 min for 3D)** and counts against the user's Claude plan limits.
- **Uploaded and generated media are git-ignored runtime data:** `web/public/{assets,media,music}`, `models/`, `.env`.
