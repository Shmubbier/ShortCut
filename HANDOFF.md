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
| **Exact segment length** slider (1-20 s), voice-cut warning with fixes | `Inspector.tsx` `SegmentPanel` | Yes (slider, meter, warning and fix) |
| **Music:** 8 original synthesised loops, AI pick + recommendations, volume, ducking under voice | `music.py`, `Video.tsx` `Music` | Panel and chips checked; **nobody has listened to the tracks yet** |
| Offline demo samples (ube editorial, jeepney 2D, tower defense 3D) | `samples/` | Yes (only used when no AI backend) |

## Recently landed

- Card and inspector lengths show on-screen seconds (minus the 0.2 s transition overlap), so a fixed 2.0 s reads 2.0 s.
- Browser-checked: a music recommendation chip switches the track (preview loads); a 1.5 s fixed length on a 9.7 s voiceover
  shows the cut-off warning, and "Use the voice's length" sets 10.0 s and clears it.
- **AI failure fallback:** if generation fails (for example Claude Code's 5-hour plan limit, which we hit this morning),
  Create loads the matching sample or demo plan with a note instead of erroring. A usage-limit error also makes the server
  skip Claude Code for ~20 min, so the fallback is instant. The *first* failing request is still slow (~2 min), because
  Claude Code retries before giving up.

## The new spec (Nov 12): "AI-powered video storyboard and editing application"

The team's spec (prompt → storyboard editor, plus footage upload → transcript → storyboard → export) is split by phase.
**The must-have for tonight is the new UI layout.**

### Who owns what (don't edit the other side's files without saying so first)

| Phases | Owner | Files |
|---|---|---|
| **1-3 UI:** centred prompt that shrinks into a floating assistant, progress bar, card-by-card reveal, icon sidebar (Assets, Script, Style, Settings), transcript panel, inspector that stays open, add/delete/empty segments, timestamps | **Claude Code** | `web/src/App.tsx`, `Canvas.tsx`, `Inspector.tsx`, `App.css`, new `web/src/panels/*` |
| **4 Footage + export:** video upload, transcription, storyboard from footage, video segments with trimming, MP4 render/export | **Codex** | `server.py` (new routes, below), `web/src/video/Video.tsx` (rendering video segments), `web/src/video/index.tsx` |
| Shared contract | Both, announce changes | Types at the top of `Video.tsx` + pydantic models in `server.py` |

### The shared data contract (already committed)

`SceneData` in `web/src/video/Video.tsx` gained:
- `role?: 'footage' | 'image' | 'narration' | 'title' | 'broll'` (content type; `kind` stays the text layout). Labels in `ROLES`.
- `title?: string` (2-4 word card name). The AI fills `role` and `title` (`server.py` `Scene`).
- `media?: { type: 'video' | 'image'; url; name?; trimStart?; trimEnd?; duration? }`: **the segment's video footage**. `trimStart` and `trimEnd` are seconds into the source clip.
  Images may keep using the older `asset` string.
- `isEmpty(scene)`: a user-inserted segment with no text, voice, media or prop.

### Codex brief: phase 4 (footage + export)

Everything below is server or renderer work. The UI side (an upload button in the Assets panel, a trim control in the
inspector) is Claude's: **expose these endpoints and Claude will wire the UI to them.**

1. `POST /api/footage/upload {name, data: dataURL}` → save to `web/public/footage/<slug>.mp4` (allow mp4/webm/mov; cap ~200 MB),
   serve it at `/footage/<file>` (add it to the static prefixes in `Handler.do_GET`; git-ignore the folder), and return
   `{url, name, duration}`. Read the duration with PyAV (`av.open(path).duration / 1e6`; PyAV 18.1 is installed with faster-whisper).
2. `POST /api/footage/transcribe {url}` → faster-whisper can read the video file directly (PyAV decodes the audio; no system
   ffmpeg is needed). Reuse `whisper()` and return `{segments: [{start, end, text, words: [...]}]}`.
3. `POST /api/footage/storyboard {url, transcript, style, aspect}` → ask the AI (same `ask()` path) to group transcript passages
   into 4-8 segments. Each gets `role: 'footage'`, `media: {type:'video', url, trimStart, trimEnd}`, `voiceover` = the passage text,
   `words` = that passage's word timings re-based to segment time (so the existing captions work), and `length` = trimEnd - trimStart.
   Return a full Plan (reuse `direction_fields` / `demo_direction` for style and music).
4. **Renderer:** in `Video.tsx` `Shot`, if `s.media?.type === 'video'`, draw `<OffthreadVideo src startFrom={trimStart*FPS}
   endAt={trimEnd*FPS}>` full-bleed behind the text (use Remotion's `<Video>` in the Player if OffthreadVideo misbehaves there),
   and keep its own audio (duck the music under it like the voiceover). In `timing()`, a footage segment's length = trimEnd - trimStart unless `length` is set.
5. **Export:** `POST /api/render {plan}` → write the props (prefix relative `/assets` `/media` `/music` `/footage` URLs with
   `http://127.0.0.1:8787`), run `npx remotion render src/video/index.tsx Main out/<id>.mp4 --props=<file> --gl=angle` in `web/`
   as a background job; `GET /api/render/<id>` returns `{status, progress, url}`. Serve the finished file under `/renders/`.
6. Verify with a real 20-60 s clip: upload → transcript → storyboard → preview plays the right slices → MP4 renders with captions.

### Claude's queue (phases 1-3), in order
1. Centred first prompt that minimises into a floating assistant icon (jiggles while working); bottom progress bar driven by real stages.
2. Staged generation: images → research and writing → storyboard; cards reveal one by one, then the preview slides in.
3. Inspector slides in from the right on selection, stays until collapsed (chevron), and reopens from a small button.
4. Icon sidebar (Assets, Script, Style, Settings): hover labels, staggered entrance, one flyout panel at a time.
5. Script panel (full transcript in order with timestamps), synced with the inspector through the same `voiceover` field.
6. Add a segment between cards, delete with undo, empty-segment state (the assistant highlights), editable start/end timestamps.

### Still on the general backlog
- Project persistence (a refresh loses the video). Claude will add `localStorage` save/restore with the UI work.
- Listen to the music; retune `music.py` recipes if needed.
- Voice all segments in parallel (thread pool in `voice()`).
- Demo polish: pre-generate 2 hero topics; keep a sample as the bad-Wi-Fi fallback.

When you finish something, update this file (what's done, what moved).

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
