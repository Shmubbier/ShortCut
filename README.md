# ShortCut: AI video storyboard editor

**Manila Hack 2026 · Content bucket.** Type a topic, get a researched, voiced, editable short video. (The app's UI is called
Blockcut.)

Prompt → research → script → segmented storyboard → live preview → export, plus a second flow that turns uploaded footage into a
storyboard from its transcript.

## What it does

- **Researched scripts.** The AI searches the web, writes a 6-8 segment plan with sources, and picks a visual style, palette
  and music to fit the topic.
- **Formats and "Your styles".** Explainer, documentary, story, listicle, tutorial, showcase, news, comedy… or paste a
  YouTube link: ShortCut measures its cut rhythm and colours, reads its captions, and saves a reusable style (structure,
  writing, editing, pace). Restyle any video into it with one click.
- **3D and photos in one video.** Concrete objects become real low-poly 3D models from [Polyfork](https://polyfork.dev)
  (strict matching, local cache); people, places and events get licensed photos (Wikimedia Commons, Openverse, NASA,
  DuckDuckGo) with source and licence kept.
- **Storyboard editor.** Pannable timeline of cards, drag to reorder, transitions and effects library, per-segment or
  whole-video AI edits ("make segment 3 punchier", "make it a story"), undo, autosave.
- **Natural voiceover.** Local Qwen3-TTS via [speech.cpp](https://github.com/nyosegawa/speech.cpp) (GPU, ~2.6 s per line), Edge
  TTS for Filipino voices; word-timed captions from faster-whisper.
- **Scripted 3D shots.** Blender (bpy) shot pipeline with exact timings and easing, automatic proof checks (overlap, grounding,
  background colour, framing) that block bad finals.
- **Export.** Remotion renders the storyboard to MP4 in 9:16, 16:9, 1:1 or 4:5.

## Stack

Python stdlib HTTP server (`server.py`) · Vite + React + [Remotion](https://www.remotion.dev) UI (`web/`) · `@remotion/three`
for 3D · AI: OpenAI Codex CLI or Claude Code CLI (headless, structured JSON output), or the Claude API.

## Run it

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
npm --prefix web install
.venv/Scripts/python server.py                     # API on :8787
npm --prefix web run dev -- --port 5173            # UI on http://localhost:5173
```

AI backend, in order of preference (set in a git-ignored `.env`):

- `ANTHROPIC_API_KEY=…` → Claude API
- `BLOCKCUT_AI=codex` → Codex CLI first, Claude Code CLI as fallback
- nothing → a signed-in Claude Code CLI, then Codex, then built-in demo samples

Optional: `ELEVENLABS_API_KEY` (Scribe v2 caption alignment), speech.cpp in `tools/speechcpp/` for Qwen voices.

## Repo map

| Path | What |
|---|---|
| `server.py` | API: plan, edit, voice, assets, styles, footage, render |
| `content_styles.py`, `style_ref.py`, `styles/` | Formats and YouTube-learned styles |
| `polyfork.py`, `asset_search.py` | 3D model and photo discovery |
| `tts.py`, `music.py` | Voices and generated music |
| `shots/` | Blender shot pipeline and scene library |
| `web/src/` | Editor UI and Remotion video (`video/Video.tsx`, `video/Stage3D.tsx`) |
| `HANDOFF.md`, `AGENTS.md`, `briefs/` | How the team (Claude Code directing Codex agents) built it |
