# Blockcut handoff (Nov 12, 2026, morning; demo tonight 6-10 PM)

How to work on the repo: [AGENTS.md](AGENTS.md). This file is **where things stand** and **what to do next**.

## Director board (Nov 12, from 10:30): Claude Code directs, Codex builds in parallel

Codex tasks run headless via `briefs/run_codex.sh <task> <api_port> <ui_port>`, each in its own worktree under
`../ManilaHack-wt/<task>` on branch `codex/<task>`. Briefs: `briefs/COMMON.md` + `briefs/<task>.md`. Logs and final messages:
`briefs/logs/`. Reports: `briefs/<task>.report.md`. The director reviews and merges into `main`.

| Task | Owner | Branch | Status |
|---|---|---|---|
| Natural voices: speech.cpp + Qwen3-TTS, delivery notes, optional Scribe v2 | Codex | `codex/voice` | running |
| Asset search: images, video clips, 3D models, with licences | Codex | `codex/assets` | running |
| YouTube link → reusable style (type, writing, editing) | Codex | `codex/youtube-style` | running |
| Blender shot pipeline (exact timing + easing), 10 s test shot, scene library with prompts | Codex | `codex/shots` | running |
| Content styles (story, listicle, clip, tutorial, showcase, news, comedy, explainer, documentary) | Claude | `main` | done (a0ae38e) |
| 3D: stronger 3D bias, server-side prop validation + one AI repair pass | Claude | `main` | done (1040909) |

Research notes: "reanimate" is a Haskell SVG library, so Blender's Python API is used for scripted 3D shots. Remotion is the
bundled After Effects replacement. Scribe v2 is a paid ElevenLabs API (optional, key-gated). speech.cpp's Qwen3-TTS has no Filipino,
so Filipino voices stay on Edge TTS.

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
- **Phase 4 implementation (Codex branch `codex/phase-5-demo-reliability`):** upload MP4/WebM/MOV with a 200 MB cap, PyAV
  duration, Whisper transcript with word timings, transcript-to-footage storyboard, trimmed video playback, music ducking,
  background Remotion MP4 render jobs, and a render download link in Settings. The Style panel also has a voice-rate slider;
  changing rate clears stale audio/captions so the user can regenerate at the chosen pace.
- **Visual smoke renders:** 2D and 3D stills rendered in 9:16, 4:5, 1:1 and 16:9; short 16:9 MP4 renders succeeded for both.
  The portrait 2D check exposed overflowing headlines; wrapping was fixed and the 9:16 frame re-rendered. These were single
  scene smoke renders, not a full multi-scene or live-browser QA pass. 3D logs include non-blocking Three.js deprecation
  warnings.

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

Everything below is server or renderer work. **The UI is already wired to these exact endpoints** (commit "Footage UI"):
- **Upload buttons:** the Asset Library ("Upload a video clip") and the hero ("or start from your own video clip").
- **Transcript review:** an editable list of passages with timestamps, then "Build storyboard from footage".
- **Clip tiles:** drag a clip onto a card or onto the inspector's Media box. That sets
  `media: {type:'video', url, name, duration, trimStart: 0, trimEnd}`, `role: 'footage'` and `length`.
- **Inspector trim:** "Trim in" and "Trim out" inputs, "Fit duration to trim", and a `#t=` browser preview of the slice.

Until a route exists, the UI shows "Video footage needs the footage server endpoints" (any HTTP 404). **Codex: build the endpoints
and the renderer exactly to the shapes below, and the buttons start working.** Uploaded clips are remembered in the browser
(`localStorage` key `blockcut.project.v1`, field `clips`), so `upload` must return a stable `url`.

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

