# Codex task 3: create a reusable style from a YouTube video

Branch `codex/youtube-style`. Read `briefs/COMMON.md` first.

## What the user wants
Paste a YouTube link → the app studies the video → saves a **style** → later videos can be generated "in that style".
A style has three parts:
- **video type:** 3D animated, infomercial, documentary, showcase, story, listicle…
- **writing style:** how the script is written: tone, person, sentence length, hook pattern, humour, language mix (e.g. Taglish);
- **editing style:** average shot length and cut rhythm, transitions, captions (on or off, position, size, look), text-on-screen
  density, music energy, and the visual look (colours, flat 2D vs 3D vs footage).

Don't copy the creator's footage, voice or assets: extract **general characteristics** only. The output is a description and parameters, not media.

## The registry already exists (use it)
`content_styles.py` (on `main`, merged into your branch) holds presets and loads custom styles from `styles/<id>.json`, with
the shape documented at the top of that file (`id, label, description, video_type, structure, writing, editing{pace, cuts,
transitions, captions, effects}, visual{style?, palette?, music?}, segments, source{url, title}`). `GET /api/styles` lists them,
and the start screen's format selector already shows custom ones under "Your styles". `generate()` already turns the chosen style
into prompt text via `style_brief()`. **Your job is to produce good `styles/<id>.json` files from a URL.**

## Build
1. **New module `style_ref.py`**, endpoint `POST /api/styles/from-url {url}` (background job, like `/api/render`:
   `GET /api/styles/jobs/<id>` returns `{status, progress, stage, style?}`):
   - **Metadata + transcript:** `yt-dlp` (add it to the venv and `requirements.txt`) with `--skip-download --write-auto-subs
     --sub-langs en.*,fil.*,tl.* --dump-json`: title, duration, chapters, description and captions with timings.
     Fall back to `youtube-transcript-api` if needed.
   - **Visual/editing analysis:** download a **low resolution** copy (≤360p, ≤3 min, to a temp dir, deleted afterwards). With PyAV
     (already installed), sample frames to find **cuts** (frame-difference histogram) → average and median shot length, cuts per
     minute; take **8-12 keyframes** → dominant colours (simple k-means in numpy) and a contact sheet. Detect burned-in captions
     cheaply if you can (bottom-third high-contrast text regions); otherwise let the AI judge from the keyframes.
   - **Synthesis:** one `ask()` call (the server's AI path; it supports images? If the CLI path can't take images, describe the
     keyframes numerically: colours, brightness, cut stats) that writes the style JSON in the registry shape. Map the colours to
     the nearest existing palette id (`paper, ube, jeepney, pop, night, arcade, mono`) and the look to the visual style
     (`editorial, 2d, pixel, 3d`). Pick `editing.pace` from the cut stats (punchy if median shot < 2.5 s).
   - Save `styles/<slug>.json` with `source: {url, title, channel}` and the measured numbers in `measured: {...}` for transparency.
2. **UI (small):** in the **Style panel** (`web/src/Panels.tsx`, `StylePanel`) or the start screen, add "Create a style from a
   YouTube link": URL input → progress → the new style appears in the format selector (refetch `/api/styles`). Show what was
   learned (type, tone, cut pace, captions, palette) so the user trusts it. If the URL fails (private, age-gated, too long), show the reason.
3. **Test** with 3 real, public videos of different types (for example a fast TikTok-style explainer short, a calm documentary
   clip and a 3D-animated or product showcase). Generate one video in each extracted style (or at least run `style_brief()`
   on it and show the prompt text), and report whether the generated script matches the reference's tone and pacing.

## Done
`POST /api/styles/from-url` works end to end on real links and produces sensible styles with measured cut stats; the styles show
up in the selector and steer generation; temp video files are cleaned up; the report lists the three test videos with what
was extracted.
