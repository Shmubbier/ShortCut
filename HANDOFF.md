# Blockcut handoff (Nov 12, 2026, morning; demo tonight 6-10 PM)

How to work on the repo: [AGENTS.md](AGENTS.md). This file is **where things stand** and **what to do next**.

## Working today (all on `main`, verified in the browser or with real generations)

| Feature | Where | Verified |
|---|---|---|
| Prompt → researched, segmented video (Claude API, or headless Claude Code with web search and sources) | `server.py` `create`/`ask_cli` | Real runs: Manila traffic (48 s), Mobile Legends 3D (122 s), jeepneys, ube |
| **Auto style:** AI picks style, palette and music; runners-up shown as one-click recommendations | `server.py` `DIRECTION_GUIDE`, `Inspector.tsx` | Arcade topic → pixel + Pixel Quest; pandesal → 3D + Lo-fi Merienda; ube → editorial + Lo-fi |
| Per-segment AI edits (only the selected segment changes) | `server.py` `edit` | Yes |
| Effects/transitions library, drag onto cards, undo | `App.tsx`, `Video.tsx` | Yes |
| Pannable timeline canvas, drag-to-reorder, tag ovals on strings | `Canvas.tsx` | Yes |
| Styles: paper editorial, 2D motion, pixel, **3D low-poly** (AI-written prop recipes, built live) | `Video.tsx`, `Stage3D.tsx`, `recipe.ts` | Rendered stills, tall and wide |
| Theme: 7 palettes, accent, fonts, grain | `theme.ts`, `Inspector.tsx` | Yes |
| Aspect ratios 9:16 / 4:5 / 1:1 / 16:9 | `Video.tsx` | Yes |
| Asset bucket: upload, grab from URL, **ScrapeGraphAI topic image search** (auto before Generate, per segment) | `server.py` `find_images` | 6 ube / 3 jeepney images |
| Voiceover (Edge TTS, PH + Filipino voices) + **Whisper word captions** | `server.py` `voice` | English and Filipino |
| **Importance** (Quick/Normal/Key) + timing meter on cards | `Video.tsx` `timing`, `Canvas.tsx` | Yes |
| **Exact segment length** slider (1-20 s), voice-cut warning with fixes | `Inspector.tsx` `SegmentPanel` | Slider and meter checked; warning not yet clicked through |
| **Music:** 8 original synthesised loops, AI pick + recommendations, volume, ducking under voice | `music.py`, `Video.tsx` `Music` | Panel and chips checked; **nobody has listened to the tracks yet** |
| Offline demo samples (ube editorial, jeepney 2D, tower defense 3D) | `samples/` | Yes (only used when no AI backend) |

## In flight right now

- **Uncommitted when this file was written:** card/inspector lengths now show on-screen seconds (minus the 0.2 s transition
  overlap, so a 2.0 s fixed length reads 2.0 s, not 2.2 s), and the `web-ui` launch entry. Committed together with this file.
- **Browser check left over:** clicking a music recommendation chip, and voicing a segment with a too-short fixed length to see
  the warning and its "Use the voice's length" fix. The logic typechecks; it hasn't been clicked yet.

## Next up, in priority order for tonight's demo

1. **Project persistence.** Save the plan to `localStorage` (or `projects/<id>.json` via the API) on every change, and restore on load.
   Right now a refresh or HMR reload loses the video. *Owner suggestion: whoever touches `App.tsx` next.*
2. **Render MP4 button.** API route that runs `npx remotion render src/video/index.tsx Main out/<id>.mp4 --props=<plan>`
   in `web/`. Asset, media and music URLs are relative (`/assets/...`), so prefix them with `http://127.0.0.1:8787` in the props file. Run in the background and poll.
3. **Listen to the music** (`web/public/music/*.wav`, or the Music panel preview). Retune `LIBRARY` recipes in `music.py` if any sound off, then rerun `python music.py`.
4. **Voice all segments in parallel** (it's sequential: ~5 s per segment). A thread pool in `server.py` `voice()`.
5. **Demo polish:** pick 2 hero topics, pre-generate them, voice them, and keep a sample loaded as a fallback for bad Wi-Fi.
6. Nice to have: true pixelation for the pixel style, a "regenerate this segment's image" button, split `server.py` into modules.

## Who owns what (to avoid two agents in one file)

| Area | Files | Suggested owner |
|---|---|---|
| Server, AI prompts, voice, images, music | `server.py`, `music.py`, `samples/` | Claude Code |
| Editor UI and persistence | `App.tsx`, `Inspector.tsx`, `Canvas.tsx`, `App.css` | Codex (UI fork on `ui-redesign` too, so coordinate) |
| Renderer, styles, 3D | `web/src/video/*` | Whoever is free; tell the other first |

Say in your first message which row you're taking. When you finish, update this file (what's done, what moved).

## Environment state

- **Servers:** API :8787, main UI :5173, `ui-redesign` UI :5175 (`.claude/launch.json` entries `api`, `web`, `web-ui`).
- **AI:** no `ANTHROPIC_API_KEY`. Claude Code CLI is signed in (`claude auth status` → loggedIn). The OpenAI credit from the
  organisers turned out to be Codex-only, not API credit.
- **Downloads are slow** (~50 KB/s). Ollama was attempted and abandoned for that reason; nothing local-LLM is installed.
- **Disk to reclaim when done:** `bench3d/tools/` (Blender, ~962 MB) and `~/.raea` (~779 MB, plus a PATH entry).
- **Bucket:** a few jeepney test images are in `web/public/assets/` (git-ignored).
- **Branches:** `main` (integration) and `ui-redesign` (worktree for the UI fork session; fast-forwarded to `main` so far, plus its uncommitted proxy config).

## Commit log so far

```
c4622d0 Auto style + music picks with recommendations; exact segment length
7bd2a78 Find topic images with ScrapeGraphAI; time segments by script length and importance
0fba08e Use signed-in Claude Code as the AI backend; add handmade demo samples
d76dac0 Read ANTHROPIC_API_KEY from a git-ignored .env on each request
becb71d Serve asset bucket and voiceover files from the API
09960e0 Load Whisper from local models/ folder and keep script spelling in captions
872b980 Initial snapshot of Blockcut (ManilaHack)
```