### Claude's phases 1-3: DONE (browser-verified, see below)
All six items below are built. Verified: real generation stages, card-by-card reveal, preview slide-in, inspector persistence and
collapse, two-way transcript/inspector sync, + insert / delete / undo, Fill with AI on an empty segment, start/end edits shifting
later segments, autosave restore after reload, New video → hero → exit animation → reveal.
**Also done after that:**
- **Footage UI** (above): clip drop, trim and fit verified with a stand-in clip; upload shows the honest 404 message.
- **Caption appearance** in the Style panel: position, size and look (dark box, bold outline, plain); the outline-top look was verified in the preview.

**Left for whoever picks up the UI next (small):** a duration stepper on the card itself (it's in the inspector today), a
"default transition" apply-to-all control, and keyboard shortcuts (Delete, Esc to deselect). None of these block the demo.

### Phase 5: demo readiness, visual validation, and asset reliability

Do this after Phase 4's footage and export path works. The goal is a reliable, quick live demo that exercises the real editor
and produces a finished video, while checking the 2D and 3D styles beyond the current limited still-render coverage.

1. **Make generation feel fast and dependable:** measure prompt-to-first-usable-storyboard time and follow-up edit time; reduce
   avoidable latency in the generation path, and keep a useful sample/fallback available when the AI backend is slow or offline.
   Report actual progress rather than adding fake progress states.
2. **Voice pacing:** add an editable talking-speed control for generated voiceover and support a revision prompt that can make
   narration/video pacing quicker. Keep generated audio, word timings, captions, and segment duration aligned after speed changes.
3. **2D/3D validation:** exercise representative 2D and 3D plans in all supported aspect ratios, including multi-scene previews
   and final renders. Fix rendering failures, invalid/empty 3D props, caption overlap, and transition issues found; extend the
   existing `recipe.check.mts` where it helps catch regressions. Record the cases and outcomes here.
4. **Reliable asset discovery:** improve beyond image-only topic search to find and import usable images, video clips, and
   3D model/reference assets. Preserve source attribution, validate formats and URLs, handle sparse or failed search results,
   and provide clear fallbacks. Prefer sources and licenses suitable for the demo; don't imply a media type is supported until
   it can be previewed and used in a segment.
5. **Demo-ready project and walkthrough:** keep a preloaded asset library and at least two prepared example projects that can
   run offline or under poor Wi-Fi. Rehearse the path: prompt → generated video → faster-pace revision → select a segment and
   use the inspector/free canvas → drag in a prepared image/effect → switch palette/style → edit the transcript → export.
   Keep reference-video style extraction framed as a future capability unless it is implemented end-to-end.
6. **Export access:** provide a clear way to reach the finished render from the editor (Share/export area or equivalent), and
   verify the exported file matches the preview, including captions, voice pacing, music, and any assigned footage.

**Completion check:** a rehearsed demo can complete both prompt and revision flows promptly, showcase manual editing and asset
assignment, render a valid final video, and recover gracefully from unavailable AI/search services. Track measured timings and
known limitations here rather than claiming unverified capabilities.

**Current follow-up:** Phase 4 code is implemented but still needs a real 20-60 s clip run through upload → transcription →
storyboard → preview → export. This checkout has no `.venv` or local Whisper model, so that integration path could not be
exercised here. Phase 5 still needs measured prompt/revision latency work, prepared offline demo projects, and broader
source-aware discovery for usable video and 3D model assets. Current search/import supports images; reference-video style
extraction remains deferred.

Original queue:
1. Centred first prompt that minimises into a floating assistant icon (jiggles while working); bottom progress bar driven by real stages.
2. Staged generation: images → research and writing → storyboard; cards reveal one by one, then the preview slides in.
3. Inspector slides in from the right on selection, stays until collapsed (chevron), and reopens from a small button.
4. Icon sidebar (Assets, Script, Style, Settings): hover labels, staggered entrance, one flyout panel at a time.
5. Script panel (full transcript in order with timestamps), synced with the inspector through the same `voiceover` field.
6. Add a segment between cards, delete with undo, empty-segment state (the assistant highlights), editable start/end timestamps.

### Still on the general backlog
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
