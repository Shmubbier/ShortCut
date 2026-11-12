# YouTube style extraction report

## Implemented

- `POST /api/styles/from-url` creates a background style-extraction job; `GET /api/styles/jobs/<id>` reports progress, result, or a useful error.
- The extractor validates YouTube URLs and a 1–180 second duration bound, reads metadata and auto captions, and falls back to `youtube-transcript-api` when caption download fails.
- It downloads a low-resolution reference into a temporary directory, samples frames for histogram cuts and shot lengths, builds a temporary 10-keyframe contact sheet, and estimates three RGB colour clusters. The media and contact sheet are deleted when the job ends.
- One AI synthesis produces general writing, structure, visual, and editing guidance. Measured pace and nearest supported palette are used, and the saved registry entry contains `source` and `measured` fields.
- The Style panel accepts a YouTube URL, polls job progress, reports failures, displays learned characteristics, and refreshes the format selector when extraction succeeds. `style_brief()` includes pace and visual look/palette so extracted styles steer generation.

## Verification

- `cd web && npx.cmd tsc -b` — passed with no TypeScript errors.
- `cd web && node src/video/bench3d/recipe.check.mts` — passed; ended with `recipe.ts OK`.
- Python syntax/import check in the shared venv — passed for `server.py` and `style_ref.py`.
- `git diff --check` — passed.
- API exercised on port 8794. All three public-video extraction jobs completed with `status: done`, saved styles, and removed temporary video/contact-sheet files.

| Reference | Extracted type/look | Duration | Cuts/min | Median shot | Palette | Prompt-only style check |
|---|---|---:|---:|---:|---|---|
| [Ferrous Sulfate — How It Works (Animated Doodle Explainer)](https://www.youtube.com/watch?v=0LAMFTKxTAs), One Minute Drugs | animated doodle pharmacology explainer, 2D | 58 s | 0 | 58 s | mono | Present-tense, short declarative narration; personifies molecules; one quantified takeaway and recap. Documentary pace, 4–6 segments. |
| [2 AM COFFEE — A short film](https://www.youtube.com/watch?v=SR__amDl1c8), Forrain | cinematic mood short, editorial | 109 s | 0 | 109 s | night | Near-silent, intimate line; slow light arc and fades. Documentary pace, 4 segments. |
| [CINEMATIC PRODUCT VIDEO — Go Good Drinks](https://www.youtube.com/watch?v=CBxgZxjdJyk), Lauren Roberts | product commercial, 3D | 20 s | 0 | 20 s | mono | No voiceover; minimal flavor labels and brand end-card copy. Documentary pace, 4–10 segments. |

The jobs sampled 697, 688, and 246 frames respectively and produced 10 keyframe colour summaries. These references show continuous drawing/camera movement or are single takes, so no hard cuts crossed the detector threshold; the measured median shot is therefore the whole clip. The first video's caption fetch received HTTP 429 from YouTube; the fallback path still completed extraction. No hard-cut claim is made for the product video's color-wash motion.

`content_styles.style_brief()` was run for `whiteboard-doodle-mechanism-explaine`, `late-night-cinematic-mood-piece`, and `cinematic-flavor-wash-product-spot`. Each prompt contains the extracted structure, writing, pace, cuts, transitions, captions, effects, visual look, palette, and segment range. Full video plans were not generated, so whether generated narration matches the references is **not verified** beyond those prompt constraints.

- `GET http://127.0.0.1:8794/api/styles` listed all three style IDs with `custom: true`.
- UI browser click-through — **not verified**; TypeScript passed, and the app was served on port 5184 for inspection.

## Reproduction

```powershell
"C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python" -m pip install -r requirements.txt
$env:BLOCKCUT_PORT = "8794"
"C:/Users/naomi/Documents/vscode shenanigans/ManilaHack/.venv/Scripts/python" server.py
# In another shell:
$env:BLOCKCUT_API = "http://127.0.0.1:8794"
npm --prefix web run dev -- --port 5184
```

Then create styles from public videos through the Style panel, poll each job to completion, and use its `id` with `content_styles.style_brief(id)`. Synthesis needs a logged-in Claude Code CLI or `ANTHROPIC_API_KEY`.

## Merge notes and dependencies

- Added `yt-dlp`, `yt-dlp-ejs`, and `youtube-transcript-api` to `requirements.txt`. YouTube downloads use a JavaScript runtime; Node 26 was available in this test environment.
- Runtime style JSON files are written under `styles/` and ignored by Git; no sample styles or downloaded media are committed.
- Only the assigned API :8794 and UI :5184 were started. Shared ports :8787, :5173 and :5175 were not touched.
- yt-dlp is distributed under [The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE); `youtube-transcript-api` is [MIT licensed](https://github.com/jdepoix/youtube-transcript-api/blob/master/LICENSE). Extraction depends on YouTube caption/video availability and reports provider restrictions as job errors.
